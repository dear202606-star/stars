"""Supabase 持久化层（纯 REST / PostgREST）。

云端优先：只需 SUPABASE_URL + SUPABASE_SERVICE_KEY 两个环境变量
（GitHub Actions Secrets），走 HTTPS 443，无需数据库驱动、无区域/IPv6 问题。
未配置时自动跳过，不阻断文章生成。

幂等：按 article_date / (article_date, full_name) upsert，同日重跑不产生重复。
表结构由 Management API 的一次性初始化脚本建立（见 scripts/init_supabase.py）。

双分类与质量分无需改表：写进已有的 sections JSONB（分类、综合质量分、
评分依据、评分分项）与 raw JSONB（完整仓库元数据），
PostgREST 可用 sections->>'分类' 直接过滤。
"""

import os
import re

import requests


def url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def key() -> str:
    return (os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
            or os.environ.get("SUPABASE_KEY", "").strip())


def enabled() -> bool:
    return bool(url() and key())


def strict() -> bool:
    """严格模式：写失败则整个任务失败，便于及时发现问题。"""
    return os.environ.get("SUPABASE_REQUIRED", "").strip() in ("1", "true", "yes")


def _headers(extra: dict = None) -> dict:
    k = key()
    h = {"apikey": k, "Authorization": f"Bearer {k}",
         "Content-Type": "application/json", "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def _postgrest(path: str, method: str = "GET",
               params: dict = None, payload=None, extra: dict = None):
    resp = requests.request(
        method, f"{url()}/rest/v1/{path}",
        headers=_headers(extra), params=params, json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(
            f"Supabase REST {method} {path} -> {resp.status_code}: "
            f"{resp.text[:300]}")
    return resp


_LABEL_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*[:：]?\s*(.*)$")


def parse_sections(summary: str) -> dict:
    """把 LLM 简介拆成 {字段名: 内容}，便于后续在 Supabase 里做分析。"""
    out, cur, buf = {}, None, []
    for line in (summary or "").splitlines():
        s = line.strip()
        if not s or s.startswith(">"):
            continue
        m = _LABEL_RE.match(s)
        if m:
            if cur:
                out[cur] = " ".join(buf).strip()
            cur, buf = m.group(1).strip(), ([m.group(2)] if m.group(2) else [])
        else:
            buf.append(s)
    if cur:
        out[cur] = " ".join(buf).strip()
    return out


def persist(article_date: str, title: str, overview: str, items: list,
            md_text: str, md_path: str, html_path: str,
            site_url: str, history: dict) -> dict:
    """写入一期完整数据。返回统计；异常按严格模式决定抛出或返回错误。"""
    if not enabled():
        return {"skipped": True, "reason": "SUPABASE_URL/KEY not configured"}

    try:
        # 1) 文章主表（upsert 按日期）
        _postgrest(
            "daily_articles", "POST",
            params={"on_conflict": "article_date"},
            extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
            payload={
                "article_date": article_date,
                "title": title,
                "overview": overview or "",
                "project_count": len(items),
                "markdown": md_text,
                "md_path": md_path,
                "html_path": html_path,
                "site_url": site_url,
            })

        # 2) 项目明细（upsert 按 日期+仓库名）
        rows = []
        for i, (repo, summary) in enumerate(items, 1):
            sections = parse_sections(summary)
            sections["分类"] = (repo.get("category_label")
                               or repo.get("category") or "未分类")
            sections["分类标识"] = repo.get("category") or ""
            score = repo.get("_score") or {}
            if score:
                sections["综合质量分"] = score.get("total")
                sections["评分依据"] = score.get("evidence")
                sections["评分分项"] = score.get("parts")
            rows.append({
                "article_date": article_date,
                "full_name": repo["full_name"],
                "rank": i,
                "html_url": repo.get("html_url"),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "language": repo.get("language"),
                "license": (repo.get("license") or {}).get("name"),
                "topics": repo.get("topics", []),
                "summary": summary,
                "sections": sections,
                "raw": repo,
            })
        _postgrest(
            "daily_projects", "POST",
            params={"on_conflict": "article_date,full_name"},
            extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
            payload=rows)

        # 3) 清掉本期已不再列出的项目，保证与文章一致
        names = [r["full_name"] for r in rows]
        _postgrest(
            "daily_projects", "DELETE",
            params={"article_date": f"eq.{article_date}",
                    "full_name": f"not.in.({','.join(names)})"}
            if names else {"article_date": f"eq.{article_date}"},
            extra={"Prefer": "return=minimal"})

        # 4) 去重历史（upsert）
        hist_rows = [
            {"full_name": name, "stars": (v or {}).get("stars"),
             "language": (v or {}).get("language"),
             "first_seen": (v or {}).get("first_seen")}
            for name, v in (history.get("recommended") or {}).items()
        ]
        if hist_rows:
            _postgrest(
                "recommended_history", "POST",
                params={"on_conflict": "full_name"},
                extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
                payload=hist_rows)

        return {"articles": 1, "projects": len(rows),
                "history": len(hist_rows), "skipped": False}
    except Exception as e:
        if strict():
            raise
        return {"error": f"{type(e).__name__}: {e}", "skipped": False}
