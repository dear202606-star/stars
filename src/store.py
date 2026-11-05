"""JSON 历史存储：按分类跨天轮播去重 + 文章索引。

用纯 JSON 而非 SQLite，因为 GitHub Actions 每次都是干净 runner，
只有随仓库提交的文件才能跨次持久化。JSON 还可直接 diff、易排查。

去重键实际是 (category, full_name)：同一项目在两个分类里各自轮播，
不因另一分类上榜而被跳过。
"""

import json
import os
from datetime import datetime, timedelta, timezone


_REPO_FIELDS = (
    "full_name", "html_url", "stargazers_count", "forks_count",
    "language", "license", "topics", "description", "homepage",
    "created_at", "pushed_at", "open_issues_count", "id",
    "category", "category_label", "_score", "archived",
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
        # 迁移：旧版「新晋 Top10」历史没有分类，标成 legacy，不参与新分类去重
        for v in data["recommended"].values():
            if isinstance(v, dict) and not v.get("category"):
                v["category"] = "legacy"
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


def recent_names(history: dict, category_key: str, before_date: str,
                 window_days: int = 7) -> set:
    """取最近 window_days 天该分类出现过的项目，用于避免连续重复。"""
    from datetime import date
    try:
        end = date.fromisoformat(before_date)
    except (ValueError, TypeError):
        return set()
    out = set()
    for day, rows in (history.get("day_selection") or {}).items():
        try:
            delta = (end - date.fromisoformat(day)).days
        except (ValueError, TypeError):
            continue
        if 0 < delta <= window_days:
            out.update(r.get("full_name") for r in rows
                       if (r or {}).get("category") == category_key)
    return out


def dedupe_for_category(history: dict, ranked: list,
                        category_key: str, n: int,
                        recent: set = None) -> list:
    """按分类轮播：未推荐过的优先，其次旧的，最后才考虑最近几天出现过的。"""
    seen = {name for name, v in (history.get("recommended") or {}).items()
            if (v or {}).get("category") == category_key}
    recent = recent or set()
    fresh, used, too_recent = [], [], []
    for r in ranked:
        name = r["full_name"]
        if name in recent:
            too_recent.append(r)
        elif name in seen:
            used.append(r)
        else:
            fresh.append(r)
    out = fresh[:n]
    for pool in (used, too_recent):
        if len(out) < n:
            out.extend(pool[: n - len(out)])
    return out


def get_day_selection(history: dict, article_date: str) -> list:
    """取当天已选定的项目快照；同日重跑时复用，保证文章稳定可复现。"""
    snap = history.get("day_selection", {}).get(article_date, [])
    # 旧版无分类字段的快照属于「新晋 Top10」，不能复用为双分类榜单
    if snap and all(not (r or {}).get("category") for r in snap):
        return []
    return snap


def last_selection_for_category(history: dict, category_key: str,
                                before_date: str) -> list:
    """采集失败时，取上一期该分类的项目兜底，保证每个分类不空榜。"""
    days = history.get("day_selection", {})
    for d in sorted(days.keys(), reverse=True):
        if d >= before_date:
            continue
        rows = [r for r in days[d] if (r or {}).get("category") == category_key]
        if rows:
            return rows
    return []


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
            "category": r.get("category", "legacy"),
            "quality_score": (r.get("_score") or {}).get("total"),
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
