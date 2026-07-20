# GitHub 采集与每日 Top10 文章生成配置
# 敏感信息建议放在 .env 文件或系统环境变量中，本文件会自动读取。

import os

# ---------- .env 自动加载（无需 python-dotenv）----------
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            # .env 中的非空值优先（覆盖系统环境变量中的空值）
            if val:
                os.environ[key] = val
            elif key not in os.environ:
                os.environ[key] = val

_load_env()

# ---------- GitHub 配置 ----------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"

# ---------- 采集策略：近7天新晋热门 ----------
DAYS_BACK = 7            # 查询近 N 天内创建的仓库
MIN_STARS = 50           # 最低 star 门槛，过滤噪音
TOP_N = 10               # 输出 Top N
PER_PAGE = 50            # 每页拉取数量（GitHub 上限 100）
MAX_PAGES = 5            # 最多翻页数，构建候选池
EXCLUDE_FORKS = True     # 排除 fork
# 排除纯列表/教程/面试题类仓库（按仓库名/描述关键词）
EXCLUDE_KEYWORDS = [
    "awesome", "interview", "tutorial", "roadmap",
    "book", "course", "learn", "cheatsheet", "resources",
    "简历", "面试", "教程", "资源",
]

# ---------- LLM 调研配置（OpenAI 兼容接口，可选）----------
# 留空则降级为模板模式（输出 description + README 摘要，不调用 LLM）
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_ENABLED = bool(LLM_API_KEY)

# ---------- 路径 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(DATA_DIR, "github_stars.db")

# ---------- 文章配置 ----------
ARTICLE_AUTHOR = os.environ.get("ARTICLE_AUTHOR", "GitHub 星榜")
