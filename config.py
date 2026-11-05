# 两仪 · 每日一页（分「数」「象」两栏）配置
# 优先级：系统环境变量(CI 注入) > .env 文件 > 代码默认值

import os

# ---------- .env 自动加载（无需 python-dotenv）----------
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8-sig") as f:  # utf-8-sig 兼容 BOM
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            # 系统环境变量(含 CI 注入)优先；仅在缺失或为空时用 .env 补齐
            if not os.environ.get(key):
                os.environ[key] = val

_load_env()


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


# ---------- GitHub 配置 ----------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"

# ---------- 采集策略：双垂直分类，高分存量轮播（不追新）----------
# 供给调研结论：近 7 天新建的金融项目个位数、术数项目为 0；
# 因此不按创建时间过滤，改按分类主题词检索长期积累的项目库，每日轮播不重复。
CATEGORIES = [
    {
        "key": "finance",
        "label": "金融与量化",
        "display": "数",
        "note": "行情、账目、投资组合",
        "tab": "金融",
        "desc": "量化交易、行情数据、投资组合、Fintech 与链上金融",
        "min_stars": _env_int("FINANCE_MIN_STARS", 500),
        "keywords": ["quant", "trading", "fintech", "backtesting",
                     "stock", "defi", "portfolio", "financial"],
        "strong": ["trading", "backtesting", "backtest", "fintech",
                   "quantitative", "stock", "defi", "portfolio", "crypto",
                   "financial", "金融", "量化", "交易", "股票", "理财",
                   "期货", "加密", "行情", "回测"],
        "weak": ["quant", "finance", "investment", "fund", "banking"],
        "match": ["quant", "trading", "trade", "fintech", "backtest", "stock",
                  "defi", "portfolio", "financial", "finance", "金融", "量化",
                  "交易", "股票", "理财", "期货", "加密", "行情"],
    },
    {
        "key": "daoshu",
        "label": "道术 · 玄学术数",
        "display": "象",
        "note": "八字、历法、占卜与塔罗",
        "tab": "道术",
        "desc": "八字、紫微斗数、风水、易经、占卜与塔罗等术数工具",
        "min_stars": _env_int("DAOSHU_MIN_STARS", 5),
        "keywords": ["bazi", "八字", "ziwei", "fengshui", "iching",
                     "tarot", "astrology", "divination", "易经", "占卜"],
        "strong": ["bazi", "ziwei", "fengshui", "iching", "tarot",
                   "astrology", "divination", "numerology", "qimen",
                   "horoscope", "lunar", "八字", "紫微", "斗数", "风水",
                   "易经", "周易", "六爻", "奇门", "占卜", "塔罗", "占星",
                   "命理", "术数", "玄学", "排盘", "黄历"],
        "weak": [],
        "match": ["bazi", "ziwei", "fengshui", "iching", "tarot",
                  "astrology", "divination", "numerology", "qimen", "horoscope",
                  "八字", "紫微", "斗数", "风水", "易经", "周易", "六爻",
                  "奇门", "占卜", "塔罗", "占星", "命理", "术数", "玄学"],
    },
]

PER_CATEGORY = _env_int("PER_CATEGORY", _env_int("TOP_N", 3))
TOP_N = PER_CATEGORY  # 兼容 --top 参数与既有调用
ROTATION_WINDOW_DAYS = _env_int("ROTATION_WINDOW_DAYS", 7)  # 最近 N 天不重复
PER_PAGE = 50
MAX_PAGES = 1          # 每个关键词取 1 页，控制请求数
SEARCH_INTERVAL = float(os.environ.get("SEARCH_INTERVAL", "1.0"))
MAX_CANDIDATES = _env_int("MAX_CANDIDATES", 400)
DAYS_BACK = _env_int("DAYS_BACK", 7)   # 兼容旧配置，本版不再按创建时间筛选
MIN_STARS = _env_int("MIN_STARS", 50)  # 兼容旧配置，实际门槛按分类 min_stars
EXCLUDE_FORKS = True
EXCLUDE_KEYWORDS = [
    "awesome", "interview", "internship", "tutorial", "roadmap",
    "book", "books", "course", "learn", "cheatsheet", "resources",
    "collection", "jobs",
    "简历", "面试", "教程", "资源", "书单", "面试题", "求职",
]

# ---------- 网络重试 ----------
HTTP_MAX_RETRIES = _env_int("HTTP_MAX_RETRIES", 3)
HTTP_RETRY_BASE_DELAY = 1.0  # 指数退避基数（秒）

# ---------- LLM 配置（OpenAI 兼容接口，可选）----------
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
LLM_ENABLED = bool(LLM_API_KEY)

# ---------- 时区（面向中文读者，按北京时间定日期）----------
TZ_OFFSET_HOURS = _env_int("TZ_OFFSET_HOURS", 8)

# ---------- 路径 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
SITE_DIR = os.environ.get("SITE_DIR", os.path.join(BASE_DIR, "docs"))
HISTORY_FILE = os.environ.get(
    "HISTORY_FILE", os.path.join(DATA_DIR, "history.json"))

# ---------- 文章配置 ----------
ARTICLE_AUTHOR = os.environ.get("ARTICLE_AUTHOR", "两仪")
SITE_TITLE = os.environ.get("SITE_TITLE", "两仪")
SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "一边算得清，一边算不尽。")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "")
