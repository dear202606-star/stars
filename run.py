#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GitHub 双分类每日精选生成器（金融与量化 / 道术玄学术数）。

全链路：按分类检索存量项目 -> 透明质量分 -> 按分类轮播去重 -> README 抓取
      -> LLM 平实中文速览 -> Markdown 文章 -> 静态站点(GitHub Pages)
      -> JSON 历史 + Supabase 持久化(幂等)。

不做「近 7 天新晋」过滤：垂类每日新项目供给不足，改从长期积累的项目库
按质量分每日轮播。可在本地运行，也可由 GitHub Actions 每日定时调用。
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

# Windows PowerShell 默认 GBK 编码，强制 stdout 用 utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
from src import (github_client, store, researcher, article, site,
                 supabase_store, scoring)


def _article_date(config, override: str = None) -> str:
    """按配置时区取"今天"，保证中文读者的日期准确（CI runner 默认 UTC）。"""
    if override:
        return override
    tz = timezone(timedelta(hours=config.TZ_OFFSET_HOURS))
    return datetime.now(tz).date().isoformat()


def main():
    parser = argparse.ArgumentParser(description="生成 GitHub 双分类每日精选")
    parser.add_argument("--date", default=None,
                        help="文章日期 YYYY-MM-DD，默认按配置时区取今天")
    parser.add_argument("--top", "--per-category", dest="per", type=int,
                        default=None,
                        help=f"每个分类取几个，默认 {config.PER_CATEGORY}")
    parser.add_argument("--no-llm", action="store_true", help="强制不使用 LLM")
    parser.add_argument("--no-site", action="store_true",
                        help="只生成 Markdown，不生成站点")
    args = parser.parse_args()

    article_date = _article_date(config, args.date)
    per = args.per or config.PER_CATEGORY
    categories = config.CATEGORIES
    expected = per * len(categories)
    if args.no_llm:
        config.LLM_ENABLED = False

    print(f"=== GitHub 双榜 · 金融与道术 | 每类 {per} 个 | {article_date} "
          f"(UTC+{config.TZ_OFFSET_HOURS}) ===")

    print("[1/7] 按分类检索 GitHub 存量项目（不按创建时间过滤）...")
    try:
        pools = github_client.fetch_candidates(config)
    except github_client.AuthError as e:
        print(f"[错误] {e}")
        sys.exit(3)
    except github_client.RateLimitError as e:
        print(f"[错误] {e}")
        sys.exit(2)
    for cat in categories:
        print(f"      {cat['label']}：候选 "
              f"{len(pools.get(cat['key'], []))} 个"
              f"（门槛 收藏 > {cat['min_stars']}，已过滤列表/教程类）")

    print("[2/7] 计算透明质量分并按分类轮播去重")
    history = store.load(config.HISTORY_FILE)
    cached = store.get_day_selection(history, article_date)
    if cached and len(cached) == expected:
        # 同日重跑（失败重试 / 手动触发）复用同一批项目，保证文章稳定可复现
        selected = cached
        print(f"      同日重跑，复用已选定的 {len(selected)} 个项目")
    else:
        selected, chosen = [], set()
        for cat in categories:
            ranked = scoring.rank(pools.get(cat["key"], []), cat)
            if not ranked:
                # 采集失败时复用上一期同类项目，保证不空榜
                ranked = [r for r in store.last_selection_for_category(
                    history, cat["key"], article_date)
                    if r.get("full_name")]
                if ranked:
                    print(f"      [警告] {cat['label']} 本期无候选，"
                          "复用上一期同类项目")
                else:
                    print(f"[错误] {cat['label']} 无候选且无往期可复用，"
                          "保留已有文章不变。")
                    sys.exit(1)
            recent = store.recent_names(
                history, cat["key"], article_date,
                getattr(config, "ROTATION_WINDOW_DAYS", 7))
            picked = [r for r in store.dedupe_for_category(
                history, ranked, cat["key"], per, recent)
                if r["full_name"] not in chosen]
            # 跨分类撞车时，从该类剩余高分项目补齐
            names = {r["full_name"] for r in picked}
            for r in ranked:
                if len(picked) >= per:
                    break
                name = r["full_name"]
                if name not in chosen and name not in names:
                    picked.append(r)
                    names.add(name)
            chosen.update(r["full_name"] for r in picked)
            selected.extend(picked)
            best = picked[0]["_score"]["total"] if picked and picked[0].get("_score") else "?"
            print(f"      {cat['label']}：选定 {len(picked)} 个，"
                  f"最高质量分 {best}")
        store.set_day_selection(history, article_date, selected)
        print(f"      合计 {len(selected)} 个（历史已收录 "
              f"{len(history['recommended'])} 个）")
    if not selected:
        print("[错误] 未选定任何项目，保留已有文章不变。")
        sys.exit(1)

    print("[3/7] 抓取 README 并生成简介"
          f"（LLM={'开启' if config.LLM_ENABLED else '关闭-模板模式'}）")
    items, readme_limited, readme_ok = [], False, 0
    for idx, repo in enumerate(selected, 1):
        full = repo["full_name"]
        print(f"      [{idx}/{len(selected)}] {full} ...", end=" ", flush=True)
        readme = ""
        if not readme_limited:
            try:
                readme = github_client.fetch_readme(full, config)
                if readme:
                    readme_ok += 1
            except github_client.AuthError as e:
                print(f"\n[错误] {e}")
                sys.exit(3)
            except github_client.RateLimitError as e:
                readme_limited = True
                print(f"\n      [警告] {e} 后续改用 description。")
        items.append((repo, researcher.research(repo, readme, config)))
        print("完成")
        time.sleep(0.3)
    print(f"      README 抓取成功 {readme_ok}/{len(selected)}")

    print("[4/7] 生成文章")
    overview = researcher.generate_overview(selected, config)
    md = article.build_article(items, article_date, overview, config)
    md_path = article.save_article(md, config.OUTPUT_DIR, article_date)
    print(f"      Markdown -> {md_path}")

    print("[5/7] 生成静态站点")
    store.mark_recommended(history, selected, article_date,
                           config.TZ_OFFSET_HOURS)
    title = f"GitHub 双榜 · 金融与道术（{article_date}）"
    if not args.no_site:
        # 必须先登记文章索引，再渲染站点，否则 feed.json / 归档会漏掉当期
        store.upsert_post(history, article_date, title, len(items),
                          f"posts/{article_date}.md",
                          f"posts/{article_date}.html")
        files = site.render_site(history, items, overview, article_date, md, config)
        print(f"      首页 -> {files['index']}")
        print(f"      当期 -> {files['html']}")
    else:
        print("      已跳过（--no-site）")

    print("[6/7] 保存历史快照")
    store.save(history, config.HISTORY_FILE)
    print(f"完成 -> {config.HISTORY_FILE}")

    print("[7/7] 持久化到 Supabase")
    if supabase_store.enabled():
        base = (config.SITE_BASE_URL or
                "https://dear202606-star.github.io/stars").rstrip("/")
        result = supabase_store.persist(
            article_date=article_date,
            title=title,
            overview=overview,
            items=items,
            md_text=md,
            md_path=f"posts/{article_date}.md",
            html_path=f"posts/{article_date}.html",
            site_url=f"{base}/posts/{article_date}.html",
            history=history,
        )
        if result.get("error"):
            print(f"      [警告] 写入失败（不影响文章）: {result['error']}")
        else:
            print(f"      已写入 {result.get('projects')} 个项目、"
                  f"{result.get('history')} 条去重历史")
    else:
        print("      未配置 SUPABASE_URL / SUPABASE_SERVICE_KEY，跳过（本地运行属正常）")

    print(f"=== DONE: {len(items)} 个项目, 日期 {article_date} ===")


if __name__ == "__main__":
    main()
