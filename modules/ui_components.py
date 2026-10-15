"""
现代化高品质 UI 视觉与幼教交互组件系统 (Modern Frontend Craft & Design System) - V3.0 鲜亮版
设计语言：干净白底 + 高明度童趣配色（珊瑚红 / 明黄 / 天蓝 / 草绿 / 粉紫），
大圆角、软阴影、大触控目标，兼顾「鲜明活泼」与「久看舒适」。
1. 1:1 还原幼儿园实物教具：4 层白色阶梯式展示书架（🔵蓝 / 🟡黄 / 🟢绿 侧边圆点色标）
2. 50 本真实封面原图画廊 + 三大专属卡通标签（故事-👑皇冠, 科普-🔍放大镜, 绘本-❤️爱心）
3. 灵动小精灵交互岛 + 教师中台资产卡片
"""
import html
from pathlib import Path
from typing import Dict, Any, List, Optional

import streamlit as st

from config.settings import BASE_DIR

# ============================================================
# 设计系统 · 设计令牌（Design Tokens）
# ==========================
# 主色 · 珊瑚红：品牌与主要行动点
C_PRIMARY = "#FF6B6B"
C_PRIMARY_DEEP = "#E14E4E"
# 辅助 · 明黄：值日荣誉 / 第三层
C_SUN = "#FFB020"
C_SUN_DEEP = "#E08C00"
# 辅助 · 天蓝：第二层 / 科普
C_SKY = "#2E9AFE"
C_SKY_DEEP = "#1B7FE0"
# 辅助 · 草绿：第四层 / 在馆状态
C_GRASS = "#22C55E"
C_GRASS_DEEP = "#159146"
# 辅助 · 粉紫：绘本 / 爱心
C_PINK = "#EC4899"
C_GRAPE = "#8B5CF6"
# 中性色
C_INK = "#22314A"        # 主文字（深蓝灰，比纯黑柔和）
C_INK_SOFT = "#5C6B84"   # 次要文字
C_LINE = "#E9EEF6"       # 描边
C_CARD = "#FFFFFF"       # 卡片


