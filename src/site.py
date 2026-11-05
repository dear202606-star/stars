"""静态站点生成器：把每期文章渲染成 GitHub Pages 可用的 HTML。

设计语言：编辑部式科技榜单（Editorial Terminal）
- Zinc/Off-Black 中性底 + 单一青柠强调色，无霓虹、无紫蓝、无 emoji
- 等宽字体承载所有数字与元信息；非对称 Hero；细线分隔替代卡片堆叠
- 真实数据可视化（收藏数相对条形），不编造任何指标
- 动效只使用 transform / opacity，尊重 prefers-reduced-motion
- 读者是不懂技术的普通人：人话简介在前，技术细节折叠在后
"""

import html
import json
import os
import re
from datetime import datetime, timedelta, timezone

CSS = r"""
:root{
  color-scheme:light dark;
  --bg:#F6F7F5;--surface:#FFFFFF;--ink:#16191D;--muted:#5C646D;
  --line:#DFE3DF;--line-2:#C6CCC6;--accent:#4F621C;--accent-soft:#EDF2DC;
  --grid:rgba(22,25,29,.032);
  --font-d:"Outfit","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --font-m:"IBM Plex Mono","SFMono-Regular",Consolas,monospace;
  --ease:cubic-bezier(.2,.8,.2,1);
}
@media(prefers-color-scheme:dark){
  :root{
    --bg:#0B0E11;--surface:#11151A;--ink:#EBEEF0;--muted:#8B939C;
    --line:#22272E;--line-2:#3A424B;--accent:#BED857;--accent-soft:#191F12;
    --grid:rgba(255,255,255,.018);
  }
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-d);
 font-size:1rem;line-height:1.75;letter-spacing:.005em;-webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
 background-image:linear-gradient(var(--grid) 1px,transparent 1px),
 linear-gradient(90deg,var(--grid) 1px,transparent 1px);
 background-size:52px 52px}
.shell{position:relative;z-index:1;max-width:1180px;margin:0 auto;
 padding:0 clamp(20px,5vw,60px)}
a{color:inherit;text-decoration:underline;text-decoration-color:var(--line-2);
 text-underline-offset:4px;text-decoration-thickness:1px}
a:hover{text-decoration-color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:4px;border-radius:2px}
.skip{position:absolute;left:-9999px;top:0;background:var(--surface);
 padding:12px 18px;z-index:60;border:1px solid var(--line-2)}
.skip:focus{left:16px;top:16px}
.mono,.num,.metric,.stat-v,.eyebrow,.tag,.jump,.live,.facts,.archive,.tools,
.rank-head span,.stat-note,.pager{font-family:var(--font-m);font-variant-numeric:tabular-nums}

/* 顶栏：细线 + 期数锚点 + 状态点 */
.topbar{position:sticky;top:0;z-index:20;border-bottom:1px solid var(--line);
 background:color-mix(in srgb,var(--bg) 90%,transparent);backdrop-filter:blur(14px)}
.topbar-inner{display:grid;grid-template-columns:auto 1fr auto;gap:24px;
 align-items:center;min-height:62px}
.brand{display:flex;align-items:center;gap:11px;font-family:var(--font-m);
 font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;
 text-decoration:none;font-weight:600}
.brand::before{content:"";width:9px;height:9px;background:var(--accent);
 transform:rotate(45deg);display:block}
.jump{display:flex;gap:clamp(8px,1.4vw,18px);justify-content:center;
 font-size:.72rem;letter-spacing:.06em;overflow-x:auto;scrollbar-width:none}
.jump::-webkit-scrollbar{display:none}
.jump a{color:var(--muted);text-decoration:none;padding:8px 2px}
.jump a:hover,.jump a[aria-current="true"]{color:var(--accent)}
.live{font-size:.7rem;letter-spacing:.12em;color:var(--muted);white-space:nowrap}
.live i{display:inline-block;width:6px;height:6px;border-radius:50%;
 background:var(--accent);margin-right:9px;vertical-align:middle;
 animation:pulse 2.6s var(--ease) infinite}

/* Hero：非对称双栏，右侧为真实统计 */
.hero{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(220px,.72fr);
 gap:clamp(30px,5.5vw,80px);align-items:end;
 padding:clamp(46px,7vw,94px) 0 clamp(38px,5vw,68px)}
.eyebrow{font-size:.72rem;letter-spacing:.2em;text-transform:uppercase;
 color:var(--muted);margin:0 0 22px}
h1{font-size:clamp(2.25rem,5.6vw,4.35rem);line-height:1.04;
 letter-spacing:-.048em;font-weight:600;margin:0 0 22px;overflow-wrap:anywhere}
h1 em{font-style:normal;color:var(--accent)}
.lede{font-size:clamp(1rem,1.45vw,1.15rem);line-height:1.72;
 color:var(--muted);max-width:52ch;margin:0 0 30px}
.overview{border-left:2px solid var(--accent);padding:2px 0 2px 20px;
 max-width:62ch;font-size:.97rem;line-height:1.75}
.overview-label{display:block;font-family:var(--font-m);font-size:.68rem;
 letter-spacing:.18em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}
.stats{border-top:1px solid var(--line-2)}
.stat{display:grid;grid-template-columns:1fr auto;align-items:baseline;
 padding:13px 0;border-bottom:1px solid var(--line)}
.stat-k{font-size:.82rem;color:var(--muted)}
.stat-v{font-size:clamp(1.35rem,2.2vw,1.8rem);font-weight:600;letter-spacing:-.04em}
.stat-u{font-size:.76rem;color:var(--muted);margin-left:7px}
.stat-note{font-size:.72rem;color:var(--muted);margin:14px 0 0;line-height:1.6}

/* 榜单：细线分隔，条目带相对收藏数条形 */
.rank-head{display:flex;justify-content:space-between;align-items:baseline;
 gap:16px;border-bottom:1px solid var(--ink);padding-bottom:14px}
.rank-head h2{font-size:1.02rem;font-weight:600;letter-spacing:.01em;margin:0}
.rank-head span{font-size:.7rem;color:var(--muted);letter-spacing:.1em}
.list{list-style:none;margin:0;padding:0}
.entry{display:grid;grid-template-columns:clamp(62px,7vw,104px) minmax(0,1fr);
 gap:clamp(18px,3vw,44px);padding:clamp(32px,4.4vw,54px) 0;
 border-bottom:1px solid var(--line);
 animation:rise .55s var(--ease) both;
 animation-delay:calc(var(--i,0) * 55ms)}
.entry-rail{display:flex;flex-direction:column;gap:20px;padding-top:4px}
.num{font-size:clamp(1.7rem,3.2vw,2.75rem);font-weight:500;
 letter-spacing:-.09em;line-height:1;color:var(--line-2);
 transition:color .3s var(--ease)}
.entry:hover .num,.entry:focus-within .num{color:var(--accent)}
.bar{height:2px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent);
 transform-origin:left;animation:grow 1s var(--ease) both;
 animation-delay:calc(var(--i,0) * 55ms + 200ms)}
.entry-head{display:flex;justify-content:space-between;align-items:baseline;
 gap:18px;flex-wrap:wrap;margin-bottom:22px}
.entry-head h3{font-size:clamp(1.15rem,2.1vw,1.6rem);font-weight:600;
 letter-spacing:-.035em;margin:0;overflow-wrap:anywhere}
.entry-head h3 a{text-decoration-color:var(--line)}
.metric{white-space:nowrap;font-size:.9rem}
.metric-v{font-size:1.05rem;font-weight:600;color:var(--accent)}
.metric-u{font-size:.72rem;color:var(--muted);margin-left:8px}

/* 五字段：标签列 + 内容列，不用胶囊 */
.summary{display:grid}
.section{display:grid;grid-template-columns:clamp(92px,11vw,142px) minmax(0,1fr);
 gap:clamp(14px,2vw,30px);padding:13px 0;border-top:1px solid var(--line)}
.section:first-child{border-top:0;padding-top:0}
.section h4{margin:0;padding-top:3px;font-family:var(--font-m);font-size:.7rem;
 font-weight:500;letter-spacing:.14em;color:var(--muted)}
.section p{margin:0;line-height:1.75}
.section ul{margin:0;padding-left:1.15em}
.section li{margin:4px 0}
details.tech{margin-top:20px;border-top:1px dashed var(--line);padding-top:10px}
details.tech summary{cursor:pointer;list-style:none;display:flex;align-items:center;
 gap:10px;min-height:44px;font-family:var(--font-m);font-size:.72rem;
 letter-spacing:.08em;color:var(--muted)}
details.tech summary::-webkit-details-marker{display:none}
details.tech summary::before{content:"";width:6px;height:6px;
 border-right:1px solid var(--accent);border-bottom:1px solid var(--accent);
 transform:rotate(45deg);transition:transform .25s var(--ease)}
details.tech[open] summary::before{transform:rotate(225deg)}
.facts{list-style:none;margin:4px 0 0;padding:0;display:grid;gap:7px;
 font-size:.82rem;color:var(--muted)}
.facts li{overflow-wrap:anywhere}
.facts a{display:inline-flex;align-items:center;min-height:44px}

/* 导航与归档 */
.pager{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
 margin:clamp(28px,4vw,48px) 0;font-size:.8rem}
.pager a{display:inline-flex;align-items:center;min-height:44px;padding:10px 16px;
 border:1px solid var(--line-2);text-decoration:none}
.pager a:hover{border-color:var(--accent);color:var(--accent)}
.archive{margin:0 0 clamp(40px,6vw,72px);padding-top:26px;
 border-top:1px solid var(--line)}
.archive h2{font-family:var(--font-d);font-size:1.02rem;font-weight:600;margin:0 0 12px}
.archive ul{list-style:none;margin:0;padding:0}
.archive li{border-bottom:1px solid var(--line)}
.archive a{display:flex;justify-content:space-between;gap:16px;
 align-items:center;min-height:44px;padding:10px 0;
 font-size:.82rem;text-decoration:none}
.archive a:hover{color:var(--accent)}
.archive .cnt{font-size:.74rem;color:var(--muted);white-space:nowrap}
.back{display:inline-block;margin:24px 0 0;font-family:var(--font-m);
 font-size:.78rem;min-height:44px;line-height:44px}
footer{padding:26px 0 54px;border-top:1px solid var(--line);
 font-size:.78rem;color:var(--muted);display:flex;
 justify-content:space-between;gap:16px;flex-wrap:wrap}
.tools{font-size:.72rem;display:flex;gap:18px}
.placeholder{max-width:60ch;padding:clamp(48px,7vw,96px) 0}

@keyframes rise{from{opacity:0;transform:translateY(15px)}to{opacity:1;transform:translateY(0)}}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(var(--pct,1))}}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.65)}}

@media(max-width:880px){
 .hero{grid-template-columns:1fr;gap:34px;align-items:start}
 .jump{display:none}
 .topbar-inner{grid-template-columns:auto 1fr}
}
@media(max-width:640px){
 .entry{grid-template-columns:1fr;gap:14px}
 .entry-rail{flex-direction:row;align-items:center;gap:16px;padding-top:0}
 .bar{flex:1}
 .section{grid-template-columns:1fr;gap:5px;padding:12px 0}
 .section h4{padding-top:0}
 h1{font-size:clamp(2rem,9vw,2.7rem)}
 .overview{font-size:.93rem}
}
@media(prefers-reduced-motion:reduce){
 *,*::before,*::after{animation:none!important;transition:none!important;
 scroll-behavior:auto!important}
 .bar i{transform:scaleX(var(--pct,1))}
}
"""


