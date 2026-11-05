"""文章排版：组装微信公众号友好的 Markdown 文章。

顺序按普通读者的价值排序：先简明速览，技术信息放最后。
"""

from datetime import date


def build_article(items: list, article_date: str = None, overview: str = "") -> str:
    """items: [(repo, summary), ...]"""
    d = article_date or date.today().isoformat()
    lines = [
        f"# GitHub 本周新晋热门 Top{len(items)}（{d}）",
        "",
        f"> 数据来源：GitHub 公共接口 ｜ 筛选近 {_days_label()}创建、收藏数增长最快的项目 ｜ {d} 自动生成",
        "",
    ]
    if overview:
        lines.append(f"**本期看点**：{overview}")
        lines.append("")
    lines.extend(["---", ""])

    for i, (repo, summary) in enumerate(items, 1):
        full = repo["full_name"]
        url = repo["html_url"]
        stars = repo.get("stargazers_count", 0)
        lines.append(f"## {i:02d}　{full}")
        lines.append("")
        lines.append(f"**{stars:,} 收藏**　·　主语言 {repo.get('language') or '未标注'}　·　"
                     f"被复制 {repo.get('forks_count', 0):,} 次")
        lines.append("")
        lines.append(summary)  # 速览在前
        lines.append("")
        lines.append(f"> 项目主页：{url}")
        lines.append(f"> 使用许可：{(repo.get('license') or {}).get('name') or '未标注'}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"\n> 本文由 {d} 自动生成。内容基于项目公开信息整理，具体能力请以项目主页为准。")
    return "\n".join(lines)


def _days_label() -> str:
    try:
        import config
        return f"{config.DAYS_BACK} 天内"
    except Exception:
        return "7 天内"


def save_article(md: str, output_dir: str, article_date: str = None) -> str:
    import os
    os.makedirs(output_dir, exist_ok=True)
    d = article_date or date.today().isoformat()
    path = os.path.join(output_dir, f"{d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path
