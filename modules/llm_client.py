"""
统一大模型中枢适配器 (Unified LLM Client)
支持阿里云百炼（主）、Google Gemini、DeepSeek 三家，可在教师管理后台动态切换。

百炼接入要点：
- 端点走 OpenAI 兼容协议 https://dashscope.aliyuncs.com/compatible-mode/v1
- 自动换模型链：某模型额度用尽/未开通时，按候选列表无缝切到下一个，不中断对话
- 所有调用统一经过 QuotaGuard 熔断器作为账单安全的兜底保险
"""
import os
import json
import time
from typing import List, Dict, Any, Optional
from google import genai
from config.settings import (
    GEMINI_API_KEY, 
    DEEPSEEK_API_KEY, 
    DEEPSEEK_BASE_URL, 
    DEEPSEEK_MODEL,
    BAILIAN_API_KEY,
    BAILIAN_BASE_URL,
    BAILIAN_MODEL,
    BAILIAN_MODEL_FALLBACKS,
    DAILY_BUDGET_TOKENS,
)
from modules.quota_guard import get_quota_guard

# 幼儿端整体响应预算（秒）。模型回退链有 6 个，逐个超时累加会到 70 秒，
# 孩子根本等不住；超过预算就返回空串，由 agent 走本地兜底文案。
LLM_TOTAL_BUDGET = 8.0


def _budget_exhausted(start_at: float, budget: float) -> bool:
    """是否已超出本次调用的总时间预算"""
    return (time.time() - start_at) >= budget


