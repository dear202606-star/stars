"""文章排版模块：将 Top N 项目组装成微信公众号友好的 Markdown 文章。"""

from datetime import date


def build_article(items: list, article_date: str = None) -> str:
    """items: [(repo, summary), ...]"""
    d = article_date or date.today().isoformat()
    lines = [
        f"# GitHub 本周新晋热门 Top{len(items)}（{d}）",
        "",
        f"> 数据来源：GitHub Search API ｜ 筛选：近7天创建 ｜ 按 Star 降序",
        f"> 自动生成于 {d}，由 GitHub 星榜整理。",
        "",
        "每天扫描 GitHub 近一周新创建且迅速涨星的项目，精选 Top "
        f"{len(items)} 做中文简介，帮你紧跟开源前沿。",
        "",
        "---",
        "",
    ]
    for i, (repo, summary) in enumerate(items, 1):
        full = repo["full_name"]
        url = repo["html_url"]
        stars = repo.get("stargazers_count", 0)
        lang = repo.get("language") or "N/A"
        forks = repo.get("forks_count", 0)
        license_name = (repo.get("license") or {}).get("name") or "N/A"
        topics = ", ".join(repo.get("topics", [])) or "无"
        lines.append(f"## {i}. {full} ⭐ {stars}")
        lines.append("")
        lines.append(f"- 仓库：{url}")
        lines.append(f"- 语言：{lang} ｜ Fork：{forks} ｜ License：{license_name}")
        lines.append(f"- Topics：{topics}")
        lines.append("")
        lines.append(summary)
        lines.append("")
        lines.append("---")
        lines.append("")
    lines.append(f"\n> 本文由 {d} 自动生成。如有兴趣，可前往仓库给作者点个 Star。")
    return "\n".join(lines)


def save_article(md: str, output_dir: str, article_date: str = None) -> str:
    import os
    os.makedirs(output_dir, exist_ok=True)
    d = article_date or date.today().isoformat()
    path = os.path.join(output_dir, f"{d}-top10.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path
