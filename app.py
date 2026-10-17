"""
幼儿园智慧图书角 AI 智能体系统 (V3.0 鲜亮品质版)
1. 视觉系统：干净白底 + 鲜亮童趣配色（珊瑚红/明黄/天蓝/草绿/粉紫），大圆角、软阴影、大触控目标
2. 零门槛交互：50 本真实封面原图画廊（单触即查）+ 实物 1:1 四层阶梯展示书架（实时架位）
3. 交互灵动岛：常驻小精灵呼吸头像 + 大触控语音录音 + edge-tts 云端高品质亲和播报
4. 教师控制台：
   - 📋 班级电子图书台账与智能盘点中心（在馆/破损/遗失状态核对 + 一键导出 Excel）
   - 📖 图书档案采编与智能排架（单本录入 + 唯一资产条目 + 三大卡通徽章绑定）
   - 👥 幼儿花名册与自主管理排班（自动循环排班 + 今日值日荣誉打卡）
   - 📊 阅读大数据透视与资源动态调配（Top 8 热力图 + 主题环形图 + AI 调仓报告）
   - ⚙️ AI 模型驱动与云平台语音配置（Gemini / DeepSeek 双模型切换 + 接口测试）
"""
import base64
import datetime
import html
import os
import re
import time
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from streamlit_mic_recorder import mic_recorder

from config.settings import (
    DEFAULT_TEACHER_PIN,
    GEMINI_API_KEY,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    BAILIAN_API_KEY,
    BAILIAN_BASE_URL,
    BAILIAN_MODEL,
    DAILY_BUDGET_TOKENS,
    DAILY_BUDGET_TTS_CHARS,
    get_secret,
)
from modules.db_manager import DatabaseManager
from modules.ui_components import (
    inject_kindergarten_css,
    inject_chat_css,
    render_brand_header,
    render_mascot_island,
    render_book_card,
    render_chat_history,
    render_duty_card,
    render_rhyme_card,
    render_metric_card,
    render_physical_4tier_bookshelf,
    get_book_cover_palette,
)
from modules.charts import render_popular_books_chart, render_theme_donut_chart
from modules.voice_engine import VoiceEngine, detect_audio_format
from modules.speech_dispatcher import get_dispatcher
from modules.analytics_engine import AnalyticsEngine
from modules.llm_client import UnifiedLLMClient
from agent.book_assistant import KindergartenBookAgent
from modules.quota_guard import get_quota_guard

