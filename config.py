# GitHub 采集与每日 Top10 文章生成配置
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

# ---------- 采集策略：近 N 天新晋热门 ----------
DAYS_BACK = _env_int("DAYS_BACK", 7)
MIN_STARS = _env_int("MIN_STARS", 50)
TOP_N = _env_int("TOP_N", 10)
PER_PAGE = 50
MAX_PAGES = 5
EXCLUDE_FORKS = True
EXCLUDE_KEYWORDS = [
    "awesome", "interview", "tutorial", "roadmap",
    "book", "course", "learn", "cheatsheet", "resources",
    "简历", "面试", "教程", "资源",
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
ARTICLE_AUTHOR = os.environ.get("ARTICLE_AUTHOR", "GitHub 星榜")
SITE_TITLE = os.environ.get("SITE_TITLE", "GitHub 新晋热门速览")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "")
