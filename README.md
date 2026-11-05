# GitHub 双榜 · 金融与道术

每天从 **两个垂直分类** 里各挑 3 个评价好的开源项目：**金融与量化**、**道术 · 玄学术数**
（八字、紫微斗数、风水、易经、占卜、塔罗等）。不做大而全的 Top10，不追新，
用平实、专业的中文讲清楚它解决什么问题，并把「评价好」的依据公开写进文章。

目标读者是**不太懂技术的普通人**。产出两套：
- **`docs/` 站点**（GitHub Pages，给普通读者看）
- **`output/*.md` + `docs/posts/*.md`**（纯文本，给公众号运营者复制）

## 为什么改成分类化 + 存量轮播

用 GitHub Search API 做过供给调研：

| 口径 | 金融/量化 | 玄学/术数 |
|------|-----------|-----------|
| 近 7 天新建、`stars>10` | 各关键词 1–16 个 | 基本为 0 |
| 全时段存量、`stars>500` | 953 个 | 极少，需大幅放宽门槛 |
| 全时段存量、不限 star | 数千 | 数万（含大量低质项目） |

「近 7 天新晋」和「两个垂类精选」互相冲突，硬凑只会天天重复或空榜。
因此改为：**不限创建时间 → 按分类主题词检索存量项目库 → 透明质量分排序 →
每日按分类轮播、不与本分类往期重复**。金融门槛 `收藏 > 500`，术数门槛 `收藏 > 5`。

## 全链路自动化

整个流程跑在 GitHub 云端，不依赖本地电脑开机，也不需要维护长期有效的 API Token：

```
GitHub Actions 定时(每天北京 09:07)
  → 内置 GITHUB_TOKEN 调 GitHub API，按两个分类分别检索存量项目
  → src/scoring.py 计算透明质量分（收藏 / 比值 / 维护 / 文档）
  → 读 data/history.json，按 (分类, 仓库) 轮播去重，每类取 3 个
  → 抓取 README
  → DeepSeek 生成平实中文速览 + 本期看点（不参与打分、不参与选项目）
  → 生成 Markdown 文章 + 双分类响应式静态站点
  → 离线单元测试（前置快速失败）
  → 持久化到 Supabase（文章 / 项目 / 去重历史）
  → 自动 commit/push 回仓库
  → GitHub Pages 自动部署（仓库为 Public 时）
```

站点地址：`https://dear202606-star.github.io/stars/`

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
> `SEARCH_INTERVAL=1`：分类检索请求间隔 1 秒，避开 GitHub 次级限流。

分类与评分**不需要新增 Secret 或改表**：写进既有 `sections` / `raw` JSONB 即可。

### GitHub Pages（已启用）

仓库为 **Public**，Pages 已通过 API 启用为 `workflow` 构建模式，
每日任务完成后自动部署，无需任何手工操作。
workflow 内置可用性检查：若仓库被改回私有，会自动跳过部署并给出告警，
不影响文章生成与 Supabase 持久化。

> 免费计划不支持私有仓库 Pages。公开前已扫描全部 git 历史，确认无密钥残留。

### 手动触发

`Actions → 每日 GitHub 双榜 · 金融与道术 → Run workflow`，可指定日期与每类数量，
用于补跑或测试。同日重跑会复用同一批项目，文章不会漂移。

## 分类配置与质量分

分类定义在 `config.py` 的 `CATEGORIES`，每项含 `key / label / desc / min_stars /
keywords / strong / weak / match`。`keywords` 用于 GitHub 检索；**归类必须有文本证据**：
仓库名命中 `strong` 主题词直接通过，标签/描述则需要两个不同主题词共现，
泛化词（`quant`、`finance`）必须两个共现。英文按词边界匹配，
所以 `defi` 不会命中 `definition`、`portfolio` 不会命中 `developer-portfolios`，
中文分词误命中（「八字」搜到计算机笔记）也会被挡掉。真实 API 实测会过滤约 40% 搜索噪声。
单个关键词查询失败只跳过该词，不会让整批任务失败；采集失败且无往期可复用时才退出。

轮播用 `data/history.json` 的 `day_selection` 快照：未推荐过的优先，
其次是很久以前推荐过的，**最近 7 天出现过的排最后**，
保证候选轮完一圈后也不会连续两天重复。

质量分由 `src/scoring.py` 计算，满分 100，**全部取自 GitHub 公开数据，可自行复核**：