# ========================================================
# 页面基础设置
# ========================================================
st.set_page_config(
    page_title="幼儿园 · 智慧图书角",
    page_icon="🦄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 注入鲜亮设计系统 CSS
inject_kindergarten_css()


# ========================================================
# 配置与会话状态初始化
# ========================================================
def _secret(key: str, default: str = "") -> str:
    """Streamlit Secrets 优先，回退到本地 settings（环境变量 / secrets.toml）"""
    try:
        value = st.secrets.get(key, None)
        if value:
            return str(value)
    except Exception:
        pass
    return get_secret(key, default)


if "llm_provider" not in st.session_state:
    st.session_state.llm_provider = "bailian"
if "cfg_gemini_key" not in st.session_state:
    st.session_state.cfg_gemini_key = _secret("GEMINI_API_KEY", GEMINI_API_KEY)
if "cfg_deepseek_key" not in st.session_state:
    st.session_state.cfg_deepseek_key = _secret("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)
if "cfg_deepseek_url" not in st.session_state:
    st.session_state.cfg_deepseek_url = _secret("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
if "cfg_deepseek_model" not in st.session_state:
    st.session_state.cfg_deepseek_model = _secret("DEEPSEEK_MODEL", DEEPSEEK_MODEL)
if "cfg_bailian_key" not in st.session_state:
    st.session_state.cfg_bailian_key = _secret("BAILIAN_API_KEY", BAILIAN_API_KEY)
if "cfg_bailian_url" not in st.session_state:
    st.session_state.cfg_bailian_url = _secret("BAILIAN_BASE_URL", BAILIAN_BASE_URL)
if "cfg_bailian_model" not in st.session_state:
    st.session_state.cfg_bailian_model = _secret("BAILIAN_MODEL", BAILIAN_MODEL)
if "cfg_teacher_pin" not in st.session_state:
    st.session_state.cfg_teacher_pin = _secret("TEACHER_PIN", DEFAULT_TEACHER_PIN)

# 初始化核心引擎（数据库单例 + 语音/分析/智能体三引擎）
if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()


def build_or_refresh_engines():
    """按当前配置构建/热重载三大引擎"""
    st.session_state.voice_engine = VoiceEngine(
        api_key=st.session_state.cfg_gemini_key,
        tts_api_key=st.session_state.cfg_bailian_key,
    )
    st.session_state.analytics_engine = AnalyticsEngine(
        provider=st.session_state.llm_provider,
        gemini_api_key=st.session_state.cfg_gemini_key,
        deepseek_api_key=st.session_state.cfg_deepseek_key,
        deepseek_base_url=st.session_state.cfg_deepseek_url,
        deepseek_model=st.session_state.cfg_deepseek_model,
        bailian_api_key=st.session_state.cfg_bailian_key,
        bailian_base_url=st.session_state.cfg_bailian_url,
        bailian_model=st.session_state.cfg_bailian_model
    )
    st.session_state.agent = KindergartenBookAgent(
        provider=st.session_state.llm_provider,
        gemini_api_key=st.session_state.cfg_gemini_key,
        deepseek_api_key=st.session_state.cfg_deepseek_key,
        deepseek_base_url=st.session_state.cfg_deepseek_url,
        deepseek_model=st.session_state.cfg_deepseek_model,
        bailian_api_key=st.session_state.cfg_bailian_key,
        bailian_base_url=st.session_state.cfg_bailian_url,
        bailian_model=st.session_state.cfg_bailian_model
    )


# 保证三大引擎始终存在（兼容旧会话状态缺字段的情况）
if not all(k in st.session_state for k in ("agent", "voice_engine", "analytics_engine")):
    build_or_refresh_engines()

db: DatabaseManager = st.session_state.db
voice_engine: VoiceEngine = st.session_state.voice_engine
analytics_engine: AnalyticsEngine = st.session_state.analytics_engine
agent: KindergartenBookAgent = st.session_state.agent

# 初始化交互与视图状态
if "is_teacher" not in st.session_state:
    st.session_state.is_teacher = False
if "active_child_tab" not in st.session_state:
    st.session_state.active_child_tab = "find"
if "highlight_row" not in st.session_state:
    st.session_state.highlight_row = 0
if "voice_message" not in st.session_state:
    st.session_state.voice_message = "嗨！宝贝，想看哪本绘本？直接用小手指点一点下方封面，或者按红色按钮对我说话哦！"
if "cloud_audio_bytes" not in st.session_state:
    st.session_state.cloud_audio_bytes = None
if "audio_play_id" not in st.session_state:
    st.session_state.audio_play_id = 0
# 异步语音：tts_seq 为最近一次投递的请求序号，tts_state 记录其阶段
if "tts_seq" not in st.session_state:
    st.session_state.tts_seq = 0
if "tts_state" not in st.session_state:
    st.session_state.tts_state = "idle"
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "child_filter_badge" not in st.session_state:
    st.session_state.child_filter_badge = "全部"
if "child_filter_tier" not in st.session_state:
    st.session_state.child_filter_tier = 0
if "child_search_kw" not in st.session_state:
    st.session_state.child_search_kw = ""
if "catalog_draft" not in st.session_state:
    st.session_state.catalog_draft = None
if "editing_book_id" not in st.session_state:
    st.session_state.editing_book_id = None

# AI 在线状态：当前 provider 配置了有效 Key 才算在线，否则使用本地规则引擎
_ai_online = bool(
    (st.session_state.llm_provider == "gemini" and st.session_state.cfg_gemini_key.strip())
    or (st.session_state.llm_provider == "deepseek" and st.session_state.cfg_deepseek_key.strip())
    or (st.session_state.llm_provider == "bailian" and st.session_state.cfg_bailian_key.strip())
)


def speak_out(message: str):
    """
    统一语音播报：**异步**投递 TTS 合成，绝不阻塞页面。

    实测百炼 Qwen3-TTS 合成一段回复要 4.35 秒；原来这里同步调用，导致每轮对话
    都要先卡 4 秒多才刷新。现在改为投递后台线程后立即返回：
      · 文字气泡立刻显示（首屏 ~0.2s）
      · fragment 每秒轮询取音频，就绪后自动播放
    连续说话时旧任务会被自动作废（见 speech_dispatcher 的请求序号守卫）。
    """
    if not message:
        st.session_state.tts_state = "idle"
        return
    seq = get_dispatcher().enqueue(
        message,
        synth=voice_engine.synthesize_cloud_speech,
        fmt_detect=detect_audio_format,
    )
    st.session_state.tts_seq = seq
    st.session_state.tts_state = "pending"
    st.session_state.tts_started_at = time.time()
    st.session_state.voice_message = message
    # 兼容旧字段：真实音频由 fragment 就绪后写入
    st.session_state.cloud_audio_bytes = None
    st.session_state.audio_play_id = st.session_state.get("audio_play_id", 0) + 1


def push_chat(user_text: str, agent_res: Dict[str, Any]) -> None:
    """把一轮问答写入对话历史，并异步触发语音播报"""
    st.session_state.chat_messages.append({"role": "user", "content": user_text})
    st.session_state.chat_messages.append({"role": "assistant", "content": agent_res.get("reply", "")})
    st.session_state.highlight_row = agent_res.get("highlight_row", 0)
    speak_out(agent_res.get("reply", ""))


def ask_agent(user_text: str) -> Dict[str, Any]:
    """统一的对话入口：带历史上下文调用 Agent"""
    text = (user_text or "").strip()
    if not text:
        return {"reply": "", "highlight_row": 0, "provider": st.session_state.llm_provider}
    # 只传最近若干轮给模型，控制 token 与延迟
    history = st.session_state.chat_messages[-6:]
    return agent.chat(text, history=history)


def clear_chat() -> None:
    """清空对话历史（小朋友随时可以重新开始）"""
    st.session_state.chat_messages = []
    st.session_state.cloud_audio_bytes = None
    st.session_state.voice_message = ""
    # 丢弃当前音频并作废在途的合成请求，避免清空后旧声音又冒出来
    st.session_state.tts_seq = 0
    st.session_state.tts_state = "idle"


def flash(message: str, kind: str = "success"):
    """暂存操作回执，使其能跨越 st.rerun() 存活（否则成功提示会被重跑吞掉）"""
    st.session_state["flash_msg"] = (kind, message)


def render_flash():
    """在视图顶部渲染并消费暂存的回执消息"""
    pending = st.session_state.pop("flash_msg", None)
    if pending:
        kind, message = pending
        getattr(st, kind)(message)


# ========================================================
# 🔐 教师认证通道弹窗（防误触儿童安全锁）
# ========================================================
@st.dialog("👩‍🏫 教师身份认证通道")
def teacher_auth_dialog():
    st.markdown("#### 🔒 请输入教师管理安全码")
    st.caption("为防止幼儿日常误触后台，进入中台需验证教师身份。")

    entered_pin = st.text_input("安全 PIN 码", type="password", max_chars=10, key="pin_input", placeholder="输入密码...")

    col_confirm, col_cancel = st.columns([1, 1])
    with col_confirm:
        if st.button("✅ 验证进入", width="stretch", type="primary"):
            if entered_pin == st.session_state.cfg_teacher_pin:
                st.session_state.is_teacher = True
                st.session_state.highlight_row = 0
                st.session_state.voice_message = ""
                st.session_state.cloud_audio_bytes = None
                st.session_state.tts_seq = 0
                st.session_state.tts_state = "idle"
                st.rerun()
            else:
                st.error("PIN 码错误，请重新输入！")
    with col_cancel:
        if st.button("❌ 取消返回", width="stretch"):
            st.rerun()


# ========================================================
# 🧒 界面形态 1：儿童乐园交互端（V3.0 真实画廊设计）
# ========================================================
def _on_child_submit() -> None:
    """
    表单提交回调：在**任何渲染之前**完成问答，因此本次 run 就能渲染出新气泡。

    为什么不用 `if submitted: ...; st.rerun()`：
    st.rerun() 会把 fragment 的刷新机制一并冲掉 —— 实测点一次发送后音频再也
    补不上。改成回调后不再需要整页 rerun：文字即时出现（~0.2s），
    音频由 fragment 在后台合成完毕后自行挂上。

    回调里只改 session_state，不做任何 st.* 渲染调用。
    """
    text = (st.session_state.get("child_typed_input") or "").strip()
    if not text:
        return
    st.session_state.child_typed_input = ""
    push_chat(text, ask_agent(text))


def render_audio_area() -> None:
    """
    语音区。

    实测结论（2026-10-14，本页）：
    · TTS 合成 4.1~4.4 秒，**绝不能同步等** —— 文字 0.2 秒就该出现；
    · `st.fragment(run_every=...)` 在本页**定时器不推进**（禁用麦克风 iframe 后
      仍然如此，排除 iframe 因素），所以不能指望它自动把音频挂上来；
    · 因此采用"机会式挂载 + 显式按钮"：
        - 每次页面渲染时检查后台合成结果，已就绪就直接渲染播放器；
        - 未就绪时显示占位，并给一个「听一听」按钮 —— 点它会触发 rerun，
          那时音频通常已经合成好，立刻就能播。
      孩子看完字若没点按钮，下一次任意交互（点封面/切导航/再问一句）
      也会自动带上播放器，不会错过。
    """
    seq = st.session_state.get("tts_seq", 0)
    if not seq:
        return
    status, data = get_dispatcher().poll(seq)

    if status == "ready":
        audio, fmt = data
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;'
            'background:linear-gradient(135deg,#ECFDF5,#D1FAE5);'
            'border:2.5px solid #10B981;border-radius:18px;padding:8px 16px;margin:6px 0 2px 0;">'
            '<span style="font-size:1.3rem;">🔊</span>'
            '<span style="font-size:1rem;color:#065F46;font-weight:700;">'
            '小精灵用云端童声为你播报'
            '</span></div>',
            unsafe_allow_html=True,
        )
        st.audio(audio, format=fmt or "audio/wav", autoplay=True)
        st.caption("没听到声音？点一下上面的播放键 ▶️")
        return

    if status == "failed":
        reason = data if isinstance(data, str) else ""
        if "取代" not in reason:
            st.warning("☁️ 云端语音暂时不可用，可以稍后再试，或者找老师帮忙哦。")
        return

    waited = time.time() - st.session_state.get("tts_started_at", time.time())
    tip = "马上就好～" if waited < 3 else "点「听一听」就能听到啦"
    c_wait, c_btn = st.columns([3, 1])
    with c_wait:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;'
            'background:linear-gradient(135deg,#FFF7ED,#FFEDD5);'
            'border:2.5px solid #FB923C;border-radius:18px;padding:10px 16px;margin:8px 0;">'
            '<span style="font-size:1.3rem;">⏳</span>'
            f'<span style="font-size:1rem;color:#9A3412;font-weight:700;">'
            f'皮皮在准备声音，{tip}</span></div>',
            unsafe_allow_html=True,
        )
    with c_btn:
        if st.button("🔊 听一听", key=f"tts_retry_{seq}", width="stretch"):
            st.rerun()


def render_child_view():
    # 顶部品牌条与隐形教师通道
    render_flash()
    render_brand_header()

    col_dummy, col_teacher_btn = st.columns([8.5, 1.5])
    with col_teacher_btn:
        if st.button("🔒 教师通道", help="点击打开教师管理后台", width="stretch"):
            teacher_auth_dialog()

    # 1. 🗣️ 语音对话区（对话气泡 + 文字输入框 + 麦克风 + 清空）
    inject_chat_css()
    with st.container(border=True):
        st.markdown(
            '<div class="kid-chat-title">🦄 和图书小精灵皮皮聊天</div>',
            unsafe_allow_html=True,
        )
        render_chat_history(st.session_state.chat_messages)
        with st.form("kid_chat_form", clear_on_submit=True):
            typed = st.text_input(
                "在这里打字问皮皮…",
                key="child_typed_input",
                placeholder="想看什么书？直接打出来～",
                label_visibility="collapsed",
            )
            c_send, c_hint = st.columns([1, 3])
            with c_send:
                st.form_submit_button("📤 发送", type="primary", width="stretch",
                                      on_click=_on_child_submit)
            with c_hint:
                st.markdown(
                    "<div style='font-size:.85rem;color:#8A5A2B;padding-top:10px;'>"
                    "也可以按住下面的红色麦克风直接说话哦～</div>",
                    unsafe_allow_html=True,
                )

    # 2. 云端语音播报（百炼 Qwen3-TTS，Cherry 音色）
    render_audio_area()

    # 麦克风语音输入 + 清空按钮（与对话框同一数据流）
    with st.container(border=True):
        st.markdown(
            '<div class="kid-mic-title">🎙️ 也可以直接对着小精灵说话</div>',
            unsafe_allow_html=True,
        )
        c_mic_box, c_clear_box = st.columns([1.5, 1.0])
        with c_mic_box:
            audio_record = mic_recorder(
                start_prompt="🔴 按下说话",
                stop_prompt="⏹️ 讲完啦",
                just_once=True,
                use_container_width=True,
                key="child_mic_v3"
            )

        with c_clear_box:
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            if st.button("🧹 重新聊聊", key="clear_chat_btn", width="stretch",
                         help="清空对话，从头开始"):
                clear_chat()
                st.rerun()

    # ---------------- 功能导航（我要找书 / 今天谁值日 / 我喜欢这本书） ----------------
    with st.container(border=True):
        st.markdown(
            '<div class="kid-nav-title">🧭 想做什么呢？点一个</div>',
            unsafe_allow_html=True,
        )
        nav1, nav2, nav3 = st.columns([1.2, 1.2, 1.2])
        with nav1:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            btn_type = "primary" if st.session_state.active_child_tab == "find" else "secondary"
            if st.button("📚 我要找书", key="nav_find_v3", type=btn_type, width="stretch"):
                st.session_state.active_child_tab = "find"
                st.rerun()

        with nav2:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            btn_type = "primary" if st.session_state.active_child_tab == "duty" else "secondary"
            if st.button("🌟 今天谁值日", key="nav_duty_v3", type=btn_type, width="stretch"):
                st.session_state.active_child_tab = "duty"
                st.rerun()

        with nav3:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            btn_type = "primary" if st.session_state.active_child_tab == "like" else "secondary"
            if st.button("❤️ 我喜欢这本书", key="nav_like_v3", type=btn_type, width="stretch"):
                st.session_state.active_child_tab = "like"
                st.rerun()

    # 语音转写（浏览器录音为 webm，voice_engine 内部自动转码送ASR）
    if audio_record and audio_record.get('bytes'):
        with st.spinner("小精灵正在认真听你说的话..."):
            transcribed_text = voice_engine.transcribe_child_audio(audio_record['bytes'])
            if transcribed_text:
                st.toast(f"小精灵听到你说：‘{transcribed_text}’", icon="👂")
                push_chat(transcribed_text, ask_agent(transcribed_text))
                st.rerun()
            else:
                st.warning("没听太清哦，可以再靠近麦克风大声说一遍！")

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # ---------------- 场景 1：我要找书（50 本真实封面画廊 + 四层阶梯书架） ----------------
    if st.session_state.active_child_tab == "find":
        st.markdown("### 🖼️ **点一点绘本封面，小精灵告诉你它在哪一层！**")
        st.caption("无需识字打字，看中哪一本，小手直接按一下就可以哦：")

        # 快捷分类筛选与搜索
        col_fil_badge, col_fil_tier, col_search = st.columns([1.8, 1.8, 1.4])
        with col_fil_badge:
            badge_choices = ["全部", "👑 故事类", "🔍 科普类", "❤️ 绘本类"]
            selected_badge = st.segmented_control("🏷️ 按卡通标签筛选：", badge_choices, default="全部", key="sc_badge")
            st.session_state.child_filter_badge = selected_badge or "全部"
        with col_fil_tier:
            tier_choices = {0: "全部层", 1: "⚪ 第1层", 2: "🔵 第2层", 3: "🟡 第3层", 4: "🟢 第4层"}
            selected_tier_label = st.segmented_control("🪵 按书架层位筛选：", list(tier_choices.values()), default="全部层", key="sc_tier")
            selected_tier = next((k for k, v in tier_choices.items() if v == selected_tier_label), 0)
            st.session_state.child_filter_tier = selected_tier
        with col_search:
            c_kw_in, c_kw_btn = st.columns([3.2, 1])
            with c_kw_in:
                kw = st.text_input("🔍 搜书名：", placeholder="输入书名或词语...", key="ti_kw")
            with c_kw_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("🔍 搜索", key="btn_kw_search", width="stretch"):
                    st.session_state.child_search_kw = (kw or "").strip()
            st.session_state.child_search_kw = (kw or "").strip()

        # 数据检索与过滤
        all_books = db.get_all_books(status='在馆')
        filtered_books = []
        for b in all_books:
            # 标签过滤
            if st.session_state.child_filter_badge != "全部":
                if "故事" in st.session_state.child_filter_badge and "故事" not in b.get("category_type", "") and "👑" not in b.get("cartoon_badge", ""):
                    continue
                if "科普" in st.session_state.child_filter_badge and "科普" not in b.get("category_type", "") and "🔍" not in b.get("cartoon_badge", ""):
                    continue
                if "绘本" in st.session_state.child_filter_badge and "绘本" not in b.get("category_type", "") and "❤️" not in b.get("cartoon_badge", ""):
                    continue
            # 层位过滤
            if st.session_state.child_filter_tier > 0 and b.get("shelf_tier") != st.session_state.child_filter_tier:
                continue
            # 关键词过滤
            if st.session_state.child_search_kw and st.session_state.child_search_kw not in b.get("title", "") and st.session_state.child_search_kw not in b.get("summary", ""):
                continue
            filtered_books.append(b)

        st.caption(f"共找到 **{len(filtered_books)}** 本绘本：")

        # 4 列绘本画廊（桌面 4 列，手机 CSS 折叠为 2 列）
        cols = st.columns(4)
        for i, book in enumerate(filtered_books):
            with cols[i % 4]:
                clicked = render_book_card(
                    book,
                    action_label="🎯 查架位",
                    action_key=f"find_book_{book['id']}"
                )
                if clicked:
                    st.session_state.highlight_row = book["shelf_tier"]
                    q = f"我想看《{book['title']}》，请问它在第几层呀？"
                    push_chat(q, ask_agent(q))
                    st.rerun()

        if not filtered_books:
            st.info("没有找到匹配的绘本，换个条件试试吧！")

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

        # 1:1 实物四层阶梯展示书架（展示真实在架书目）
        render_physical_4tier_bookshelf(highlight_tier=st.session_state.highlight_row, books=all_books)

    # ---------------- 场景 2：今天谁值日（荣誉绶带与勋章打卡） ----------------
    elif st.session_state.active_child_tab == "duty":
        today_duty = db.get_today_duty()

        render_duty_card(today_duty)

        c_d1, c_d2 = st.columns([2, 1])
        with c_d1:
            if today_duty.get("completed"):
                st.success("🎉 太赞了！今天的值日整理任务已经打卡完成！大家都是爱护图书的优秀好宝宝！")
            elif not today_duty.get("is_today", True):
                st.info("🌸 今天是周末，图书角也休息哦～周五的值日小管家辛苦啦，下周见！")
            else:
                st.info("💡 值日生小朋友整理完散乱的书架后，点击右侧金牌打卡领取【今日护书小卫士】勋章吧！")
        with c_d2:
            if not today_duty.get("completed") and today_duty.get("is_today", True):
                if st.button("✨ 我整理好啦！\n(打卡领勋章)", type="primary", width="stretch"):
                    ok = db.mark_duty_completed(today_duty.get("duty_date"))
                    if ok:
                        st.balloons()
                        _msg = f"哇！太能干了！恭喜【{today_duty['student_names']}】获得今天的值日小英雄勋章！"
                        st.session_state.chat_messages.append({"role": "assistant", "content": _msg})
                        speak_out(_msg)
                        st.rerun()
                    else:
                        st.warning("今天还没有排班记录，打卡失败，请联系老师先排班～")
            elif today_duty.get("completed"):
                st.button("🏆 荣誉勋章已佩戴", disabled=True, width="stretch")

        render_rhyme_card()

    # ---------------- 场景 3：我喜欢这本书（红心点赞榜） ----------------
    elif st.session_state.active_child_tab == "like":
        st.markdown("### ❤️ **为你最心爱的绘本送上小红心！**")
        st.caption("每次按下红心，小精灵都会为你记录，老师也能知道哪些绘本是大家最喜欢的哦！")

        all_books = db.get_all_books(status='在馆')
        cols = st.columns(4)
        for i, book in enumerate(all_books):
            with cols[i % 4]:
                clicked = render_book_card(
                    book,
                    action_label="💖 送红心",
                    action_key=f"like_btn_{book['id']}",
                    show_like_count=True
                )
                if clicked:
                    db.increment_book_interaction(book['title'], action_type='like', student_name="小读者")
                    st.toast(f"你给《{book['title']}》点亮了一颗小红心！", icon="💖")
                    _like_msg = f"谢谢你喜欢《{book['title']}》，小精灵已经帮你记录下来啦！"
                    st.session_state.chat_messages.append({"role": "assistant", "content": _like_msg})
                    speak_out(_like_msg)
                    st.rerun()



# ========================================================
# 👩‍🏫 界面形态 2：教师智慧管理中台
# ========================================================
_STATUS_PILLS = {
    "在馆": ("#D1FAE5", "#065F46", "#34D399"),
    "破损": ("#FEF3C7", "#92400E", "#F59E0B"),
    "遗失": ("#FEE2E2", "#991B1B", "#EF4444"),
    "借出": ("#DBEAFE", "#1E40AF", "#3B82F6"),   # 蓝色借出徽章
}


def _render_books_html_table(books, show_status: bool = True):
    """渲染鲜亮风格的图书台账 HTML 表格（替代默认灰色 dataframe）"""
    rows_html = ""
    for idx, b in enumerate(books):
        status = b.get("inventory_status", "在馆")
        pill_bg, pill_fg, pill_bd = _STATUS_PILLS.get(status, ("#F1F5F9", "#334155", "#CBD5E1"))
        status_cell = (
            f'<span style="background:{pill_bg}; color:{pill_fg}; border:1.5px solid {pill_bd}; '
            f'padding:2px 10px; border-radius:999px; font-weight:800; font-size:0.78rem; white-space:nowrap;">{html.escape(status)}</span>'
        ) if show_status else ""

        # 层位：彩色圆形数字徽章
        tier = b.get("shelf_tier", 1)
        tier_bg = {1: "#64748B", 2: "#2563EB", 3: "#D97706", 4: "#059669"}.get(tier, "#334155")
        tier_cell = (
            f'<span style="background:{tier_bg};color:#fff;border-radius:50%;'
            f'width:26px;height:26px;display:inline-flex;align-items:center;'
            f'justify-content:center;font-weight:900;font-size:0.9rem;">{tier}</span>'
        )

        # 格位：去掉 L 前缀（L2-05 → 2-05）
        slot_raw = str(b.get("shelf_slot", ""))
        slot_short = slot_raw.lstrip("L") if slot_raw.startswith("L") else slot_raw

        # 借阅人（借出时显示）
        borrowed_by = b.get("borrowed_by", "")
        borrow_date = b.get("borrow_date", "")
        borrower_cell = (
            f'<span style="font-size:0.78rem;color:#1E40AF;font-weight:700;white-space:nowrap;">'
            f'📌 {html.escape(borrowed_by)}<br>'
            f'<span style="font-size:0.72rem;color:#6B7280;">{html.escape(borrow_date)}</span></span>'
        ) if borrowed_by else '<span style="color:#CBD5E1;font-size:0.75rem;">—</span>'

        zebra = "background:#F8FAFD;" if idx % 2 == 1 else ""
        td = "padding:8px 10px;"
        asset_code = html.escape(str(b.get("asset_code", "")))
        # 注意：插值进 markdown 的 HTML 片段必须零缩进，否则会被解析器转义为代码块
        rows_html += (
            f'<tr style="border-bottom:1px solid #EEF2F8; {zebra}">'
            # 序号徽章，悬停显示完整资产编码
            f'<td style="{td} text-align:center; white-space:nowrap;" title="{asset_code}">'
            f'<span style="background:#F1F5F9;color:#5C6B84;border-radius:6px;'
            f'padding:2px 7px;font-weight:800;font-size:0.82rem;">#{idx+1}</span></td>'
            f'<td style="{td} font-weight:800; color:#22314A; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">《{html.escape(b.get("title", ""))}》</td>'
            f'<td style="{td} color:#5C6B84; white-space:nowrap;">{html.escape(b.get("category_type", ""))}</td>'
            f'<td style="{td} white-space:nowrap;">{html.escape(b.get("cartoon_badge", ""))}</td>'
            f'<td style="{td} color:#5C6B84; white-space:nowrap; font-size:0.82rem;">{html.escape(b.get("zone_name", ""))}</td>'
            f'<td style="{td} text-align:center; white-space:nowrap;">{tier_cell}</td>'
            f'<td style="{td} color:#5C6B84; white-space:nowrap; font-size:0.82rem;">{html.escape(slot_short)}</td>'
            f'<td style="{td} text-align:center;">{status_cell}</td>'
            f'<td style="{td} text-align:center;">{borrower_cell}</td>'
            f'<td style="{td} color:#8494AC; font-size:0.78rem; max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="{html.escape(str(b.get("inventory_notes", "")))}">{html.escape(str(b.get("inventory_notes", "")))}</td>'
            f'<td style="{td} text-align:center; font-weight:800; color:#E14E4E;">{b.get("read_count", 0)}</td>'
            f'<td style="{td} text-align:center; font-weight:800; color:#DB2777;">{b.get("like_count", 0)}</td>'
            f'</tr>'
        )

    th = "padding:10px 10px; color:#B4713A; font-weight:900; font-size:0.78rem;"
    st.markdown(f"""
<div style="background:#FFFFFF; border:1.5px solid #E9EEF6; border-radius:18px; overflow:hidden; box-shadow:0 5px 14px rgba(34,49,74,0.05);">
<div style="overflow-x:auto;">
<table style="width:100%; border-collapse:collapse; font-size:0.86rem;">
<thead>
<tr style="background:linear-gradient(135deg, #FFF3EC, #FFE9DF); border-bottom:2px solid #FFD4C2;">
<th style="{th} text-align:center; white-space:nowrap;" title="悬停可查看完整资产编码">序#</th>
<th style="{th} text-align:left;">绘本书名</th>
<th style="{th} text-align:left;">大类</th>
<th style="{th} text-align:left;">标签</th>
<th style="{th} text-align:left;">分区</th>
<th style="{th} text-align:center;">层</th>
<th style="{th} text-align:left;">格位</th>
<th style="{th} text-align:center;">状态</th>
<th style="{th} text-align:center;">借阅人</th>
<th style="{th} text-align:left;">备注</th>
<th style="{th} text-align:center;">借阅</th>
<th style="{th} text-align:center;">❤️</th>
</tr>
</thead>
<tbody>{rows_html}</tbody>
</table>
</div>
</div>
""", unsafe_allow_html=True)


def render_teacher_view():
    # 顶部专业 Header
    render_flash()
    t_col_info, t_col_exit = st.columns([8, 2])
    with t_col_info:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 6px; flex-wrap: wrap;">
            <h2 style="margin: 0; color: #22314A; font-weight: 900; letter-spacing: -0.3px;">👩‍🏫 智慧图书角 · 教师综合管理中台</h2>
            <span style="background: linear-gradient(135deg, #E0F2FE, #DBEAFE); color: #1D4ED8; font-size: 0.78rem; font-weight: 800; padding: 5px 13px; border-radius: 999px; border: 1.5px solid #BFDBFE;">
                当前AI思考中枢: {html.escape(st.session_state.llm_provider.upper())}{' · 在线' if _ai_online else ' · 本地模式'}
            </span>
        </div>
        """, unsafe_allow_html=True)
        st.caption("班级电子图书台账 · 智能盘点导出 · 档案采编排架 · 幼儿自主管理 · 阅读大数据透视")
    with t_col_exit:
        if st.button("🚪 退出管理并回锁儿童端", type="primary", width="stretch"):
            st.session_state.is_teacher = False
            st.session_state.highlight_row = 0
            st.session_state.voice_message = "欢迎回到图书小精灵乐园！"
            st.session_state.cloud_audio_bytes = None
            st.session_state.tts_seq = 0
            st.session_state.tts_state = "idle"
            st.rerun()

    st.markdown("---")

    tab_inventory, tab_catalog, tab_duty, tab_analytics, tab_settings = st.tabs([
        "📋 1. 班级电子图书台账与盘点中心",
        "📖 2. 图书档案采编与智能录入",
        "📅 3. 幼儿花名册与值日排班",
        "📊 4. 阅读偏好分析与调仓建议",
        "⚙️ 5. AI 模型驱动与云平台语音配置"
    ])

    # ------------------ Tab 1: 班级电子图书台账与盘点中心 ------------------
    with tab_inventory:
        st.markdown('<div class="section-title">📋 班级电子图书台账与资产盘点登记中心</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">自动生成唯一档案条目与卡通标签，支持快速核对在馆、破损、遗失状态，一键导出完整盘点清单。</div>', unsafe_allow_html=True)

        # 5 个核心盘点指标卡
        inv_stats = db.get_inventory_statistics()
        c_i1, c_i2, c_i3, c_i4, c_i5 = st.columns(5)
        with c_i1:
            render_metric_card("在册藏书总数", str(inv_stats['total_books']), "本", accent="#22314A", icon="📚")
        with c_i2:
            render_metric_card("在馆正常流通", str(inv_stats['in_library_count']), "本", accent="#16A34A", icon="🟢")
        with c_i3:
            render_metric_card("破损待修补", str(inv_stats['damaged_count']), "本", accent="#D97706", icon="🛠️")
        with c_i4:
            render_metric_card("确认遗失", str(inv_stats['lost_count']), "本", accent="#DC2626", icon="❓")
        with c_i5:
            render_metric_card("藏书完好率", f"{inv_stats['integrity_rate']}", "%", accent="#2563EB", icon="🛡️")

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        # 一键导出 Excel 按钮与提示（内存生成，不落盘）
        c_exp_btn, c_exp_info = st.columns([1.6, 3])
        with c_exp_btn:
            st.download_button(
                label="📥 一键导出班级图书资产盘点台账 (.xlsx)",
                data=db.build_inventory_excel_bytes(),
                file_name=f"班级图书资产盘点台账_{datetime.date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width="stretch"
            )
        with c_exp_info:
            st.info("💡 **一键盘点导出**：自动汇总当前班级全部绘本的唯一资产编码、卡通图标标签、层位编号、在馆/破损/遗失状态，完美替代教师手工登记盘点。")

        st.markdown("---")

        # 快速盘点状态修改工具箱
        with st.expander("🔍 快速调整单本图书盘点状态 (在馆 / 破损 / 遗失 / 补充备注)", expanded=False):
            all_books_list = db.get_all_books()
            c_sel_bk, c_sel_st, c_notes, c_upd_btn = st.columns([2.5, 1.5, 2, 1.2])
            with c_sel_bk:
                book_options = {b['id']: f"{b['asset_code']} - 《{b['title']}》 ({b['inventory_status']})" for b in all_books_list}
                chosen_bk_id = st.selectbox("选择绘本条目：", options=list(book_options.keys()), format_func=lambda x: book_options[x])
            with c_sel_st:
                chosen_st = st.selectbox("更新盘点状态：", ["在馆", "破损", "遗失"])
            with c_notes:
                chosen_note = st.text_input("备注说明：", placeholder="如：封皮开线待修补 / 借出遗失")
            with c_upd_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("💾 确认更新", type="primary", width="stretch"):
                    db.update_book_inventory_status(chosen_bk_id, chosen_st, chosen_note)
                    flash("图书盘点状态已成功更新并动态刷新台账！")
                    st.rerun()

        # 图书台账表格展示与多维筛选
        st.markdown("#### 📑 班级电子图书台账明细列表")

        c_flt_t, c_flt_s, c_flt_c = st.columns([1, 1, 1])
        with c_flt_t:
            flt_tier = st.selectbox("筛选书架层位：", [0, 1, 2, 3, 4], format_func=lambda x: "全部层位" if x == 0 else f"第 {x} 层")
        with c_flt_s:
            flt_status = st.selectbox("筛选盘点状态：", ["全部状态", "在馆", "破损", "遗失"])
        with c_flt_c:
            flt_cat = st.selectbox("筛选大类标签：", ["全部分类", "👑 故事类", "🔍 科普类", "❤️ 绘本类"])

        # 查询对应数据
        tier_arg = flt_tier if flt_tier > 0 else None
        status_arg = flt_status if flt_status != "全部状态" else None
        books_data = db.get_all_books(tier=tier_arg, status=status_arg)

        if flt_cat != "全部分类":
            if "故事" in flt_cat:
                books_data = [b for b in books_data if "故事" in b.get("category_type", "") or "👑" in b.get("cartoon_badge", "")]
            elif "科普" in flt_cat:
                books_data = [b for b in books_data if "科普" in b.get("category_type", "") or "🔍" in b.get("cartoon_badge", "")]
            elif "绘本" in flt_cat:
                books_data = [b for b in books_data if "绘本" in b.get("category_type", "") or "❤️" in b.get("cartoon_badge", "")]

        if books_data:
            _render_books_html_table(books_data)
        else:
            st.warning("暂无匹配的图书台账记录。")

        st.markdown("---")
        st.markdown("#### 📤📥 借书 & 还书管理")

        # ── 借书登记 ──────────────────────────────────────────────────────
        with st.expander("📤 借书登记（将图书借给老师 / 家长）", expanded=False):
            available_books = db.get_all_books(status='在馆')
            if not available_books:
                st.info("当前没有在馆图书可供借出。")
            else:
                avail_map = {
                    b['id']: f"{b['asset_code']} 《{b['title']}》"
                    for b in available_books
                }
                bc1, bc2, bc3, bc4 = st.columns([2.5, 1.8, 1.8, 1.2])
                with bc1:
                    borrow_book_id = st.selectbox(
                        "选择要借出的图书：",
                        options=list(avail_map.keys()),
                        format_func=lambda x: avail_map[x],
                        key="borrow_sel"
                    )
                with bc2:
                    borrower_name = st.text_input(
                        "借阅人姓名：",
                        placeholder="如：李老师 / 张小明家长",
                        key="borrower_name"
                    )
                with bc3:
                    exp_ret = st.date_input(
                        "预计归还日期：",
                        key="exp_ret_date",
                        value=datetime.date.today() + datetime.timedelta(days=7)
                    )
                with bc4:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("📤 确认借出", type="primary", width="stretch", key="do_borrow_btn"):
                        if not borrower_name.strip():
                            st.error("请填写借阅人姓名！")
                        elif borrow_book_id:
                            ok = db.borrow_book(
                                borrow_book_id,
                                borrower_name.strip(),
                                expected_return=str(exp_ret)
                            )
                            if ok:
                                flash(f"借书成功！已登记 {borrower_name.strip()} 借阅，预计 {exp_ret} 归还。")
                                st.rerun()
                            else:
                                st.error("借书失败，该书可能已被借出或不存在！")

        # ── 还书登记 ──────────────────────────────────────────────────────
        with st.expander("📥 还书登记（确认图书归还入库）", expanded=False):
            borrowed_books = db.get_borrowed_books()
            if not borrowed_books:
                st.info("📭 当前没有借出中的图书，无需还书登记。")
            else:
                ret_map = {
                    b['id']: (
                        f"《{b['title']}》"
                        f" → 借阅人：{b.get('borrowed_by', '?')}"
                        f"（借出：{b.get('borrow_date', '?')}）"
                    )
                    for b in borrowed_books
                }
                rc1, rc2, rc3 = st.columns([3, 2, 1.2])
                with rc1:
                    return_book_id = st.selectbox(
                        "选择归还的图书：",
                        options=list(ret_map.keys()),
                        format_func=lambda x: ret_map[x],
                        key="return_sel"
                    )
                with rc2:
                    return_notes = st.text_input(
                        "归还备注（书况等）：",
                        placeholder="如：品相完好 / 封皮稍有磨损",
                        key="return_notes"
                    )
                with rc3:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("📥 确认还书", type="primary", width="stretch", key="do_return_btn"):
                        ok = db.return_book(return_book_id, notes=return_notes)
                        if ok:
                            flash("还书成功！图书已恢复在馆状态。")
                            st.rerun()
                        else:
                            st.error("还书失败，请确认该书是否处于借出状态！")

        # ── 借还流水 ──────────────────────────────────────────────────────
        with st.expander("📋 借还流水记录（最近 50 条）", expanded=False):
            history = db.get_borrow_history(50)
            if history:
                df_hist = pd.DataFrame(history)
                show_cols = ["book_title", "borrower_name", "borrow_date",
                             "expected_return", "actual_return", "notes"]
                df_hist = df_hist[[c for c in show_cols if c in df_hist.columns]]
                df_hist.columns = [
                    {"book_title": "书名", "borrower_name": "借阅人",
                     "borrow_date": "借出日期", "expected_return": "预计归还",
                     "actual_return": "实际归还", "notes": "备注"}.get(c, c)
                    for c in df_hist.columns
                ]
                if "实际归还" in df_hist.columns:
                    df_hist["实际归还"] = df_hist["实际归还"].fillna("📌 未归还")
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("暂无借还记录。")

    # ------------------ Tab 2: 图书档案采编与智能录入 ------------------
    with tab_catalog:
        st.markdown('<div class="section-title">📖 图书档案录入与采编模块</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">支持教师单本录入绘本信息：书名、主题类别、封面图片、所属分区、书架层位编号，自动绑定卡通标签。</div>', unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("#### ✨ AI 智能辅助打标（输入书名自动生成标准化档案推荐）")
            c_input, c_ai_btn = st.columns([3, 1])
            with c_input:
                ai_book_input = st.text_input("输入绘本书名", placeholder="例如：我有友情要出租 / 小熊不刷牙 / 猜猜我有多爱你", key="ai_book_input_key")
            with c_ai_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("🤖 AI 智能解析建档", type="secondary", width="stretch"):
                    if ai_book_input.strip():
                        with st.spinner(f"正在调用 {st.session_state.llm_provider.upper()} 深度推理绘本档案并推荐层位..."):
                            draft = agent.auto_catalog(ai_book_input.strip())
                            st.session_state.catalog_draft = draft
                            st.success("智能解析完成！已生成下方【绘本身份证预览卡】。")
                    else:
                        st.warning("请输入书名！")

            draft = st.session_state.catalog_draft or {}

            # 若生成了草稿，展示【绘本身份证预览卡】
            if draft:
                st.markdown(f"""
                <div class="book-id-card">
                    <div class="id-badge-stamp">AI 智能认证</div>
                    <h3 style="margin-top: 0; color: #1E293B;">🪪 《{html.escape(draft.get('title', ''))}》标准化电子档案卡</h3>
                    <div style="display: flex; gap: 22px; margin: 12px 0; flex-wrap: wrap; font-size: 0.95rem; color: #334155;">
                        <div><b>作者:</b> {html.escape(draft.get('author', '名家绘本'))}</div>
                        <div><b>主题类别:</b> {html.escape(draft.get('category_type', '绘本类'))}</div>
                        <div><b>卡通标签:</b> {html.escape(draft.get('cartoon_badge', '❤️ 绘本'))}</div>
                        <div><b>所属分区:</b> {html.escape(draft.get('zone_name', '品格习惯区'))}</div>
                        <div><b>推荐架位:</b> 第 {draft.get('shelf_tier', 1)} 层 ({html.escape(str(draft.get('shelf_slot', 'L1-01')))})</div>
                    </div>
                    <p style="color: #475569; font-size: 0.95rem; margin: 8px 0;"><b>故事核心导读:</b> {html.escape(draft.get('summary', ''))}</p>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # 单本详细录入表单
            st.markdown("#### 📝 单本图书档案录入表单")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                new_title = st.text_input("绘本书名 *", value=draft.get("title", ""), placeholder="例如：大卫，不可以")
                new_author = st.text_input("作者", value=draft.get("author", "名家绘本"), placeholder="例如：大卫·香农")

                cat_options = ["故事类", "科普类", "绘本类"]
                cat_idx = cat_options.index(draft.get("category_type")) if draft.get("category_type") in cat_options else 2
                new_category = st.selectbox("主题类别 *", cat_options, index=cat_idx)

                badge_map = {
                    "故事类": "👑 故事",
                    "科普类": "🔍 科普",
                    "绘本类": "❤️ 绘本"
                }
                new_badge = badge_map[new_category]
                st.info(f"关联卡通图标标签：**{new_badge}** (自动绑定故事‑皇冠、科普‑放大镜、绘本‑爱心)")

                zone_options = ["品格习惯区", "自然科学区", "社会情感区", "传统文化区", "创意益智区"]
                zone_idx = zone_options.index(draft.get("zone_name")) if draft.get("zone_name") in zone_options else 0
                new_zone = st.selectbox("所属分区 *", zone_options, index=zone_idx)

            with col_t2:
                tier_val = draft.get("shelf_tier", 1)
                tier_idx = [1, 2, 3, 4].index(tier_val) if tier_val in [1, 2, 3, 4] else 0
                new_tier = st.selectbox("书架层位编号 (1-4层) *", [1, 2, 3, 4], index=tier_idx, format_func=lambda x: f"第 {x} 层")

                color_labels = {
                    1: "⚪ 第 1 层 · 顶层平视区",
                    2: "🔵 第 2 层 · 蓝色圆点区",
                    3: "🟡 第 3 层 · 黄色圆点区",
                    4: "🟢 第 4 层 · 绿色圆点区"
                }
                new_color_label = color_labels[new_tier]
                st.info(f"书架标识：**{new_color_label}**")

                new_slot = st.text_input("书架格位编号 *", value=draft.get("shelf_slot", f"L{new_tier}-01"), placeholder="例如：L1-01 / L2-05")
                new_cover_path = st.text_input("封面图片路径 (或留空使用预置)", value=draft.get("cover_image_path", ""), placeholder="例如：static/book_covers/book_cover_01.png")

            new_summary = st.text_area("故事导读 / 核心教育价值", value=draft.get("summary", ""), placeholder="简要描述绘本故事情节与教育引导价值...")

            if st.button("💾 确认并保存图书档案至云端台账", type="primary", width="stretch"):
                if not new_title.strip():
                    st.error("书名不能为空！")
                else:
                    success = db.add_or_update_book(
                        title=new_title,
                        author=new_author,
                        category_type=new_category,
                        cartoon_badge=new_badge,
                        zone_name=new_zone,
                        shelf_tier=new_tier,
                        shelf_slot=new_slot,
                        shelf_color_label=new_color_label,
                        cover_image_path=new_cover_path,
                        summary=new_summary or f"精彩经典的{new_category}绘本。"
                    )
                    if success:
                        st.session_state.catalog_draft = None
                        flash(f"《{new_title}》电子档案录入成功！唯一条目与卡通标签已动态更新至台账。")
                        st.rerun()
                    else:
                        st.error("保存失败，请检查控制台日志（可能是资产编码冲突或数据库写入异常）。")

        st.markdown("---")

        # ===== 图书档案管理（全字段修改 / 二次确认删除） =====
        st.markdown("#### 🛠️ 图书档案管理（修改 / 删除）")
        st.caption("选中图书后可「加载并修改」全部档案字段；删除需勾选确认框且不可恢复，儿童端书架会同步移除。")

        all_books_mgmt = db.get_all_books()
        if all_books_mgmt:
            book_label_map = {
                b["id"]: f"{b['asset_code']} - 《{b['title']}》 ({b['inventory_status']})"
                for b in all_books_mgmt
            }
            c_mg_sel, c_mg_edit = st.columns([3, 1])
            with c_mg_sel:
                mgmt_book_id = st.selectbox(
                    "选择要管理的绘本条目：",
                    options=list(book_label_map.keys()),
                    format_func=lambda x: book_label_map[x],
                    key="mgmt_book_select"
                )
            with c_mg_edit:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("✏️ 加载并修改这本", type="secondary", width="stretch", key="mgmt_load_edit_btn"):
                    st.session_state.editing_book_id = mgmt_book_id
                    st.session_state.catalog_draft = None
                    st.rerun()

            # ---- 编辑表单（加载后内联展开，回显该图书全部字段） ----
            if st.session_state.get("editing_book_id"):
                edit_book = db.get_book_by_id(st.session_state.editing_book_id)
                if edit_book:
                    st.markdown("---")
                    st.markdown(f"##### ✏️ 正在修改档案：《{edit_book['title']}》（资产编码 {edit_book['asset_code']}）")
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        e_title = st.text_input("绘本书名 *", value=edit_book["title"], key="edit_title")
                        e_author = st.text_input("作者", value=edit_book.get("author", ""), key="edit_author")
                        e_cat_options = ["故事类", "科普类", "绘本类"]
                        e_cat_idx = e_cat_options.index(edit_book["category_type"]) if edit_book["category_type"] in e_cat_options else 2
                        e_category = st.selectbox("主题类别 *", e_cat_options, index=e_cat_idx, key="edit_category")
                        e_badge_map = {"故事类": "👑 故事", "科普类": "🔍 科普", "绘本类": "❤️ 绘本"}
                        e_badge = e_badge_map[e_category]
                        st.info(f"关联卡通图标标签：**{e_badge}**")
                        e_zone_options = ["品格习惯区", "自然科学区", "社会情感区", "传统文化区", "创意益智区"]
                        e_zone_idx = e_zone_options.index(edit_book["zone_name"]) if edit_book["zone_name"] in e_zone_options else 0
                        e_zone = st.selectbox("所属分区 *", e_zone_options, index=e_zone_idx, key="edit_zone")
                    with ec2:
                        e_tier_options = [1, 2, 3, 4]
                        e_tier_idx = e_tier_options.index(edit_book["shelf_tier"]) if edit_book["shelf_tier"] in e_tier_options else 0
                        e_tier = st.selectbox("书架层位编号 (1-4层) *", e_tier_options, index=e_tier_idx,
                                              format_func=lambda x: f"第 {x} 层", key="edit_tier")
                        e_color_labels = {
                            1: "⚪ 第 1 层 · 顶层平视区",
                            2: "🔵 第 2 层 · 蓝色圆点区",
                            3: "🟡 第 3 层 · 黄色圆点区",
                            4: "🟢 第 4 层 · 绿色圆点区"
                        }
                        e_color_label = e_color_labels[e_tier]
                        st.info(f"书架标识：**{e_color_label}**")
                        e_slot = st.text_input("书架格位编号 *", value=edit_book.get("shelf_slot", ""), key="edit_slot")
                        e_cover = st.text_input("封面图片路径（留空保留原封面）",
                                                value=edit_book.get("cover_image_path", ""), key="edit_cover")
                        e_status_options = ["在馆", "破损", "遗失"]
                        e_status_idx = e_status_options.index(edit_book["inventory_status"]) if edit_book["inventory_status"] in e_status_options else 0
                        e_status = st.selectbox("盘点状态", e_status_options, index=e_status_idx, key="edit_status")
                        e_notes = st.text_input("盘点备注", value=edit_book.get("inventory_notes", ""), key="edit_notes")
                    e_summary = st.text_area("故事导读 / 核心教育价值", value=edit_book.get("summary", ""), key="edit_summary")

                    c_e_save, c_e_cancel = st.columns([1, 1])
                    with c_e_save:
                        if st.button("💾 保存修改", type="primary", width="stretch", key="edit_save_btn"):
                            if not e_title.strip():
                                st.error("书名不能为空！")
                            else:
                                ok = db.update_book(
                                    st.session_state.editing_book_id,
                                    title=e_title,
                                    author=e_author,
                                    category_type=e_category,
                                    cartoon_badge=e_badge,
                                    zone_name=e_zone,
                                    shelf_tier=e_tier,
                                    shelf_slot=e_slot,
                                    shelf_color_label=e_color_label,
                                    cover_image_path=e_cover,
                                    summary=e_summary or f"精彩经典的{e_category}绘本。",
                                    inventory_status=e_status,
                                    inventory_notes=e_notes,
                                )
                                if ok:
                                    flash(f"《{e_title}》档案修改已保存！台账与儿童端书架同步生效。")
                                    st.session_state.editing_book_id = None
                                    st.rerun()
                                else:
                                    st.error("保存失败：可能已存在同名图书，或数据库写入异常，请检查控制台日志。")
                    with c_e_cancel:
                        if st.button("✖️ 取消编辑", width="stretch", key="edit_cancel_btn"):
                            st.session_state.editing_book_id = None
                            st.rerun()
                else:
                    # 目标已被删除等场景，安静退出编辑态
                    st.session_state.editing_book_id = None

            # ---- 删除（勾选二次确认） ----
            st.markdown("---")
            st.markdown("##### 🗑️ 注销删除绘本档案")
            del_target = db.get_book_by_id(mgmt_book_id)
            if del_target:
                st.warning(
                    f"即将删除：《{del_target['title']}》（{del_target['asset_code']}）— "
                    "删除后该档案将永久从台账与儿童端书架移除，**不可恢复**！"
                )
                del_confirm = st.checkbox(
                    f"⚠️ 我已了解风险，确认删除《{del_target['title']}》",
                    key=f"mgmt_del_confirm_{mgmt_book_id}"
                )
                if st.button("🗑️ 确认删除", type="secondary", key="mgmt_del_btn"):
                    if not del_confirm:
                        st.warning("请先勾选确认框再执行删除！")
                    else:
                        ok = db.delete_book(mgmt_book_id)
                        if ok:
                            if st.session_state.get("editing_book_id") == mgmt_book_id:
                                st.session_state.editing_book_id = None
                            flash(f"《{del_target['title']}》档案已注销删除，图书角已同步移除。", kind="warning")
                            st.rerun()
                        else:
                            st.error("删除失败：该图书可能已被删除，请刷新页面后重试。")
        else:
            st.info("当前台账为空，暂无图书档案可管理。")

    # ------------------ Tab 3: 幼儿名单与值日排班 ------------------
    with tab_duty:
        st.markdown('<div class="section-title">👥 幼儿自主管理 · 轮流值日排班中心</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">构建幼儿主人翁管理模式，实现班级幼儿有序轮流值日与荣誉成长激励。</div>', unsafe_allow_html=True)

        col_stu_left, col_stu_right = st.columns([1, 1])
        with col_stu_left:
            st.markdown("#### 📝 班级幼儿花名册")
            students = db.get_all_students()
            student_names = [s["name"] for s in students]
            st.write(f"当前在册幼儿共 **{len(students)}** 名：")
            # 徽章化展示幼儿名单，更直观
            if student_names:
                badges = " ".join(
                    f'<span style="display:inline-block; background:linear-gradient(135deg,#E0F2FE,#DBEAFE); color:#1D4ED8; font-weight:800; font-size:0.85rem; padding:5px 14px; border-radius:999px; margin:3px 4px 3px 0; border:1.5px solid #BFDBFE;">{html.escape(n)}</span>'
                    for n in student_names
                )
                st.markdown(f"<div style='margin:8px 0;'>{badges}</div>", unsafe_allow_html=True)
            else:
                st.info("当前花名册为空，请先添加幼儿。")

            # 单人快速添加
            st.markdown("##### ➕ 添加单个幼儿")
            c_add_name, c_add_btn = st.columns([3, 1])
            with c_add_name:
                add_student_name = st.text_input("新幼儿姓名", placeholder="例如：小美", key="add_student_name_input", label_visibility="collapsed")
            with c_add_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("➕ 添加入园", type="secondary", width="stretch", key="add_student_btn"):
                    if add_student_name.strip():
                        if db.add_student(add_student_name.strip()):
                            flash(f"幼儿「{add_student_name.strip()}」已加入花名册！如需参与排班，请刷新右侧排班表。")
                            st.rerun()
                        else:
                            st.error("添加失败，请检查控制台日志。")
                    else:
                        st.warning("请输入幼儿姓名！")

            # 批量导入（明确为增量添加，不会删除名单之外的人）
            st.markdown("##### 📥 批量导入幼儿名单（增量添加，不会移除名单之外的人）")
            names_text = st.text_area("输入幼儿姓名（支持用逗号、空格或换行分隔）", placeholder="乐乐, 阳阳, 欣欣, 朵朵, 浩浩...", key="batch_names_area")
            if st.button("更新幼儿名单并自动排班", type="primary", key="batch_update_btn"):
                if names_text.strip():
                    name_list = [n for n in re.split(r'[,，\s\n]+', names_text.strip()) if n]
                    db.set_students_batch(name_list)
                    db.generate_duty_schedule(days_ahead=30, students_per_day=2)
                    flash("幼儿名单已增量更新，并已重新自动循环排班！（重新排班会覆盖未来 30 天的手动调整）")
                    st.rerun()

            # 单人管理：改名 / 删除（含排班影响评估）
            with st.expander("🛠️ 幼儿管理（改名 / 删除）", expanded=False):
                if students:
                    stu_label_map = {s["id"]: s["name"] for s in students}
                    c_stu_sel, c_stu_rename = st.columns([1, 1])
                    with c_stu_sel:
                        mgmt_stu_id = st.selectbox(
                            "选择要管理的幼儿：",
                            options=list(stu_label_map.keys()),
                            format_func=lambda x: stu_label_map[x],
                            key="mgmt_student_select"
                        )
                    with c_stu_rename:
                        mgmt_new_name = st.text_input(
                            "输入新姓名（改名用）",
                            placeholder="保留原名则不修改",
                            key="mgmt_student_newname"
                        )
                    if st.button("💾 保存改名", type="secondary", key="rename_student_btn"):
                        if not mgmt_new_name.strip():
                            st.warning("请先输入新姓名！")
                        else:
                            ok = db.update_student(mgmt_stu_id, mgmt_new_name.strip())
                            if ok:
                                flash(f"幼儿已改名为「{mgmt_new_name.strip()}」，花名册与排班表同步生效！")
                                st.rerun()
                            else:
                                st.error("改名失败：可能已存在同名幼儿，请检查控制台日志。")

                    st.markdown("---")
                    # 删除：先评估排班影响，勾选确认后执行
                    impact = db.get_student_duty_impact(mgmt_stu_id)
                    if impact["exists"]:
                        warn_lines = [f"即将删除幼儿「**{impact['name']}**」，删除后不可恢复！"]
                        if impact["future_dates"]:
                            warn_lines.append(
                                f"该幼儿出现在 **{len(impact['future_dates'])}** 条今天起的排班中，将被同步移除"
                                f"（最早 {impact['future_dates'][0]}）。"
                            )
                        else:
                            warn_lines.append("该幼儿当前不在任何未来排班中。")
                        if impact["history_count"]:
                            warn_lines.append(f"另有 {impact['history_count']} 条历史打卡记录将原样保留。")
                        st.warning("\n\n".join(warn_lines))
                        stu_del_confirm = st.checkbox(
                            f"⚠️ 我已了解风险，确认删除「{impact['name']}」",
                            key=f"stu_del_confirm_{mgmt_stu_id}"
                        )
                        if st.button("🗑️ 确认删除幼儿", type="secondary", key="stu_del_btn"):
                            if not stu_del_confirm:
                                st.warning("请先勾选确认框再执行删除！")
                            else:
                                ok = db.delete_student(mgmt_stu_id)
                                if ok:
                                    flash(f"幼儿「{impact['name']}」已从花名册删除，未来排班已同步更新。", kind="warning")
                                    st.rerun()
                                else:
                                    st.error("删除失败：该幼儿可能已被删除，请刷新页面后重试。")
                else:
                    st.info("当前花名册为空，请先添加幼儿。")

        with col_stu_right:
            st.markdown("#### 📅 今日值日状态")
            today_duty = db.get_today_duty()
            st.info(f"**日期**：{today_duty['duty_date']}\n\n**今日值日生**：{today_duty['student_names']}\n\n**任务**：{today_duty['duty_task']}\n\n**打卡状态**：{'✅ 已完成整理' if today_duty.get('completed') else '⏳ 待打卡'}")

            # ===== 手动调整某一天的值日安排 =====
            st.markdown("##### 🛠️ 手动调整某一天的值日安排")
            if students:
                adj_date = st.date_input("选择要调整的日期", value=datetime.date.today(), key="duty_adjust_date")
                adj_date_str = adj_date.strftime("%Y-%m-%d")
                existing_row = db.get_duty_by_date(adj_date_str)
                if existing_row:
                    default_duty_names = [n for n in
                                          (p.strip() for p in existing_row["student_names"].split("、"))
                                          if n and n in student_names]
                    st.caption(
                        f"该日当前安排：**{existing_row['student_names']}**"
                        f"（打卡：{'✅ 已完成' if existing_row['completed'] else '⏳ 待打卡'}），保存后将覆盖并重置打卡。"
                    )
                else:
                    default_duty_names = []
                    st.caption("该日暂无排班，保存后将新增这一天的值日安排。")
                adj_names = st.multiselect(
                    "选择这一天值日的幼儿：",
                    options=student_names,
                    default=default_duty_names,
                    key="duty_adjust_names"
                )
                if st.button("💾 保存这一天的值日安排", type="primary", key="duty_adjust_save"):
                    if not adj_names:
                        st.warning("请至少选择一名值日幼儿！（如需取消该日安排，请使用下方「删除该日排班」）")
                    else:
                        ok = db.upsert_duty(adj_date_str, adj_names)
                        if ok:
                            flash(f"{adj_date_str} 的值日安排已更新为：{'、'.join(adj_names)}")
                            st.rerun()
                        else:
                            st.error("保存失败，请检查控制台日志。")
            else:
                st.info("请先在左侧添加幼儿，才能安排值日。")

            # ===== 批量重新生成（天数 / 每日人数可配） =====
            st.markdown("##### 🔁 批量重新生成排班")
            c_gen_days, c_gen_per = st.columns([1, 1])
            with c_gen_days:
                gen_days = st.number_input("生成未来天数", min_value=7, max_value=90, value=30, step=1, key="duty_gen_days")
            with c_gen_per:
                gen_per_label = st.selectbox("每日值日人数", ["1 人", "2 人", "3 人"], index=1, key="duty_gen_per")
                gen_per = int(gen_per_label[0])
            if st.button("🔄 立即重新生成轮流排班表", type="secondary", key="duty_regen_btn"):
                if not students:
                    st.warning("花名册为空，无法排班，请先添加幼儿！")
                else:
                    db.generate_duty_schedule(days_ahead=int(gen_days), students_per_day=gen_per)
                    flash(f"未来 {int(gen_days)} 天工作日排班表已按每日 {gen_per} 人重新生成！（将覆盖该范围内已有安排）")
                    st.rerun()

            # ===== 未来排班一览 + 单日删除 =====
            st.markdown("##### 📅 未来 30 天排班一览")
            schedule_rows = db.get_duty_schedule(days_ahead=30)
            if schedule_rows:
                weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                duty_rows_html = ""
                for idx, row in enumerate(schedule_rows):
                    d = datetime.date.fromisoformat(row["duty_date"])
                    date_cell = (
                        f'<b style="color:#22314A;">{row["duty_date"]}</b>'
                        f' <span style="color:#8494AC; font-size:0.8rem;">{weekday_cn[d.weekday()]}</span>'
                    )
                    if row["duty_date"] == today_str:
                        date_cell += (
                            ' <span style="background:#FEE2E2; color:#991B1B; font-weight:800; font-size:0.72rem;'
                            ' padding:1px 8px; border-radius:999px; border:1px solid #FECACA; margin-left:4px;">今天</span>'
                        )
                    done_cell = ('<span style="color:#16A34A; font-weight:800;">✅ 已完成</span>' if row["completed"]
                                 else '<span style="color:#D97706; font-weight:800;">⏳ 待打卡</span>')
                    zebra = "background:#F8FAFD;" if idx % 2 == 1 else ""
                    duty_rows_html += (
                        f'<tr style="border-bottom:1px solid #EEF2F8; {zebra}">'
                        f'<td style="padding:8px 12px; white-space:nowrap;">{date_cell}</td>'
                        f'<td style="padding:8px 12px; font-weight:700; color:#22314A;">{html.escape(row["student_names"])}</td>'
                        f'<td style="padding:8px 12px; text-align:center;">{done_cell}</td>'
                        f'</tr>'
                    )
                th = "padding:10px 12px; color:#1D4ED8; font-weight:900; font-size:0.8rem;"
                st.markdown(f"""
<div style="background:#FFFFFF; border:1.5px solid #E9EEF6; border-radius:18px; overflow:hidden; box-shadow:0 5px 14px rgba(34,49,74,0.05);">
<div style="overflow-x:auto;">
<table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
<thead>
<tr style="background:linear-gradient(135deg, #EFF6FF, #DBEAFE); border-bottom:2px solid #BFDBFE;">
<th style="{th} text-align:left; white-space:nowrap;">日期</th>
<th style="{th} text-align:left;">值日生</th>
<th style="{th} text-align:center;">打卡状态</th>
</tr>
</thead>
<tbody>{duty_rows_html}</tbody>
</table>
</div>
</div>
""", unsafe_allow_html=True)

                # 单日删除（勾选二次确认）
                duty_date_map = {
                    row["duty_date"]: (
                        f"{row['duty_date']}（{weekday_cn[datetime.date.fromisoformat(row['duty_date']).weekday()]}）"
                        f"{row['student_names']}"
                    )
                    for row in schedule_rows
                }
                st.markdown("---")
                del_duty_date = st.selectbox(
                    "选择要删除的排班日期：",
                    options=list(duty_date_map.keys()),
                    format_func=lambda x: duty_date_map[x],
                    key="duty_del_select"
                )
                del_duty_confirm = st.checkbox(
                    f"⚠️ 我已了解：删除后 {del_duty_date} 的排班将永久移除，不可恢复",
                    key=f"duty_del_confirm_{del_duty_date}"
                )
                if st.button("🗑️ 删除该日排班", type="secondary", key="duty_del_btn"):
                    if not del_duty_confirm:
                        st.warning("请先勾选确认框再执行删除！")
                    else:
                        ok = db.delete_duty(del_duty_date)
                        if ok:
                            flash(f"{del_duty_date} 的排班已删除。", kind="warning")
                            st.rerun()
                        else:
                            st.error("删除失败：该日排班可能已被删除，请刷新页面后重试。")
            else:
                st.info("未来 30 天暂无排班记录，请使用上方「批量重新生成排班」生成。")

    # ------------------ Tab 4: 阅读偏好与动态调配看板 ------------------
    with tab_analytics:
        st.markdown('<div class="section-title">📊 幼儿阅读大数据透视与资源动态调配</div>', unsafe_allow_html=True)
        stats = db.get_reading_analytics()

        # 3 个现代化高阶指标卡
        col_m1, col_m2, col_m3 = st.columns(3)
        total_books = len(db.get_all_books())
        total_students = len(db.get_all_students())
        total_reads = sum(b.get("read_count", 0) for b in db.get_all_books())

        with col_m1:
            render_metric_card("在架绘本总量", str(total_books), "本", accent="#FF6B6B", icon="📚")
        with col_m2:
            render_metric_card("参与阅读幼儿", str(total_students), "人", accent="#2E9AFE", icon="🧒")
        with col_m3:
            render_metric_card("累计借阅打卡人次", str(total_reads), "次", accent="#22C55E", icon="🔥")

        st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

        # Plotly 现代鲜亮图表
        col_chart_left, col_chart_right = st.columns(2)

        with col_chart_left:
            st.markdown("#### 🏆 最受欢迎绘本 Top 8 (翻阅与点赞热力)")
            fig_bar = render_popular_books_chart(stats["popular_books"])
            if fig_bar:
                st.plotly_chart(fig_bar, width="stretch")
            else:
                st.info("暂无借阅数据")

        with col_chart_right:
            st.markdown("#### 🍩 幼儿阅读主题偏好环形分布")
            fig_pie = render_theme_donut_chart(stats["theme_stats"])
            if fig_pie:
                st.plotly_chart(fig_pie, width="stretch")
            else:
                st.info("暂无主题数据")

        st.markdown("---")

        # 冷门图书警示区
        st.markdown("#### ⚠️ 滞销/冷门绘本预警 (长期低频借阅)")
        if stats["dormant_books"]:
            td = "padding:8px 12px;"
            # 注意：插值进 markdown 的 HTML 片段必须零缩进，否则会被解析器转义为代码块
            dormant_rows = "".join(
                f'<tr style="border-bottom:1px solid #EEF2F8;">'
                f'<td style="{td} font-weight:800; color:#22314A;">《{html.escape(b["title"])}》</td>'
                f'<td style="{td} text-align:center; color:#5C6B84;">{b.get("read_count", 0)}</td>'
                f'<td style="{td} text-align:center; color:#5C6B84;">{b.get("like_count", 0)}</td>'
                f'<td style="{td} color:#5C6B84;">{html.escape(str(b.get("shelf_color_label", "")))}</td>'
                f'</tr>'
                for b in stats["dormant_books"]
            )
            th = "padding:10px 12px; color:#9A3412; font-weight:900; font-size:0.8rem;"
            st.markdown(f"""
<div style="background:#FFFFFF; border:1.5px solid #E9EEF6; border-radius:18px; overflow:hidden;">
<table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
<thead><tr style="background:linear-gradient(135deg,#FFF7ED,#FFEDD5); border-bottom:2px solid #FED7AA;">
<th style="{th} text-align:left;">冷门书名</th>
<th style="{th} text-align:center;">借阅次数</th>
<th style="{th} text-align:center;">红心数</th>
<th style="{th} text-align:left;">当前架位</th>
</tr></thead>
<tbody>{dormant_rows}</tbody>
</table>
</div>
""", unsafe_allow_html=True)
        else:
            st.info("暂无冷门绘本，全班阅读热情很高！")

        st.markdown("---")
        st.markdown("#### 💡 AI 教学决策指导与动态调仓报告")

        if st.button("🤖 深度生成最新《图书角动态调配建议书》", type="primary"):
            with st.spinner(f"正在调用 {st.session_state.llm_provider.upper()} 根据全班借阅行为生成专业教研建议..."):
                report = analytics_engine.generate_optimization_report(stats)
                st.session_state.analytics_report = report

        if "analytics_report" in st.session_state and st.session_state.analytics_report:
            st.markdown(st.session_state.analytics_report)
        else:
            st.info("💡 点击上方「🤖 深度生成最新《图书角动态调配建议书》」按钮，即可调用 AI 深度推理引擎分析全班借阅行为，并输出专业教研与调仓采购指导报告。")

    # ------------------ Tab 5: AI 模型与云平台语音配置 ------------------
    with tab_settings:
        st.markdown('<div class="section-title">⚙️ AI 模型驱动与云平台语音配置中心</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">支持在运行态即时修改大语言模型与云端语音引擎配置，支持一键连通性测试与热重载。</div>', unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("#### 1. 核心认知大语言模型 (LLM) 引擎选择")
            current_prov = st.session_state.llm_provider
            prov_options = ["bailian", "gemini", "deepseek"]
            prov_labels = {
                "bailian": "☁️ 阿里云百炼 Qwen (推荐 / 国内直连 / LLM+TTS 同平台 / 多模型自动切换)",
                "gemini": "Google Gemini (极速多模态 / 音频理解与智能建档)",
                "deepseek": "DeepSeek (国产顶尖大模型 / 赛事申报推荐)"
            }
            if current_prov not in prov_options:
                current_prov = "bailian"
            new_prov = st.radio(
                "选择当前系统使用的认知大模型：",
                options=prov_options,
                index=prov_options.index(current_prov),
                format_func=lambda x: prov_labels[x]
            )

            st.caption(
                "💡 百炼为推荐首选：LLM 与语音合成同平台同 Key、国内直连不用代理、"
                "Qwen3-TTS 中文自然度最高。已开通多个模型额度，某模型用尽时系统会自动切到下一个，无需手动干预。"
            )

            st.markdown("---")
            st.markdown("#### 2. 额度使用情况与安全保险")
            _guard = get_quota_guard()
            _snap_llm = _guard.snapshot("bailian_llm", "tokens", DAILY_BUDGET_TOKENS)
            _snap_tts = _guard.snapshot("bailian_tts", "chars", DAILY_BUDGET_TTS_CHARS)
            g1, g2, g3 = st.columns(3)
            with g1:
                st.metric(
                    "百炼 LLM 今日 Token",
                    f"{_snap_llm['used']:,} / {_snap_llm['limit']:,}",
                    delta="已熔断" if _snap_llm["tripped"] else "额度充足",
                    delta_color="inverse" if _snap_llm["tripped"] else "normal",
                )
            with g2:
                st.metric(
                    "百炼 TTS 今日字符",
                    f"{_snap_tts['used']:,} / {_snap_tts['limit']:,}",
                    delta="已熔断" if _snap_tts["tripped"] else "额度充足",
                    delta_color="inverse" if _snap_tts["tripped"] else "normal",
                )
            with g3:
                st.metric("剩余可用 TTS 字符", f"{_snap_tts['remaining']:,}")
            st.caption(
                "🛡️ 上限为本地安全阈值（远高于你的免费额度，仅作兜底保险）。"
                "即使触及，系统会自动降级到 edge-tts 永久免费通道，账单恒为 0。"
            )
            if _snap_llm["tripped"] or _snap_tts["tripped"]:
                st.warning(f"部分引擎已熔断：{_snap_llm['reason'] or _snap_tts['reason']}（自动降级到 edge-tts 永久免费通道）")
            if st.button("🔓 手动解熔断（调整额度后使用）", key="reset_trip"):
                _guard.reset()
                flash("已解除今日全部熔断标记，百炼引擎恢复可用。")
                st.rerun()

            st.markdown("---")
            st.markdown("#### 3. 云平台语音合成 (TTS) 发音试听")
            c_tts_test, c_tts_play = st.columns([2, 2])
            with c_tts_test:
                test_tts_text = st.text_input("测试播报语句：", value="亲爱的小朋友，两个小八路在第二层蓝色圆点处哦！")
                if st.button("🔊 生成并试听云端亲和语音", key="test_tts_btn"):
                    with st.spinner("正在请求百炼 Qwen3-TTS 合成（失败自动降级 edge-tts）..."):
                        t_bytes = voice_engine.synthesize_cloud_speech(test_tts_text)
                        if t_bytes:
                            st.session_state.test_audio_bytes = t_bytes
                            _fmt = detect_audio_format(t_bytes).replace("audio/", "").upper()
                            st.success(f"语音合成成功！格式 {_fmt}，音色 {getattr(voice_engine, 'active_voice', '-')}。")
                        else:
                            st.error("云端语音合成失败，请检查网络环境（浏览器 Web Speech 仍可兜底播报）。")
            with c_tts_play:
                if "test_audio_bytes" in st.session_state and st.session_state.test_audio_bytes:
                    st.markdown("**试听播放：**")
                    st.audio(st.session_state.test_audio_bytes, format=detect_audio_format(st.session_state.test_audio_bytes), autoplay=True)

            st.markdown("---")
            st.markdown("#### 4. 模型参数与 API Key 配置")

            c_g1, c_d1, c_a1 = st.columns(3)
            with c_g1:
                st.markdown("##### 🌐 Google Gemini 配置 (文本对话与多模态音频识别)")
                input_gemini_key = st.text_input("Gemini API Key", value=st.session_state.cfg_gemini_key, type="password")
                if st.button("🧪 测试 Gemini API 连通性", key="test_gemini"):
                    res = UnifiedLLMClient.test_provider_connection("gemini", input_gemini_key)
                    if res["success"]:
                        st.success(res["message"])
                    else:
                        st.error(res["message"])

            with c_d1:
                st.markdown("##### 🇨🇳 DeepSeek 配置 (国产大模型，竞赛申报专用)")
                input_ds_key = st.text_input("DeepSeek API Key", value=st.session_state.cfg_deepseek_key, type="password", placeholder="例如: sk-...")
                input_ds_url = st.text_input("DeepSeek Base URL", value=st.session_state.cfg_deepseek_url)
                input_ds_model = st.text_input("DeepSeek 模型名", value=st.session_state.cfg_deepseek_model)
                if st.button("🧪 测试 DeepSeek API 连通性", key="test_ds"):
                    res = UnifiedLLMClient.test_provider_connection("deepseek", input_ds_key, input_ds_url, input_ds_model)
                    if res["success"]:
                        st.success(res["message"])
                    else:
                        st.error(res["message"])

            with c_a1:
                st.markdown("##### ☁️ 阿里云百炼配置 (推荐 / LLM + TTS 共用同一 Key)")
                input_bl_key = st.text_input("百炼 API Key", value=st.session_state.cfg_bailian_key, type="password", placeholder="sk-...")
                input_bl_url = st.text_input("百炼 Base URL", value=st.session_state.cfg_bailian_url)
                input_bl_model = st.text_input("首选模型名", value=st.session_state.cfg_bailian_model)
                if st.button("🧪 测试百炼 API 连通性", key="test_bailian"):
                    res = UnifiedLLMClient.test_provider_connection(
                        "bailian", input_bl_key, input_bl_url, input_bl_model
                    )
                    if res["success"]:
                        st.success(res["message"])
                    else:
                        st.error(res["message"])
                st.caption("首选模型额度用尽时自动切换到回退链上的下一个模型。")

            st.markdown("---")
            st.markdown("#### 5. 安全与权限设置")
            input_pin = st.text_input("修改教师管理安全 PIN 码", value=st.session_state.cfg_teacher_pin, max_chars=10)

            st.markdown("---")
            if st.button("💾 保存所有配置并立即热重载引擎", type="primary", width="stretch"):
                st.session_state.llm_provider = new_prov
                st.session_state.cfg_gemini_key = input_gemini_key.strip()
                st.session_state.cfg_deepseek_key = input_ds_key.strip()
                st.session_state.cfg_deepseek_url = input_ds_url.strip()
                st.session_state.cfg_deepseek_model = input_ds_model.strip()
                st.session_state.cfg_bailian_key = input_bl_key.strip()
                st.session_state.cfg_bailian_url = input_bl_url.strip()
                st.session_state.cfg_bailian_model = input_bl_model.strip()
                st.session_state.cfg_teacher_pin = input_pin.strip()

                build_or_refresh_engines()
                flash("配置已成功更新并热重载！所有对话与语音引擎已切换为最新配置。")
                st.rerun()


# ========================================================
# 🚀 主路由控制器
# ========================================================
if st.session_state.is_teacher:
    render_teacher_view()
else:
    render_child_view()
