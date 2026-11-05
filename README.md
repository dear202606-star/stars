# GitHub 每日新晋热门 Top10

每天自动扫描 GitHub 近 7 天新创建、迅速涨星的项目，精选 Top10，用**大白话**写成中文简介，
自动发布成网页。目标读者是**不太懂技术的普通人**。

产出两套：
- **`docs/` 站点**（GitHub Pages，给普通读者看）
- **`output/*.md` + `docs/posts/*.md`**（纯文本，给公众号运营者复制）

## 全链路自动化

整个流程跑在 GitHub 云端，不依赖本地电脑开机，也不需要维护长期有效的 API Token：

```
GitHub Actions 定时(每天北京 09:07)
  → 内置 GITHUB_TOKEN 调 GitHub API 采集
  → 读取 data/history.json 跨天去重
  → 抓取 README
  → DeepSeek 生成大白话简介 + 本期看点
  → 生成 Markdown 文章 + 响应式静态站点
  → 单元测试（28 项）
  → 持久化到 Supabase（文章 / 项目 / 去重历史）
  → 自动 commit/push 回仓库
  → GitHub Pages 自动部署（仓库为 Public 时）
```

站点地址（仓库公开后）：`https://dear202606-star.github.io/stars/`

### 已配置完成的 Secrets

