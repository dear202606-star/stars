"""文章排版：两仪 · 每日一页。

只呈现项目本身；筛选、评分口径、生成过程都不写进读者看到的内容里。
依据仍保留，但用一句人话说出，而不是罗列指标。
"""

from datetime import date

from src import scoring


def build_article(items: list, article_date: str = None,
                  overview: str = "", config=None) -> str:
    """items: [(repo, summary), ...]，repo 带 category 与 _score。"""
    if config is None:
        import config as _config
        config = _config
    d = article_date or date.today().isoformat()
    categories = getattr(config, "CATEGORIES", [])
    site_title = getattr(config, "SITE_TITLE", "两仪")
    tagline = getattr(config, "SITE_TAGLINE", "一边算得清，一边算不尽。")
    groups = scoring.group_items(items, categories) if categories else \
        [(None, items)]

    lines = [f"# {site_title} · {d}", "", f"> {tagline}", ""]
    if overview:
        lines.extend([overview, ""])
    lines.extend(["---", ""])

    for cat, group in groups:
        if cat:
            lines.extend([
                f"## {cat.get('display') or cat['label']}"
                f" · {cat.get('tab') or cat['label']}",
                "",
                f"> {cat.get('note') or cat.get('desc', '')}",
                "",
            ])
        for i, (repo, summary) in enumerate(group, 1):
            stars = repo.get("stargazers_count", 0)
            score = repo.get("_score") or {}
            head = (f"**{scoring.score_text(repo)}**　·　{stars:,} 人收藏"
                    if score else f"**{stars:,} 人收藏**")
            lines.extend([f"### {i:02d}　{repo['full_name']}", "", head, ""])
            if score:
                lines.extend([f"> {scoring.plain_evidence(repo, False)}", ""])
            lines.extend([
                summary,
                "",
                f"> 项目页：{repo['html_url']}",
                "",
                "---",
                "",
            ])

    lines.append("> 内容据项目公开信息整理，具体以项目页为准。")
    return "\n".join(lines)


def save_article(md: str, output_dir: str, article_date: str = None) -> str:
    import os
    os.makedirs(output_dir, exist_ok=True)
    d = article_date or date.today().isoformat()
    path = os.path.join(output_dir, f"{d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path