def _esc(s) -> str:
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
    """把 LLM 简介渲染成带 h4 小标题的语义化 HTML。"""
    out, buf, label = [], [], None

    def flush():
        nonlocal buf, label
        lines = [l for l in buf if l.strip()]
        if not lines:
            buf = []
            return
        body, paras, lists = [], [], []
        for line in lines:
            m = _ITEM_RE.match(line)
            (lists if m else paras).append(m.group(1) if m else line)
        for p in paras:
            body.append(f"<p>{_inline(p.strip())}</p>")
        if lists:
            body.append("<ul>" + "".join(f"<li>{_inline(t)}</li>" for t in lists) + "</ul>")
        if body:
            out.append('<section class="section">'
                       + (f'<h4>{_esc(label)}</h4>' if label else "")
                       + "".join(body) + "</section>")
        buf, label = [], None

    for raw in summary.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if line.strip().startswith(">"):
            continue
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


def _render_card(idx: int, repo: dict, summary: str, max_stars: int = 1) -> str:
    """渲染一个榜单条目（保留函数名以兼容既有调用）。"""
    full = repo["full_name"]
    url = repo["html_url"]
    stars = repo.get("stargazers_count", 0)
    lang = repo.get("language") or "未标注"
    forks = repo.get("forks_count", 0)
    lic = (repo.get("license") or {}).get("name") or "未标注"
    topics = ", ".join(repo.get("topics", [])) or "无"
    pct = max(0.04, stars / max_stars) if max_stars else 1
    cid = f"p{idx}"
    return (
        f'<li class="entry" id="{cid}" aria-labelledby="{cid}-title" '
        f'style="--i:{idx-1};--pct:{pct:.4f}">\n'
        f'<div class="entry-rail"><span class="num" aria-hidden="true">{idx:02d}</span>'
        f'<div class="bar" role="img" aria-label="收藏数相对本期最高项目：{pct*100:.0f}%">'
        f'<i></i></div></div>\n'
        f'<div class="entry-body">\n'
        f'<header class="entry-head">'
        f'<h3 id="{cid}-title"><a href="{_esc(url)}" target="_blank" rel="noopener" '
        f'aria-label="在新窗口打开 GitHub 项目页：{_esc(full)}">{_esc(full)}</a></h3>'
        f'<div class="metric"><span class="metric-v">{stars:,}</span>'
        f'<span class="metric-u">收藏</span></div></header>\n'
        f'<div class="summary">{render_summary(summary)}</div>\n'
        f'<details class="tech"><summary>项目详情（给懂技术的人）</summary>\n'
        f'<ul class="facts">'
        f'<li><a href="{_esc(url)}" target="_blank" rel="noopener">'
        f'在新窗口打开项目页</a></li>'
        f'<li>主语言：{_esc(lang)} ｜ 被复制 {forks:,} 次 ｜ 使用许可：{_esc(lic)}</li>'
        f'<li>项目标签：{_esc(topics)}</li>'
        f'<li>仓库地址（可复制）：{_esc(url)}</li>'
        f'</ul></details>\n</div></li>'
    )