class UnifiedLLMClient:
    def __init__(self, 
                 provider: str = "bailian", 
                 gemini_api_key: Optional[str] = None,
                 deepseek_api_key: Optional[str] = None,
                 deepseek_base_url: Optional[str] = None,
                 deepseek_model: Optional[str] = None,
                 bailian_api_key: Optional[str] = None,
                 bailian_base_url: Optional[str] = None,
                 bailian_model: Optional[str] = None):
        self.provider = provider.lower()  # 'bailian' / 'gemini' / 'deepseek'
        # None 表示未指定（回退环境变量/本地配置）；显式传空串表示清空 Key
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
        self.deepseek_api_key = deepseek_api_key if deepseek_api_key is not None else os.getenv("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)
        self.deepseek_base_url = deepseek_base_url if deepseek_base_url is not None else os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
        self.deepseek_model = deepseek_model if deepseek_model is not None else os.getenv("DEEPSEEK_MODEL", DEEPSEEK_MODEL)
        self.bailian_api_key = bailian_api_key if bailian_api_key is not None else os.getenv("BAILIAN_API_KEY", BAILIAN_API_KEY)
        self.bailian_base_url = bailian_base_url if bailian_base_url is not None else os.getenv("BAILIAN_BASE_URL", BAILIAN_BASE_URL)
        self.bailian_model = bailian_model if bailian_model is not None else os.getenv("BAILIAN_MODEL", BAILIAN_MODEL)
        self.guard = get_quota_guard()

        # 百炼候选模型链：优先用户配置的，其次按 BAILIAN_MODEL_FALLBACKS 回退。
        # 某模型额度用尽或未开通时自动切换到下一个，对话不中断。
        self.bailian_models = [self.bailian_model] + [
            m for m in BAILIAN_MODEL_FALLBACKS if m != self.bailian_model
        ]
        # 运行时状态：实际生效的模型（供后台展示「当前正在用哪个模型」）
        self.active_model = self.bailian_models[0]
        
        # 默认优先使用的 Gemini 模型列表（按新旧程度降级尝试，遇配额/过载自动切换）
        self.gemini_models = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

    def chat(self, user_query: str, system_prompt: str, tools_context: str = "") -> str:
        """多轮/单轮通用自然语言交互（不含历史，单轮）"""
        if self.provider == "gemini":
            return self._chat_with_gemini(user_query, system_prompt, tools_context)
        elif self.provider == "bailian":
            return self._call_bailian_raw(f"{tools_context}\n\n小朋友问：{user_query}", system_prompt)
        else:
            return self._chat_with_deepseek(user_query, system_prompt, tools_context)

    def chat_multi_turn(
        self,
        user_query: str,
        system_prompt: str,
        tools_context: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_turns: int = 4,
    ) -> str:
        """
        带历史的多轮对话。

        历史裁剪：仅保留最近 max_turns 轮（2*max_turns 条消息），控制 token 与延迟。
        百炼侧走 OpenAI 兼容的 messages 数组；DeepSeek 同协议；
        Gemini 无状态，将历史拼进 prompt 文本。
        """
        history = (history or [])[-max_turns * 2:]
        if not history:
            return self.chat(user_query, system_prompt, tools_context)

        if self.provider == "gemini":
            # Gemini 走文本拼接：把历史按时间顺序写进上下文
            lines = "\n".join(
                f"{'小朋友' if m.get('role') == 'user' else '皮皮'}：{m.get('content', '')}"
                for m in history
            )
            merged = f"{tools_context}\n\n【你们刚才的对话】\n{lines}\n\n小朋友现在问：{user_query}"
            return self._chat_with_gemini(merged, system_prompt, "")

        if self.provider == "bailian":
            return self._call_bailian_messages(
                user_query, system_prompt, tools_context, history
            )

        # DeepSeek / 其他 OpenAI 兼容端点
        return self._chat_with_deepseek_multi(user_query, system_prompt, tools_context, history)

    def _call_bailian_messages(self, user_query: str, system_prompt: str,
                               tools_context: str, history: List[Dict[str, str]]) -> str:
        """百炼多轮：构造完整 messages 数组后走同一套模型回退 + 熔断逻辑"""
        if not self.bailian_api_key or not self.bailian_api_key.strip():
            return ""

        estimated = sum(len(m.get("content", "")) for m in history) * 2 + len(user_query) * 2 + 800
        start_at = time.time()
        allowed, reason = self.guard.acquire(
            "bailian_llm", kind="tokens", estimated=estimated, limit=DAILY_BUDGET_TOKENS
        )
        if not allowed:
            print(f"[bailian] 本地熔断拦截，未发起请求: {reason}")
            return ""

        try:
            import requests
        except ImportError:
            print("[bailian] requests 未安装，无法调用百炼")
            return ""

        # 事实约束写进 system，保证每一轮都受约束
        system_content = (
            f"{system_prompt}\n\n"
            f"以下是图书角实时数据库信息，回答必须以此为准，不得编造层号、人名与书名：\n{tools_context}"
        )
        messages = [{"role": "system", "content": system_content}]
        for m in history:
            role = "assistant" if m.get("role") == "assistant" else "user"
            content = (m.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_query})

        return self._post_bailian(messages, estimated)

    def _post_bailian(self, messages: List[Dict[str, str]], estimated: int) -> str:
        """统一的百炼请求执行：遍历模型回退链 + 熔断记账"""
        try:
            import requests
        except ImportError:
            print("[bailian] requests 未安装，无法调用百炼")
            return ""

        url = f"{self.bailian_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.bailian_api_key.strip()}",
            "Content-Type": "application/json",
        }
        for model_name in self.bailian_models:
            if _budget_exhausted(start_at, LLM_TOTAL_BUDGET):
                print(f"[bailian] 超出总预算 {LLM_TOTAL_BUDGET}s，停止回退，交本地兜底")
                return ""
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 220,
            }
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=(5, 12))
            except Exception as e:
                print(f"[bailian] 请求异常（{model_name}）: {str(e)[:90]}")
                continue

            if res.status_code == 200:
                try:
                    content = res.json()["choices"][0]["message"]["content"]
                    usage = res.json().get("usage") or {}
                    self.guard.record("bailian_llm", tokens=int(usage.get("total_tokens") or 0) or estimated)
                    if self.active_model != model_name:
                        self.active_model = model_name
                        print(f"[bailian] 已切换到模型: {model_name}")
                    return (content or "").strip()
                except Exception as e:
                    print(f"[bailian] 响应解析失败（{model_name}）: {e}")
                    continue

            body = res.text[:300]
            low = body.lower()
            if res.status_code == 404 or "model_not_found" in low or "model not exist" in low:
                print(f"[bailian] 模型 {model_name} 未开通/不可用，自动切换下一个")
                continue
            if self.guard.handle_response_error(f"bailian_llm:{model_name}", res.status_code, body):
                print(f"[bailian] 模型 {model_name} 额度异常，自动切换下一个: {body[:120]}")
                continue
            print(f"[bailian] 响应错误 {res.status_code}（{model_name}）: {body}")
        return ""

    def _chat_with_deepseek_multi(self, user_query: str, system_prompt: str,
                                   tools_context: str, history: List[Dict[str, str]]) -> str:
        """DeepSeek 多轮：同为 OpenAI 兼容协议，直接拼 messages"""
        if not self.deepseek_api_key or not self.deepseek_api_key.strip():
            return ""
        try:
            import requests
        except ImportError:
            return ""
        system_content = f"{system_prompt}\n\n{tools_context}"
        messages = [{"role": "system", "content": system_content}]
        for m in history:
            role = "assistant" if m.get("role") == "assistant" else "user"
            if m.get("content"):
                messages.append({"role": role, "content": m["content"]})
        messages.append({"role": "user", "content": user_query})
        try:
            res = requests.post(
                f"{self.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.deepseek_api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json={"model": self.deepseek_model, "messages": messages, "temperature": 0.3},
                timeout=30,
            )
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"DeepSeek 多轮调用异常: {e}")
        return ""

    def auto_catalog(self, book_title: str) -> Dict[str, Any]:
        """为绘本自动梳理生成标准化档案"""
        prompt = f"""你是一名资深幼儿园课程与绘本专家。请为绘本《{book_title}》生成标准化图书角档案。
请严格以 JSON 格式输出，不要包含多余文字：
{{
    "title": "{book_title}",
    "author": "作者姓名",
    "target_age": "适读年龄段（小班 (3-4岁) / 中班 (4-5岁) / 大班 (5-6岁) / 全园通用）",
    "theme": "教育主题分类（规则习惯 / 情绪管理 / 科学探索 / 亲子温情 / 创意想象）",
    "shelf_row": 推荐书架层位（整数 1、2、3 或 4）,
    "shelf_color": "架位标识（1对应'⚪ 第1层·顶层平视区'，2对应'🔵 第2层·蓝色圆点区'，3对应'🟡 第3层·黄色圆点区'，4对应'🟢 第4层·绿色圆点区'）",
    "summary": "50字以内的儿童故事导读及教育意义"
}}"""

        if self.provider == "gemini":
            content = self._call_gemini_raw(prompt)
        elif self.provider == "bailian":
            content = self._call_bailian_raw(prompt)
        else:
            content = self._call_deepseek_raw(prompt)

        # 解析与规范化：模型可能漏字段或返回非标准结构，逐字段兜底保证下游可用
        parsed: Dict[str, Any] = {}
        try:
            content = (content or "").strip()
            if "```" in content:
                content = content.split("```json")[-1].split("```")[0].strip()
            if content:
                loaded = json.loads(content)
                if isinstance(loaded, dict):
                    parsed = loaded
        except Exception:
            parsed = {}

        shelf_row = parsed.get("shelf_row")
        if not isinstance(shelf_row, int) or shelf_row not in (1, 2, 3, 4):
            shelf_row = 2

        return {
            "title": parsed.get("title") or book_title,
            "author": parsed.get("author") or "名家绘本",
            "target_age": parsed.get("target_age") or "中班 (4-5岁)",
            "theme": parsed.get("theme") or "趣味认知与习惯养成",
            "shelf_row": shelf_row,
            "shelf_color": parsed.get("shelf_color") or "🔵 第2层·蓝色圆点区",
            "summary": parsed.get("summary") or f"关于《{book_title}》的精彩儿童故事，适合幼儿自主翻阅与探索。"
        }

    def generate_analytics_report(self, popular_books: list, dormant_books: list, theme_stats: list) -> str:
        """生成教师端图书角动态调仓指导报告"""
        top_titles = [f"《{b['title']}》({b.get('theme', '综合')}, 借阅{b.get('read_count',0)}次)" for b in popular_books[:4]]
        cold_titles = [f"《{b['title']}》({b.get('theme', '综合')}, 借阅{b.get('read_count',0)}次)" for b in dormant_books[:3]]

        prompt = f"""你是一名学前教育专家和幼儿园绘本区角教研督导。
请根据班级图书角借阅数据为带班教师撰写《图书角动态调配与阅读指导建议》：
数据：
- 最受欢迎绘本：{', '.join(top_titles) if top_titles else '数据收集中'}
- 滞销冷门预警：{', '.join(cold_titles) if cold_titles else '暂无严重冷门'}
- 主题分布：{', '.join([f"{t['theme']}({t['book_count']}本)" for t in theme_stats])}

请必须包含以下四个完整模块：
一、 幼儿阅读兴趣热点透视
二、 滞销冷门图书调仓下架建议（明确指出建议收仓的2本并给出原因）
三、 资源动态配置与补强推荐清单（推荐2-3本适合幼儿的优质补充绘本）
四、 班级区角延伸教育活动建议"""

        if self.provider == "gemini":
            resp = self._call_gemini_raw(prompt)
        elif self.provider == "bailian":
            resp = self._call_bailian_raw(prompt)
        else:
            resp = self._call_deepseek_raw(prompt)

        # 调用失败返回空串，由上层 AnalyticsEngine 决定结构化离线兜底
        return resp if resp and len(resp) > 60 else ""

    # ================= 内部 Gemini 调用 =================
    def _chat_with_gemini(self, user_query: str, system_prompt: str, tools_context: str) -> str:
        full_prompt = f"{system_prompt}\n\n图书角当前上下文数据：\n{tools_context}\n\n小朋友说：{user_query}\n请用亲切童趣的幼师语言回复小朋友："
        return self._call_gemini_raw(full_prompt)

    def _call_gemini_raw(self, prompt: str) -> str:
        if not self.gemini_api_key or not self.gemini_api_key.strip():
            return ""
        try:
            client = genai.Client(api_key=self.gemini_api_key.strip())
            for model_name in self.gemini_models:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                    if resp and resp.text:
                        return resp.text.strip()
                except Exception as model_err:
                    # 如果该模型超出额度或不可用，尝试降级至下一个模型
                    continue
        except Exception as e:
            print(f"Gemini API Error: {e}")
        return ""

    # ================= 内部百炼（DashScope）调用 =================
    def _chat_with_bailian(self, user_query: str, system_prompt: str, tools_context: str) -> str:
        full_prompt = f"{tools_context}\n\n小朋友问：{user_query}"
        return self._call_bailian_raw(full_prompt, system_prompt)

    def _call_bailian_raw(self, prompt: str, system_prompt: str = "") -> str:
        """
        调用阿里云百炼 OpenAI 兼容接口。

        三层保障：
        1. 本地预算闸门（QuotaGuard）——账单兜底保险
        2. 自动换模型链 —— 某模型额度用尽/未开通时无缝切下一个，对话不中断
        3. 全部候选均不可用时返回空串，由上层降级到本地规则引擎
        """
        if not self.bailian_api_key or not self.bailian_api_key.strip():
            return ""

        # 本地预算闸门：预估 ~2 token/字符（含 system prompt 与输出余量）
        estimated = int((len(prompt) + len(system_prompt)) * 2) + 500
        start_at = time.time()
        allowed, reason = self.guard.acquire(
            "bailian_llm", kind="tokens", estimated=estimated, limit=DAILY_BUDGET_TOKENS
        )
        if not allowed:
            print(f"[bailian] 本地熔断拦截，未发起请求: {reason}")
            return ""

        try:
            import requests
        except ImportError:
            print("[bailian] requests 未安装，无法调用百炼")
            return ""

        url = f"{self.bailian_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.bailian_api_key.strip()}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        for model_name in self.bailian_models:
            # 整体时间预算：回退链有 6 个模型，逐个 (5,12) 最坏要 70 秒，
            # 幼儿端绝对等不起。超过 8 秒就放弃，交给本地兜底 ——
            # 早答一句"书在第几层"远好过让孩子干等一分钟。
            if _budget_exhausted(start_at, LLM_TOTAL_BUDGET):
                print(f"[bailian] 超出总预算 {LLM_TOTAL_BUDGET}s，停止回退，交本地兜底")
                return ""
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.3,
                # 幼儿端要求秒回：限制输出长度，避免模型长篇大论拖慢响应
                "max_tokens": 220,
            }
            try:
                # (connect, read)：连接 5s、读取 12s。
                # 幼儿端等不了 30 秒——超时即换下一个模型，最后由本地规则引擎兜底。
                res = requests.post(url, headers=headers, json=payload, timeout=(5, 12))
            except Exception as e:
                print(f"[bailian] 请求异常（{model_name}）: {str(e)[:90]}")
                continue

            if res.status_code == 200:
                try:
                    result = res.json()
                    content = result["choices"][0]["message"]["content"]
                    usage = result.get("usage") or {}
                    consumed = int(usage.get("total_tokens") or 0) or estimated
                    self.guard.record("bailian_llm", tokens=consumed)
                    # 记录实际生效的模型，供后台展示「当前正在用哪个模型」
                    if self.active_model != model_name:
                        self.active_model = model_name
                        print(f"[bailian] 已切换到模型: {model_name}")
                    return (content or "").strip()
                except Exception as e:
                    print(f"[bailian] 响应解析失败（{model_name}）: {e}")
                    continue

            body = res.text[:300]
            # 404 = 模型未开通；400 + model_not_found = 模型名不可用。
            # 这两类都只影响「这一个模型」，换下一个候选即可，不属于全局额度问题。
            low = body.lower()
            if res.status_code == 404 or "model_not_found" in low or "model not exist" in low:
                print(f"[bailian] 模型 {model_name} 未开通/不可用，自动切换下一个")
                continue

            # 额度耗尽：百炼的额度错误同样伪装成 429/403/Throttling。
            # 关键：额度是【按模型】计的，所以这里不熔断整条链路，而是继续换模型——
            # 只要候选链里还有有额度的模型，就能继续服务。
            if self.guard.handle_response_error(f"bailian_llm:{model_name}", res.status_code, body):
                print(f"[bailian] 模型 {model_name} 额度异常，自动切换下一个: {body[:120]}")
                continue

            print(f"[bailian] 响应错误 {res.status_code}（{model_name}）: {body}")

        return ""

    # ================= 内部 DeepSeek 调用 =================
    def _chat_with_deepseek(self, user_query: str, system_prompt: str, tools_context: str) -> str:
        full_prompt = f"{tools_context}\n\n小朋友问：{user_query}"
        return self._call_deepseek_raw(full_prompt, system_prompt)

    def _call_deepseek_raw(self, prompt: str, system_prompt: str = "") -> str:
        if not self.deepseek_api_key or not self.deepseek_api_key.strip():
            return ""
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key.strip()}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            url = f"{self.deepseek_base_url.rstrip('/')}/chat/completions"
            data = {
                "model": self.deepseek_model,
                "messages": messages,
                "temperature": 0.3
            }
            res = requests.post(url, headers=headers, json=data, timeout=30)
            if res.status_code == 200:
                result = res.json()
                return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"DeepSeek API Error: {e}")
        return ""

    # ================= 连接状态测试 =================
    @staticmethod
    def test_provider_connection(provider: str, api_key: str, base_url: str = "", model: str = "") -> Dict[str, Any]:
        """在管理界面供教师一键测试 API 连通性"""
        if not api_key.strip():
            return {"success": False, "message": "API Key 不能为空！"}

        if provider == "gemini":
            try:
                client = genai.Client(api_key=api_key.strip())
                for m in ["gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]:
                    try:
                        resp = client.models.generate_content(model=m, contents="测试连通性，请回复四个字：连接成功")
                        if resp and resp.text:
                            return {"success": True, "message": f"Gemini 连接成功！(使用模型: {m})"}
                    except Exception:
                        continue
                return {"success": False, "message": "Gemini API 响应异常或当前模型配额已达上限。"}
            except Exception as e:
                return {"success": False, "message": f"连接失败: {str(e)}"}
        elif provider == "bailian":
            try:
                import requests
                url = f"{(base_url or 'https://dashscope.aliyuncs.com/compatible-mode/v1').rstrip('/')}/chat/completions"
                headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
                # 逐个候选模型探测，返回第一个可用的，并报告整条可用链
                candidates = [model] if model else list(BAILIAN_MODEL_FALLBACKS)
                available = []
                for m in candidates:
                    payload = {
                        "model": m,
                        "messages": [{"role": "user", "content": "测试连接，请回复：连接成功"}],
                        "max_tokens": 50,
                        "temperature": 0.1,
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=15)
                    if res.status_code == 200:
                        available.append(m)
                        continue
                    low = res.text.lower()
                    if res.status_code == 404 or "model_not_found" in low or "model not exist" in low:
                        continue  # 该模型未开通，跳过继续探测
                    return {
                        "success": False,
                        "message": f"百炼响应错误 ({res.status_code}): {res.text[:120]}",
                    }
                if available:
                    return {
                        "success": True,
                        "message": f"百炼连接成功！可用模型 {len(available)}/{len(candidates)}：{', '.join(available)}",
                    }
                return {
                    "success": False,
                    "message": "所有候选模型均不可用。请到百炼控制台「开通管理」开通对应模型，或在上方手动填写已开通的模型名。",
                }
            except Exception as e:
                return {"success": False, "message": f"请求异常: {str(e)}"}
        else:
            try:
                import requests
                headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
                url = f"{(base_url or 'https://api.deepseek.com/v1').rstrip('/')}/chat/completions"
                payload = {
                    "model": model or "deepseek-chat",
                    "messages": [{"role": "user", "content": "测试连接，请回复：连接成功"}],
                    "temperature": 0.1
                }
                res = requests.post(url, headers=headers, json=payload, timeout=10)
                if res.status_code == 200:
                    return {"success": True, "message": "DeepSeek API 验证成功！"}
                else:
                    return {"success": False, "message": f"DeepSeek 响应错误 ({res.status_code}): {res.text[:100]}"}
            except Exception as e:
                return {"success": False, "message": f"请求异常: {str(e)}"}
