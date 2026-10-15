"""
阶段七测试套件：阿里云百炼接入 + 本地额度熔断器 + 自动换模型/换音色验证

核心验收目标：
1. QuotaGuard 计数、闸门拦截、熔断标记、解熔断、额度错误识别（沿用并强化）
2. 音频容器格式自动识别（百炼返回 WAV、edge 返回 MP3，前端不能写死格式）
3. 首选 LLM 模型 404/429 时自动切换到回退链上的下一个（用户核心需求）
4. 首选 TTS 音色不可用时自动切换到下一个音色
5. 熔断后零 HTTP 请求；预算超限本地拦截
6. 全链路降级链不抛异常（百炼 → edge-tts → None）

测试全程使用独立临时数据库，不污染 data/ 下的生产用量记录。
"""
import base64
import json
import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.quota_guard import QuotaGuard, _is_quota_error


class TestQuotaGuardCore(unittest.TestCase):
    """熔断器核心逻辑"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "quota_test.db")
        self.guard = QuotaGuard(db_path=self.db)

    def tearDown(self):
        import modules.quota_guard as qg
        qg._guard_singleton = None
        self._tmp.cleanup()

    def test_01_额度错误识别(self):
        """只有额度/限流类错误才算额度问题，普通 400 不算"""
        self.assertTrue(_is_quota_error(401, "invalid api key"))
        self.assertTrue(_is_quota_error(429, ""))
        self.assertTrue(_is_quota_error(403, "AllocationQuota.FreeTierOnly"))
        self.assertTrue(_is_quota_error(400, "You exceeded your current quota"))
        self.assertTrue(_is_quota_error(400, "余额不足"))
        self.assertFalse(_is_quota_error(400, "invalid request: messages required"))
        self.assertFalse(_is_quota_error(404, "ModelNotFound"))
        self.assertFalse(_is_quota_error(500, "internal error"))

    def test_02_记账与剩余额度计算(self):
        self.guard.record("e1", tokens=1000)
        self.guard.record("e1", tokens=500)
        self.assertEqual(self.guard.today_used("e1", "tokens"), 1500)
        self.assertEqual(self.guard.remaining("e1", "tokens", limit=5000), 3500)
        # 不同引擎独立计数
        self.guard.record("e2", chars=300)
        self.assertEqual(self.guard.today_used("e1", "tokens"), 1500)
        self.assertEqual(self.guard.today_used("e2", "chars"), 300)

    def test_03_闸门放行与拦截(self):
        """预算内放行，超预估拦截，用尽后熔断"""
        allowed, reason = self.guard.acquire("llm", "tokens", estimated=500, limit=1000)
        self.assertTrue(allowed, reason)
        self.guard.record("llm", tokens=500)
        allowed, reason = self.guard.acquire("llm", "tokens", estimated=900, limit=1000)
        self.assertFalse(allowed)
        self.assertIn("超过", reason)
        self.assertFalse(self.guard.is_tripped("llm")[0], "仅超预估不应熔断")
        self.guard.record("llm", tokens=500)
        self.assertFalse(self.guard.acquire("llm", "tokens", estimated=10, limit=1000)[0])
        self.assertTrue(self.guard.is_tripped("llm")[0])
        self.assertFalse(self.guard.acquire("llm", "tokens", estimated=0, limit=1000)[0])

    def test_04_手动熔断与解熔断(self):
        self.guard.trip("tts", "HTTP 403: AllocationQuota.FreeTierOnly")
        self.assertTrue(self.guard.is_tripped("tts")[0])
        self.assertFalse(self.guard.acquire("tts", "chars", estimated=10, limit=10000)[0])
        self.guard.reset("tts")
        self.assertFalse(self.guard.is_tripped("tts")[0])
        self.assertTrue(self.guard.acquire("tts", "chars", estimated=10, limit=10000)[0])

    def test_05_快照数据完整(self):
        self.guard.record("llm", tokens=800)
        snap = self.guard.snapshot("llm", "tokens", limit=2000)
        self.assertEqual((snap["used"], snap["limit"], snap["remaining"]), (800, 2000, 1200))
        self.assertFalse(snap["tripped"])


class TestAudioFormatDetect(unittest.TestCase):
    """音频容器格式自动识别（百炼 WAV vs edge MP3）"""

    def test_06_格式识别(self):
        from modules.voice_engine import detect_audio_format
        # WAV: RIFF....WAVE
        self.assertEqual(detect_audio_format(b"RIFF\x24\x08\x00\x00WAVEfmt "), "audio/wav")
        # MP3: ID3 标签 或 帧同步头
        self.assertEqual(detect_audio_format(b"ID3\x04\x00\x00\x00\x00"), "audio/mp3")
        self.assertEqual(detect_audio_format(b"\xff\xfb\x90\x00" + b"\x00" * 20), "audio/mp3")
        # OGG / FLAC
        self.assertEqual(detect_audio_format(b"OggS\x00\x02" + b"\x00" * 20), "audio/ogg")
        self.assertEqual(detect_audio_format(b"fLaC\x00\x00\x00\x22"), "audio/flac")
        # 空/未知输入安全兜底
        self.assertEqual(detect_audio_format(b""), "audio/mp3")
        self.assertEqual(detect_audio_format(b"garbage"), "audio/mp3")


class TestBailianLLMSwitch(unittest.TestCase):
    """百炼 LLM 自动换模型链"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        import modules.quota_guard as qg
        from modules.llm_client import UnifiedLLMClient
        qg._guard_singleton = QuotaGuard(db_path=os.path.join(self._tmp.name, "quota_llm.db"))
        self.client = UnifiedLLMClient(
            provider="bailian", bailian_api_key="fake-key",
            bailian_base_url="https://example.invalid/compatible-mode/v1",
            bailian_model="qwen3.5-flash",
        )

    def tearDown(self):
        import modules.quota_guard as qg
        qg._guard_singleton = None
        self._tmp.cleanup()

    def test_07_候选链包含全部兜底模型(self):
        """候选链必须覆盖配置的全部回退模型，且首选在最前"""
        from config.settings import BAILIAN_MODEL_FALLBACKS
        chain = self.client.bailian_models
        self.assertEqual(chain[0], "qwen3.5-flash")
        for m in BAILIAN_MODEL_FALLBACKS:
            self.assertIn(m, chain, f"回退模型 {m} 必须进入候选链")
        self.assertEqual(len(chain), len(set(chain)), "候选链不应有重复项")

    def test_08_无Key时安全返回空串(self):
        from modules.llm_client import UnifiedLLMClient
        c = UnifiedLLMClient(provider="bailian", bailian_api_key="")
        self.assertEqual(c._call_bailian_raw("测试"), "", "无 Key 必须返回空串由上层降级")

    def test_09_熔断后零请求(self):
        """已熔断时必须被本地拦截，一个 HTTP 请求都不发"""
        calls = []

        def _boom(*a, **k):
            calls.append(1)
            raise AssertionError("熔断后不应发起任何 HTTP 请求")

        import requests
        orig = requests.post
        requests.post = _boom
        try:
            self.client.guard.trip("bailian_llm", "模拟额度耗尽")
            self.assertEqual(self.client._call_bailian_raw("小朋友问：今天谁值日？", "你是皮皮"), "")
            self.assertEqual(len(calls), 0, "熔断后绝不能发出 HTTP 请求")
        finally:
            requests.post = orig

    def test_10_预算超限被拦截(self):
        calls = []

        def _counting(*a, **k):
            calls.append(1)
            raise AssertionError("超预算不应发起请求")

        import requests
        orig = requests.post
        requests.post = _counting
        try:
            self.client.guard.record("bailian_llm", tokens=99999999)
            self.assertEqual(self.client._call_bailian_raw("测试"), "")
            self.assertEqual(len(calls), 0, "预算用尽后不应发起请求")
        finally:
            requests.post = orig

    def test_11_模型404自动切换(self):
        """首选模型 404 时逐个降级，且不熔断（额度是按模型计的）"""
        attempts = []

        class Resp:
            status_code = 404
            text = '{"error":{"code":"ModelNotFound","message":"model not exist"}}'

            def json(self):
                return {}

        import requests
        orig = requests.post
        requests.post = lambda u, headers=None, json=None, timeout=None, **k: (
            attempts.append(json.get("model")), Resp()
        )[1]
        try:
            self.assertEqual(self.client._call_bailian_raw("测试"), "")
            self.assertGreaterEqual(len(attempts), 2, "404 时应尝试多个候选模型")
            self.assertEqual(len(set(attempts)), len(attempts), "候选模型不应重复")
            self.assertFalse(self.client.guard.is_tripped("bailian_llm")[0], "404 不属额度问题，不应熔断整条链路")
        finally:
            requests.post = orig

    def test_12_额度429自动切换到下一模型(self):
        """首选模型额度耗尽(429)时自动换下一个模型，对话不中断（核心需求）"""
        attempts = []

        class Throttled:
            status_code = 429
            text = '{"error":{"code":"Throttling","message":"exceeded your current quota"}}'

            def json(self):
                return {}

        class OkResp:
            status_code = 200
            text = "{}"

            def json(self):
                return {
                    "choices": [{"message": {"content": " 连接成功 "}}],
                    "usage": {"total_tokens": 88},
                }

        import requests
        orig = requests.post

        def _route(u, headers=None, json=None, timeout=None, **k):
            m = json.get("model")
            attempts.append(m)
            return Throttled() if m == "qwen3.5-flash" else OkResp()

        requests.post = _route
        try:
            out = self.client._call_bailian_raw("测试")
            self.assertEqual(out, "连接成功", "额度耗尽后应无缝切到下一模型继续服务")
            self.assertEqual(attempts[0], "qwen3.5-flash", "应先尝试首选模型")
            self.assertGreaterEqual(len(attempts), 2, "首选失败后必须尝试下一个")
            self.assertEqual(self.client.active_model, attempts[-1], "生效模型应更新为实际成功的那个")
            self.assertNotEqual(self.client.active_model, "qwen3.5-flash")
            self.assertEqual(self.client.guard.today_used("bailian_llm", "tokens"), 88, "成功后必须记账")
        finally:
            requests.post = orig

    def test_13_全部模型不可用时返回空串(self):
        """候选链全部失效时返回空串，由上层降级本地规则引擎，绝不抛异常"""

        class Resp:
            status_code = 429
            text = '{"error":{"code":"Throttling"}}'

            def json(self):
                return {}

        import requests
        orig = requests.post
        requests.post = lambda *a, **k: Resp()
        try:
            self.assertEqual(self.client._call_bailian_raw("测试"), "")
        finally:
            requests.post = orig

    def test_14_连通性测试接口(self):
        """后台连通性测试：空 Key 与全 404 均给出可读提示"""
        from modules.llm_client import UnifiedLLMClient
        res = UnifiedLLMClient.test_provider_connection("bailian", "")
        self.assertFalse(res["success"])
        self.assertIn("不能为空", res["message"])

        class NotFound:
            status_code = 404
            text = '{"error":{"code":"ModelNotFound"}}'

            def json(self):
                return {}

        import requests
        orig = requests.post
        requests.post = lambda *a, **k: NotFound()
        try:
            res = UnifiedLLMClient.test_provider_connection("bailian", "k", "", "")
            self.assertFalse(res["success"])
            self.assertIn("不可用", res["message"])
        finally:
            requests.post = orig

    def test_15_连通性测试报告可用链(self):
        """连通性测试应探测全部候选并报告可用数量"""
        from modules.llm_client import UnifiedLLMClient
        probed = []

        class Resp:
            status_code = 200
            text = "{}"

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        import requests
        orig = requests.post
        requests.post = lambda u, headers=None, json=None, timeout=None, **k: (
            probed.append(json.get("model")), Resp()
        )[1]
        try:
            res = UnifiedLLMClient.test_provider_connection("bailian", "k", "", "")
            self.assertTrue(res["success"])
            self.assertGreaterEqual(len(probed), 5, "应探测候选链上的多个模型")
            self.assertIn("可用模型", res["message"])
        finally:
            requests.post = orig