def _head(title: str, css_path: str = "style.css", og_url: str = "") -> str:
    og = ""
    if og_url:
        og = (f'<meta property="og:title" content="{_esc(title)}">\n'
              f'<meta property="og:description" content="每天用大白话讲清楚 GitHub 上刚火起来的项目">\n'
              f'<meta property="og:url" content="{_esc(og_url)}">\n')
    fonts = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?'
        'family=IBM+Plex+Mono:wght@400;500;600&'
        'family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">\n'
    )
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f'<title>{_esc(title)}</title>\n'
        f'<meta name="description" content="{_esc(title)} - 每天用大白话讲清楚 GitHub 上刚火起来的项目">\n'
        f'{og}{fonts}<link rel="stylesheet" href="{css_path}">\n'
        '</head>\n<body>\n<a class="skip" href="#main">跳到正文</a>\n'
    )


def _topbar(site_title: str, items: list, current_date: str,
            is_post: bool = False) -> str:
    root = "../index.html" if is_post else "index.html"
    jump = ""
    if len(items) <= 12:
        for i in range(1, len(items) + 1):
            href = (f"posts/{current_date}.html" if is_post else f"#p{i}")
            jump += f'<a href="{href}">{i:02d}</a>'
    return (
        '<header class="topbar"><div class="shell topbar-inner">'
        f'<a class="brand" href="{root}">{_esc(site_title)}</a>'
        f'<nav class="jump" aria-label="本期项目导航">{jump}</nav>'
        '<span class="live"><i aria-hidden="true"></i>每日自动更新</span>'
        '</div></header>'
    )


