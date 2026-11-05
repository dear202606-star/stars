"""文章排版：组装微信公众号友好的 Markdown 文章。

顺序按普通读者的价值排序：先大白话简介，技术信息放最后。
"""

from datetime import date


def build_article(items: list, article_date: str = None, overview: str = "") -> str:
    """items: [(repo, summary), ...]"""
    d = article_date or date.today().isoformat()
    lines = [
        f"# GitHub 本周新晋热门 Top{len(items)}（{d}）",
        "",
        f"> 用大白话讲清楚每个项目，不懂技术也能看懂。",
        f"> 数据来源：GitHub ｜ 近{_days_label()}新冒出来的高收藏项目 ｜ {d} 自动生成",
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
        lines.append(f"## {i}. {full}（{stars:,} 人收藏）")
        lines.append("")
        lines.append(summary)  # 人话简介在前
        lines.append("")
        lines.append(f"> 项目主页：{url}")
        lines.append("> 主语言：%s ｜ 被 %s 人复制 ｜ 使用许可：%s" % (
            repo.get("language") or "未标注",
            f"{repo.get('forks_count', 0):,}",
            (repo.get("license") or {}).get("name") or "未标注"))
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"\n> 本文由 {d} 自动生成。觉得有意思，可以去项目主页给作者点个收藏。")
    return "\n".join(lines)


def _days_label() -> str:
    try:
        import config
        return f"近{config.DAYS_BACK}天"
    except Exception:
        return "近7天"


def save_article(md: str, output_dir: str, article_date: str = None) -> str:
    import os
    os.makedirs(output_dir, exist_ok=True)
    d = article_date or date.today().isoformat()
    path = os.path.join(output_dir, f"{d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path
