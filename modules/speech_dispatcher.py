"""
异步语音播报：文字先出、声音后补。

问题背景（2026-10-14 实测）：
  百炼 Qwen3-TTS 合成一段 60 字回复要 **4.35 秒**。原来 `speak_out()` 同步调用它，
  于是每一轮对话都要先卡 4 秒多才刷新页面 —— 文字明明 3ms 就想好了，孩子却在干等。

解决：把「合成」丢进后台线程，主流程立即返回；页面先渲染文字气泡和一个
「正在准备声音」的占位，再由 `st.fragment(run_every=...)` 每秒轮询取结果。

三个必须处理的坑：
1. **请求序号守卫**：连续说话时，先发出的合成请求可能后到，把新回复的音频覆盖掉
   （表现为"读出来的和看到的不一样"）。用单调递增的 seq 校验，seq 不匹配的迟到结果直接丢弃。
2. **打断**：新提问到来时，上一轮还没合成完的任务标记作废，不再白等。
3. **线程安全**：后台线程不能碰 st.session_state（那是 Streamlit 上下文绑定的），
   结果统一写进线程安全的 `JobResult` 对象，由主线程取走后再写入 session_state。
"""
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# 单条回复的字符上限：太长合成慢且没必要（TTS 按字符计费）
MAX_TTS_CHARS = 300
# 合成超时（秒）：超过就放弃，宁可不出声也不要让页面干等
TTS_TIMEOUT = 12.0


@dataclass
class JobResult:
    """后台合成结果容器。线程间只通过它通信，不碰 session_state。"""
    seq: int                      # 产生该结果的请求序号
    done: bool = False            # 合成是否已结束（成功或失败）
    audio: Optional[bytes] = None
    fmt: Optional[str] = None
    error: str = ""
    elapsed: float = 0.0

    def reset(self) -> None:
        self.done = False
        self.audio = None
        self.fmt = None
        self.error = ""
        self.elapsed = 0.0


@dataclass
class SpeechDispatcher:
    """
    语音播报调度器（全局单例）。

    用法：
        disp = get_dispatcher()
        slot = disp.enqueue(text)          # 立即返回，不阻塞
        # ... 页面渲染文字 ...
        audio, fmt = disp.poll(slot.seq)   # fragment 里每秒轮询
    """
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _seq: int = 0
    _slots: dict = field(default_factory=dict)     # seq -> JobResult
    _latest_seq: int = 0
    _cancelled: set = field(default_factory=set)

    def enqueue(self, text: str, synth: Callable[[str], Any],
                fmt_detect: Callable[[bytes], str],
                max_chars: int = MAX_TTS_CHARS) -> int:
        """
        把一段文本丢进后台合成，立刻返回新的请求序号。

        synth: 同步合成函数 (text) -> bytes|None
        fmt_detect: 从字节流推断音频格式 (bytes) -> str
        """
        clean = _sanitize(text, max_chars)
        with self._lock:
            self._seq += 1
            seq = self._seq
            self._latest_seq = seq
            # 新请求到来 -> 作废所有更早的未完成请求
            self._cancelled = {s for s in self._slots if s < seq and not self._slots[s].done}
            slot = JobResult(seq=seq)
            self._slots[seq] = slot

        if not clean:
            with self._lock:
                slot.done = True
                slot.error = "空文本"
            return seq

        def worker():
            import time
            t0 = time.time()
            _trace(f"worker-{seq} 启动，文本 {len(clean)} 字")
            try:
                data = synth(clean)
                _trace(f"worker-{seq} 合成返回，{len(data) if data else 0} 字节，"
                       f"耗时 {time.time()-t0:.2f}s")
                with self._lock:
                    # 迟到且已作废 -> 直接丢弃，绝不覆盖更新的回复
                    if seq in self._cancelled:
                        slot.error = "已被更新的请求取代"
                        _trace(f"worker-{seq} 结果已作废（被新请求取代）")
                    else:
                        slot.audio = data
                        slot.fmt = fmt_detect(data) if data else None
                if not data:
                    _trace(f"worker-{seq} 合成失败：返回空")
            except Exception as exc:  # 后台线程绝不能把异常抛回主线程
                _trace(f"worker-{seq} 后台异常：{exc!r}")
                with self._lock:
                    slot.error = str(exc)
            finally:
                slot.elapsed = time.time() - t0
                slot.done = True
                _trace(f"worker-{seq} 结束，done=True")

        threading.Thread(target=worker, daemon=True, name=f"tts-{seq}").start()
        return seq

    def poll(self, seq: int) -> tuple:
        """
        查询某次请求的状态。返回 (状态, 数据)：
          ("pending", None)     仍在合成
          ("ready",   (bytes, fmt))  就绪
          ("failed",  原因字符串)    失败/超时
        """
        with self._lock:
            slot = self._slots.get(seq)
            if slot is None:
                return "failed", "请求不存在"
            if not slot.done:
                return "pending", None
            if slot.audio:
                return "ready", (slot.audio, slot.fmt)
            if seq in self._cancelled:
                return "failed", "已被新的提问取代"
            return "failed", slot.error or "云端语音合成失败"

    def is_latest(self, seq: int) -> bool:
        with self._lock:
            return seq == self._latest_seq

    def cleanup(self, keep: int = 20) -> None:
        """只保留最近 keep 条，避免长时间使用内存缓慢增长"""
        with self._lock:
            if len(self._slots) <= keep:
                return
            for s in sorted(self._slots)[: len(self._slots) - keep]:
                if self._slots[s].done:
                    self._slots.pop(s, None)


def _sanitize(text: str, max_chars: int) -> str:
    """清理合成文本：去掉不适合朗读的符号与过长内容"""
    if not text:
        return ""
    t = str(text)
    for bad in ("📘", "📗", "📙", "🔊", "🔁", "⚪", "🔵", "🟡", "🟢", "🧒", "🦄",
                "🎙️", "📤", "🧹", "❤️", "⭐", "🌟", "1️⃣", "2️⃣", "3️⃣"):
        t = t.replace(bad, " ")
    t = t.replace("\n", "，").replace("~", "。")
    t = " ".join(t.split())
    return t[:max_chars]


_DISPATCHER: Optional[SpeechDispatcher] = None
_D_LOCK = threading.Lock()


def get_dispatcher() -> SpeechDispatcher:
    global _DISPATCHER
    if _DISPATCHER is None:
        with _D_LOCK:
            if _DISPATCHER is None:
                _DISPATCHER = SpeechDispatcher()
    return _DISPATCHER


def _trace(msg: str) -> None:
    """
    调试追踪：写文件而不是 print。

    Streamlit 会把 script 里的 print 吞进它自己的 logger（重定向到 stdout 时
    在某些启动方式下看不到），排查异步链路时必须落盘才查得到。
    """
    try:
        import os
        import time
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "temp_check", "speech_trace.log")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass
