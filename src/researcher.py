"""LLM 调研模块：生成面向普通读者的大白话简介，未配置 LLM 时降级为模板。"""

import re

import requests

# 两个 prompt 共用的风格铁律，避免"导读"和"正文"两套口气
STYLE_RULES = (
    "- 大白话，像跟朋友聊天，禁止用「致力于、赋能、一站式、无缝、开箱即用、"
    "生态、闭环、降本增效、助力」这类套话\n"
    "- 禁止 AI 连接词和句式：「值得注意的是、总的来说、不仅…而且…、"
    "在当今…背景下、首先/其次/最后、此外、值得一提的是」\n"
    "- 别用「该项目、本品、本工具」，要写「它、这个项目」\n"
    "- 遇到专业词一律换成生活里的类比；换不掉就整句删掉，不要加括号解释术语\n"
    "- 别堆 emoji，别滥用破折号\n"
    "- 客观真实，README 和元信息里没有的不要编造，不知道就写「暂不确定」\n"
    "- 自检：读给完全不懂电脑的人听，任何一处要停下来想一下，就重写"
)

SYSTEM_PROMPT = (
    "你是一个给朋友推荐好东西的人，现在要用大白话介绍一个开源项目。"
    "读者是不太懂技术的普通人，请像聊天一样自然地介绍，绝不能像产品说明书或 AI 生成的八股文。\n\n"
    "请严格用以下结构输出。每个小标题单独一行、用 **加粗** 包起来、后面不要跟冒号或正文；"
    "有多条要点时每条必须以 `- ` 开头：\n\n"
    "**这是什么**\n"
    "用一句大白话说清楚它是干嘛的。比如别写「基于 LLM 的 RAG 框架」，"
    "要写「一个帮你快速给 AI 喂资料的软件」。\n\n"
    "**能做什么**\n"
    "2-3 条要点，每条用「它能……」「你可以……」开头，讲一个具体本事。\n\n"
    "**上手难不难**\n"
    "只能用这三种说法之一，后面加一句为什么："
    "「很简单，点开就能用」/「要装点东西，跟着说明走就行」/「得懂点编程」。\n"
    "禁止用星星或其他符号表示难度。\n\n"
    "**谁最适合用**\n"
    "一句话说出哪类人最需要它、能省掉什么麻烦。\n\n"
    "**为什么火**\n"
    "它最近为什么受关注。没线索就写「暂不确定」，别编。\n\n"
    f"写作铁律：\n{STYLE_RULES}\n"
    "- 总字数 150-250 字，别写长"
)

OVERVIEW_PROMPT = (
    "你是一个给普通读者写技术速览的编辑。基于今天的榜单，用 2-3 句大白话说说"
    "这批项目整体在忙什么、有什么共同点。\n\n"
    f"写作铁律：\n{STYLE_RULES}\n"
    "- 80-150 字，直接输出总结，不要标题、不要「本期看点」前缀"
)


def research(repo: dict, readme: str, config) -> str:
    if config.LLM_ENABLED:
        try:
            return _llm_summarize(repo, readme, config)
        except Exception as e:
            return _fallback(repo, readme, f"（AI 简介生成失败：{e}）")
    return _fallback(repo, readme)


def _llm_summarize(repo: dict, readme: str, config) -> str:
    meta = _meta_block(repo)
    user_prompt = (
        f"仓库：{repo['full_name']}\n{meta}\n\n"
        f"README（节选）：\n{readme[:3000] if readme else '（无 README）'}\n\n"
        "请按指定结构输出中文简介。"
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
            "max_tokens": 700,
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


def _meta_block(repo: dict) -> str:
    return (
        f"- 描述：{repo.get('description') or '无'}\n"
        f"- 主语言：{repo.get('language') or 'N/A'}\n"
        f"- 收藏数：{repo.get('stargazers_count', 0)}\n"
        f"- 被复制数：{repo.get('forks_count', 0)}\n"
        f"- 使用许可：{(repo.get('license') or {}).get('name') or 'N/A'}\n"
        f"- 标签：{', '.join(repo.get('topics', [])) or '无'}\n"
        f"- 创建时间：{repo.get('created_at', 'N/A')}\n"
        f"- 最近更新：{repo.get('pushed_at', 'N/A')}"
    )


def generate_overview(repos: list, config) -> str:
    """生成 2-3 句本期看点。失败返回空串（站点会补占位文案）。"""
    if not config.LLM_ENABLED or not repos:
        return ""
    try:
        repo_lines = "\n".join(
            f"- {r['full_name']}（{r.get('stargazers_count', 0)} 人收藏）: "
            f"{r.get('description') or '无'}"
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
                    {"role": "user", "content": f"本期榜单：\n{repo_lines}"},
                ],
                "temperature": 0.5,
                "max_tokens": 250,
            },
            timeout=45,
        )
        resp.raise_for_status()
        choices = resp.json().get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content", "").strip()
            # 归一化：去掉模型可能自带的前缀
            return re.sub(r"^(本期看点|看点|总结)\s*[：:]\s*", "", text).strip()
    except Exception:
        pass
    return ""


def _fallback(repo: dict, readme: str, note: str = "") -> str:
    """未配置 LLM 时的降级模板：同样说人话，不塞英文原文和占位符。"""
    desc = repo.get("description") or "项目主页暂时没有写简介"
    is_en = not re.search(r"[\u4e00-\u9fff]", desc)
    what = f"这是一个用来{desc.strip('。.')}的工具。" if not is_en else (
        f"项目主页上写的是：{desc}（原描述是英文）")
    stars = repo.get("stargazers_count", 0)
    return (
        f"**这是什么**\n{what}\n\n"
        f"**能做什么**\n"
        "- 具体功能写在项目主页上，点下面「去 GitHub 看看这个项目」就能看到。\n"
        "- 主页通常是英文的，看不懂可以只看截图和动图。\n\n"
        f"**上手难不难**\n要装点东西，跟着主页的说明走就行。\n\n"
        f"**谁最适合用**\n需要这类工具的人，具体能省什么事得看项目主页的介绍。\n\n"
        f"**为什么火**\n目前有 {stars:,} 人收藏，是最近一周新冒出来的热门项目。{note}"
    )
