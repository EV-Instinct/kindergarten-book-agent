"""
阶段四测试套件：多模态语音与童声播报验证
测试范围：
1. VoiceEngine 初始化（无 Key 时不构建客户端，有 Key 时正常构建）
2. 音频 MIME 魔数识别（浏览器 webm 录音 / wav / mp3）
3. ffmpeg 转码链路（webm -> 16k 单声道 WAV）
4. TTS 文本清洗（去 emoji，保发音纯净）
5. Web Speech 幼教专用发音播放器 HTML/JS 生成
6. 空音频与异常输入的容错处理
7. 云端语音合成（edge-tts）：网络可达时验证字节流，不可达时验证优雅降级不抛异常
"""
import os
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.voice_engine import (
    VoiceEngine,
    detect_audio_mime,
    transcode_to_wav_16k,
)


class TestStage4Voice(unittest.TestCase):
    def setUp(self):
        self.voice_engine = VoiceEngine()

    def test_01_client_initialization(self):
        """测试 Gemini 客户端按 Key 有无正确构建/不构建"""
        # 无 Key：客户端应为 None（不再硬编码密钥，安全降级）
        engine_no_key = VoiceEngine(api_key="")
        self.assertIsNone(engine_no_key.client, "未配置 API Key 时不应构建客户端")

        # 有 Key：客户端应成功构建（Key 有效性在调用时才校验）
        engine_with_key = VoiceEngine(api_key="dummy-test-key")
        self.assertIsNotNone(engine_with_key.client, "配置 API Key 后应成功构建客户端")

    def test_02_detect_audio_mime(self):
        """测试浏览器录音格式的魔数识别"""
        self.assertEqual(detect_audio_mime(b"RIFFxxxxWAVEfmt"), "audio/wav")
        self.assertEqual(detect_audio_mime(b"\x1aE\xdf\xa3xxxx"), "audio/webm")  # Matroska/WebM
        self.assertEqual(detect_audio_mime(b"OggSxxxx"), "audio/ogg")
        self.assertEqual(detect_audio_mime(b"ID3xxxx"), "audio/mp3")
        self.assertEqual(detect_audio_mime(b"\xff\xfbxxxx"), "audio/mp3")
        self.assertEqual(detect_audio_mime(b"xxxxftypM4A"), "audio/mp4")
        self.assertEqual(detect_audio_mime(b""), "audio/wav")  # 空输入安全兜底

    def test_03_transcode_webm_to_wav(self):
        """测试 ffmpeg 转码链路：构造 webm 录音并转 16k 单声道 WAV"""
        # 生成一段 1 秒静音 WAV，再转成 webm 模拟浏览器 MediaRecorder 输出
        with tempfile.TemporaryDirectory() as tmp:
            src_wav = os.path.join(tmp, "src.wav")
            webm_path = os.path.join(tmp, "rec.webm")
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1", src_wav],
                capture_output=True, timeout=30
            )
            if not os.path.exists(src_wav):
                self.skipTest("ffmpeg 不可用，跳过转码测试")
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-i", src_wav, "-c:a", "libopus", webm_path],
                capture_output=True, timeout=30
            )
            if not os.path.exists(webm_path):
                self.skipTest("ffmpeg 无法生成 webm，跳过转码测试")

            with open(webm_path, "rb") as f:
                webm_bytes = f.read()

            # 识别为 webm 并成功转码为 wav
            self.assertEqual(detect_audio_mime(webm_bytes), "audio/webm")
            wav_bytes = transcode_to_wav_16k(webm_bytes, "audio/webm")
            self.assertIsNotNone(wav_bytes, "webm 应能转码为 WAV")
            self.assertTrue(wav_bytes.startswith(b"RIFF"), "转码结果应为 WAV 容器")

            # wav 输入原样返回（无需转码）
            with open(src_wav, "rb") as f:
                raw_wav = f.read()
            self.assertEqual(transcode_to_wav_16k(raw_wav, "audio/wav"), raw_wav)

    def test_04_tts_text_cleaning(self):
        """测试 TTS 文本清洗：去除 emoji 与书名号，保证发音纯净"""
        cleaned = self.voice_engine._clean_tts_text("🦄《两个小八路》✨在第二层🔵蓝色圆点处哦！❤️")
        self.assertNotIn("🦄", cleaned)
        self.assertNotIn("《", cleaned)
        self.assertNotIn("🔵", cleaned)
        self.assertIn("两个小八路", cleaned)
        self.assertIn("第二层", cleaned)
        self.assertEqual(self.voice_engine._clean_tts_text(""), "")

    def test_05_web_speech_removed(self):
        """
        验证浏览器 Web Speech 已被彻底移除。

        背景：Windows 系统语音会与云端 Cherry 童声抢声，
        表现为「换了引擎但声音没变」，故已整块删除，本用例防止回退。
        """
        self.assertFalse(
            hasattr(self.voice_engine, "generate_speech_player_html"),
            "Web Speech 备用播放器已被移除，不应再存在",
        )
        # 全模块不得残留 speechSynthesis 调用
        with open(
            os.path.join(PROJECT_ROOT, "modules", "voice_engine.py"), "r", encoding="utf-8"
        ) as f:
            src = f.read()
        self.assertNotIn("speechSynthesis", src, "voice_engine.py 不应残留 speechSynthesis")
        self.assertNotIn("SpeechSynthesisUtterance", src, "不应残留 SpeechSynthesisUtterance")

    def test_06_transcribe_empty_audio_fallback(self):
        """测试空音频或无效字节的健壮性处理"""
        result = self.voice_engine.transcribe_child_audio(b"")
        self.assertEqual(result, "", "空音频应安全返回空字符串，不产生异常中断")

    def test_07_cloud_speech_synthesis_graceful(self):
        """
        测试云端语音合成的优雅降级：
        - 主引擎（百炼 Qwen3-TTS）可用时：返回 >1KB 的合法音频（WAV）
        - 主引擎与 edge 兜底都不可用时：返回 None 且不抛异常（由前端 Web Speech 兜底）
        """
        from modules.voice_engine import detect_audio_format

        test_text = "宝贝，《两个小八路》在第二层蓝色圆点处哦！"
        audio_bytes = self.voice_engine.synthesize_cloud_speech(test_text)

        if audio_bytes is not None:
            self.assertGreater(len(audio_bytes), 1000, "生成的音频字节流应大于 1KB")
            # 容器格式校验：百炼返回 WAV(RIFF/WAVE)，edge 返回 MP3(ID3/帧同步头)
            head = audio_bytes[:12]
            is_wav = head.startswith(b"RIFF") and head[8:12] == b"WAVE"
            is_mp3 = head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
            self.assertTrue(
                is_wav or is_mp3,
                f"应返回合法音频流，实际容器={detect_audio_format(audio_bytes)}",
            )
        else:
            # 云端不可达属于环境限制，方法必须优雅返回 None 而非崩溃
            self.assertIsNone(audio_bytes)


if __name__ == "__main__":
    unittest.main()