class TestBailianTTSFallback(unittest.TestCase):
    """百炼 TTS 音色自动回退 + 三级降级链"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        import modules.quota_guard as qg
        from modules.voice_engine import VoiceEngine
        qg._guard_singleton = QuotaGuard(db_path=os.path.join(self._tmp.name, "quota_tts.db"))
        self.engine = VoiceEngine(api_key="", tts_api_key="fake-key-for-test")

    def tearDown(self):
        import modules.quota_guard as qg
        qg._guard_singleton = None
        self._tmp.cleanup()

    def test_16_音色候选链覆盖全部回退音色(self):
        from config.settings import BAILIAN_TTS_VOICE_FALLBACKS
        chain = self.engine.voices
        self.assertEqual(chain[0], "Cherry", "首选音色应为 Cherry（芊悦）")
        for v in BAILIAN_TTS_VOICE_FALLBACKS:
            self.assertIn(v, chain, f"回退音色 {v} 必须进入候选链")
        self.assertEqual(len(chain), len(set(chain)), "候选链不应有重复项")

    def test_17_音色不可用时自动切换(self):
        """首选音色失败时自动换下一个音色，播报不中断（核心需求）"""
        attempted = []
        pcm = b"RIFF" + b"\x00" * 500  # 伪 WAV

        class Resp:
            status_code = 200
            text = "{}"

            def json(self):
                return {"output": {"audio": {"url": "https://example.invalid/a.wav"}}}

        class BadVoice:
            status_code = 400
            text = '{"code":"InvalidParameter","message":"voice not available"}'

            def json(self):
                return {}

        import requests
        orig_post, orig_get = requests.post, requests.get
        requests.get = lambda u, timeout=None, **k: type(
            "R", (), {"status_code": 200, "content": pcm}
        )()
        requests.post = lambda u, headers=None, json=None, timeout=None, **k: (
            attempted.append(json["input"]["voice"]),
            BadVoice() if json["input"]["voice"] == "Cherry" else Resp(),
        )[1]
        try:
            audio = self.engine.synthesize_cloud_speech("小朋友你好呀")
            self.assertIsNotNone(audio, "音色切换后仍应成功返回音频")
            self.assertEqual(audio, pcm, "应返回下载到的完整音频")
            self.assertEqual(attempted[0], "Cherry", "应先尝试首选音色")
            self.assertGreaterEqual(len(attempted), 2, "首选失败后必须尝试下一个音色")
            self.assertNotEqual(self.engine.active_voice, "Cherry")
        finally:
            requests.post, requests.get = orig_post, orig_get

    def test_18_百炼成功路径解析URL并下载(self):
        """百炼成功响应应正确提取 URL 并下载音频"""
        pcm = b"RIFF" + b"\xAB" * 800

        class Resp:
            status_code = 200
            text = "{}"

            def json(self):
                return {"output": {"audio": {"url": "https://example.invalid/ok.wav"}}}

        import requests
        orig_post, orig_get = requests.post, requests.get
        requests.post = lambda *a, **k: Resp()
        requests.get = lambda u, timeout=None, **k: type(
            "R", (), {"status_code": 200, "content": pcm}
        )()
        try:
            audio = self.engine.synthesize_cloud_speech("小朋友你好呀")
            self.assertEqual(audio, pcm)
            self.assertEqual(self.engine.active_voice, "Cherry", "首选音色可用时应保持不变")
            from modules.quota_guard import get_quota_guard
            used = get_quota_guard().today_used("bailian_tts", "chars")
            self.assertGreater(used, 0, "TTS 成功后必须按字符数记账")
        finally:
            requests.post, requests.get = orig_post, orig_get

    def test_19_无百炼Key时降级edge(self):
        """未配置百炼 Key 时直接走 edge-tts，不抛异常"""
        from modules.voice_engine import VoiceEngine
        engine = VoiceEngine(api_key="", tts_api_key="")
        edge_called = []
        engine._synthesize_edge = lambda t, v=None: (edge_called.append(t), b"ID3" + b"\x00" * 512)[1]
        out = engine.synthesize_cloud_speech("小朋友你好")
        self.assertEqual(len(edge_called), 1, "无百炼 Key 应降级到 edge-tts")
        self.assertEqual(out[:3], b"ID3")

    def test_20_百炼熔断后降级edge且零请求(self):
        """百炼已熔断时必须跳过云端请求，直接降级 edge-tts"""
        import requests
        from modules.quota_guard import get_quota_guard
        get_quota_guard().trip("bailian_tts", "模拟额度耗尽")
        sent = []
        orig = requests.post
        requests.post = lambda *a, **k: (sent.append(1), AssertionError("熔断后不应请求云端"))[1]
        edge_called = []
        self.engine._synthesize_edge = lambda t, v=None: (edge_called.append(t), b"ID3" + b"\x00" * 512)[1]
        try:
            out = self.engine.synthesize_cloud_speech("小朋友你好")
            self.assertEqual(out[:3], b"ID3", "熔断后应返回 edge 兜底音频")
            self.assertEqual(len(edge_called), 1)
            self.assertEqual(len(sent), 0, "熔断后绝不能向云端发起请求")
        finally:
            requests.post = orig

    def test_21_全链路失效返回None(self):
        """百炼熔断 + edge 失败时返回 None，交给前端 Web Speech，绝不抛异常"""
        from modules.quota_guard import get_quota_guard
        get_quota_guard().trip("bailian_tts", "模拟额度耗尽")
        self.engine._synthesize_edge = lambda t, v=None: None
        self.assertIsNone(self.engine.synthesize_cloud_speech("小朋友你好"))

    def test_22_空文本与超长文本处理(self):
        self.assertIsNone(self.engine.synthesize_cloud_speech(""))
        self.assertIsNone(self.engine.synthesize_cloud_speech("   "))
        import modules.voice_engine as ve
        captured = {}
        self.engine._synthesize_edge = lambda t, v=None: (
            captured.setdefault("t", t), b"ID3" + b"\x00" * 512
        )[1]
        self.engine.synthesize_cloud_speech("啊" * 1000)
        self.assertLessEqual(len(captured.get("t", "")), ve.MAX_TTS_CHARS, "超长文本应安全截断")

    def test_23_文本清洗去除emoji(self):
        cleaned = self.engine._clean_tts_text("🦄《两个小八路》✨在第二层🔵哦！❤️")
        self.assertNotIn("🦄", cleaned)
        self.assertNotIn("《", cleaned)
        self.assertNotIn("🔵", cleaned)
        self.assertIn("两个小八路", cleaned)
        self.assertEqual(self.engine._clean_tts_text(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)