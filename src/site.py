"""静态站点生成器：把每期文章渲染成 GitHub Pages 可用的 HTML。

设计目标：读者是「不太懂技术的普通人」。
先给人话简介，技术细节默认收进 <details>；符合 WCAG 2.1 AA。
"""

import html
import json
import os
import re
from datetime import datetime, timedelta, timezone

CSS = """
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#fff;--text:#1f2328;--muted:#59636e;
--line:#d8dee4;--accent:#0550ae;--accent-soft:#ddf4ff;--star:#9a6700;
--shadow:0 1px 3px rgba(31,35,40,.08)}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--text:#e6edf3;
--muted:#9198a1;--line:#30363d;--accent:#79c0ff;--accent-soft:#122d4a;--star:#e3b341;
--shadow:0 1px 3px rgba(0,0,0,.4)}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
line-height:1.8;font-size:1rem;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:underline;text-underline-offset:3px}
a:hover{text-decoration-thickness:2px}
a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:3px;border-radius:4px}
.skip{position:absolute;left:-9999px;top:0;background:var(--card);padding:10px 16px;z-index:10}
.skip:focus{left:12px;top:12px}
.wrap{max-width:820px;margin:0 auto;padding:0 18px}
header.hero{padding:40px 0 26px;border-bottom:1px solid var(--line);margin-bottom:26px}
.brand{font-size:.875rem;letter-spacing:.08em;color:var(--accent);font-weight:700}
h1{font-size:1.875rem;line-height:1.35;margin:12px 0 10px;letter-spacing:-.02em;
overflow-wrap:anywhere}
.promise{font-size:1rem;font-weight:600;margin:0 0 6px}
.meta{color:var(--muted);font-size:.875rem;margin:0}
.overview{margin-top:20px;background:var(--accent-soft);border-left:4px solid var(--accent);
padding:14px 18px;border-radius:0 10px 10px 0;font-size:1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:22px 24px;margin:0 0 18px;box-shadow:var(--shadow)}
.card h2{font-size:1.25rem;margin:0 0 4px;overflow-wrap:anywhere}
.card h2 .rank{color:var(--muted);font-weight:600;margin-right:8px}
.stars{color:var(--star);font-size:.9375rem;font-weight:700;white-space:nowrap}
.section{margin:16px 0 0}
.section h3{display:inline-block;font-size:.875rem;font-weight:700;color:var(--accent);
background:var(--accent-soft);padding:2px 12px;border-radius:20px;margin:0 0 6px}
.section p{margin:0 0 8px}
.section ul{margin:0;padding-left:22px}.section li{margin:4px 0}
details.tech{margin-top:18px;border-top:1px dashed var(--line);padding-top:10px}
details.tech summary{cursor:pointer;color:var(--muted);font-size:.875rem;padding:6px 0;
list-style:none;display:block;min-height:24px}
details.tech summary::-webkit-details-marker{display:none}
details.tech summary::before{content:"▸ ";color:var(--accent)}
details.tech[open] summary::before{content:"▾ "}
.facts{list-style:none;padding:0;margin:8px 0 0;font-size:.875rem;color:var(--muted)}
.facts li{margin:6px 0;overflow-wrap:anywhere}
.facts a{display:inline-block;padding:4px 0}
.archive{margin:36px 0 20px;padding-top:24px;border-top:1px solid var(--line)}
.archive h2{font-size:1.1875rem;margin:0 0 12px}
.archive ul{list-style:none;padding:0}
.archive li{padding:0;border-bottom:1px dashed var(--line);font-size:.9375rem}
.archive a{display:block;padding:11px 0}
.archive .cnt{color:var(--muted);font-size:.875rem}
.pager{display:flex;justify-content:space-between;gap:12px;margin:24px 0;flex-wrap:wrap}
.pager a{display:block;padding:10px 14px;border:1px solid var(--line);border-radius:10px;
background:var(--card);min-height:44px}
footer{padding:28px 0 44px;color:var(--muted);font-size:.875rem;text-align:center}
.tools{margin-top:12px;font-size:.8125rem}
.back{display:inline-block;margin:22px 0;font-size:.9375rem}
@media(max-width:600px){h1{font-size:1.5rem}.card{padding:18px}.wrap{padding:0 14px}
header.hero{padding:28px 0 20px}.meta,.facts{font-size:.9375rem}}
@media(max-width:380px){.pager{flex-direction:column}.stars{display:block;margin-top:4px}}
"""


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _inline(s: str) -> str:
    """行内格式：加粗、代码、裸链接（链接保留下划线，不仅靠颜色区分）。"""
    s = _esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"(https?://[^\s<]+)",
               r'<a href="\1" target="_blank" rel="noopener">\1</a>', s)
    return s


# 小标题：`**这是什么**` 或 `**这是什么**：内容`（容忍模型格式偏差）
_LABEL_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*[:：]?\s*(.*)$")
# 列表项：- / * / 1. / 1、 / 一、
_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.、)]|[一二三四五六七八九十]+[、.])\s+(.+)$")