| 分项 | 权重 | 计算方式 |
|------|------|----------|
| 累计收藏 | 40 | `min(1, log10(stars+1)/4) × 40`，对数压缩避免头部永远霸榜 |
| 收藏/复制比 | 20 | `stars/forks` 分段档位：`<1` 0.2、`<4` 0.4、`<8` 0.7、`8–25` 1.0、`≤60` 0.8、更高 0.6 |
| 最近维护 | 25 | 按 `pushed_at` 距今：≤30 天 1.0、≤90 天 0.8、≤180 天 0.6、≤365 天 0.35、更久 0.1；归档记 0 |
| 文档与许可 | 15 | 有简介 0.3 + 有 license 0.3 + 标签数 0.1/0.2 + 有主页 0.2 |

> 收藏/复制比反映「关注」与「实际动手」的比例，**不是好坏的绝对标准**，
> 所以用分段档位而非线性放大，避免极端值主导排序。
> LLM 只把公开信息写成平实中文，不参与打分、不参与选项目。

每篇文章在每个项目标题下都写明 **综合质量分** 与 **评分依据原文**（含四项原始值），
页面顶部常驻四项分项得分，榜单末尾有「筛选与评分口径」说明。

## Supabase 持久化

三张表（`scripts/init_supabase.py` 幂等建表，已在线创建完成，均启用 RLS）：

| 表 | 主键 | 内容 |
|----|------|------|
| `daily_articles` | `article_date` | 标题、本期看点、项目数、Markdown 全文、站点/文章路径 |
| `daily_projects` | `(article_date, full_name)` | 排名、收藏数、语言、许可、标签、简介、`sections` JSONB、`raw` JSONB |
| `recommended_history` | `full_name` | 跨天去重历史（本地 `history.json` 里带分类与分数） |

`sections` JSONB 除了五字段结构化简介，还包含 `分类`、`分类标识`、
`综合质量分`、`评分依据`、`评分分项`；`raw` 保留完整仓库元数据。
按分类查询示例：

