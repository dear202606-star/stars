"""GitHub API 采集：查询近 N 天新晋高 star 项目 + 抓取 README。

带指数退避重试；区分 401(凭证失效)/403(限流)/5xx(可重试)，
避免瞬时故障导致整批失败。
"""

import base64
import time

import requests


class RateLimitError(RuntimeError):
    """GitHub API 触发速率限制。"""


class AuthError(RuntimeError):
    """GitHub 凭证无效或已过期（401）。"""


def _headers(token: str) -> dict:
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _request_with_retry(method: str, url: str, *, headers: dict,
                        config, **kwargs) -> requests.Response:
    """统一请求入口：对可重试错误做指数退避，对认证/限流错误快速失败。"""
    max_retries = getattr(config, "HTTP_MAX_RETRIES", 3)
    base_delay = getattr(config, "HTTP_RETRY_BASE_DELAY", 1.0)
    session = requests.Session()
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            resp = session.request(method, url, headers=headers, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise RuntimeError(f"GitHub API 网络错误（已重试 {max_retries} 次）: {e}")

        if resp.status_code == 401:
            raise AuthError(
                "GitHub 凭证无效或已过期（401 Bad credentials）。"
                "本地请更新 .env 的 GITHUB_TOKEN；CI 中使用内置 GITHUB_TOKEN 不会出现此问题。")
        if resp.status_code == 403:
            raise RateLimitError(
                f"GitHub API 速率限制（403）。响应: {resp.text[:200]}")
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            resp.raise_for_status()
        return resp
    raise RuntimeError(f"GitHub API 请求失败: {last_exc}")


def search_recent_stars(config) -> list:
    """查询近 DAYS_BACK 天创建、star 大于 MIN_STARS 的仓库，按 star 降序。"""
    from datetime import datetime, timedelta, timezone
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
        resp = _request_with_retry(
            "GET", f"{config.GITHUB_API_BASE}/search/repositories",
            headers=headers, config=config, params=params, timeout=30)
        items = resp.json().get("items", [])
        repos.extend(items)
        if len(items) < config.PER_PAGE:
            break
    return repos


def fetch_readme(owner_repo: str, config, max_chars: int = 4000) -> str:
    """抓取 README 文本。404 返回空串；凭证/限流错误向上抛，其余失败打印警告。"""
    headers = _headers(config.GITHUB_TOKEN)
    url = f"{config.GITHUB_API_BASE}/repos/{owner_repo}/readme"
    try:
        resp = _request_with_retry(
            "GET", url, headers=headers, config=config, timeout=20)
        if resp.status_code == 404:
            return ""
        encoded = resp.json().get("content", "")
        if not encoded:
            return ""
        text = base64.b64decode(encoded).decode("utf-8", errors="ignore")
        return text[:max_chars]
    except (AuthError, RateLimitError):
        raise
    except Exception as e:
        print(f"      [警告] 获取 README 失败: {type(e).__name__}: {e}")
        return ""


def should_exclude(repo: dict, config) -> bool:
    """根据关键词排除纯列表/教程类仓库。"""
    name = (repo.get("full_name", "") + " " + (repo.get("description") or "")
            ).lower()
    return any(kw.lower() in name for kw in config.EXCLUDE_KEYWORDS)
