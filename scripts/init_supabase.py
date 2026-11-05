#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性初始化 Supabase 表结构（幂等，可重复运行）。

使用 Supabase Management API 执行 DDL，纯云端、无需数据库驱动。
仅需在首次部署或表结构变更时运行一次；日常每日任务不执行本脚本。

双分类与质量分不需要改表：src/supabase_store.py 把它们写进已有的
daily_projects.sections / raw JSONB，线上既有表直接可用，无需新 Secret。
按分类查询示例：
    /rest/v1/daily_projects?sections->>分类=eq.金融与量化

用法：
    SUPABASE_ACCESS_TOKEN=sbp_xxx python scripts/init_supabase.py
"""

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests

PROJECT_REF = os.environ.get(
    "SUPABASE_PROJECT_REF", "kzfdxhooplhaydohqlyq")

DDL = """
CREATE TABLE IF NOT EXISTS public.daily_articles (
    article_date   DATE PRIMARY KEY,
    title          TEXT NOT NULL,
    overview       TEXT,
    project_count  INTEGER NOT NULL,
    markdown       TEXT,
    md_path        TEXT,
    html_path      TEXT,
    site_url       TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.daily_projects (
    article_date  DATE NOT NULL
        REFERENCES public.daily_articles(article_date) ON DELETE CASCADE,
    full_name     TEXT NOT NULL,
    rank          INTEGER NOT NULL,
    html_url      TEXT,
    stars         INTEGER,
    forks         INTEGER,
    language      TEXT,
    license       TEXT,
    topics        TEXT[],
    summary       TEXT,
    sections      JSONB,
    raw           JSONB,
    PRIMARY KEY (article_date, full_name)
);
CREATE INDEX IF NOT EXISTS idx_daily_projects_stars
    ON public.daily_projects (stars DESC);
CREATE INDEX IF NOT EXISTS idx_daily_projects_date
    ON public.daily_projects (article_date DESC);

CREATE TABLE IF NOT EXISTS public.recommended_history (
    full_name   TEXT PRIMARY KEY,
    stars       INTEGER,
    language    TEXT,
    first_seen  DATE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.daily_articles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_projects      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommended_history ENABLE ROW LEVEL SECURITY;
"""


def main():
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if not token:
        print("缺少 SUPABASE_ACCESS_TOKEN，跳过初始化。")
        return 0
    endpoint = (f"https://api.supabase.com/v1/projects/{PROJECT_REF}"
                "/database/query")
    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
        json={"query": DDL}, timeout=60)
    if not resp.ok:
        print(f"初始化失败 {resp.status_code}: {resp.text[:400]}")
        return 1
    print("Supabase 表结构初始化完成（幂等）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
