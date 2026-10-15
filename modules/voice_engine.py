"""
多模态语音交互与高品质语音引擎 (Voice & Audio Engine)
1. 语音输入识别（ASR）：Google Gemini 多模态音频理解（识别幼儿童音发音）
   - 浏览器 MediaRecorder 输出为 webm/opus，先经 ffmpeg 转 16k 单声道 WAV 再送 Gemini
2. 语音输出播报（TTS）：三级降级链
   - 一级：阿里云百炼 Qwen3-TTS（qwen3-tts-flash + Cherry 音色，中文自然度最高）
   - 二级：edge-tts 微软云 TTS（免 Key、永久免费，音质次之）
   - 三级：浏览器 Web Speech 合成（前端兜底，零依赖）
   全链路受 QuotaGuard 熔断器约束作为账单兜底；百炼侧另配音色自动回退链
"""
import asyncio
import concurrent.futures
import html
import io
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from config.settings import GEMINI_API_KEY
from config.settings import (
    BAILIAN_API_KEY,
    BAILIAN_TTS_MODEL,
    BAILIAN_TTS_URL,
    BAILIAN_TTS_VOICE,
    BAILIAN_TTS_VOICE_FALLBACKS,
    DAILY_BUDGET_TTS_CHARS,
)
from modules.quota_guard import get_quota_guard

# edge-tts 发音人：晓晓（温柔亲和女声，贴近幼师语调），可用环境变量覆盖
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
# 单次合成的最大字符数（百炼单请求限长，超长需分段，这里取安全值）
MAX_TTS_CHARS = 500

# 浏览器录音常见容器 -> 标准音频 mime 映射（Gemini 仅接受常见音频格式）
_MAGIC_MIME_MAP = [
    (b"RIFF", "audio/wav"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"ID3", "audio/mp3"),
    (b"\xff\xfb", "audio/mp3"),
    (b"\xff\xf3", "audio/mp3"),
]


def detect_audio_mime(audio_bytes: bytes) -> str:
    """根据文件魔数推断音频 MIME 类型，默认按 wav 处理"""
    if not audio_bytes:
        return "audio/wav"
    for magic, mime in _MAGIC_MIME_MAP:
        if audio_bytes.startswith(magic):
            return mime
    if audio_bytes[:4] == b"\x1aE\xdf\xa3":  # EBML 头 -> Matroska/WebM
        return "audio/webm"
    if len(audio_bytes) > 8 and audio_bytes[4:8] == b"ftyp":  # ISO-BMFF -> mp4/m4a
        return "audio/mp4"
    return "audio/wav"


def _find_ffmpeg() -> Optional[str]:
    """三级兜底定位 ffmpeg：环境变量 > PATH > 常见安装路径"""
    candidate = os.getenv("FFMPEG_BINARY")
    if candidate and os.path.exists(candidate):
        return candidate
    found = shutil.which("ffmpeg")
    if found:
        return found
    for pattern in (
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg*\bin\ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ):
        import glob
        for path in glob.glob(pattern):
            if os.path.exists(path):
                return path
    return None


