"""LLM 调研模块：生成面向普通读者、专业但好懂的项目速览。

定位是「科技媒体的简明项目速览」：说人话，但不幼稚；每个判断都有依据。
未配置 LLM 时降级为模板，降级稿同样保持专业口吻。
"""

import re
from datetime import datetime, timezone

import requests

# 两个 prompt 共用的编辑准则
STYLE_RULES = (
    "- 说人话，但不幼稚：禁止「小助手、干活、交差、开个工位、一键搞定、神器」这类"
    "拟人化或卖萌表达；用平实、准确的中文\n"
    "- 禁止空话套话：「致力于、赋能、一站式、无缝、开箱即用、生态、闭环、降本增效、助力」\n"
    "- 禁止 AI 连接词与句式：「值得注意的是、总的来说、不仅…而且…、"
    "在当今…背景下、首先/其次/最后、此外、值得一提的是」\n"
    "- 别用「该项目、本品、本工具」，写「它、这个项目」\n"
    "- 专业词第一次出现时用一句生活化的话解释清楚，之后可直接使用，不要堆术语\n"
    "- 每个判断尽量有依据：能引用给定数据（发布天数、收藏数、被复制数、标签）就引用；"
    "没有依据时明确说「公开信息里看不出来」，不要猜测媒体曝光、大厂背书或团队背景\n"
    "- 客观，不夸大、不编造 README 与元信息里没有的功能\n"
    "- 不用 emoji，不用破折号堆砌，不用感叹号\n"
    "- 自检：一个不懂技术的成年人读完，能准确复述这是做什么的、自己要不要用"
)

SYSTEM_PROMPT = (
    "你是科技媒体的编辑，正在为普通读者写一份「开源项目速览」。"
    "读者不是程序员，但希望得到准确、有判断力的信息，而不是被哄着说话。"
    "语气平实、克制、专业，像一份写得很好的产品简报。\n\n"
    "请严格用以下结构输出。每个小标题单独一行、用 **加粗** 包起来、后面不要跟冒号或正文；"
    "有多条要点时每条必须以 `- ` 开头：\n\n"
    "**这是什么**\n"
    "一句话给出定义和类别，让人立刻知道它属于哪类东西、解决什么问题。"
    "例如不要写「基于 LLM 的 RAG 框架」，要写「一个把资料整理好交给 AI 使用的工具」。\n\n"
    "**能做什么**\n"
    "2-3 条具体能力，每条一个事实，用「它可以……」「支持……」这类陈述句。"
    "不写空泛的宣传语。\n\n"
    "**上手难不难**\n"
    "从「很简单，打开就能用」/「要装点东西，跟着说明走就行」/「得懂点编程」中选一个，"
    "再用一句话说明依据（比如需要本地安装、要配密钥、要看懂命令行）。\n"
    "禁止用星星或其他符号表示难度。\n\n"
    "**谁最适合用**\n"
    "指出一到两类具体人群，以及它能替他们省掉哪一件事。避免「所有人都能用」。\n\n"
    "**为什么值得关注**\n"
    "基于给定数据做有依据的解读：它在几天内积累了多少收藏、被复制多少次、"
    "标签指向哪个方向、解决了什么此前麻烦的问题。"
    "如果数据不足以判断原因，就如实写「公开信息里看不出具体原因，但 N 天内积累 X 收藏，"
    "说明关注度确实集中」。不要编造媒体报道、公司背书或融资信息。\n\n"
    f"编辑准则：\n{STYLE_RULES}\n"
    "- 总字数 180-280 字"
)

OVERVIEW_PROMPT = (
    "你是科技媒体的值班编辑，要为今天的开源榜单写一段「本期看点」。\n"
    "基于给定的真实榜单数据（项目名、收藏数、标签、描述），"
    "用 2-3 句话指出这批项目共同在解决什么问题、反映出什么方向。\n\n"
    "要求：\n"
    "- 必须有具体依据，至少提到一个真实项目名或真实数字，不要写「都在让 AI 更强大」这类空话\n"
    "- 不做预测、不喊口号、不编造趋势结论\n"
    f"{STYLE_RULES}\n"
    "- 80-150 字，直接输出正文，不要标题、不要「本期看点」前缀"
)


def research(repo: dict, readme: str, config) -> str:
    if config.LLM_ENABLED:
        try:
            return _llm_summarize(repo, readme, config)
        except Exception as e:
            return _fallback(repo, readme, f"（自动简介生成失败：{e}）")
    return _fallback(repo, readme)


def _llm_summarize(repo: dict, readme: str, config) -> str:
    user_prompt = (
        f"仓库：{repo['full_name']}\n{_meta_block(repo)}\n\n"
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


def _meta_block(repo: dict) -> str:
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    return (
        f"- 官方描述：{repo.get('description') or '无'}\n"
        f"- 主语言：{repo.get('language') or '未标注'}\n"
        f"- 收藏数：{stars:,}\n"
        f"- 被复制数：{forks:,}\n"
        f"- 创建至今：{_days_since(repo.get('created_at'))}（本项目只收录近 7 天新建仓库）\n"
        f"- 使用许可：{(repo.get('license') or {}).get('name') or '未标注'}\n"
        f"- 标签：{', '.join(repo.get('topics', [])) or '无'}\n"
        f"- 最近更新：{repo.get('pushed_at', '未知')}"
    )


def generate_overview(repos: list, config) -> str:
    """生成 2-3 句本期看点。失败返回空串（站点会补占位文案）。"""
    if not config.LLM_ENABLED or not repos:
        return ""
    try:
        repo_lines = "\n".join(
            f"- {r['full_name']}｜{r.get('stargazers_count', 0):,} 收藏｜"
            f"{r.get('forks_count', 0):,} 次复制｜"
            f"标签：{', '.join(r.get('topics', [])) or '无'}｜"
            f"描述：{r.get('description') or '无'}"
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
                    {"role": "user", "content": f"本期榜单真实数据：\n{repo_lines}"},
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
            return re.sub(r"^(本期看点|看点|总结)\s*[：:]\s*", "", text).strip()
    except Exception:
        pass
    return ""


def _fallback(repo: dict, readme: str, note: str = "") -> str:
    """未配置 LLM 时的降级稿：保持专业口吻，不塞英文原文和占位符。"""
    desc = repo.get("description") or "项目主页暂未提供简介"
    is_en = not re.search(r"[\u4e00-\u9fff]", desc)
    what = (f"官方对它的描述是：{desc}。主页为英文，暂未翻译成中文。"
            if is_en else f"{desc.strip('。.')}。")
    stars = repo.get("stargazers_count", 0)
    days = _days_since(repo.get("created_at"))
    return (
        f"**这是什么**\n{what}\n\n"
        f"**能做什么**\n"
        "- 具体功能与使用方法写在项目主页，页面通常配有截图和操作说明。\n"
        "- 本次未能生成自动简介，建议直接查看主页确认能力范围。\n\n"
        f"**上手难不难**\n需要按主页说明安装和配置，具体步骤以项目文档为准。\n\n"
        f"**谁最适合用**\n遇到该类问题、并愿意自行部署工具的人。\n\n"
        f"**为什么值得关注**\n创建至今 {days}，已积累 {stars:,} 收藏，"
        f"是近一周新出现的受关注项目。{note}"
    )