def _archive_block(history: dict, current_date: str) -> str:
    posts = [p for p in history.get("posts", []) if p.get("date") != current_date]
    if not posts:
        return ""
    items = "".join(
        f'<li><a href="posts/{_esc(p["date"])}.html">'
        f'<span>{_esc(p.get("date", ""))} · {_esc(p.get("title") or "往期文章")}</span>'
        f'<span class="cnt">Top {p.get("count", "?")}</span></a></li>'
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
    return '<nav class="pager" aria-label="相邻期导航">' + "".join(parts) + '</nav>'


def _tools(article_date: str) -> str:
    md = (f'<a href="posts/{article_date}.md">下载本期纯文本</a>'
          if article_date else "")
    return (
        '<footer><div>数据来源 '
        '<a href="https://github.com/trending" target="_blank" rel="noopener">GitHub</a>'
        ' · 每日自动生成</div>'
        f'<div class="tools">{md}<a href="feed.json">数据源（JSON）</a></div></footer>'
    )


def _stats(items: list, config, now: str, issue_no: int) -> str:
    total = sum(r.get("stargazers_count", 0) for r, _ in items)
    rows = [
        ("本期项目", f"{len(items):,}", "个"),
        ("合计收藏", f"{total:,}", ""),
        ("观察窗口", f"{config.DAYS_BACK}", "天"),
        ("期号", f"{issue_no:03d}", ""),
    ]
    body = ""
    for k, v, u in rows:
        unit = f'<span class="stat-u">{u}</span>' if u else ""
        body += (f'<div class="stat"><span class="stat-k">{k}</span>'
                 f'<span><span class="stat-v">{v}</span>{unit}</span></div>')
    return (f'<aside class="stats" aria-label="本期数据">{body}'
            f'<p class="stat-note">数据来自 GitHub 公共接口<br>'
            f'更新于 {now} (UTC+{config.TZ_OFFSET_HOURS})</p></aside>')


def render_placeholder(config) -> str:
    """生成首次部署时的占位首页，避免 Pages 在首期生成前 404。"""
    os.makedirs(config.SITE_DIR, exist_ok=True)
    site_title = getattr(config, "SITE_TITLE", "GitHub 新晋热门速览")
    page = (
        _head(site_title)
        + _topbar(site_title, [], "", False)
        + '<main class="shell" id="main"><div class="placeholder">'
        + '<p class="eyebrow">每日开源速览 · 即将上线</p>'
        + '<h1>刚火起来的项目，<em>讲清楚</em>。</h1>'
        + '<p class="lede">每天扫描 GitHub 近一周新创建、收藏数涨得最快的项目，'
        + '用大白话逐个介绍。第一次自动任务跑完后，这里会出现榜单。</p>'
        + '<p><a href="https://github.com/dear202606-star/stars" '
        + 'target="_blank" rel="noopener">先去看看项目源码</a></p>'
        + '</div></main>' + _tools("") + '</body></html>'
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
    """生成首页、当期 HTML、当期 Markdown、样式、feed.json。"""
    site_dir = config.SITE_DIR
    posts_dir = os.path.join(site_dir, "posts")
    os.makedirs(posts_dir, exist_ok=True)

    title = f"GitHub 本周新晋热门 Top{len(items)}（{article_date}）"
    site_title = getattr(config, "SITE_TITLE", "GitHub 新晋热门速览")
    max_stars = max((r.get("stargazers_count", 0) for r, _ in items), default=1) or 1
    cards = "".join(_render_card(i, r, s, max_stars)
                    for i, (r, s) in enumerate(items, 1))
    overview_text = overview or "本期看点整理中，直接往下看项目也行。"
    archive = _archive_block(history, article_date)
    pager = _pager(history, article_date)
    now = datetime.now(timezone(timedelta(hours=config.TZ_OFFSET_HOURS))
                       ).strftime("%Y-%m-%d %H:%M")
    issue_no = len(history.get("posts", []))

    hero = (
        '<section class="hero"><div class="hero-main">'
        f'<p class="eyebrow">{article_date} · 第 {issue_no:03d} 期 · '
        f'近 {config.DAYS_BACK} 天新晋项目</p>'
        f'<h1>本周新晋热门 <em>Top {len(items)}</em></h1>'
        '<p class="lede">每天一次，把 GitHub 上刚冒出来的项目讲清楚。'
        '不用懂技术，先看它解决什么问题、谁用得上、上手难不难。</p>'
        f'<div class="overview"><span class="overview-label">本期看点</span>'
        f'{_inline(overview_text)}</div>'
        '</div>' + _stats(items, config, now, issue_no) + '</section>'
    )
    ranking = (
        '<section aria-labelledby="ranking-title">'
        '<div class="rank-head"><h2 id="ranking-title">本期榜单</h2>'
        '<span>按收藏数排序 · 条形为相对值</span></div>'
        f'<ol class="list">{cards}</ol></section>'
    )
    base = getattr(config, "SITE_BASE_URL", "")
    og_url = (base.rstrip("/") + "/index.html") if base else ""

    index_html = (
        _head(f"{site_title} · {article_date}", "style.css", og_url)
        + _topbar(site_title, items, article_date, False)
        + f'<main class="shell" id="main">{hero}{ranking}{pager}{archive}</main>'
        + _tools(article_date) + '</body></html>'
    )
    post_html = (
        _head(title, "../style.css", og_url)
        + _topbar(site_title, items, article_date, True)
        + f'<main class="shell" id="main">'
        + '<a class="back" href="../index.html">← 返回首页</a>'
        + hero + ranking + pager + archive
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
    with open(os.path.join(site_dir, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")

    feed = {"site": site_title, "updated_at": now,
            "latest": article_date, "posts": history.get("posts", [])}
    with open(os.path.join(site_dir, "feed.json"), "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
    return files