def inject_kindergarten_css():
    """注入现代高精视觉样式库（V3.0 鲜亮设计系统）"""
    st.markdown("""
    <style>
    /* ============ 全局基底 ============ */
    .stApp {
        background: linear-gradient(165deg, #FFF7EE 0%, #F2F7FF 52%, #FDF5FF 100%) !important;
        background-attachment: fixed !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif !important;
        color: #22314A;
    }
    /* 注意：不要用 `.stApp *` 全局覆盖字体——会连 Streamlit 图标字体
       (Material Symbols) 和代码块等宽字体一起覆盖，导致图标显示为原始文本 */
    .main .block-container {
        padding: 1.6rem 2.2rem 3rem !important;
        max-width: 1560px !important;
    }

    /* 隐藏 Streamlit 默认装饰，保持画面干净 */
    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent !important; }

    /* ============ 顶部品牌条 ============ */
    .brand-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: linear-gradient(120deg, #FFE9DC 0%, #FFF6E9 45%, #E6F4FF 100%);
        backdrop-filter: blur(18px);
        border: 3px solid #FF9A76;
        border-radius: 26px;
        padding: 15px 26px;
        box-shadow: 0 10px 32px rgba(255, 122, 89, 0.22), 0 2px 6px rgba(34, 49, 74, 0.06);
        margin-bottom: 20px;
    }
    .brand-title {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 1.6rem;
        font-weight: 800;
        color: #22314A;
        letter-spacing: -0.3px;
    }
    .brand-badge {
        background: linear-gradient(135deg, #FF8A65 0%, #FF6B6B 100%);
        color: #FFFFFF;
        font-size: 0.8rem;
        font-weight: 800;
        padding: 5px 13px;
        border-radius: 999px;
        box-shadow: 0 4px 10px rgba(255, 107, 107, 0.35);
        letter-spacing: 0.5px;
    }
    .brand-sub {
        font-size: 0.86rem;
        color: #5C6B84;
        font-weight: 700;
        letter-spacing: 1px;
    }

    /* ============ 灵动小精灵交互岛 ============ */
    .mascot-island {
        background: linear-gradient(145deg, #FFFFFF 0%, #FFF6EC 100%);
        border: 2px solid #FFE3C2;
        border-radius: 30px;
        padding: 20px 26px;
        box-shadow: 0 18px 40px rgba(255, 160, 90, 0.14);
        margin-bottom: 20px;
    }
    .mascot-content {
        display: flex;
        align-items: center;
        gap: 20px;
    }
    .mascot-avatar {
        width: 84px;
        height: 84px;
        background: linear-gradient(135deg, #FFD166 0%, #FF8A65 100%);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.9rem;
        box-shadow: 0 12px 24px rgba(255, 138, 101, 0.4), inset 0 -6px 12px rgba(255,255,255,0.35);
        animation: floatMascot 3.5s ease-in-out infinite;
        flex-shrink: 0;
        border: 3px solid #FFFFFF;
    }
    @keyframes floatMascot {
        0%, 100% { transform: translateY(0px) rotate(0deg); }
        50% { transform: translateY(-7px) rotate(4deg); }
    }
    .speech-balloon {
        background: #FFFFFF;
        border: 2px solid #FFE3C2;
        border-radius: 22px;
        padding: 15px 22px;
        box-shadow: 0 6px 16px rgba(255, 160, 90, 0.10);
        flex-grow: 1;
        position: relative;
    }
    .speech-meta {
        font-size: 0.78rem;
        font-weight: 800;
        color: #B4713A;
        margin-bottom: 5px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .ai-chip {
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.4px;
    }
    .ai-chip-on { background: linear-gradient(135deg, #E0F2FE, #DBEAFE); color: #1D4ED8; border: 1px solid #BFDBFE; }
    .ai-chip-off { background: #F1F5F9; color: #64748B; border: 1px solid #E2E8F0; }
    .speech-text {
        font-size: 1.22rem;
        font-weight: 700;
        color: #3D2E22;
        line-height: 1.55;
        margin: 0;
    }

    /* ============ 儿童端导航胶囊 ============ */
    .nav-pill-row { margin: 4px 0 14px 0; }
    .stButton > button {
        border-radius: 999px !important;
        font-weight: 800 !important;
        letter-spacing: 0.3px;
        transition: all 0.18s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
        border: 1.5px solid transparent !important;
    }
    .stButton > button[kind="secondary"] {
        background: #FFFFFF !important;
        color: #22314A !important;
        border: 1.5px solid #D8E2F0 !important;
        box-shadow: 0 3px 8px rgba(34, 49, 74, 0.06) !important;
    }
    .stButton > button[kind="secondary"]:hover {
        border-color: #FF6B6B !important;
        color: #E14E4E !important;
        transform: translateY(-1px);
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #FF8A65 0%, #FF6B6B 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 8px 18px rgba(255, 107, 107, 0.35) !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 24px rgba(255, 107, 107, 0.45) !important;
    }

    /* ============ 绘本画廊卡片 ============ */
    .book-card {
        background: #FFFFFF;
        border: 2px solid #F1E4D4;
        border-radius: 20px;
        padding: 10px 8px 12px;
        box-shadow: 0 6px 16px rgba(180, 140, 100, 0.08);
        transition: all 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
        text-align: center;
        position: relative;
        margin-bottom: 6px;
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    .book-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 16px 32px rgba(255, 138, 101, 0.20);
        border-color: #FFB59A;
    }
    .book-cover-frame {
        width: 106px;
        height: 144px;
        border-radius: 4px 8px 8px 4px;
        overflow: hidden;
        position: relative;
        box-shadow: 3px 5px 12px rgba(30, 20, 10, 0.22);
        border-left: 4px solid rgba(20, 14, 8, 0.30);
        background: #F8FAFC;
        margin: 2px auto 8px auto;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .book-cover-frame img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        image-rendering: -webkit-optimize-contrast;
    }
    .book-badge-tag {
        position: absolute;
        top: 5px;
        right: 5px;
        color: #FFFFFF;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 0.68rem;
        font-weight: 800;
        box-shadow: 0 3px 7px rgba(0,0,0,0.22);
        z-index: 5;
        letter-spacing: 0.3px;
    }
    .badge-story  { background: linear-gradient(135deg, #FBBF24, #F59E0B); }
    .badge-science{ background: linear-gradient(135deg, #60A5FA, #2563EB); }
    .badge-picture{ background: linear-gradient(135deg, #F472B6, #DB2777); }
    .book-title {
        font-size: 0.84rem;
        font-weight: 800;
        color: #22314A;
        margin: 2px 0 3px 0;
        line-height: 1.3;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 112px;
    }
    .book-shelf-label {
        font-size: 0.7rem;
        font-weight: 700;
        color: #7C8BA5;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 112px;
    }
    .book-like-count {
        font-size: 0.78rem;
        color: #DB2777;
        font-weight: 800;
        margin-bottom: 5px;
    }
    .like-pop { animation: likePop 0.45s cubic-bezier(0.34, 1.56, 0.64, 1); }
    @keyframes likePop {
        0% { transform: scale(1); }
        45% { transform: scale(1.35); }
        100% { transform: scale(1); }
    }

    /* 封面占位（无图时按类别生成鲜亮拟态封皮） */
    .cover-placeholder {
        width: 100%; height: 100%;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        font-weight: 800;
    }
    .cover-placeholder .cp-emblem { font-size: 2.3rem; margin-bottom: 4px; }
    .cover-placeholder .cp-title { font-size: 0.74rem; padding: 0 6px; line-height: 1.2; }

    /* ============ 4 层实物阶梯书架 ============ */
    .step-shelf {
        background: #FFFFFF;
        border: 3px solid #E4EBF5;
        border-radius: 30px;
        padding: 22px 24px;
        box-shadow: 0 14px 34px rgba(34, 49, 74, 0.07);
        margin: 20px 0;
    }
    .step-tier-card {
        background: #FFFFFF;
        border: 2.5px solid #E4EBF5;
        border-radius: 22px;
        overflow: hidden;
        transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        position: relative;
        margin-bottom: 14px;
    }
    .step-tier-header {
        padding: 14px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
    }
    .step-tier-dot {
        width: 44px; height: 44px;
        border-radius: 14px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.4rem;
        flex-shrink: 0;
        box-shadow: inset 0 -3px 6px rgba(0,0,0,0.06);
    }
    .step-tier-name { font-size: 1.08rem; font-weight: 800; }
    .step-tier-books { font-size: 0.8rem; font-weight: 600; margin-top: 2px; }
    .step-tier-count {
        font-size: 0.72rem; font-weight: 800;
        padding: 2px 10px; border-radius: 999px; margin-left: 8px;
    }
    .step-tier-active {
        border: 3px solid #FFB020 !important;
        background: linear-gradient(145deg, #FFFBEB, #FFF7E0) !important;
        box-shadow: 0 0 0 6px rgba(255, 176, 32, 0.16), 0 12px 26px rgba(245, 158, 11, 0.22) !important;
        transform: scale(1.015);
    }
    .step-beacon {
        background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%);
        color: white;
        font-size: 0.84rem;
        font-weight: 800;
        padding: 7px 16px;
        border-radius: 999px;
        animation: pulseBeacon 1.6s infinite;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
        box-shadow: 0 6px 14px rgba(245, 158, 11, 0.4);
    }
    @keyframes pulseBeacon {
        0% { transform: scale(0.96); box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.6); }
        70% { transform: scale(1.05); box-shadow: 0 0 0 12px rgba(245, 158, 11, 0); }
        100% { transform: scale(0.96); box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
    }
    .step-tier-tag {
        font-size: 0.8rem; font-weight: 800;
        padding: 5px 13px; border-radius: 999px; white-space: nowrap;
    }

    /* ============ 值日荣誉卡 ============ */
    .duty-card {
        background: linear-gradient(145deg, #FFFDF2 0%, #FFF3C4 100%);
        border: 2.5px solid #FFD54A;
        border-radius: 28px;
        padding: 24px 28px;
        margin: 16px 0;
        box-shadow: 0 14px 32px rgba(245, 176, 32, 0.18);
        position: relative;
        overflow: hidden;
    }
    .duty-card::after {
        content: "🏅";
        position: absolute;
        right: -10px; top: -18px;
        font-size: 7rem;
        opacity: 0.10;
        transform: rotate(14deg);
    }
    .duty-pill {
        background: linear-gradient(135deg, #F59E0B, #E08C00);
        color: white;
        padding: 5px 15px;
        border-radius: 999px;
        font-weight: 800;
        font-size: 0.82rem;
        letter-spacing: 0.5px;
        box-shadow: 0 5px 12px rgba(245, 158, 11, 0.35);
    }
    .duty-name {
        color: #92400E;
        margin: 12px 0 6px 0;
        font-size: 1.9rem;
        font-weight: 900;
        letter-spacing: -0.3px;
    }
    .duty-task { font-size: 1.08rem; color: #B45309; margin: 0; font-weight: 700; }
    .duty-crown { font-size: 4.2rem; filter: drop-shadow(0 8px 14px rgba(245, 158, 11, 0.35)); }

    .rhyme-card {
        background: #FFFFFF;
        border-radius: 22px;
        padding: 20px 24px;
        border: 2px dashed #FFD54A;
        text-align: center;
        margin-top: 14px;
    }
    .rhyme-text { font-size: 1.08rem; color: #5C6B84; margin: 0; font-weight: 700; line-height: 1.7; }

    /* ============ 教师端组件 ============ */
    .pro-metric-card {
        background: #FFFFFF;
        border: 1.5px solid #E9EEF6;
        border-radius: 20px;
        padding: 18px 20px;
        box-shadow: 0 5px 14px rgba(34, 49, 74, 0.05);
        transition: all 0.2s ease;
        height: 100%;
    }
    .pro-metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 22px rgba(34, 49, 74, 0.09);
    }
    .pro-metric-title {
        font-size: 0.86rem;
        color: #5C6B84;
        font-weight: 700;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .pro-metric-val {
        font-size: 1.75rem;
        font-weight: 900;
        color: #22314A;
        letter-spacing: -0.5px;
    }
    .pro-metric-unit { font-size: 0.9rem; color: #8494AC; font-weight: 700; }

    .section-title {
        font-size: 1.12rem;
        font-weight: 900;
        color: #22314A;
        margin: 6px 0 2px 0;
        letter-spacing: -0.2px;
    }
    .section-caption { font-size: 0.86rem; color: #7C8BA5; font-weight: 600; }

    /* 图书身份证预览卡 */
    .book-id-card {
        background: linear-gradient(145deg, #FFFFFF, #F4F8FF);
        border: 2px solid #C7D9F5;
        border-radius: 22px;
        padding: 20px 24px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 8px 20px rgba(46, 154, 254, 0.08);
    }
    .id-badge-stamp {
        position: absolute;
        top: 14px; right: -38px;
        background: linear-gradient(135deg, #2E9AFE, #1B7FE0);
        color: white;
        font-size: 0.74rem;
        font-weight: 800;
        padding: 5px 44px;
        transform: rotate(38deg);
        box-shadow: 0 4px 10px rgba(46, 154, 254, 0.35);
        letter-spacing: 1px;
    }

    /* 信息提示条美化 */
    .stAlert { border-radius: 16px !important; border: none !important; font-weight: 600 !important; }

    /* 选项卡（教师中台 Tab） */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(255,255,255,0.7);
        padding: 8px;
        border-radius: 20px;
        border: 1.5px solid #E9EEF6;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 999px !important;
        font-weight: 800 !important;
        padding: 8px 18px !important;
        color: #5C6B84 !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #FF8A65 0%, #FF6B6B 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 6px 14px rgba(255, 107, 107, 0.3) !important;
    }

    /* 输入控件圆角统一 */
    .stTextInput input, .stSelectbox div, .stTextArea textarea {
        border-radius: 14px !important;
    }

    /* 数据表格容器 */
    [data-testid="stDataFrame"] {
        border-radius: 18px !important;
        overflow: hidden;
        border: 1.5px solid #E9EEF6 !important;
    }

    /* 语音播报条 */
    .speech-fallback-bar {
        background: linear-gradient(135deg, #FFF9F2 0%, #FFF3E0 100%);
        border: 2px solid #FFD9A8;
        border-radius: 18px;
        padding: 12px 20px;
        margin: 10px 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        box-shadow: 0 5px 14px rgba(255, 176, 32, 0.14);
    }
    .speech-replay-btn {
        background: linear-gradient(135deg, #FF9A9E 0%, #FF6B6B 100%);
        color: #FFFFFF;
        border: none;
        border-radius: 999px;
        padding: 8px 18px;
        font-size: 0.9rem;
        font-weight: 800;
        cursor: pointer;
        box-shadow: 0 5px 12px rgba(255, 107, 107, 0.35);
        white-space: nowrap;
        transition: transform 0.15s ease;
    }
    .speech-replay-btn:hover { transform: scale(1.05); }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# 组件：顶部品牌条
# ============================================================
def render_brand_header(subtitle: str = "轻轻一触 · 自主找书 · 快乐归位"):
    """渲染儿童端顶部品牌条"""
    st.markdown(f"""
    <div class="brand-header">
        <div class="brand-title">
            <span>🦄 阳光幼儿园 · 智慧图书小精灵</span>
            <span class="brand-badge">童趣触控版</span>
        </div>
        <div class="brand-sub">{html.escape(subtitle)}</div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 组件：灵动小精灵交互岛
# ============================================================
def render_mascot_island(message: str, active_ai: str = "GEMINI", ai_online: bool = True):
    """渲染灵动小精灵交互岛（常驻视觉焦点）"""
    safe_msg = html.escape(message if message else "嗨！宝贝，想看哪本绘本？直接用小手指点一点下方封面，或者按红色按钮对我说话哦！")
    chip_cls = "ai-chip-on" if ai_online else "ai-chip-off"
    ai_text = html.escape(str(active_ai).upper()) if ai_online else "本地模式"
    html_code = f"""
    <div class="mascot-island">
        <div class="mascot-content">
            <div class="mascot-avatar">🦄</div>
            <div class="speech-balloon">
                <div class="speech-meta">
                    <span>✨ 图书小精灵皮皮在线</span>
                    <span class="ai-chip {chip_cls}">{ai_text}</span>
                </div>
                <p class="speech-text">{safe_msg}</p>
            </div>
        </div>
    </div>
    """
    st.markdown(html_code, unsafe_allow_html=True)


# ============================================================
# 组件：绘本画廊卡片（找书 / 点赞复用）
# ============================================================
import base64
from functools import lru_cache

@lru_cache(maxsize=128)
def _load_cover_as_data_url(file_path_str: str) -> str:
    """内部带缓存的读取并生成 data:image/png;base64,... 字符串"""
    try:
        p = Path(file_path_str)
        if not p.is_file():
            return ""
        suffix = p.suffix.lower().lstrip(".")
        mime = "jpeg" if suffix in ("jpg", "jpeg") else "png"
        raw = p.read_bytes()
        if not raw:
            return ""
        b64_str = base64.b64encode(raw).decode("utf-8")
        return f"data:image/{mime};base64,{b64_str}"
    except Exception:
        return ""


def cover_to_url(cover_path: str) -> str:
    """
    将图书封面路径转换为可内嵌的 Data URL（base64）。
    无论在本地 Windows 还是 Streamlit Cloud (Linux) 容器内，
    均可 100% 可靠加载，不受静态资源路由或跨平台路径影响。
    """
    if not cover_path:
        return ""
    
    # 1. 尝试直接以传入路径寻找
    p = Path(cover_path)
    if p.is_file():
        return _load_cover_as_data_url(str(p.resolve()))
    
    # 2. 尝试从 BASE_DIR 相对拼接寻找
    try:
        p_rel = (BASE_DIR / cover_path).resolve()
        if p_rel.is_file():
            return _load_cover_as_data_url(str(p_rel))
    except Exception:
        pass

    # 3. 容错回退：无论路径前缀如何，只要文件名存在于 static/book_covers/ 下即能命中
    filename = p.name
    if filename:
        p_fallback = (BASE_DIR / "static" / "book_covers" / filename).resolve()
        if p_fallback.is_file():
            return _load_cover_as_data_url(str(p_fallback))

    return ""


def render_book_card(book: Dict[str, Any], action_label: str, action_key: str,
                     show_like_count: bool = False, cover_width: int = 106):
    """
    渲染单本绘本卡片：封面 + 分类徽章 + 书名 + 架位 + 动作按钮。
    整张卡片为单一 HTML 岛（封面以静态服务 URL 内嵌 + 懒加载），保证版式不散架。
    action_key 必须全局唯一（Streamlit widget key）。
    """
    cover_path = book.get("cover_image_path", "")
    badge_type = book.get("cartoon_badge", "❤️ 绘本")
    if "👑" in badge_type or "故事" in badge_type:
        badge_class = "badge-story"
    elif "🔍" in badge_type or "科普" in badge_type:
        badge_class = "badge-science"
    else:
        badge_class = "badge-picture"

    safe_title = html.escape(book.get("title", ""))
    shelf_label = f"{book.get('shelf_slot', '')} · {book.get('shelf_color_label', '')}"
    frame_h = int(cover_width * 1.36)

    # 封面：优先静态 URL 内嵌真实封面，否则类别拟态占位
    cover_url = cover_to_url(cover_path)
    if cover_url:
        cover_html = (
            f'<img src="{html.escape(cover_url)}" alt="《{safe_title}》封面" '
            f'loading="lazy" decoding="async">'
        )
    else:
        palette = get_book_cover_palette(book.get("category_type", "绘本类"))
        cover_html = (
            f'<div class="cover-placeholder" style="background:{palette["bg"]}; color:{palette["color"]};">'
            f'<span class="cp-emblem">{palette["emblem"]}</span>'
            f'<span class="cp-title">{safe_title[:6]}</span>'
            f'</div>'
        )

    like_html = ""
    if show_like_count:
        like_html = f'<div class="book-like-count">❤️ {book.get("like_count", 0)}</div>'

    st.markdown(f"""
    <div class="book-card">
        <span class="book-badge-tag {badge_class}">{html.escape(badge_type)}</span>
        <div class="book-cover-frame" style="width:{cover_width}px; height:{frame_h}px;">{cover_html}</div>
        <div class="book-title" title="{safe_title}">《{safe_title}》</div>
        <div class="book-shelf-label">{html.escape(shelf_label)}</div>
        {like_html}
    </div>
    """, unsafe_allow_html=True)

    return st.button(action_label, key=action_key, width="stretch")


# ============================================================
# 组件：实物 4 层阶梯书架
# ============================================================
def render_physical_4tier_bookshelf(highlight_tier: int = 0, books: Optional[List[Dict[str, Any]]] = None):
    """
    1:1 实物现场 4 层白色阶梯绘本展架渲染。
    结合照片左侧圆点贴纸实标：
    - Tier 1: 顶层（无标）
    - Tier 2: 二层（🔵 蓝点贴纸标）
    - Tier 3: 三层（🟡 黄点贴纸标）
    - Tier 4: 底层（🟢 绿点贴纸标）
    books 传入真实在架图书时，各层展示真实书目与数量。
    """
    # 按层聚合真实书目
    tier_books: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: [], 4: []}
    for b in (books or []):
        t = b.get("shelf_tier", 1)
        if t in tier_books:
            tier_books[t].append(b)

    def _tier_desc(tier: int) -> str:
        items = tier_books.get(tier, [])
        if items:
            samples = "、".join(f"《{x['title']}》" for x in items[:3])
            more = f" 等 {len(items)} 本" if len(items) > 3 else ""
            return samples + more
        return "等待上架"

    def _tier_count(tier: int, color: str) -> str:
        n = len(tier_books.get(tier, []))
        return f'<span class="step-tier-count" style="background:{color}1A; color:{color};">{n} 本</span>'

    tiers = [
        (1, "⚪", "#94A3B8", "#F8FAFC", "第 1 层 · 顶层平视区", "白色阶梯 · 伸手即拿", "#5C6B84"),
        (2, "🔵", C_SKY, "#EFF6FF", "第 2 层 · 蓝色圆点区", "🔵 蓝标排 · 平视黄金层", C_SKY_DEEP),
        (3, "🟡", C_SUN, "#FFFBEB", "第 3 层 · 黄色圆点区", "🟡 黄标排 · 触手可及", C_SUN_DEEP),
        (4, "🟢", C_GRASS, "#ECFDF5", "第 4 层 · 绿色圆点区", "🟢 绿标排 · 稳妥底座层", C_GRASS_DEEP),
    ]

    tier_html = ""
    for tier, dot, dot_color, bg_color, name, tag, tag_color in tiers:
        active = "step-tier-active" if highlight_tier == tier else ""
        if highlight_tier == tier:
            beacon = f'<span class="step-beacon">🌟 就在这里！{name.split(" · ")[0]}！</span>'
        else:
            beacon = f'<span class="step-tier-tag" style="background:{tag_color}14; color:{tag_color};">{tag}</span>'

        # 注意：插值进 markdown 的 HTML 片段必须零缩进，否则会被解析器转义为代码块
        tier_html += (
            f'<div class="step-tier-card {active}">'
            f'<div class="step-tier-header" style="background: {bg_color};">'
            f'<div style="display: flex; align-items: center; gap: 14px; min-width: 0;">'
            f'<span class="step-tier-dot" style="background: {dot_color}22;">{dot}</span>'
            f'<div style="min-width: 0;">'
            f'<div class="step-tier-name" style="color: {tag_color};">{name}{_tier_count(tier, tag_color)}</div>'
            f'<div class="step-tier-books" style="color: {tag_color}CC;">{html.escape(_tier_desc(tier))}</div>'
            f'</div></div>'
            f'<div>{beacon}</div>'
            f'</div></div>'
        )

    st.markdown(f"""
<div class="step-shelf">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px;">
<div style="display: flex; align-items: center; gap: 10px;">
<span style="font-size: 1.5rem;">🪵</span>
<h3 style="margin: 0; font-size: 1.28rem; font-weight: 900; color: #22314A;">实物 4 层阶梯书架 · 实时架位</h3>
</div>
<span style="font-size: 0.84rem; color: #7C8BA5; font-weight: 700;">结合书架左侧圆点贴纸，精准寻书与归位</span>
</div>
{tier_html}
</div>
""", unsafe_allow_html=True)


