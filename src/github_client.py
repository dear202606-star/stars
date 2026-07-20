"""GitHub Search API 采集模块：查询近 N 天新晋高 star 项目，并抓取 README。"""

import base64
import requests
from datetime import datetime, timedelta, timezone


class RateLimitError(RuntimeError):
    """GitHub API 触发速率限制时抛出。"""


def _headers(token: str) -> dict:
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def search_recent_stars(config) -> list:
    """查询近 DAYS_BACK 天创建、star 大于 MIN_STARS 的仓库，按 star 降序。"""
    since = (datetime.now(timezone.utc) - timedelta(days=config.DAYS_BACK)
             ).strftime("%Y-%m-%d")
    query = f"created:>{since} stars:>{config.MIN_STARS}"
    if config.EXCLUDE_FORKS:
        query += " fork:false"

    headers = _headers(config.GITHUB_TOKEN)
    repos = []
    for page in range(1, config.MAX_PAGES + 1):
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": config.PER_PAGE,
            "page": page,
        }
        resp = requests.get(f"{config.GITHUB_API_BASE}/search/repositories",
                            headers=headers, params=params, timeout=30)
        if resp.status_code == 403:
            # 速率限制（与 fetch_readme 保持一致的异常类型）
            raise RateLimitError(
                f"GitHub Search API 速率限制，请在 .env 配置 GITHUB_TOKEN。"
                f"响应: {resp.text[:200]}")
        resp.raise_for_status()
        items = resp.json().get("items", [])
        repos.extend(items)
        if len(items) < config.PER_PAGE:
            break
    return repos


def fetch_readme(owner_repo: str, config, max_chars: int = 4000) -> str:
    """抓取仓库 README 文本，截断到 max_chars。404 返回空串；403 抛 RateLimitError。"""
    headers = _headers(config.GITHUB_TOKEN)
    url = f"{config.GITHUB_API_BASE}/repos/{owner_repo}/readme"
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 404:
            return ""
        if resp.status_code == 403:
            raise RateLimitError(
                f"README 接口速率限制（未配置 GITHUB_TOKEN 或额度用尽）。")
        resp.raise_for_status()
        encoded = resp.json().get("content", "")
        if not encoded:
            return ""
        text = base64.b64decode(encoded).decode("utf-8", errors="ignore")
        return text[:max_chars]
    except RateLimitError:
        raise
    except Exception as e:
        # 记录失败原因，便于排查（不再静默吞掉所有异常）
        print(f"      [警告] 获取 README 失败: {type(e).__name__}: {e}")
        return ""


def should_exclude(repo: dict, config) -> bool:
    """根据关键词排除纯列表/教程类仓库。"""
    name = (repo.get("full_name", "") + " " + (repo.get("description") or "")
            ).lower()
    return any(kw.lower() in name for kw in config.EXCLUDE_KEYWORDS)
