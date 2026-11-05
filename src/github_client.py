"""GitHub API 采集：按垂直分类检索存量项目 + 抓取 README。

不做「近 N 天新建」过滤：垂类每日新项目供给不足（术数类近乎为 0），
改由 src/scoring.py 对长期积累的项目库打质量分、再按日轮播。

带指数退避重试；区分 401(凭证失效)/403(限流)/5xx(可重试)，
单个关键词失败只跳过该词，不让整批任务失败。
"""

import base64
import re
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
            # 次级限流是短时窗口，退避后重试；主限流直接失败便于快速定位
            if "secondary rate limit" in resp.text.lower() and attempt < max_retries:
                time.sleep(base_delay * (2 ** (attempt + 2)))
                continue
            raise RateLimitError(
                f"GitHub API 速率限制（403）。响应: {resp.text[:200]}")
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            resp.raise_for_status()
        return resp
    raise RuntimeError(f"GitHub API 请求失败: {last_exc}")


def search_category(config, category: dict) -> list:
    """按分类主题词检索存量项目，合并去重后返回候选池。

    每个关键词单独查询（GitHub 仓库搜索对多词 OR 支持不稳定），
    命中的查询词记在 _queries 里，供评分模块做归类校验。
    """
    headers = _headers(config.GITHUB_TOKEN)
    pool = {}
    min_stars = category.get("min_stars", 0)
    interval = getattr(config, "SEARCH_INTERVAL", 1.0)

    for kw in category["keywords"]:
        query = f"{kw} in:name,description stars:>{min_stars}"
        if getattr(config, "EXCLUDE_FORKS", True):
            query += " fork:false"
        query += " archived:false"
        try:
            for page in range(1, getattr(config, "MAX_PAGES", 1) + 1):
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
                if resp.status_code != 200:
                    print(f"      [警告] 关键词 {kw} 返回 "
                          f"{resp.status_code}: {resp.text[:160]}")
                    break
                items = resp.json().get("items", [])
                for item in items:
                    name = item.get("full_name")
                    if not name:
                        continue
                    if name in pool:
                        pool[name]["_queries"].append(kw)
                    else:
                        row = dict(item)
                        row["_queries"] = [kw]
                        pool[name] = row
                if len(items) < config.PER_PAGE:
                    break
        except (AuthError, RateLimitError) as e:
            # 认证失效整批失败；限流只跳过该词，其余词仍可出稿
            if isinstance(e, AuthError):
                raise
            print(f"      [警告] 关键词 {kw} 触发限流，跳过：{e}")
        except Exception as e:
            print(f"      [警告] 关键词 {kw} 查询失败，跳过："
                  f"{type(e).__name__}: {e}")
        time.sleep(interval)

    rows = list(pool.values())
    rows.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    limit = getattr(config, "MAX_CANDIDATES", 400)
    return rows[:limit]


def fetch_candidates(config) -> dict:
    """采集所有分类的候选池，返回 {category_key: [repo, ...]}。"""
    out = {}
    for category in config.CATEGORIES:
        rows = search_category(config, category)
        out[category["key"]] = [
            r for r in rows if not should_exclude(r, config)]
    return out


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
    """排除纯列表/教程/招聘类仓库；英文按词边界，避免误伤 orderbook 等。"""
    text = (repo.get("full_name", "") + " " + (repo.get("description") or "")
            ).lower()
    for kw in config.EXCLUDE_KEYWORDS:
        k = kw.lower()
        if re.search(r"[a-z]", k):
            # 容忍 s / es / ing 后缀：internship 能排除 Internships
            if re.search(r"(?<![a-z0-9])" + re.escape(k)
                         + r"(?:s|es|ing)?(?![a-z0-9])", text):
                return True
        elif k in text:
            return True
    return False
