"""LLM 调研模块：用 OpenAI 兼容接口生成项目中文简介；未配置时降级为模板。"""

import requests

SYSTEM_PROMPT = (
    "你是一位资深技术博主，擅长用简洁清晰的中文介绍开源项目。"
    "请基于 GitHub 仓库元信息与 README，输出一段中文项目简介，"
    "严格使用以下 Markdown 结构（不要加一级标题，不要加粗字段名）：\n"
    "- 一句话定位：用一句话概括这个项目是什么、解决什么问题\n"
    "- 核心功能：3-5 条要点\n"
    "- 适用场景：目标用户与典型用法\n"
    "- 技术栈：主要语言与依赖\n"
    "- 上手难度：简单/中等/较高，并说明\n"
    "- 活跃度：根据近期更新与 star 增长简评\n"
    "要求：客观、不夸大、不编造未给出的信息，总字数 250-400 字。"
)


def research(repo: dict, readme: str, config) -> str:
    if config.LLM_ENABLED:
        try:
            return _llm_summarize(repo, readme, config)
        except Exception as e:
            return _fallback(repo, readme, f"\n\n> （LLM 调用失败：{e}，以下为模板简介）")
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
        f"- Star：{repo.get('stargazers_count', 0)}\n"
        f"- Fork：{repo.get('forks_count', 0)}\n"
        f"- License：{(repo.get('license') or {}).get('name') or 'N/A'}\n"
        f"- Topics：{', '.join(repo.get('topics', [])) or '无'}\n"
        f"- 创建时间：{repo.get('created_at', 'N/A')}\n"
        f"- 最近推送：{repo.get('pushed_at', 'N/A')}\n"
        f"- Open Issues：{repo.get('open_issues_count', 0)}"
    )


def _fallback(repo: dict, readme: str, note: str = "") -> str:
    desc = repo.get("description") or "暂无描述"
    excerpt = (readme[:400].strip() if readme else "（无 README）")
    return (
        f"- 一句话定位：{desc}\n"
        f"- 核心功能：见 README\n"
        f"- 适用场景：见 README\n"
        f"- 技术栈：{repo.get('language') or 'N/A'}\n"
        f"- 上手难度：待评估\n"
        f"- 活跃度：Star {repo.get('stargazers_count', 0)}，"
        f"最近推送 {repo.get('pushed_at', 'N/A')}\n\n"
        f"> README 节选：\n> {excerpt}{note}"
    )
