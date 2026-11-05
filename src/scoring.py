"""透明质量分：把「评价好的项目」变成可复核、可写进文章的公开指标。

GitHub 没有原生评分。这里用四类完全来自公共接口的代理指标合成 0-100 分，
每一项都保留原始值和得分，读者可以自己核对，模型不参与打分。

    累计收藏 40 + 收藏/复制比 20 + 最近维护 25 + 文档与许可 15 = 100

注意：收藏/复制比反映「关注」与「实际动手」的比例，不是好坏的绝对标准，
因此用分段档位而非线性放大，避免极端值主导排序。
"""

import math
import re
from datetime import datetime, timezone

WEIGHTS = {"stars": 40, "ratio": 20, "activity": 25, "docs": 15}

FORMULA = (
    "综合质量分 = 累计收藏(40) + 收藏/复制比(20) + 最近维护(25) + 文档与许可(15)，"
    "满分 100；四项均取自 GitHub 公开数据，可在项目主页自行复核。"
)

_LABELS = {
    "stars": "累计收藏",
    "ratio": "收藏/复制比",
    "activity": "最近维护",
    "docs": "文档与许可",
}


def label(part: str) -> str:
    return _LABELS.get(part, part)


def _haystack(repo: dict) -> str:
    parts = [repo.get("full_name", ""), repo.get("description") or ""]
    parts.extend(repo.get("topics") or [])
    return " ".join(parts).lower()


def _word_hit(text: str, word: str) -> bool:
    """英文按词边界匹配（defi 不命中 definition），中文按子串匹配。"""
    w = str(word).lower()
    if not w:
        return False
    if re.search(r"[a-z]", w):
        return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])",
                         text) is not None
    return w in text


def matches_category(repo: dict, category: dict) -> bool:
    """归类必须有文本证据，不因「被这个关键词搜到」就直接放行。

    GitHub 中文分词与子串匹配很宽松（「defi」能搜到 DefinitelyTyped、
    「八字」能搜到计算机基础笔记），所以：
    - 高专指度 strong 词命中 name / topics / description 任一处即通过
    - 泛化 weak 词（quant、finance 等）必须两个不同词共现才通过
    """
    name = repo.get("full_name", "").split("/")[-1].lower()
    topics = " ".join(repo.get("topics") or []).lower()
    desc = (repo.get("description") or "").lower()
    strong = category.get("strong") or category.get("match") or []
    weak = category.get("weak") or []

    # 仓库名里出现主题词，是最强的归类证据
    if any(_word_hit(name, w) for w in strong):
        return True
    # 只在标签/描述里出现时，要求两个不同主题词共现：
    # 「Ajenti ... stock plugins」「C++ DataFrame ... financial」这类顺带提一词的会被挡掉
    secondary = {w for w in strong
                 if _word_hit(topics, w) or _word_hit(desc, w)}
    if len(secondary) >= 2:
        return True
    weak_hits = {w for w in weak
                 if _word_hit(name, w) or _word_hit(topics, w)
                 or _word_hit(desc, w)}
    return len(weak_hits) >= 2


def _days_since(iso: str, now: datetime):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (now - dt).days)
    except (ValueError, TypeError):
        return None


def _ratio_grade(ratio: float) -> tuple:
    """返回 (0-1 系数, 档位说明)。中间区间得分最高，两端保守。"""
    if ratio < 1:
        return 0.20, "复制多于收藏"
    if ratio < 4:
        return 0.40, "以动手改造为主"
    if ratio < 8:
        return 0.70, "关注与使用接近"
    if ratio <= 25:
        return 1.00, "关注与使用比例健康"
    if ratio <= 60:
        return 0.80, "关注明显多于动手"
    return 0.60, "关注远多于动手"


