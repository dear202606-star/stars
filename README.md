# GitHub 每日新晋热门 Top10

每天扫描 GitHub 近 7 天新创建且迅速涨星的项目，精选 Top10 生成中文简介，输出为 Markdown 文章，便于发微信公众号。

## 工作流程

```
GitHub Search API 采集 -> 过滤列表/教程类 -> SQLite 去重 -> 抓 README
-> LLM 生成中文简介(可选) -> 输出 Markdown 文章
```

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置（可选但推荐）

在项目根目录创建 `.env` 文件：

```env
# GitHub Token（强烈建议配置，否则 Search API 速率仅 10 次/分钟）
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# LLM 配置（OpenAI 兼容接口，留空则用模板模式）
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxxxxxxx
LLM_MODEL=gpt-4o-mini
```

> 也支持 DeepSeek、智谱、Moonshot 等任何 OpenAI 兼容服务，改 `LLM_BASE_URL` 和 `LLM_MODEL` 即可。

### 3. 运行

```powershell
python run.py
```

输出文件：`output/YYYY-MM-DD-top10.md`

### 常用参数

```powershell
python run.py --no-llm          # 强制模板模式，不调用 LLM
python run.py --top 5           # 只取 Top5
python run.py --date 2026-07-19 # 指定日期
```

## 筛选策略

- **近 7 天创建** 且 **star > 50** 的新晋项目
- 按 star 降序，构建候选池（最多 250 个）
- 排除 fork、awesome/面试/教程类仓库
- 跨天去重：已推荐过的项目优先跳过，保证内容新鲜

## 输出示例

```markdown
# GitHub 本周新晋热门 Top10（2026-07-20）

## 1. owner/repo ⭐ 1234
- 仓库：https://github.com/owner/repo
- 语言：Python ｜ Fork：56 ｜ License：MIT
- Topics：ai, llm

- 一句话定位：...
- 核心功能：...
- 适用场景：...
...
```

## 定时自动化

可配合 CodeBuddy 的 automation 功能每日定时执行 `python run.py`。

## 目录结构

```
githubStars/
├── config.py            # 配置（读环境变量/.env）
├── run.py               # 主入口
├── src/
│   ├── github_client.py # GitHub API 采集
│   ├── snapshot.py      # SQLite 去重
│   ├── researcher.py    # LLM/模板调研
│   └── article.py       # 文章排版
├── data/                # SQLite 数据库（运行时生成）
└── output/              # 每日文章（运行时生成）
```