def render_summary(summary: str) -> str:
    """把 LLM 简介渲染成带 h3 小标题的语义化 HTML（读屏可在项目内导航）。"""
    out, buf, label = [], [], None

    def flush():
        nonlocal buf, label
        lines = [l for l in buf if l.strip()]
        if not lines:
            buf = []
            return
        body = []
        paras, lists = [], []
        for line in lines:
            m = _ITEM_RE.match(line)
            (lists if m else paras).append(m.group(1) if m else line)
        for p in paras:
            body.append(f"<p>{_inline(p.strip())}</p>")
        if lists:
            body.append("<ul>" + "".join(f"<li>{_inline(t)}</li>" for t in lists) + "</ul>")
        if body:
            out.append('<section class="section">'
                       + (f'<h3 class="label">{_esc(label)}</h3>' if label else "")
                       + "".join(body) + "</section>")
        buf, label = [], None

    for raw in summary.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if line.strip().startswith(">"):
            continue  # 忽略降级提示 / README 节选
        m = _LABEL_RE.match(line)
        if m:
            flush()
            label = m.group(1).strip()
            tail = m.group(2).strip()
            if tail:
                buf.append(tail)
        else:
            buf.append(line)
    flush()
    return "".join(out)


def _stars(n: int) -> str:
    return f'<span class="stars"><span aria-hidden="true">⭐</span> {n:,} 人收藏</span>'


def _render_card(idx: int, repo: dict, summary: str) -> str:
    full = repo["full_name"]
    url = repo["html_url"]
    stars = repo.get("stargazers_count", 0)
    lang = repo.get("language") or "未标注"
    forks = repo.get("forks_count", 0)
    lic = (repo.get("license") or {}).get("name") or "未标注"
    topics = ", ".join(repo.get("topics", [])) or "无"
    cid = f"p{idx}"
    # 人话简介在前，技术元数据折叠在后
    return (
        f'<article class="card" aria-labelledby="{cid}">\n'
        f'<h2 id="{cid}"><span class="rank">{idx:02d}</span>{_esc(full)} {_stars(stars)}</h2>\n'
        f'<div class="summary">{render_summary(summary)}</div>\n'
        f'<details class="tech"><summary>项目详情（给懂技术的人）</summary>\n'
        f'<ul class="facts">'
        f'<li><a href="{_esc(url)}" target="_blank" rel="noopener" '
        f'aria-label="在新窗口打开 GitHub 项目页：{_esc(full)}">'
        f'去 GitHub 看看这个项目 <span aria-hidden="true">↗</span>（新窗口打开）</a></li>'
        f'<li>主语言：{_esc(lang)} ｜ {forks:,} 人复制过去改 ｜ 使用许可：{_esc(lic)}</li>'
        f'<li>项目标签：{_esc(topics)}</li>'
        f'<li>仓库地址（可复制）：{_esc(url)}</li>'
        f'</ul></details>\n</article>'
    )


def _head(title: str, css_path: str = "style.css", og_url: str = "") -> str:
    og = ""
    if og_url:
        og = (f'<meta property="og:title" content="{_esc(title)}">\n'
              f'<meta property="og:description" content="用大白话介绍 GitHub 新晋热门项目">\n'
              f'<meta property="og:url" content="{_esc(og_url)}">\n')
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f'<title>{_esc(title)}</title>\n'
        f'<meta name="description" content="{_esc(title)} - 用大白话介绍 GitHub 新晋热门项目">\n'
        f'{og}<link rel="stylesheet" href="{css_path}">\n'
        '</head>\n<body>\n<a class="skip" href="#main">跳到正文</a>\n'
    )


def _archive_block(history: dict, current_date: str) -> str:
    posts = [p for p in history.get("posts", []) if p.get("date") != current_date]
    if not posts:
        return ""
    items = "".join(
        f'<li><a href="posts/{_esc(p["date"])}.html">'
        f'{_esc(p.get("date", ""))} · {_esc(p.get("title") or "往期文章")}'
        f'<span class="cnt"> · Top {p.get("count", "?")}</span></a></li>'
        for p in posts[:60]
    )
    return ('<nav class="archive" aria-label="往期文章">'
            '<h2>往期回顾</h2><ul>' + items + '</ul></nav>')


def _pager(history: dict, current_date: str) -> str:
    posts = sorted(history.get("posts", []),
                   key=lambda p: p.get("date", ""), reverse=True)
    idx = next((i for i, p in enumerate(posts) if p.get("date") == current_date), None)
    if idx is None:
        return ""
    newer = posts[idx - 1] if idx > 0 else None
    older = posts[idx + 1] if idx + 1 < len(posts) else None
    parts = []
    if newer:
        parts.append(f'<a href="posts/{_esc(newer["date"])}.html">← 新一期 {_esc(newer["date"])}</a>')
    else:
        parts.append('<span></span>')
    if older:
        parts.append(f'<a href="posts/{_esc(older["date"])}.html">旧一期 {_esc(older["date"])} →</a>')
    else:
        parts.append('<span></span>')
    return '<nav class="pager" aria-label="相邻期导航">' + "".join(parts) + '</nav>'