def score_repo(repo: dict, now: datetime = None) -> dict:
    """给单个仓库打分，返回总分 + 四项原始值/得分 + 一句可读依据。"""
    now = now or datetime.now(timezone.utc)
    stars = max(0, int(repo.get("stargazers_count") or 0))
    forks = max(0, int(repo.get("forks_count") or 0))
    archived = bool(repo.get("archived"))

    # 1) 累计收藏：对数压缩，避免头部项目永远霸榜
    star_co = min(1.0, math.log10(stars + 1) / 4.0)
    s_stars = round(star_co * WEIGHTS["stars"], 1)

    # 2) 收藏/复制比：分段档位，不把极端比值当质量
    ratio = round(stars / max(forks, 1), 1)
    ratio_co, grade = _ratio_grade(ratio)
    s_ratio = round(ratio_co * WEIGHTS["ratio"], 1)

    # 3) 最近维护：按最近一次 push 距今分档，归档项目记 0
    days = _days_since(repo.get("pushed_at"), now)
    if archived or days is None:
        act_co, act_note = 0.0, "归档或无更新时间"
    elif days <= 30:
        act_co, act_note = 1.0, f"{days} 天前更新"
    elif days <= 90:
        act_co, act_note = 0.8, f"{days} 天前更新"
    elif days <= 180:
        act_co, act_note = 0.6, f"{days} 天前更新"
    elif days <= 365:
        act_co, act_note = 0.35, f"{days} 天前更新"
    else:
        act_co, act_note = 0.1, f"{days} 天前更新"
    s_activity = round(act_co * WEIGHTS["activity"], 1)

    # 4) 文档与许可：四个可核查的存在性信号
    desc = bool((repo.get("description") or "").strip())
    lic = (repo.get("license") or {}).get("name") or ""
    topics = repo.get("topics") or []
    homepage = repo.get("homepage") or ""
    doc_co = (0.3 if desc else 0) + (0.3 if lic else 0) \
        + (0.2 if len(topics) >= 2 else (0.1 if topics else 0)) \
        + (0.2 if homepage else 0)
    s_docs = round(doc_co * WEIGHTS["docs"], 1)
    doc_note = "、".join(x for x in [
        "有简介" if desc else "无简介",
        f"{lic} 许可" if lic else "无许可",
        f"{len(topics)} 个标签" if topics else "无标签",
        "有主页" if homepage else "无主页",
    ])

    parts = {
        "stars": {"score": s_stars, "max": WEIGHTS["stars"], "value": stars},
        "ratio": {"score": s_ratio, "max": WEIGHTS["ratio"],
                  "value": ratio, "grade": grade},
        "activity": {"score": s_activity, "max": WEIGHTS["activity"],
                     "value": days, "note": act_note},
        "docs": {"score": s_docs, "max": WEIGHTS["docs"], "note": doc_note},
    }
    total = round(sum(p["score"] for p in parts.values()), 1)
    evidence = (
        f"累计 {stars:,} 收藏（{s_stars:.1f}/{WEIGHTS['stars']}）；"
        f"收藏/复制比 {ratio}，{grade}（{s_ratio:.1f}/{WEIGHTS['ratio']}）；"
        f"{act_note}（{s_activity:.1f}/{WEIGHTS['activity']}）；"
        f"{doc_note}（{s_docs:.1f}/{WEIGHTS['docs']}）"
    )
    return {"total": total, "parts": parts, "evidence": evidence,
            "formula": FORMULA}


def group_items(items: list, categories: list) -> list:
    """按分类顺序把 [(repo, summary)] 分组，返回 [(category, items), ...]。

    无 category 的旧数据归入第一类，保证历史文章与离线测试不会凭空丢项目。
    """
    buckets = {c["key"]: [] for c in categories}
    fallback = categories[0]["key"] if categories else None
    for pair in items:
        key = (pair[0] or {}).get("category") or fallback
        buckets.setdefault(key, []).append(pair)
    return [(c, buckets.get(c["key"], [])) for c in categories]


def rank(repos: list, category: dict, now: datetime = None) -> list:
    """过滤归类、打分、按总分降序。返回带 category / _score 的新字典列表。"""
    out = []
    for r in repos:
        if r.get("fork") or r.get("archived"):
            continue
        if not matches_category(r, category):
            continue
        row = dict(r)
        row["category"] = category["key"]
        row["category_label"] = category["label"]
        row["_score"] = score_repo(row, now)
        out.append(row)
    out.sort(key=lambda r: (r["_score"]["total"],
                            r.get("stargazers_count", 0),
                            r.get("full_name", "")), reverse=True)
    return out
