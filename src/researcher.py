"""LLM 调研模块：给普通读者写一页克制、好读的短札。

不解释筛选、打分、收录、更新这些幕后过程，也不罗列指标。
未配置 LLM 时降级为模板，语气与正式稿一致。
"""

import re
from datetime import datetime, timezone

import requests

from src import scoring

# 两个 prompt 共用的编辑准则
STYLE_RULES = (
    "- 说人话，但不幼稚：禁止「小助手、干活、交差、开个工位、一键搞定、神器」这类"
    "拟人化或卖萌表达；用平实、准确的中文\n"
    "- 禁止空话套话：「致力于、赋能、一站式、无缝、开箱即用、生态、闭环、降本增效、助力」\n"
    "- 禁止 AI 连接词与句式：「值得注意的是、总的来说、不仅…而且…、"
    "在当今…背景下、首先/其次/最后、此外、值得一提的是」\n"
    "- 别用「该项目、本品、本工具」，写「它、这个项目」\n"
    "- 专业词第一次出现时用一句生活化的话解释清楚，之后可直接使用，不要堆术语\n"
    "- 不解释筛选、打分、收录、更新这类幕后过程，也不要写「本榜」「本期」「按…选出」\n"
    "- 不罗列指标、公式、分数、权重；最多自然地带出一两个真实数字"
    "（如「七万多人收藏」）\n"
    "- 判断要有依据：能引用给定资料就自然带一句；没有依据时明说"
    "「公开信息里看不出来」，不要猜测媒体曝光、大厂背书或团队背景\n"
    "- 客观，不夸大、不编造 README 与元信息里没有的功能\n"
    "- 不用「新晋、刚火、暴涨、新星、黑马、广受好评、社区活跃」这类追新或无来源的说法\n"
    "- 不用 emoji，不用破折号堆砌，不用感叹号\n"
    "- 语气像一页写得克制的杂志短札，不像产品说明书或评测报告\n"
    "- 自检：一个不懂技术的成年人读完，能准确复述这是做什么的、自己要不要用"
)

SYSTEM_PROMPT = (
    "你在给普通读者写一页短札。读者不懂技术，不想被哄着说话，也不想读说明书。"
    "语气克制、自然、有判断力，像一页写得很好的杂志笔记。\n\n"
    "请严格用以下结构输出。每个小标题单独一行、用 **加粗** 包起来、后面不要跟冒号或正文；"
    "有多条要点时每条必须以 `- ` 开头：\n\n"
    "**这是什么**\n"
    "一句话给出定义和类别，让人立刻知道它属于哪类东西、解决什么问题。"
    "例如不要写「基于 LLM 的 RAG 框架」，要写「一个把资料整理好交给 AI 使用的工具」。\n\n"
    "**能做什么**\n"
    "2-3 条具体能力，每条一个事实，用「它可以……」「支持……」这类陈述句。"
    "不写空泛的宣传语。\n\n"
    "**上手难不难**\n"
    "用一句话说清普通人要跨过什么门槛，比如要不要装东西、要不要看懂命令行。"
    "禁止用星星或其他符号表示难度。\n\n"
    "**谁最适合用**\n"
    "指出一到两类具体人群，以及它能替他们省掉哪一件事。避免「所有人都能用」。\n\n"
    "**为什么值得关注**\n"
    "用一两句自然的话说出它为什么值得留意：它替人省掉了哪件麻烦事，"
    "公开信息里哪些细节让人放心（比如一直在更新、说明写得清楚、很多人长期收藏）。"
    "最多带一个真实数字。不要罗列指标、不要解释分数或筛选规则、"
    "不要写它是怎么被选进来的。数据不足以判断时如实说「公开信息里看不出来」。"
    "不要编造媒体报道、公司背书或融资信息。\n\n"
    f"编辑准则：\n{STYLE_RULES}\n"
    "- 总字数 180-280 字"
)

OVERVIEW_PROMPT = (
    "你要为「两仪」写一页刊首的题记。这一页分「数」与「象」两栏，"
    "各自收了几个值得留意的开源项目。\n"
    "读下面的项目资料，用两到三句话点出今天这两栏各自在讲什么，"
    "让没读过的人也愿意往下看。\n\n"
    "要求：\n"
    "- 至少提到一个真实项目名或真实数字，不写「都在让工具更好用」这类空话\n"
    "- 不做预测、不喊口号、不编造趋势、不解释这一页是怎么来的\n"
    "- 不写「新晋/刚火/暴涨/评分/筛选/收录/轮播/自动生成」\n"
    f"{STYLE_RULES}\n"
    "- 80-150 字，直接输出正文，不要标题、不要前缀"
)