| Secret | 用途 |
|--------|------|
| `LLM_API_KEY` | DeepSeek API Key |
| `SUPABASE_URL` | `https://kzfdxhooplhaydohqlyq.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Supabase service_role key（服务端写入，绕过 RLS） |

> GitHub API 用的是 Actions 自动注入的 `GITHUB_TOKEN`（每次运行新生成、永不过期），
> **无需**维护个人 PAT。以上 Secrets 已通过 GitHub API 写入仓库，无需手工配置。
> `SUPABASE_REQUIRED=1`：云端写 Supabase 失败即让任务失败，避免静默丢数据；
> 本地未配置时自动跳过，不阻断文章生成。

### GitHub Pages（已启用）

仓库为 **Public**，Pages 已通过 API 启用为 `workflow` 构建模式，
每日任务完成后自动部署，无需任何手工操作。
workflow 内置可用性检查：若仓库被改回私有，会自动跳过部署并给出告警，
不影响文章生成与 Supabase 持久化。

> 免费计划不支持私有仓库 Pages。公开前已扫描全部 git 历史，确认无密钥残留。

### 手动触发

`Actions → 每日 GitHub 新晋热门 Top10 → Run workflow`，支持指定日期和 Top N，
用于补跑或测试。同日重跑会复用同一批项目，文章不会漂移。

## Supabase 持久化

三张表（`scripts/init_supabase.py` 幂等建表，已在线创建完成，均启用 RLS）：

| 表 | 主键 | 内容 |
|----|------|------|
| `daily_articles` | `article_date` | 标题、本期看点、项目数、Markdown 全文、站点/文章路径 |
| `daily_projects` | `(article_date, full_name)` | 排名、收藏数、语言、许可、标签、大白话简介、`sections` JSONB（五字段结构化）、原始元数据 |
| `recommended_history` | `full_name` | 跨天去重历史 |

写入走 **PostgREST REST API**（`src/supabase_store.py`），纯 HTTPS 443、无数据库驱动、
无区域/IPv6 问题；按主键 upsert，同日重跑幂等，并会清掉本期不再列出的项目。

表结构变更时重新执行（需 Management API token，仅一次性、非每日任务）：

```powershell
$env:SUPABASE_ACCESS_TOKEN="sbp_xxx"
python scripts/init_supabase.py
```

> 密钥只放 GitHub Secrets，绝不写进代码或提交到仓库。
> `scripts/init_supabase.py` 只用于一次性建表，日常任务不执行。

## 本地运行

```powershell
pip install -r requirements.txt
python run.py
```

可选参数：

```powershell
python run.py --top 5              # 只取 Top5
python run.py --date 2026-11-05    # 指定日期（同日重跑会复用同一批项目）
python run.py --no-llm             # 不调用 LLM，用降级模板
python run.py --no-site            # 只生成 Markdown，不生成站点
python -m unittest discover -s tests -v   # 跑全套测试（28 项，无需网络）
```

本地配置在项目根目录 `.env`（参考 `.env.example`）：

```env
GITHUB_TOKEN=ghp_xxx          # 本地必填；CI 中不需要
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
TZ_OFFSET_HOURS=8
```

> 优先级：系统环境变量 > `.env` > 代码默认值。**密钥只放 `.env` 或 CI Secret，
> 绝不要写进 `config.py`**（会被提交泄露）。

## 内容模板（面向普通读者）

每个项目固定 5 段，按普通人的阅读价值排序：

| 字段 | 作用 |
|------|------|
| **这是什么** | 一句大白话说清楚它是干嘛的，不许堆术语 |
| **能做什么** | 2-3 条具体本事 |
| **上手难不难** | 文字描述（很简单 / 要装点东西 / 得懂编程），不用星级符号 |
| **谁最适合用** | 哪类人、省掉什么麻烦 |
| **为什么火** | 没线索就写「暂不确定」，不许编 |

风格铁律（`src/researcher.py` 的 `STYLE_RULES`，两个 prompt 共用）：
禁用「致力于/赋能/一站式/生态/闭环」等套话、禁用 AI 连接词、
术语一律换生活类比换不掉就删、不知道就直说、读给不懂电脑的人听不能卡壳。

站点设计：人话简介在前，技术元数据（语言/Fork/许可/标签）默认折叠进
「项目详情（给懂技术的人）」；卡片字段是 `<h3>` 标题便于读屏导航；
有跳过链接、键盘焦点样式、常驻下划线、深浅色适配、移动端响应式。

## 准确性与及时性设计

| 保障 | 实现 |
|------|------|
| 不漏跑 | GitHub Actions 云端 cron，与本地开机状态无关 |
| Token 不过期 | 内置 `GITHUB_TOKEN` 每次运行自动注入，无需 PAT |
| 时区正确 | 按 UTC+8 取文章日期（CI runner 默认 UTC） |
| 同日重跑结果一致 | `day_selection` 快照复用同一批项目，文章不漂移 |
| 跨天不重复 | `data/history.json` 随仓库持久化，新项目优先 |
| 抗瞬时故障 | 网络超时/5xx 指数退避重试；401/403 明确区分并快速失败 |
| 数据不编造 | prompt 强制「没线索写暂不确定」，降级模板也不塞英文原文 |
| 不破坏已有内容 | 采集为空直接退出；提交前跑 28 项单元测试 |
| 幂等发布 | 文章索引按日期 upsert，无变更则跳过提交 |
| 持久化可靠 | Supabase 按主键 upsert；云端严格模式写失败即告警并失败 |
| 线上无本地依赖 | 全部配置走 GitHub Secrets，全部执行走 Actions，无需本地开机/脚本 |

## 目录结构

```
githubStars/
├── .github/workflows/daily.yml  # GitHub Actions 定时 + Pages 部署
├── config.py                    # 配置（环境变量 / .env）
├── run.py                       # 主流程编排
├── src/
│   ├── github_client.py         # GitHub API 采集 + 重试
│   ├── store.py                 # JSON 历史去重（可随 git 持久化）
│   ├── researcher.py            # 大白话文案模板 + LLM
│   ├── article.py               # Markdown 文章
│   ├── site.py                  # 静态站点生成（含 CSS）
│   └── supabase_store.py        # Supabase REST 持久化
├── scripts/init_supabase.py     # 一次性建表（Management API）
├── tests/                       # 28 项离线测试（单元 + 端到端 + 持久化）
├── docs/                        # GitHub Pages 站点（自动生成、提交）
│   ├── index.html               # 首页（最新一期）
│   ├── posts/YYYY-MM-DD.html    # 每期页面
│   ├── posts/YYYY-MM-DD.md      # 每期纯文本（公众号用）
│   ├── style.css / feed.json
│   └── .nojekyll
├── data/history.json            # 去重历史 + 文章索引（自动生成、提交）
└── output/                      # 本地 Markdown 存档（不提交）
```
