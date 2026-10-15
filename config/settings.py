# 幼儿园图书管理与智能体配置文件
# 安全约定：任何 API Key 都不硬编码在本文件中。
# 密钥读取优先级：环境变量 > .streamlit/secrets.toml（本地开发，已列入 .gitignore）> 默认空值
import os
import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# 本地开发密钥文件（不纳入版本库，云端部署时由 Streamlit Secrets 注入）
_SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"


def _load_local_secrets() -> dict:
    """本地开发时从 .streamlit/secrets.toml 读取密钥；文件不存在时返回空字典"""
    if not _SECRETS_PATH.exists():
        return {}
    try:
        with open(_SECRETS_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        print(f"[settings] 解析 secrets.toml 失败: {e}")
        return {}


_LOCAL_SECRETS = _load_local_secrets()


def get_secret(name: str, default: str = "") -> str:
    """统一密钥读取：环境变量优先，其次本地 secrets.toml，最后默认值"""
    return os.getenv(name) or _LOCAL_SECRETS.get(name, default) or default


# 默认数据库路径 (本地 SQLite，可平滑迁移至云端 Supabase)
DB_PATH = get_secret("SQLITE_DB_PATH", str(DATA_DIR / "kindergarten_books.db"))

# 教师默认管理 PIN 码
DEFAULT_TEACHER_PIN = get_secret("TEACHER_PIN", "123456")

# DeepSeek API 配置
DEEPSEEK_API_KEY = get_secret("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = get_secret("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = get_secret("DEEPSEEK_MODEL", "deepseek-chat")

# Gemini API 配置（默认空串；未配置时 AI 功能自动降级为本地规则引擎）
GEMINI_API_KEY = get_secret("GEMINI_API_KEY", "")

# ==================== 阿里云百炼（DASHSCOPE）配置 ====================
# LLM 与 TTS 共用同一个百炼 API Key，国内直连、无需代理。
BAILIAN_API_KEY = get_secret("BAILIAN_API_KEY", "")
# LLM 走 OpenAI 兼容端点
BAILIAN_BASE_URL = get_secret(
    "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
BAILIAN_MODEL = get_secret("BAILIAN_MODEL", "qwen-flash")
# 自动换模型链：某个模型额度用尽/不可用时，按顺序无缝切到下一个（已实测本账号可用）
# 顺序按【实测首字延迟】从快到慢排列（同一 prompt 重复调用取稳定值）：
#   qwen-flash ≈ 0.33s ｜ qwen-plus ≈ 1.5s ｜ qwen3.5-flash ≈ 12s（推理模型，会先"想"再答）
# 注意：qwen3.5-flash 是 reasoning 模型，幼儿端等不起，只作末位兜底。
BAILIAN_MODEL_FALLBACKS = [
    "qwen-flash",      # 首选：轻量够用，秒回
    "qwen-plus",       # 兜底 1：能力更强，约 1.5s
    "qwen3.5-plus",    # 兜底 2
    "qwen-long",       # 兜底 3
    "qwen3.5-flash",   # 末位兜底：推理模型，约 12s，仅在前述全挂时用
]

# TTS 走百炼原生 multimodal-generation 端点，返回 WAV 音频 URL（24h 内有效）
BAILIAN_TTS_MODEL = get_secret("BAILIAN_TTS_MODEL", "qwen3-tts-flash")
BAILIAN_TTS_URL = get_secret(
    "BAILIAN_TTS_URL",
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
)
# 默认音色 Cherry（芊悦）：阳光积极、亲切自然小姐姐。实测同段文本 8.08 秒，
# 是 10 个候选音色里最贴近幼儿老师自然语速的（其余多在 10 秒以上偏慢）。
BAILIAN_TTS_VOICE = get_secret("BAILIAN_TTS_VOICE", "Cherry")
# 自动换音色链：当前音色不可用时按顺序回退，保证播报永不断档
BAILIAN_TTS_VOICE_FALLBACKS = [
    "Cherry",   # 芊悦：阳光亲切小姐姐（首选）
    "Maia",     # 知性温柔女声
    "Mia",      # 泉水般温柔
    "Katerina", # 成熟知性女声
    "Serena",   # 苏瑶：温柔治愈
    "Momo",     # 活泼俏皮
    "Nini",     # 软糯甜妹（偏儿童向）
]

# ==================== 本地免费额度熔断（账单安全的硬保险）====================
# 云厂商免费额度耗尽后默认自动转为按量计费，只有靠本地拦截才能保证不扣费。
# 用户已在百炼开通数十个模型额度，此处设为高阈值作为兜底保险，而非主要限额手段。
DAILY_BUDGET_TOKENS = int(get_secret("DAILY_BUDGET_TOKENS", "2000000"))      # LLM 每日 Token 上限
DAILY_BUDGET_TTS_CHARS = int(get_secret("DAILY_BUDGET_TTS_CHARS", "500000"))  # TTS 每日字符上限