def transcode_to_wav_16k(audio_bytes: bytes, src_mime: str) -> Optional[bytes]:
    """将 webm/mp4 等浏览器录音转码为 16kHz 单声道 PCM WAV（Gemini 兼容）"""
    if src_mime == "audio/wav":
        return audio_bytes
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=_MIME_SUFFIX.get(src_mime, ".webm"), delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            in_path = tmp_in.name
        out_path = in_path + ".wav"
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", in_path,
                 "-ar", "16000", "-ac", "1", "-f", "wav", out_path],
                capture_output=True, timeout=30
            )
            if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 44:
                with open(out_path, "rb") as f:
                    return f.read()
        finally:
            for p in (in_path, out_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
    except Exception as e:
        print(f"[voice] 音频转码失败: {e}")
    return None


_MIME_SUFFIX = {
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
}


def detect_audio_format(audio_bytes: bytes) -> str:
    """
    根据字节流首部识别音频容器格式（供前端 st.audio 使用）。
    百炼 Qwen3-TTS 返回 WAV，edge-tts 返回 MP3，故不能写死单一格式。
    """
    if not audio_bytes:
        return "audio/mp3"
    head = audio_bytes[:16]
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mp3"
    return "audio/mp3"


class VoiceEngine:
    def __init__(self, api_key: Optional[str] = None, tts_api_key: Optional[str] = None):
        # api_key=None 表示未指定（回退环境变量/本地配置）；显式传空串表示清空 Key
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
        self.api_key = api_key or ""
        # TTS 用独立的百炼 Key（与 Gemini ASR 的 Key 无关，可分别配置）
        if tts_api_key is None:
            tts_api_key = os.getenv("BAILIAN_API_KEY", BAILIAN_API_KEY)
        self.tts_api_key = tts_api_key or ""
        # TTS 引擎名：百炼优先（音质最好），edge-tts 永久免费兜底
        self.tts_engine = os.getenv("TTS_ENGINE", "bailian")
        # 音色候选链：首选 Cherry，失败自动回退，保证播报永不断档
        self.voices = [BAILIAN_TTS_VOICE] + [
            v for v in BAILIAN_TTS_VOICE_FALLBACKS if v != BAILIAN_TTS_VOICE
        ]
        # 运行时状态：实际生效的音色（供后台展示）
        self.active_voice = self.voices[0]
        # edge-tts 已实测 403 失效，此标志用于进程内快速跳过，避免每次白等超时
        self._edge_disabled = False
        self.client = None
        if self.api_key and self.api_key.strip():
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key.strip())
            except Exception as e:
                print(f"[voice] Gemini 客户端初始化失败: {e}")

    # ==================== 语音输入（ASR） ====================
    def transcribe_child_audio(self, audio_bytes: bytes, mime_type: Optional[str] = None) -> str:
        """
        使用 Gemini 多模态音频理解，精准识别幼儿普通话童音（处理发音不准、童音含糊）。
        浏览器录音为 webm/opus，自动转码为 16k 单声道 WAV 后送模型。
        """
        if not self.client or not audio_bytes:
            return ""

        src_mime = mime_type or detect_audio_mime(audio_bytes)
        wav_bytes = transcode_to_wav_16k(audio_bytes, src_mime)
        if wav_bytes is None:
            # 无 ffmpeg 时：Gemini 原生支持的格式可直传，其余（如 webm）放弃识别
            if src_mime not in ("audio/wav", "audio/mp3", "audio/aiff", "audio/aac", "audio/ogg", "audio/flac"):
                print(f"[voice] 未找到 ffmpeg 且 {src_mime} 格式 Gemini 不支持，无法识别")
                return ""
            wav_bytes = audio_bytes

        prompt = (
            "你是一名亲切的幼儿园老师。请听这段音频，音频中是幼儿园小朋友在说话。\n"
            "请将音频中的童音转录为文字，并推测孩子想找的书名或意图（如：我想看大卫不可以、小蝌蚪找妈妈在哪里、今天谁值日）。\n"
            "请直接输出识别后的简明语句，不要包含任何多余的解释或标点废话。"
        )

        try:
            from google.genai import types
            audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
            for model_name in ["gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=[audio_part, prompt]
                    )
                    if response and response.text:
                        return response.text.strip().replace("“", "").replace("”", "")
                except Exception:
                    continue
        except Exception as e:
            print(f"[voice] 语音识别异常: {e}")
        return ""

    # ==================== 语音输出（TTS）三级降级链 ====================
    def synthesize_cloud_speech(self, text: str, voice: Optional[str] = None) -> Optional[bytes]:
        """
        统一语音合成入口：豆包 TTS（主）→ edge-tts（兜底）→ None（交前端 Web Speech）。
        全链路受本地熔断约束，免费额度用尽后不再向云端发起任何付费请求。
        """
        if not text or not text.strip():
            return None
        clean_text = self._clean_tts_text(text)
        if not clean_text:
            return None
        clean_text = clean_text[:MAX_TTS_CHARS]

        # 一级：百炼 Qwen3-TTS（可通过 TTS_ENGINE=edge 强制关闭）
        if self.tts_engine.lower() != "edge":
            audio_bytes = self._synthesize_bailian(clean_text)
            if audio_bytes:
                return audio_bytes

        # 二级：edge-tts 微软云 TTS（永久免费，无额度限制）
        return self._synthesize_edge(clean_text, voice)

    # ---------- 一级：阿里云百炼 Qwen3-TTS ----------
    def _synthesize_bailian(self, clean_text: str) -> Optional[bytes]:
        """
        调用百炼 Qwen3-TTS 语音合成，返回 WAV 字节流。

        音色自动回退：首选 Cherry，逐个尝试候选音色链，
        某个音色不可用（未开通/额度耗尽）时自动换下一个，播报永不断档。
        """
        if not self.tts_api_key or not self.tts_api_key.strip():
            return None

        guard = get_quota_guard()
        # 本地预算闸门：字符数即为百炼 TTS 的计费单位
        allowed, reason = guard.acquire(
            "bailian_tts", kind="chars", estimated=len(clean_text), limit=DAILY_BUDGET_TTS_CHARS
        )
        if not allowed:
            print(f"[tts-bailian] 本地熔断拦截，未发起请求: {reason}")
            return None

        try:
            import requests
        except ImportError:
            print("[tts-bailian] requests 未安装，跳过")
            return None

        headers = {
            "Authorization": f"Bearer {self.tts_api_key.strip()}",
            "Content-Type": "application/json",
        }

        for voice_name in self.voices:
            payload = {
                "model": BAILIAN_TTS_MODEL,
                "input": {
                    "text": clean_text,
                    "voice": voice_name,
                    "language_type": "Chinese",
                },
            }
            try:
                res = requests.post(
                    BAILIAN_TTS_URL, headers=headers, json=payload, timeout=45
                )
            except Exception as e:
                print(f"[tts-bailian] 请求异常（音色 {voice_name}）: {e}")
                continue

            if res.status_code == 200:
                audio_url = self._extract_audio_url(res)
                if audio_url:
                    audio = self._download_audio(audio_url)
                    if audio and len(audio) > 200:
                        guard.record("bailian_tts", chars=len(clean_text))
                        if self.active_voice != voice_name:
                            self.active_voice = voice_name
                            print(f"[tts-bailian] 已切换音色: {voice_name}")
                        return audio
                print(f"[tts-bailian] 音色 {voice_name} 返回空音频，尝试下一个音色")
                continue

            body = res.text[:250]
            # 音色/额度问题只影响当前音色，换下一个候选即可，不中断播报
            print(f"[tts-bailian] 音色 {voice_name} 失败（{res.status_code}），尝试下一个: {body}")
            # 全部音色都是鉴权/额度问题导致时，记一次熔断供后台展示
            if voice_name == self.voices[-1]:
                guard.handle_response_error("bailian_tts", res.status_code, body)

        return None

    @staticmethod
    def _extract_audio_url(res) -> str:
        """从百炼 TTS 响应中提取音频 URL（响应为单段 JSON）"""
        try:
            data = res.json()
        except Exception:
            return ""
        audio = ((data.get("output") or {}).get("audio") or {})
        return audio.get("url") or ""

    @staticmethod
    def _download_audio(url: str) -> Optional[bytes]:
        """下载百炼返回的音频（URL 24h 内有效）"""
        try:
            import requests
            res = requests.get(url, timeout=45)
            if res.status_code == 200 and len(res.content) > 200:
                return res.content
            print(f"[tts-bailian] 音频下载失败（{res.status_code}）")
        except Exception as e:
            print(f"[tts-bailian] 音频下载异常: {e}")
        return None

    # ---------- 二级：edge-tts 微软云 TTS（已失效，仅保留作应急）----------
    def _synthesize_edge(self, clean_text: str, voice: Optional[str] = None) -> Optional[bytes]:
        """
        调用 edge-tts 微软云语音合成（免 Key、永久免费）。

        注意（2026-10-14 实测）：微软已将 Edge 免费 TTS 接口收紧，
        持续返回 403 Invalid response status，该通道实际不可用。
        这里保留仅为网络异常时的应急路径，并加进程级熔断标志：
        一旦确认失败（403/鉴权类），本进程后续直接跳过，不再白等两次超时（约 50s）。
        最终兜底交给前端 Web Speech。
        """
        if self._edge_disabled:
            return None

        voice = voice or EDGE_TTS_VOICE

        def _run_once() -> bytes:
            import edge_tts

            async def _synthesize() -> bytes:
                communicate = edge_tts.Communicate(
                    clean_text, voice, rate="-8%", pitch="+6Hz"
                )
                buf = io.BytesIO()
                async for chunk in communicate.stream():
                    if chunk.get("type") == "audio" and chunk.get("data"):
                        buf.write(chunk["data"])
                return buf.getvalue()

            return asyncio.run(_synthesize())

        # 仅重试 1 次、缩短超时，避免不可用时拖慢整个页面响应
        for attempt in range(1):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_run_once)
                    audio_bytes = future.result(timeout=12)
                if audio_bytes and len(audio_bytes) > 200:
                    return audio_bytes
            except concurrent.futures.TimeoutError:
                print("[tts-edge] 合成超时（已缩短等待，跳过重试）")
            except Exception as e:
                msg = str(e)
                # 403/鉴权类 = 接口已被微软收紧，进程内永久跳过，避免每次都白等
                if "403" in msg or "Invalid response status" in msg or "Unauthorized" in msg:
                    self._edge_disabled = True
                    print("[tts-edge] 微软接口已失效（403），本进程不再重试，改由前端 Web Speech 兜底")
                else:
                    print(f"[tts-edge] 合成失败: {msg}")
        return None

    @staticmethod
    def _clean_tts_text(text: str) -> str:
        """去除 emoji 与特殊符号，保留纯文本，保证 TTS 发音自然"""
        import re
        clean = re.sub(
            r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF\u2190-\u21FF✅❌⚠️⭐✨❤️]",
            "", text
        )
        clean = clean.replace("《", "").replace("》", "").replace("\n", " ").strip()
        return clean

