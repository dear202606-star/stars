#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GitHub 每日新晋热门 Top10 文章生成器。

流程：采集近7天高 star 项目 -> 去重取 Top10 -> 抓 README -> LLM/模板生成简介 -> 输出 Markdown。
"""

import argparse
import sys
import time
from datetime import date

# Windows PowerShell 默认 GBK 编码，强制 stdout 用 utf-8，避免 emoji/中文报错
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
from src import github_client, snapshot, researcher, article


def main():
    parser = argparse.ArgumentParser(description="生成 GitHub 每日新晋热门 Top10 文章")
    parser.add_argument("--date", default=None, help="文章日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--top", type=int, default=None, help=f"Top N，默认 {config.TOP_N}")
    parser.add_argument("--no-llm", action="store_true", help="强制不使用 LLM")
    args = parser.parse_args()

    article_date = args.date or date.today().isoformat()
    top_n = args.top or config.TOP_N
    if args.no_llm:
        config.LLM_ENABLED = False

    print(f"[1/5] 采集近 {config.DAYS_BACK} 天新晋高 star 项目 ...")
    try:
        candidates = github_client.search_recent_stars(config)
    except github_client.RateLimitError as e:
        print(f"[错误] {e}")
        print("请在 .env 配置 GITHUB_TOKEN 后重试。")
        sys.exit(2)
    candidates = [r for r in candidates if not github_client.should_exclude(r, config)]
    print(f"      候选 {len(candidates)} 个（已过滤列表/教程类）")

    if not candidates:
        print("未采集到候选项目，退出。")
        sys.exit(1)

    print("[2/5] 去重并选取 Top", top_n)
    conn = snapshot.get_conn(config.DB_PATH)
    selected = snapshot.dedupe(conn, candidates, top_n)
    print(f"      选定 {len(selected)} 个")

    print("[3/5] 抓取 README 并生成简介"
          f"（LLM={'开启' if config.LLM_ENABLED else '关闭-模板模式'}）")
    items = []
    readme_limited = False
    for idx, repo in enumerate(selected, 1):
        full = repo["full_name"]
        print(f"      [{idx}/{len(selected)}] {full} ...", end=" ", flush=True)
        readme = ""
        if not readme_limited:
            try:
                readme = github_client.fetch_readme(full, config)
            except github_client.RateLimitError as e:
                readme_limited = True
                print(f"\n      [警告] {e} 后续项目改用 description 生成简介。")
        summary = researcher.research(repo, readme, config)
        items.append((repo, summary))
        print("完成")
        time.sleep(0.5)  # 控制 API 频率

    print("[4/5] 生成文章")
    md = article.build_article(items, article_date)

    print("[5/5] 保存文章")
    path = article.save_article(md, config.OUTPUT_DIR, article_date)
    print(f"完成 -> {path}")

    # 记录已推荐
    for repo, _ in items:
        snapshot.mark_recommended(conn, repo, article_date)
    conn.close()
    print("已更新历史快照。")


if __name__ == "__main__":
    main()
