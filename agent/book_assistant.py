"""
智慧图书角智能体中枢 (Kindergarten Book Assistant) - V2.0 旗舰版
结合实景 4 层白色阶梯书架（顶层、二层🔵蓝点、三层🟡黄点、四层🟢绿点），
精准识别绘本位置，绑定三大专属卡通标签（故事-👑, 科普-🔍, 绘本-❤️）。
"""
import os
import json
import random
from typing import Dict, Any, List, Optional
from modules.db_manager import DatabaseManager
from modules.llm_client import UnifiedLLMClient
from agent.topic_index import match_topic
from config.settings import (
    GEMINI_API_KEY,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    BAILIAN_API_KEY,
    BAILIAN_BASE_URL,
    BAILIAN_MODEL,
)

class KindergartenBookAgent:
    def __init__(self, 
                 provider: str = "bailian",
                 gemini_api_key: Optional[str] = None,
                 deepseek_api_key: Optional[str] = None,
                 deepseek_base_url: Optional[str] = None,
                 deepseek_model: Optional[str] = None,
                 bailian_api_key: Optional[str] = None,
                 bailian_base_url: Optional[str] = None,
                 bailian_model: Optional[str] = None):
        self.provider = provider
        self.db = DatabaseManager()
        self.llm_client = UnifiedLLMClient(
            provider=provider,
            gemini_api_key=gemini_api_key,
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=deepseek_base_url,
            deepseek_model=deepseek_model,
            bailian_api_key=bailian_api_key,
            bailian_base_url=bailian_base_url,
            bailian_model=bailian_model
        )
        
        self.system_prompt = (
            "你叫‘图书精灵皮皮’，是阳光幼儿园智慧图书角的贴心AI小助手。\n"
            "你的语言风格必须充满童趣、亲切短小、温和有爱（多使用‘呀’、‘哦’、‘哇’等语气词）。\n"
            "图书角使用4层白色阶梯书架：\n"
            "- 第1层：顶层平视区\n"
            "- 第2层：贴有蓝色圆点贴纸 🔵\n"
            "- 第3层：贴有黄色圆点贴纸 🟡\n"
            "- 第4层：贴有绿色圆点贴纸 🟢\n"
            "你的职责：\n"
            "1. 告诉小朋友想借的图书放在第几层、什么颜色的圆点处；\n"
            "2. 告诉小朋友今天轮到谁当值日小管家，并播报整理口诀；\n"
            "3. 鼓励小朋友轻拿轻放、看完归位，树立自主管理主人翁意识。\n"
            "请严格依据提供的图书角实时数据库信息回答，切勿编造层号与人名！"
        )

    def chat(self, user_query: str, prefer_fast: bool = False,
            history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        处理儿童自然语言或语音转写输入，返回亲切回答与实物 4 层书架高亮层号

        参数：
            user_query  儿童输入（文本或语音转写结果）
            prefer_fast 保留兼容参数；当前实现对「数据库可直答」一律走本地快答
            history     历史对话 [{'role': 'user'|'assistant', 'content': str}, ...]，
                        用于多轮上下文（如「它讲什么故事？」能接上文提到的书）
        """
        user_query = user_query.strip()
        history = history or []

        books = self.db.get_all_books()
        today_duty = self.db.get_today_duty()

        # 书名匹配需跨轮次：用户在多轮里常省略书名（「它在哪层」）
        matched_book = self._match_book(user_query, books, history)

        if matched_book:
            self.db.increment_book_interaction(matched_book['title'], action_type='search', student_name="小读者")

        context = self._build_context(matched_book, today_duty, books)

        # 分流：能由数据库给出事实的一律毫秒级本地回答，开放问题才交大模型
        ai_reply, is_local = self._dispatch_local(
            user_query, books, today_duty, matched_book, history
        )
        if not is_local:
            ai_reply = self.llm_client.chat_multi_turn(
                user_query, self.system_prompt, context, history
            )
            if ai_reply:
                ai_reply = self._sanitize_llm_reply(ai_reply, books, matched_book, user_query)
            if not ai_reply:
                ai_reply = self._fallback_reply(books, matched_book, user_query)

        # 只有"找书定位"才点亮书架层位；问候/推荐/多本清单不该误导幼儿去某一层
        highlight_tier = 0
        if matched_book and not self._is_detail_question(user_query):
            highlight_tier = matched_book['shelf_tier']
        elif not matched_book:
            # 只有当回答里明确指向**唯一一层**时才高亮，多本清单一律不高亮
            tiers = self._distinct_tiers(ai_reply)
            highlight_tier = tiers.pop() if len(tiers) == 1 else 0

        return {
            "reply": ai_reply,
            "highlight_row": highlight_tier,
            "provider": self.provider,
            "matched_title": matched_book['title'] if matched_book else None,
        }

    # ================= 意图路由（本地快答） =================

    def _dispatch_local(self, user_query: str, books: List[Dict[str, Any]],
                        today_duty: Dict[str, Any],
                        matched_book: Optional[Dict[str, Any]],
                        history: List[Dict[str, str]]) -> tuple:
        """
        本地快答分发。返回 (回复文本, 是否已本地回答)。
        已本地回答 -> True；需要大模型 -> (None, False)
        """
        q = user_query

        def has(*ks: str) -> bool:
            return any(k in q for k in ks)

        # 1) 值日播报（最高优先级）
        if has("值日", "谁管", "小助手", "打扫", "整理", "值班"):
            return self._build_duty_reply(today_duty), True

        # 2) 已匹配到具体书 -> 按追问类型用数据库事实回答
        if matched_book:
            if has("几岁", "多大", "年龄", "适读", "适合几"):
                return self._build_age_reply(matched_book), True
            if has("谁写", "作者", "谁做", "谁画"):
                return self._build_author_reply(matched_book), True
            if has("在哪", "哪里", "第几层", "哪一层", "什么书"):
                return self._build_book_reply(matched_book), True
            # 「它讲什么故事」这类内容型追问交大模型（真实档案已在 context 里）
            return None, False

        # 3) 打招呼 / 自我介绍 / 能力说明
        if has("你好", "您好", "hello", "早上好", "中午好", "下午好", "晚上好",
                "在吗", "在不在", "有人吗", "嗨"):
            if has("你是谁", "你叫什么", "你是什么", "介绍一下你", "介绍自己"):
                return self._build_identity_reply(books), True
            return self._build_greet_reply(books), True

        if has("你是谁", "你叫什么", "你是什么", "介绍一下你"):
            return self._build_identity_reply(books), True

        if has("你会什么", "能做什么", "会做什么", "怎么用", "怎么玩", "能帮我", "有什么功能"):
            return self._build_capability_reply(books), True

        # 4) 图书角有多少书 / 都有什么书
        if has("几本书", "多少本", "几本", "有什么书", "都有什么", "图书角有什么"):
            return self._build_count_reply(books), True

        # 5) 随便推荐
        if has("推荐", "随便", "来一本", "给我一本", "有什么好看", "选一本"):
            return self._build_recommend_reply(books), True

        # 6) 主题检索（海洋/动物/勇敢/红色…）——只认能落到真实书名上的主题
        topic_hits = match_topic(q, [b['title'] for b in books])
        if topic_hits:
            by_title = {b['title']: b for b in books}
            picked = [by_title[t] for t in topic_hits if t in by_title]
            # 「小雪球是谁写的」——书名简称 + 细节追问，按第一本答细节
            if picked and has("谁写", "作者", "谁画", "几岁", "多大", "多大"):
                return self._build_author_reply(picked[0]), True
            return self._build_topic_reply(picked), True

        # 7) 告别
        if has("再见", "拜拜", "我要走了", "下次见"):
            return self._build_bye_reply(), True

        # 8) 明确在找书但主题落不到真实书名 -> 诚实说没有 + 给真实替代，
        #    不放行到大模型（否则会编书名，且要白等 1~3 秒）
        if self._looks_like_book_search(q):
            return self._build_no_such_topic_reply(q, books), True

        # 9) 没点名书却问细节 -> 反问书名，别让大模型自由发挥
        if has("几岁", "多大", "谁写", "作者", "在哪", "哪里", "第几层", "是什么书"):
            return self._build_need_title_reply(books), True

        # 10) 其余交大模型
        return None, False

    @staticmethod
    def _is_detail_question(q: str) -> bool:
        """内容型追问（故事/适读/作者）不该点亮书架层位"""
        return any(k in q for k in ["故事", "讲什么", "简介", "内容", "适读", "几岁",
                                    "多大", "作者", "是谁", "好看", "推荐"])

    @staticmethod
    def _distinct_tiers(text: str) -> set:
        """从文本里抽出所有"第N层"的层号集合（阿拉伯/中文数字都认）"""
        import re
        cn = {"一": 1, "二": 2, "三": 3, "四": 4}
        out = set()
        for t in re.findall(r"第\s*([1-4一二三四])\s*层", text or ""):
            if t in cn:
                out.add(cn[t])
            elif t.isdigit():
                out.add(int(t))
        return out

    @classmethod
    def _sanitize_llm_reply(cls, reply: str, books: List[Dict[str, Any]],
                            matched_book: Optional[Dict[str, Any]],
                            user_query: str) -> str:
        """
        大模型事实护栏：图书角是**实物书架**，编书名=让幼儿白跑一趟。

        实测大模型在被问「有没有恐龙的书」时会凭空造出《恐龙大冒险》并给出
        假的层号（第2层），比答不出危害大得多。这里逐条校验：
        1) 回复里引用的《书名》必须真实存在；
        2) 引用真实书时，说的层号必须和数据库一致；
        任一不通过 -> 丢掉这段编造，改用本地安全回复。
        """
        import re

        if not reply:
            return ""
        titles = {b['title']: b for b in books}
        cited = re.findall(r"《([^》]{1,40})》", reply)

        for c in cited:
            c = c.strip()
            if c in titles:
                continue
            # 容忍模型把附加语塞进书名（如《两个小八路 在第2层》）
            if not any(t.startswith(c[:4]) or c.startswith(t[:4]) for t in titles):
                print(f"[agent-guard] 拦截幻觉书名《{c}》")
                return cls._fallback_reply(books, matched_book, user_query)

        # 校验层号：提到"第N层"却与目标图书不符 -> 同样判为幻觉
        if matched_book:
            said = cls._distinct_tiers(reply)
            if said and said - {matched_book.get('shelf_tier')}:
                print(f"[agent-guard] 拦截错误层号 {said}（应为 {matched_book.get('shelf_tier')}）")
                return cls._build_book_reply(matched_book)
        return reply

    # ================= 多轮上下文辅助 =================
    def _match_book(self, user_query: str, books: List[Dict[str, Any]],
                    history: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """
        匹配目标绘本。策略：
        1. 本轮输入含完整书名 -> 直接命中
        2. 本轮只说「它/这本/那本」-> 沿用上一轮匹配到的书
        3. 模糊包含匹配 -> 取书名被提及最多的那本
        """
        for b in books:
            if b['title'] in user_query:
                return b

        # 省略指代：回溯最近一次助手回答中提到的书
        pronoun_hint = any(k in user_query for k in ["它", "这本", "那本", "这本呢", "还有呢"])
        if pronoun_hint or not user_query:
            for msg in reversed(history):
                if msg.get("role") != "assistant":
                    continue
                for b in books:
                    if b['title'] in msg.get("content", ""):
                        return b
        return None

    def _build_context(self, matched_book: Optional[Dict[str, Any]],
                       today_duty: Dict[str, Any], books: List[Dict[str, Any]]) -> str:
        """构造给大模型的图书角事实上下文（严格限定事实来源，防止编造）"""
        ctx = (
            f"【今日值日信息】：值日生是{today_duty.get('student_names')}，"
            f"任务是：{today_duty.get('duty_task')}，"
            f"打卡状态：{'已打卡' if today_duty.get('completed') else '未打卡'}。\n"
            f"【在架图书总数】：{len(books)} 本\n"
        )
        if matched_book:
            ctx += (
                f"【当前讨论的图书真实档案】：书名《{matched_book['title']}》，"
                f"属于【{matched_book.get('category_type','绘本')}"
                f"{matched_book.get('cartoon_badge','❤️')}】，"
                f"放置在【第 {matched_book['shelf_tier']} 层 · "
                f"{matched_book['shelf_color_label']}，格位 {matched_book.get('shelf_slot','L1-01')}】，"
                f"故事简介：{matched_book.get('summary','')}。\n"
            )
        else:
            ctx += "【在架图书排位示例】：\n" + "\n".join(
                f"- 《{b['title']}》在【第{b['shelf_tier']}层，{b['shelf_color_label']}】"
                for b in books[:8]
            )
        return ctx

    @classmethod
    def _fallback_reply(cls, books: List[Dict[str, Any]],
                        matched_book: Optional[Dict[str, Any]],
                        user_query: str = "") -> str:
        """大模型不可用/超时时的本地兜底：用真实在架数据回答，绝不说空话"""
        if matched_book:
            return cls._build_book_reply(matched_book)
        if not books:
            return "图书角还没有书哦，等老师放几本进来吧！"

        # 主题词命中但大模型挂了 -> 至少把真实架位给出来
        topic_hits = match_topic(user_query, [b['title'] for b in books])
        if topic_hits:
            by_title = {b['title']: b for b in books}
            picked = [by_title[t] for t in topic_hits if t in by_title]
            return self._build_topic_reply(picked)

        sample = "、".join(f"《{b['title']}》" for b in books[:3])
        return (
            f"这个问题我得再想想～不过我可以马上告诉你书架上有什么！\n"
            f"图书角现在有 {len(books)} 本绘本，比如 {sample} 等等。\n"
            f"说出书名我就能告诉你它在哪一层，或者跟我说想看什么类型（海洋、动物、勇敢…）也行哦！"
        )

    # ================= 确定性回答构造（全部基于数据库事实） =================

    @staticmethod
    def _loc(book: Dict[str, Any]) -> str:
        """书架位置的统一表述"""
        return f"{book.get('shelf_color_label', '')} 格位 {book.get('shelf_slot', '')}".strip()

    @classmethod
    def _build_greet_reply(cls, books: List[Dict[str, Any]]) -> str:
        return (
            f"嗨！宝贝，我是图书小精灵皮皮～🦄\n"
            f"图书角有 {len(books)} 本绘本，我最擅长帮你做这几件事：\n"
            f"1️⃣ 说出书名，我告诉你它在哪一层\n"
            f"2️⃣ 说想看什么（海洋？动物？勇敢的故事？），我帮你挑\n"
            f"3️⃣ 问问今天谁当值日小卫士\n"
            f"你现在想玩哪一个呀？"
        )

    @classmethod
    def _build_identity_reply(cls, books: List[Dict[str, Any]]) -> str:
        return (
            f"我叫皮皮，是图书小精灵，就住在阳光幼儿园的图书角里～🦄\n"
            f"图书角的 {len(books)} 本书，每一本放在第几层、哪个格位，我全都记得牢牢的！\n"
            f"所以你随便问，书名也好、想看什么类型也好，我都能帮你找到。"
        )

    @classmethod
    def _build_capability_reply(cls, books: List[Dict[str, Any]]) -> str:
        return (
            f"我能帮你做这些事：\n"
            f"🔍 找书——说书名（比如《两个小八路》），我秒答它在第几层\n"
            f"🎨 按口味挑书——说「想看海洋的」「想看勇敢的」，我从 {len(books)} 本里给你挑\n"
            f"🗣️ 讲故事——想知道讲什么，我可以讲给你听\n"
            f"⭐ 今日值日——问问今天轮到谁当值日小卫士\n"
            f"试试直接说：「我想看关于海洋的书」！"
        )

    @classmethod
    def _build_count_reply(cls, books: List[Dict[str, Any]]) -> str:
        by_tier: Dict[int, int] = {}
        for b in books:
            by_tier[b.get('shelf_tier', 1)] = by_tier.get(b.get('shelf_tier', 1), 0) + 1
        dots = {1: "⚪ 第 1 层 · 顶层平视区", 2: "🔵 第 2 层 · 蓝色圆点",
                3: "🟡 第 3 层 · 黄色圆点", 4: "🟢 第 4 层 · 绿色圆点"}
        lines = [f"{dots.get(t, f'第 {t} 层')}：{by_tier.get(t, 0)} 本" for t in sorted(by_tier)]
        return (
            f"图书角一共 {len(books)} 本绘本，都在这 4 层架子上：\n"
            + "\n".join(lines)
            + "\n想看哪一类？跟我说「海洋」「动物」「勇敢」这种词就行～"
        )

    @classmethod
    def _spread_pick(cls, books: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
        """跨层各取一本，避免推荐结果全是第 1 层（视觉单调且信息量低）"""
        by_tier: Dict[int, List[Dict[str, Any]]] = {}
        for b in books:
            by_tier.setdefault(b.get('shelf_tier', 1), []).append(b)
        picked: List[Dict[str, Any]] = []
        for tier in sorted(by_tier):
            if len(picked) >= n:
                break
            picked.append(by_tier[tier][0])
        if len(picked) < n:  # 层数不够再从剩余里补
            rest = [b for b in books if b not in picked]
            picked.extend(rest[: n - len(picked)])
        return picked[:n]

    @classmethod
    def _build_recommend_reply(cls, books: List[Dict[str, Any]]) -> str:
        pool = [b for b in books if b.get('inventory_status') == '在馆'] or books
        picked = cls._spread_pick(pool, 3)
        if not picked:
            return "书架上暂时还没有书，等老师放几本进来吧！"
        lines = "\n".join(f"📘《{b['title']}》—— {cls._loc(b)}" for b in picked)
        return (
            f"我给你挑了 {len(picked)} 本，点封面我还能告诉你更多哦：\n{lines}\n"
            f"看中哪本就点小手指告诉我，我带你去看！"
        )

    @classmethod
    def _build_topic_reply(cls, picked: List[Dict[str, Any]]) -> str:
        if not picked:
            return "这个主题我暂时没找到合适的书，要不要换个词问问看？"
        shown = picked[:5]
        lines = "\n".join(f"📘《{b['title']}》—— {cls._loc(b)}" for b in shown)
        more = f"\n还有 {len(picked) - len(shown)} 本同类书，说书名我继续帮你找！" \
            if len(picked) > len(shown) else ""
        return (
            f"找到啦！{len(picked)} 本相关的绘本：\n{lines}{more}\n"
            f"先拿哪一本？走过去的时候小心台阶哦～"
        )

    @classmethod
    def _build_age_reply(cls, book: Dict[str, Any]) -> str:
        return (
            f"《{book['title']}》是{book.get('category_type', '绘本')}，"
            f"适合 3~6 岁的小朋友看～\n"
            f"它放在 {cls._loc(book)}，想看的话喊我一声！"
        )

    @classmethod
    def _build_author_reply(cls, book: Dict[str, Any]) -> str:
        author = book.get('author') or "经典名家"
        return (
            f"《{book['title']}》是{author}的哦～\n"
            f"它属于{book.get('category_type', '绘本')}{book.get('cartoon_badge', '')}，"
            f"放在 {cls._loc(book)}。"
        )

    @staticmethod
    def _build_bye_reply() -> str:
        return (
            "拜拜啦～👋\n"
            "看完书记得把它送回原来的老位置哦，这样下次才能马上找到！\n"
            "想我了就回来找我玩呀，皮皮一直在图书角等你～"
        )

    @classmethod
    def _build_need_title_reply(cls, books: List[Dict[str, Any]]) -> str:
        """没点名书却问细节 —— 反问书名，顺手给 3 个真实书名当例子"""
        sample = "、".join(f"《{b['title']}》" for b in books[:3])
        return (
            f"你想问的是哪一本书呀？把书名告诉我就行～\n"
            f"比如 {sample} 这样直接说，我马上告诉你它在哪一层、几岁适合看！"
        )

    # ---------- "找的书不存在" 的诚实回复 ----------

    #: 抽取主题词时要剥掉的客套话/口语噪声
    _SEARCH_STOP = (
        "有没有关于", "有没有", "有木有", "哪里有", "哪里", "想看看", "想看关于",
        "想看", "想找", "找一找", "找找", "看一下", "看看", "看书", "读书", "讲",
        "的绘本", "的图书", "的故事", "的书", "绘本", "图书", "故事", "书",
        "帮我", "给我", "可以", "能", "我要", "我想", "推荐", "一本",
        "一些", "什么", "哪些", "请问", "吗", "呢", "呀", "啊", "的", "了", "请",
    )

    @classmethod
    def _looks_like_book_search(cls, q: str) -> bool:
        """是不是一句明确的"找书"请求（而非闲聊）"""
        return any(k in q for k in ("有没有", "想看", "想找", "找一找", "找找",
                                    "看一下", "有没有关于", "哪里有", "有哪"))

    @classmethod
    def _extract_topic_word(cls, q: str) -> str:
        """从"有没有关于恐龙的书"里剥出"恐龙"；剥不干净返回空"""
        import re
        s = q
        for w in cls._SEARCH_STOP:
            s = s.replace(w, "")
        s = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", s)
        return s if 2 <= len(s) <= 8 else ""

    @classmethod
    def _build_no_such_topic_reply(cls, q: str, books: List[Dict[str, Any]]) -> str:
        """
        图书角没有这个主题的书。绝不说"好像有一本"——实物书架上找不到就是找不到，
        让幼儿照着找会白跑一趟。改为诚实说明 + 从真实书里给同类别替代。
        """
        in_stock = [b for b in books if b.get('inventory_status') == '在馆'] or books
        topic = cls._extract_topic_word(q)

        if topic:
            # 按类别找最接近的：科普类/故事类优先
            pool = [b for b in in_stock if b.get('category_type') == '科普类'] or in_stock
            lines = "\n".join(f"📘《{b['title']}》—— {cls._loc(b)}"
                              for b in cls._spread_pick(pool, 3))
            return (
                f"图书角暂时还没有讲「{topic}」的书哦，这里是真实书架，我就不乱说啦～😅\n"
                f"不过这几本也许你会喜欢：\n{lines}\n"
                f"想看别的类型就跟我说，比如「海洋」「勇敢」「动物」！"
            )

        lines = "\n".join(f"📘《{b['title']}》—— {cls._loc(b)}"
                          for b in cls._spread_pick(in_stock, 3))
        return (
            f"你可以说得再具体一点点嘛，比如「想看海洋的」「想看勇敢的故事」～\n"
            f"先看看这几本：\n{lines}"
        )

    @staticmethod
    def _build_book_reply(book: Dict[str, Any]) -> str:
        """基于数据库事实生成绘本定位的确定性回答（毫秒级返回）"""
        color_word = {
            1: "白色阶梯的最顶层",
            2: "蓝色圆点的那一层",
            3: "黄色圆点的那一层",
            4: "绿色圆点的那一层",
        }.get(book.get("shelf_tier", 1), "彩色圆点的那一层")
        return (
            f"宝贝找到啦！《{book['title']}》就摆放在【第 {book['shelf_tier']} 层 · {color_word}】，"
            f"格位是 {book.get('shelf_slot', 'L1-01')} 哦！\n"
            f"轻轻拿、轻轻翻，看完记得送它回家呀！"
        )

    @staticmethod
    def _build_duty_reply(today_duty: Dict[str, Any]) -> str:
        """基于数据库事实生成值日播报（毫秒级返回，无需大模型）"""
        if not today_duty:
            return "今天还没有安排值日小卫士哦，等老师来安排吧！"
        status_text = (
            "已经完成整理打卡啦，太棒了！🎉"
            if today_duty.get("completed")
            else "完成整理后记得打卡领取小卫士勋章哦！"
        )
        return (
            f"叮咚！今天的图书值日小卫士是【{today_duty.get('student_names')}】！\n"
            f"今日口诀：{today_duty.get('duty_task')}。{status_text}"
        )

    def auto_catalog(self, book_title: str) -> Dict[str, Any]:
        """为单本绘本自动生成标准化 4 层档案与三大卡通图标"""
        from modules.excel_importer import determine_category_and_badge, determine_shelf_location
        clean_title = book_title.strip()
        category_type, cartoon_badge, zone_name = determine_category_and_badge(clean_title)
        shelf_tier, shelf_slot, shelf_color = determine_shelf_location(clean_title, 1)

        # 尝试调用大模型获得精美简介
        draft = self.llm_client.auto_catalog(clean_title)
        return {
            "title": clean_title,
            "author": draft.get("author", "名家绘本"),
            "category_type": category_type,
            "cartoon_badge": cartoon_badge,
            "zone_name": zone_name,
            "shelf_tier": shelf_tier,
            "shelf_slot": shelf_slot,
            "shelf_color_label": shelf_color,
            "summary": draft.get("summary", f"适合幼儿阅读的经典{category_type}《{clean_title}》，培养良好习惯与探索精神。")
        }

    def _extract_highlight_tier(self, text: str) -> int:
        if "第 1 层" in text or "第1层" in text or "第 1 排" in text or "第1排" in text or "顶层" in text:
            return 1
        elif "第 2 层" in text or "第2层" in text or "第 2 排" in text or "第2排" in text or "蓝点" in text or "蓝色" in text:
            return 2
        elif "第 3 层" in text or "第3层" in text or "第 3 排" in text or "第3排" in text or "黄点" in text or "黄色" in text:
            return 3
        elif "第 4 层" in text or "第4层" in text or "第 4 排" in text or "第4排" in text or "绿点" in text or "绿色" in text:
            return 4
        return 0