```
/rest/v1/daily_projects?sections->>分类=eq.金融与量化
```

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
python run.py --top 5              # 每个分类取 5 个（默认 3）
python run.py --date 2026-11-05    # 指定日期（同日重跑会复用同一批项目）
python run.py --no-llm             # 不调用 LLM，用降级模板
python run.py --no-site            # 只生成 Markdown，不生成站点
python -m unittest discover -s tests -v   # 跑全套离线测试，无需网络
```

本地配置在项目根目录 `.env`（参考 `.env.example`）：

```env
GITHUB_TOKEN=ghp_xxx          # 本地必填；CI 中不需要
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
TZ_OFFSET_HOURS=8
PER_CATEGORY=3
FINANCE_MIN_STARS=500
DAOSHU_MIN_STARS=5
```

> 优先级：系统环境变量 > `.env` > 代码默认值。**密钥只放 `.env` 或 CI Secret，
> 绝不要写进 `config.py`**（会被提交泄露）。

## 内容模板（面向普通读者，但保持专业）

每个项目固定 5 段，按阅读价值排序：

| 字段 | 作用 |
|------|------|
| **这是什么** | 一句话给出定义与类别，不堆术语 |
| **能做什么** | 2-3 条具体能力，每条一个事实 |
| **上手难不难** | 三档文字描述 + 依据（不用星级符号） |
| **谁最适合用** | 具体人群 + 能省掉哪件事 |
| **为什么值得关注** | 引用质量分分项与原始数据做有依据的解读 |

编辑准则（`src/researcher.py` 的 `STYLE_RULES`，两个 prompt 共用）：
说人话但不幼稚（禁「小助手/干活/神器」）、禁套话与 AI 连接词、
禁「新晋/刚火/暴涨/黑马」等追新表述、禁「广受好评」这类无来源评价、
专业词首次出现用一句生活化的话解释、每个判断尽量引用给定数据、
数据不足就如实说「公开信息里看不出来」，不编造媒体报道或大厂背书。

## 设计系统（Editorial Terminal）

站点视觉按专业设计技能的反通用约束实现（`src/site.py` 的 `CSS` 常量）：

- **色彩**：Zinc/Off-Black 中性底 + 单一青柠强调色（深浅两套明度均满足 WCAG AA）；
  无霓虹、无紫蓝渐变、无纯黑、无 emoji
- **字体**：Outfit（展示）+ IBM Plex Mono（所有数字与元信息）+ 中文系统字体
- **布局**：非对称 Hero（左标题 / 右真实统计）、两个分类各自成栏、
  细线分隔替代卡片堆叠、CSS Grid；**880 / 640 / 380 三档断点**，
  手机端分类头、榜单、五字段、评分口径全部折叠为单列
- **数据可视化**：每个项目的收藏数相对条形 + 质量分四项分项，只使用真实数据
- **动效**：staggered 入场、条形生长、状态点脉冲，仅 `transform`/`opacity`；
  `prefers-reduced-motion` 时全部关闭
- **无障碍**：skip link、`:focus-visible`、h1→h2→h3→h4 层级、
  `aria-labelledby`、常驻下划线（不仅靠颜色）、44px 触摸目标

站点结构：速览在前，技术元数据与评分依据默认折叠进「项目详情」；
顶部有分类与项目锚点导航，往期页含归档与相邻期导航。

### 移动端兼容

- **分类导航不丢**：880px 以下只隐藏纯数字锚点，两个分类入口始终可点；
  640px 以下隐藏状态文字、缩小品牌名，380px 以下进一步压缩间距与内边距
- **不横向滚动**：栅格列用 `minmax(0,1fr)`，品牌名 `text-overflow:ellipsis`，
  长项目名与评分依据用 `overflow-wrap:anywhere`，导航自身可横向滚动
- **触摸可用**：导航、翻页、归档、折叠项、页脚链接均 ≥44px；
  sticky 顶栏与锚点 `scroll-margin-top` 对齐
- **长文本可读**：Markdown 里的评分依据按四项拆成短行，手机/微信里不用读一长串数字
- **真实视口验证**：用 Chromium 在 320 / 375 / 390 / 768 / 1280 五档实测，
  `scrollWidth == innerWidth`（无横向溢出），分类入口全部可见，手机端为单列

## 准确性与及时性设计

| 保障 | 实现 |
|------|------|
| 不漏跑 | GitHub Actions 云端 cron，与本地开机状态无关 |
| Token 不过期 | 内置 `GITHUB_TOKEN` 每次运行自动注入，无需 PAT |
| 时区正确 | 按 UTC+8 取文章日期（CI runner 默认 UTC） |
| 同日重跑结果一致 | `day_selection` 快照复用同一批项目，文章不漂移 |
| 跨天不重复 | `data/history.json` 按 `(分类, 仓库)` 记录，未推荐过的优先；最近 7 天出现过的排最后 |
| 归类不误收 | 词边界 + 双词文本证据，真实 API 实测过滤约 40% 搜索噪声 |
| 垂类不空榜 | 某类本期无候选时复用上一期同类项目；无往期才失败退出 |
| 移动端可用 | 320/375/390/768/1280 五档真实视口无横向溢出，分类导航常驻，44px 触摸目标 |
| 抗瞬时故障 | 网络超时/5xx/次级限流指数退避；单个关键词失败只跳过该词；401 快速失败 |
| 评分可复核 | 四项全部来自公开数据，文章与页面都写出原始值与分项得分 |
| 数据不编造 | 判断须引用给定真实数据，依据不足则如实说明；LLM 不参与打分与筛选 |
| 不破坏已有内容 | 采集为空直接退出；提交前跑全套离线单元测试 |
| 幂等发布 | 文章索引按日期 upsert，无变更则跳过提交 |
| 持久化可靠 | Supabase 按主键 upsert；云端严格模式写失败即告警并失败 |
| 线上无本地依赖 | 全部配置走 GitHub Secrets，全部执行走 Actions，无需本地开机/脚本 |

## 目录结构

```
githubStars/
├── .github/workflows/daily.yml  # GitHub Actions 定时 + Pages 部署
├── config.py                    # 配置：双分类词库、门槛、每类数量
├── run.py                       # 主流程编排
├── src/
│   ├── github_client.py         # 分类检索 + 重试 + README 抓取
│   ├── scoring.py               # 归类校验 + 透明质量分 + 分组
│   ├── store.py                 # JSON 历史：按分类轮播去重
│   ├── researcher.py            # 平实中文文案模板 + LLM
│   ├── article.py               # Markdown 文章（含评分依据）
│   ├── site.py                  # 双分类静态站点（含 CSS）
│   └── supabase_store.py        # Supabase REST 持久化
├── scripts/init_supabase.py     # 一次性建表（Management API）
├── tests/                       # 离线测试（单元 + 端到端 + 持久化 + 分类评分）
├── docs/                        # GitHub Pages 站点（自动生成、提交）
│   ├── index.html               # 首页（最新一期）
│   ├── posts/YYYY-MM-DD.html    # 每期页面
│   ├── posts/YYYY-MM-DD.md      # 每期纯文本（公众号用）
│   ├── style.css / feed.json
│   └── .nojekyll
├── data/history.json            # 去重历史 + 文章索引（自动生成、提交）
└── output/                      # 本地 Markdown 存档（不提交）
```