# ============================================================
# 组件：值日荣誉卡
# ============================================================
def render_duty_card(today_duty: Dict[str, Any]):
    """渲染今日值日生荣誉卡（儿童端）"""
    names = today_duty.get("student_names", "全班小朋友")
    task = today_duty.get("duty_task", "轻拿轻放，看完送图书回家")
    is_today = today_duty.get("is_today", True)
    completed = today_duty.get("completed", 0)

    if not is_today:
        title_note = " <span style='font-size:0.9rem; color:#B45309; font-weight:700;'>(今天是周末，看看本周的值日小标兵吧)</span>"
    else:
        title_note = ""

    if completed:
        status_html = """<div style="margin-top: 12px; background: linear-gradient(135deg, #D1FAE5, #A7F3D0); border: 2px solid #34D399; border-radius: 16px; padding: 12px 18px; font-weight: 800; color: #065F46; font-size: 1.02rem;">
            🎉 太棒了！今天的整理任务已经打卡完成，大家都是爱护图书的优秀好宝宝！</div>"""
    else:
        status_html = """<div style="margin-top: 12px; background: #FFFFFF; border: 2px dashed #FFD54A; border-radius: 16px; padding: 12px 18px; font-weight: 700; color: #92400E; font-size: 1.0rem;">
            💡 整理完散乱的书架后，点击上方金牌按钮打卡，领取【今日护书小卫士】勋章吧！</div>"""

    st.markdown(f"""
    <div class="duty-card">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;">
            <div style="min-width: 0;">
                <span class="duty-pill">🎖️ 班级小主人</span>
                <h2 class="duty-name">今日图书小管家：【{html.escape(names)}】{title_note}</h2>
                <p class="duty-task">📋 任务口诀：{html.escape(task)}</p>
            </div>
            <div class="duty-crown">👑</div>
        </div>
        {status_html}
    </div>
    """, unsafe_allow_html=True)