def _tools(article_date: str) -> str:
    return (
        '<footer><div>数据来源 <a href="https://github.com/trending" '
        'target="_blank" rel="noopener">GitHub ↗</a> · 每天自动生成</div>'
        f'<div class="tools">给站长的工具：'
        f'<a href="posts/{article_date}.md">下载本期纯文本</a> · '
        '<a href="feed.json">数据源（JSON）</a></div></footer>'
    )


def render_placeholder(config) -> str:
    """生成首次部署时的占位首页，避免 Pages 在首期生成前 404。"""
    os.makedirs(config.SITE_DIR, exist_ok=True)
    site_title = getattr(config, "SITE_TITLE", "GitHub 新晋热门速览")
    page = (
        _head(site_title)
        + '<main class="wrap" id="main"><header class="hero">'
        + f'<div class="brand">{_esc(site_title)}</div>'
        + '<h1>每天用大白话讲清楚 GitHub 上刚火起来的项目</h1>'
        + '<p class="promise">不懂技术也能看懂。</p>'
        + '</header><div class="card"><section class="section">'
        + '<h3 class="label">首期内容生成中</h3>'
        + '<p>这个站点每天自动更新一次。第一次自动任务跑完后，'
        + '这里会列出最近一周新冒出来、收藏数涨得最快的项目，'
        + '并逐个用大白话介绍它们是干嘛的。</p>'
        + '<p>想现在看看项目源码，可以'
        + '<a href="https://github.com/dear202606-star/stars" target="_blank" '
        + 'rel="noopener">去仓库看看 ↗</a>。</p>'
        + '</section></div></main>'
        + _tools("") + '</body></html>'
    )
    path = os.path.join(config.SITE_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(config.SITE_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)
    with open(os.path.join(config.SITE_DIR, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")
    return path


def render_site(history: dict, items: list, overview: str,
                article_date: str, md_text: str, config) -> dict:
    """生成首页、当期 HTML、当期 Markdown、样式、feed.json。返回生成文件清单。"""
    site_dir = config.SITE_DIR
    posts_dir = os.path.join(site_dir, "posts")
    os.makedirs(posts_dir, exist_ok=True)

    title = f"GitHub 本周新晋热门 Top{len(items)}（{article_date}）"
    site_title = getattr(config, "SITE_TITLE", "GitHub 新晋热门速览")
    cards = "".join(_render_card(i, r, s) for i, (r, s) in enumerate(items, 1))
    # 看点生成失败时给固定占位，避免布局跳动
    overview_text = overview or "本期看点整理中，直接往下看项目也行。"
    overview_html = (
        f'<div class="overview"><strong>本期看点：</strong>{_inline(overview_text)}</div>')
    archive = _archive_block(history, article_date)
    pager = _pager(history, article_date)
    now = datetime.now(timezone(timedelta(hours=config.TZ_OFFSET_HOURS))
                       ).strftime("%Y-%m-%d %H:%M")

    hero = (
        f'<header class="hero"><div class="brand">{_esc(site_title)}</div>'
        f'<h1>{_esc(title)}</h1>'
        f'<p class="promise">用大白话讲清楚每个项目，不懂技术也能看懂。</p>'
        f'<p class="meta">每天自动更新 · 近 {config.DAYS_BACK} 天新晋高星项目 · '
        f'更新于 {now}（UTC+{config.TZ_OFFSET_HOURS}）</p>'
        f'{overview_html}</header>'
    )
    base = getattr(config, "SITE_BASE_URL", "")
    og_url = (base.rstrip("/") + "/index.html") if base else ""

    index_html = (
        _head(f"{site_title} · {article_date}", "style.css", og_url)
        + f'<main class="wrap" id="main">{hero}{cards}{pager}{archive}</main>'
        + _tools(article_date) + '</body></html>'
    )
    post_html = (
        _head(title, "../style.css", og_url)
        + f'<main class="wrap" id="main"><a class="back" href="../index.html">← 返回首页</a>'
        + hero + cards + pager + archive
        + '</main>' + _tools(article_date) + '</body></html>'
    )

    files = {}
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    files["index"] = os.path.join(site_dir, "index.html")
    with open(os.path.join(posts_dir, f"{article_date}.html"), "w", encoding="utf-8") as f:
        f.write(post_html)
    files["html"] = os.path.join(posts_dir, f"{article_date}.html")
    with open(os.path.join(posts_dir, f"{article_date}.md"), "w", encoding="utf-8") as f:
        f.write(md_text)
    files["md"] = os.path.join(posts_dir, f"{article_date}.md")
    with open(os.path.join(site_dir, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)
    # 跳过 Jekyll，保证 .md 可访问
    with open(os.path.join(site_dir, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")

    feed = {
        "site": site_title,
        "updated_at": now,
        "latest": article_date,
        "posts": history.get("posts", []),
    }
    with open(os.path.join(site_dir, "feed.json"), "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
    return files
