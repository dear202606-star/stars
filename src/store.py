"""JSON 历史存储：跨天去重 + 文章索引。

用纯 JSON 而非 SQLite，因为 GitHub Actions 每次都是干净 runner，
只有随仓库提交的文件才能跨次持久化。JSON 还可直接 diff、易排查。
"""

import json
import os
from datetime import datetime, timedelta, timezone


_REPO_FIELDS = (
    "full_name", "html_url", "stargazers_count", "forks_count",
    "language", "license", "topics", "description",
    "created_at", "pushed_at", "open_issues_count", "id",
)


def _empty() -> dict:
    return {"recommended": {}, "posts": [], "day_selection": {}}


def load(history_file: str) -> dict:
    if not os.path.exists(history_file):
        return _empty()
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("recommended", {})
        data.setdefault("posts", [])
        data.setdefault("day_selection", {})
        return data
    except (json.JSONDecodeError, OSError):
        return _empty()


def save(history: dict, history_file: str) -> None:
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    tmp = history_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp, history_file)  # 原子写入，避免半文件


def is_recommended(history: dict, full_name: str) -> bool:
    return full_name in history["recommended"]


def dedupe(history: dict, candidates: list, top_n: int) -> list:
    """优先返回未推荐过的；不足 top_n 时用已推荐过的补齐。"""
    fresh, used = [], []
    for r in candidates:
        (fresh if not is_recommended(history, r["full_name"]) else used).append(r)
    result = fresh[:top_n]
    if len(result) < top_n:
        result.extend(used[: top_n - len(result)])
    return result


def get_day_selection(history: dict, article_date: str) -> list:
    """取当天已选定的项目快照；同日重跑时复用，保证文章稳定可复现。"""
    return history.get("day_selection", {}).get(article_date, [])


def set_day_selection(history: dict, article_date: str, repos: list) -> None:
    """精简保存当天选定项目，只保留最近 14 天，避免文件无限增长。"""
    snap = [{k: r.get(k) for k in _REPO_FIELDS} for r in repos]
    days = history.setdefault("day_selection", {})
    days[article_date] = snap
    for old in sorted(days.keys())[:-14]:
        days.pop(old, None)


def mark_recommended(history: dict, repos: list, article_date: str,
                     tz_offset_hours: int = 8) -> None:
    now = datetime.now(timezone(timedelta(hours=tz_offset_hours))).isoformat()
    for r in repos:
        history["recommended"][r["full_name"]] = {
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language"),
            "first_seen": article_date,
            "updated_at": now,
        }


def upsert_post(history: dict, article_date: str, title: str,
                count: int, md_file: str, html_file: str) -> None:
    """幂等写入文章索引：同一天重复运行只覆盖，不产生重复条目。"""
    entry = {
        "date": article_date,
        "title": title,
        "count": count,
        "md": md_file,
        "html": html_file,
    }
    posts = [p for p in history["posts"] if p.get("date") != article_date]
    posts.append(entry)
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    history["posts"] = posts