def render_rhyme_card():
    """渲染图书角快乐儿歌卡"""
    st.markdown("""
    <div class="rhyme-card">
        <p class="rhyme-text">
            🎵 <b>图书角快乐儿歌</b><br>
            小绘本，真好看，轻轻拿，轻轻翻。<br>看完了，送回家，爱护图书人人夸！
        </p>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 组件：教师端指标卡
# ============================================================
def render_metric_card(title: str, value: str, unit: str = "", accent: str = "#FF6B6B", icon: str = "📚"):
    """渲染教师中台高阶指标卡（左侧鲜明色条）"""
    unit_html = f'<span class="pro-metric-unit">{unit}</span>' if unit else ""
    st.markdown(f"""
    <div class="pro-metric-card" style="border-left: 5px solid {accent};">
        <div class="pro-metric-title">{icon} {html.escape(title)}</div>
        <div class="pro-metric-val" style="color: {accent};">{value} {unit_html}</div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 配色：绘本封面拟态调色板（鲜亮版）
# ============================================================
def get_book_cover_palette(category_type: str = "绘本类") -> Dict[str, str]:
    """根据主题类别返回鲜亮拟态配色与象征徽标"""
    cat_str = str(category_type) if category_type else "绘本类"
    palettes = {
        "故事类": {
            "bg": "linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)",
            "color": "#92400E",
            "emblem": "👑",
            "tag": "故事",
            "border": "#F59E0B"
        },
        "科普类": {
            "bg": "linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)",
            "color": "#1E40AF",
            "emblem": "🔍",
            "tag": "科普",
            "border": "#2563EB"
        },
        "绘本类": {
            "bg": "linear-gradient(135deg, #FCE7F3 0%, #FBCFE8 100%)",
            "color": "#9D174D",
            "emblem": "❤️",
            "tag": "绘本",
            "border": "#DB2777"
        }
    }
    for key, val in palettes.items():
        if key in cat_str or val["tag"] in cat_str or val["emblem"] in cat_str:
            return val
    return palettes["绘本类"]


# 兼容旧函数名别名
render_realistic_bookshelf = render_physical_4tier_bookshelf


# ============================================================
# 🧒 组件：语音对话气泡（与图书精灵皮皮的多轮对话）
# ============================================================
def render_chat_bubble(role: str, text: str, avatar: str = "") -> None:
    """
    渲染单个聊天气泡。
    role='user' 右对齐（小朋友）；role='assistant' 左对齐（图书精灵皮皮）。
    文本经 html.escape 转义，防止 XSS。
    """
    is_user = role == "user"
    safe = html.escape(text or "")
    # 保留换行
    safe = safe.replace("\n", "<br/>")

    if is_user:
        align, bg, color, who = "flex-end", "linear-gradient(135deg,#BAE6FD 0%,#7DD3FC 100%)", "#0C4A6E", avatar or "🧒"
        tail, edge = "border-bottom-right-radius:8px;", "#0284C7"
    else:
        align, bg, color, who = "flex-start", "linear-gradient(135deg,#FED7AA 0%,#FDBA74 100%)", "#7C2D12", avatar or "🦄"
        tail, edge = "border-bottom-left-radius:8px;", "#EA580C"

    st.markdown(f"""
    <div style="display:flex; justify-content:{align}; margin:10px 0;">
        <div style="max-width:78%; display:flex; gap:10px; align-items:flex-start;">
            <div style="flex-shrink:0; width:40px; height:40px; border-radius:50%;
                        background:{bg}; display:flex; align-items:center;
                        justify-content:center; font-size:1.3rem;
                        box-shadow:0 2px 6px rgba(0,0,0,.08);">{who}</div>
            <div style="background:{bg}; color:{color}; border:2.5px solid {edge};
                        border-left-width:6px;
                        {tail} padding:12px 16px; font-size:1.02rem; font-weight:600;
                        line-height:1.65; box-shadow:0 3px 10px rgba(0,0,0,.10);">
                {safe}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_chat_history(messages: List[Dict[str, str]]) -> None:
    """渲染完整对话历史（messages: [{'role','content'}, ...]）"""
    if not messages:
        render_chat_bubble(
            "assistant",
            "嗨！宝贝，我是图书小精灵皮皮～🦄\n"
            "你可以问我：\n"
            "· 《两个小八路》在哪里呀？\n"
            "· 今天谁值日？\n"
            "· 你最喜欢什么故事？\n"
            "也可以按住红色麦克风直接跟我说哦！",
        )
        return
    for m in messages:
        render_chat_bubble(m.get("role", "assistant"), m.get("content", ""))


def inject_chat_css() -> None:
    """
    儿童端对话区样式：鲜艳配色 + 放大输入框。

    关键点：Streamlit 会把 st.markdown 里的块级 HTML 提取成**独立空 div**，
    后续组件全变成它的兄弟节点——所以绝不能靠 '<div class="chat-shell">' 包内容。
    正解：st.container(border=True) + 容器内放一个标记元素，再用 :has() 精确上色，
    这样边框/渐变才会真正包住气泡和输入框。
    """
    st.markdown("""
    <style>
    /* 对话区容器：饱和渐变 + 橙色粗边框 */
    [data-testid="stLayoutWrapper"]:has(.kid-chat-title) {
        background: linear-gradient(150deg, #FFF1E6 0%, #E8F4FF 55%, #F3E9FF 100%);
        border: 3.5px solid #FF7A59 !important;
        border-radius: 24px;
        box-shadow: 0 8px 24px rgba(255,122,89,.28);
        padding: 8px 16px 14px 16px;
    }
    .kid-chat-title {
        font-size: 1.1rem; font-weight: 900; color: #C2410C;
        margin: 6px 0 10px 0; padding: 8px 14px;
        background: linear-gradient(135deg, #FF7A59, #FF4D8D);
        color: #FFFFFF; border-radius: 999px;
        display: inline-block; box-shadow: 0 4px 10px rgba(255,77,141,.35);
    }

    /* 麦克风区：天蓝边框 */
    [data-testid="stLayoutWrapper"]:has(.kid-mic-title) {
        background: linear-gradient(120deg, #E3F2FF 0%, #FFF4E6 100%);
        border: 3.5px solid #38BDF8 !important;
        border-radius: 22px;
        box-shadow: 0 6px 18px rgba(56,189,248,.28);
        padding: 8px 16px 12px 16px;
    }
    .kid-mic-title {
        font-size: 1.02rem; font-weight: 900; color: #075985;
        margin: 4px 0 8px 0;
    }

    /* 导航区：绿色边框 */
    [data-testid="stLayoutWrapper"]:has(.kid-nav-title) {
        background: linear-gradient(120deg, #DCFCE7 0%, #FEF3C7 100%);
        border: 3.5px solid #34D399 !important;
        border-radius: 22px;
        box-shadow: 0 6px 18px rgba(52,211,153,.28);
        padding: 8px 16px 12px 16px;
    }
    .kid-nav-title {
        font-size: 1.02rem; font-weight: 900; color: #065F46;
        margin: 4px 0 6px 0;
    }

    /* 文字输入框：白底 + 橙边，和周围区分明显 */
    [data-testid="stTextInput"] input {
        border: 3px solid #FF7A59 !important;
        border-radius: 999px !important;
        background: #FFFFFF !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: #7C2D12 !important;
        box-shadow: 0 4px 14px rgba(255,122,89,.22);
    }
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stFormSubmitButton"] button:hover {
        background: linear-gradient(135deg, #FF7A59, #FF4D8D) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 999px !important;
        font-weight: 900 !important;
    }

    /* 所有圆角按钮统一形态 */
    [data-testid="stButton"] button {
        border-radius: 999px !important;
        font-weight: 800 !important;
        border-width: 2.5px !important;
    }

    /* ============ 手机端响应式适配 (≤ 768px) ============ */
    @media (max-width: 768px) {

        /* 内容区：收紧内边距，最大宽度放开 */
        .main .block-container {
            padding: 0.7rem 0.7rem 2rem !important;
            max-width: 100% !important;
        }

        /* 品牌头条：垂直堆叠，字号降档 */
        .brand-header {
            flex-direction: column;
            align-items: flex-start;
            padding: 10px 14px;
            gap: 4px;
            border-radius: 18px;
        }
        .brand-title { font-size: 1.05rem !important; gap: 7px; }
        .brand-sub   { font-size: 0.72rem !important; }
        .brand-badge { font-size: 0.7rem !important; padding: 3px 10px; }

        /* 小精灵岛屿：缩小头像，对话文字减小 */
        .mascot-island { padding: 12px 14px; border-radius: 20px; }
        .mascot-avatar { width: 60px !important; height: 60px !important; font-size: 2rem !important; }
        .speech-text   { font-size: 0.95rem !important; }

        /* 书卡封面：缩到 80×108 */
        .book-cover-frame {
            width: 80px !important;
            height: 108px !important;
        }

        /* 所有按钮触控目标 ≥ 48px，字号稍大 */
        .stButton > button {
            min-height: 48px !important;
            font-size: 0.9rem !important;
        }

        /* 段控件允许折行，防止超出屏幕 */
        [data-testid="stSegmentedControl"] {
            flex-wrap: wrap !important;
            gap: 4px !important;
        }
        [data-testid="stSegmentedControl"] label {
            font-size: 0.8rem !important;
            padding: 4px 8px !important;
        }

        /* Streamlit columns 在手机上折两列：
           给每个 column 最小宽度 46%，让 flex 自动折行 */
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 46% !important;
        }

        /* 表格横向滚动 */
        div[data-testid="stMarkdown"] table {
            display: block !important;
            overflow-x: auto !important;
        }

        /* 输入框标签字号 */
        .stTextInput label, .stSelectbox label,
        .stDateInput label, .stTextArea label {
            font-size: 0.85rem !important;
        }

        /* Tab 标题缩小 */
        .stTabs [data-baseweb="tab"] { font-size: 0.78rem !important; padding: 6px 8px !important; }

        /* 导航胶囊行高减小 */
        .nav-pill-row { margin: 2px 0 8px 0; }
    }

    /* 超小屏 (≤ 480px，低端安卓 / 320px 手机) */
    @media (max-width: 480px) {
        .brand-title { font-size: 0.9rem !important; }
        .mascot-avatar { width: 50px !important; height: 50px !important; font-size: 1.6rem !important; }
        .book-cover-frame {
            width: 68px !important;
            height: 92px !important;
        }
        /* 超小屏书卡标题也缩小 */
        .book-title-text { font-size: 0.68rem !important; }

        /* 极小屏每列允许更窄，防止截断 */
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 44% !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

