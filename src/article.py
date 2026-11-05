"""文章排版：组装微信公众号友好的 Markdown 文章。

按两个垂直分类分栏；顺序仍按普通读者的价值排序：先速览，技术信息放最后；
综合质量分与评分依据常驻在每个项目标题下方，读者可自行复核。
"""

from datetime import date

from src import scoring


def _part_detail(key: str, part: dict) -> str:
    """把分项还原成一句人能读、手机上能换行的话。"""
    value = part.get("value")
    if key == "stars":
        return f"累计 {value:,} 收藏"
    if key == "ratio":
        return f"收藏/复制比 {value}，{part.get('grade', '')}"
    if key in ("activity", "docs"):
        return part.get("note") or "公开信息里没有这一项"
    return str(value)


def build_article(items: list, article_date: str = None,
                  overview: str = "", config=None) -> str:
    """items: [(repo, summary), ...]，repo 带 category 与 _score。"""
    if config is None:
        import config as _config
        config = _config
    d = article_date or date.today().isoformat()
    categories = getattr(config, "CATEGORIES", [])
    per = getattr(config, "PER_CATEGORY", 3)
    groups = scoring.group_items(items, categories) if categories else \
        [(None, items)]

    lines = [
        f"# GitHub 双榜 · 金融与道术（{d}）",
        "",
        f"> 数据来源：GitHub 公共接口 ｜ 两个垂直分类各 {per} 个，"
        "按透明质量分从长期积累的项目里轮播精选，不追新、优先不重复 "
        f"｜ {d} 自动生成",
        "",
    ]
    if overview:
        lines.append(f"**本期看点**：{overview}")
        lines.append("")
    lines.extend(["---", ""])

    for cat, group in groups:
        if cat:
            lines.extend([
                f"## {cat['label']}",
                "",
                f"> {cat['desc']} ｜ 收录门槛：累计收藏 > {cat['min_stars']} "
                f"｜ 本期 {len(group)} 个",
                "",
            ])
        for i, (repo, summary) in enumerate(group, 1):
            full = repo["full_name"]
            url = repo["html_url"]
            stars = repo.get("stargazers_count", 0)
            score = repo.get("_score") or {}
            lines.append(f"### {i:02d}　{full}")
            lines.append("")
            total = score.get("total")
            if total is not None:
                head = f"**综合质量分 {total} / 100**　·　{stars:,} 收藏"
            else:
                head = f"**{stars:,} 收藏**"
            lines.append(
                f"{head}　·　主语言 {repo.get('language') or '未标注'}　·　"
                f"被复制 {repo.get('forks_count', 0):,} 次")
            lines.append("")
            if score.get("parts"):
                # 分项各占一行：手机上不用横向滚动，也不必读一长串数字
                lines.append(f"> 评分依据：综合质量分 {total} / 100，四项分项如下")
                for k, p in score["parts"].items():
                    lines.append(
                        f"> - {scoring.label(k)} {p.get('score', 0):.1f}/"
                        f"{p.get('max', 0)}：{_part_detail(k, p)}")
                lines.append("")
            lines.append(summary)  # 速览在前
            lines.append("")
            lines.append(f"> 项目主页：{url}")
            lines.append(f"> 使用许可：{(repo.get('license') or {}).get('name') or '未标注'}")
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.extend([
        f"> 评分口径：{scoring.FORMULA}",
        "> 收藏/复制比反映关注与实际动手的比例，不是好坏的绝对标准。",
        "",
        f"> 本文由 {d} 自动生成。内容基于项目公开信息整理，具体能力请以项目主页为准。",
    ])
    return "\n".join(lines)


def save_article(md: str, output_dir: str, article_date: str = None) -> str:
    import os
    os.makedirs(output_dir, exist_ok=True)
    d = article_date or date.today().isoformat()
    path = os.path.join(output_dir, f"{d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path