def research(repo: dict, readme: str, config) -> str:
    if config.LLM_ENABLED:
        try:
            return _llm_summarize(repo, readme, config)
        except Exception as e:
            # 错误只进运行日志，不写进读者看到的文字
            print(f"      [警告] 简介生成失败，改用模板："
                  f"{type(e).__name__}: {e}")
    return _fallback(repo, readme)


def _llm_summarize(repo: dict, readme: str, config) -> str:
    user_prompt = (
        f"仓库：{repo['full_name']}\n{_meta_block(repo, config)}\n\n"
        f"README（节选）：\n{readme[:3000] if readme else '（无 README）'}\n\n"
        "请按指定结构输出中文速览。"
    )
    resp = requests.post(
        f"{config.LLM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model": config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.5,
            "max_tokens": 800,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError(f"LLM 返回空 choices，响应: {str(data)[:300]}")
    content = choices[0].get("message", {}).get("content", "")
    if not content or not content.strip():
        raise ValueError("LLM 返回内容为空")
    return content.strip()


def _days_since(created_at: str) -> str:
    if not created_at:
        return "未知"
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        return f"{max(0, days)} 天"
    except Exception:
        return "未知"


def _category_label(key: str, config=None) -> str:
    for c in getattr(config, "CATEGORIES", []) or []:
        if c.get("key") == key:
            return c.get("label", key)
    return key or "未分类"


def _meta_block(repo: dict, config=None) -> str:
    """给 LLM 的背景资料：只留可写进文章的事实，不给公式与过程。"""
    return "\n".join([
        f"栏目：{repo.get('category_label') or _category_label(repo.get('category'), config)}",
        f"项目自己的介绍：{repo.get('description') or '无'}",
        f"多少人收藏：{repo.get('stargazers_count', 0):,}",
        f"被复制：{repo.get('forks_count', 0):,}",
        f"创建至今：{_days_since(repo.get('created_at'))}",
        f"最近更新：{repo.get('pushed_at') or '未知'}",
        f"主语言：{repo.get('language') or '未标注'}",
        f"许可：{(repo.get('license') or {}).get('name') or '未标注'}",
        f"标签：{', '.join(repo.get('topics', [])) or '无'}",
    ])


def generate_overview(repos: list, config) -> str:
    """生成 2-3 句本期看点。失败返回空串（站点会补占位文案）。"""
    if not config.LLM_ENABLED or not repos:
        return ""
    try:
        repo_lines = "\n".join(
            f"- {r.get('category_label') or _category_label(r.get('category'), config)}"
            f"｜{r['full_name']}｜{r.get('stargazers_count', 0):,} 人收藏｜"
            f"标签：{', '.join(r.get('topics', [])) or '无'}｜"
            f"简介：{r.get('description') or '无'}"
            for r in repos
        )
        resp = requests.post(
            f"{config.LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": config.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": OVERVIEW_PROMPT},
                    {"role": "user", "content": f"今天这一页的项目：\n{repo_lines}"},
                ],
                "temperature": 0.5,
                "max_tokens": 300,
            },
            timeout=45,
        )
        resp.raise_for_status()
        choices = resp.json().get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content", "").strip()
            return re.sub(r"^(本期看点|看点|题记|总结)\s*[：:]\s*", "", text).strip()
    except Exception:
        pass
    return ""


def _fallback(repo: dict, readme: str, note: str = "") -> str:
    """降级稿同样是一页短札，不塞英文原文、指标或幕后过程。"""
    desc = repo.get("description") or "项目页暂未提供简介"
    is_en = not re.search(r"[\u4e00-\u9fff]", desc)
    what = (f"项目页上的介绍是：{desc}。是英文，暂未译出。"
            if is_en else f"{desc.strip('。.')}。")
    return (
        f"**这是什么**\n{what}\n\n"
        f"**能做什么**\n"
        "- 具体能做什么写在项目页，通常配有截图和说明。\n"
        "- 这次没能把简介写完，建议直接看项目页确认。\n\n"
        f"**上手难不难**\n要按项目页的说明安装和配置，具体以文档为准。\n\n"
        f"**谁最适合用**\n正为这类事费神、愿意自己动手试一试的人。\n\n"
        f"**为什么值得关注**\n{scoring.plain_evidence(repo)}"
        f"这些都写在公开的项目页上。{note}"
    )
