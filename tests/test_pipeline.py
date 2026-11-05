"""全链路离线测试：不依赖网络/API Key，验证核心逻辑正确。"""

import json
import os
import tempfile
import unittest

from datetime import datetime, timezone

import config
from src import article, scoring, site, store

_LABELS = {"finance": "金融与量化", "daoshu": "道术 · 玄学术数"}
_NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


def _repo(name: str, stars: int, category: str = None) -> dict:
    r = {
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "stargazers_count": stars,
        "forks_count": stars // 10,
        "language": "Python",
        "license": {"name": "MIT"},
        "topics": ["ai", "tool"],
        "description": "一个测试项目",
        "homepage": "",
        "created_at": "2026-11-01T00:00:00Z",
        "pushed_at": "2026-11-05T00:00:00Z",
        "open_issues_count": 3,
        "id": stars,
        "archived": False,
    }
    if category:
        r["category"] = category
        r["category_label"] = _LABELS.get(category, category)
        # 真实归类需要文本证据，测试数据也带上分类主题词
        r["description"] = ("开源量化交易回测工具" if category == "finance"
                            else "八字紫微斗数排盘工具")
        r["_score"] = scoring.score_repo(r, now=_NOW)
    return r


SUMMARY = (
    "**这是什么**\n"
    "一个把资料整理好交给 AI 使用的工具。\n\n"
    "**能做什么**\n"
    "- 自动归拢文件\n"
    "- 生成摘要\n\n"
    "**上手难不难**\n"
    "很简单，打开就能用。\n\n"
    "**谁最适合用**\n"
    "需要整理大量资料的研究者。\n\n"
    "**为什么值得关注**\n"
    "4 天内积累 1,234 收藏，关注度集中。"
)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "history.json")

    def test_empty_and_save_load(self):
        h = store.load(self.path)
        self.assertEqual(h["recommended"], {})
        self.assertEqual(h["posts"], [])
        self.assertEqual(h["day_selection"], {})
        store.mark_recommended(h, [_repo("a/b", 100)], "2026-11-05")
        store.save(h, self.path)
        self.assertIn("a/b", store.load(self.path)["recommended"])

    def test_corrupted_file_recovers(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{bad json")
        self.assertEqual(store.load(self.path)["posts"], [])

    def test_dedupe_prefers_fresh(self):
        h = store.load(self.path)
        store.mark_recommended(h, [_repo("a/b", 100)], "2026-11-01")
        cands = [_repo("a/b", 100), _repo("c/d", 90), _repo("e/f", 80)]
        out = store.dedupe(h, cands, 2)
        self.assertEqual([r["full_name"] for r in out], ["c/d", "e/f"])

    def test_dedupe_backfills_from_used_without_duplicates(self):
        h = store.load(self.path)
        store.mark_recommended(h, [_repo("a/b", 100)], "2026-11-01")
        out = store.dedupe(h, [_repo("a/b", 100), _repo("c/d", 90)], 5)
        self.assertEqual([r["full_name"] for r in out], ["c/d", "a/b"])

    def test_upsert_post_is_idempotent(self):
        h = store.load(self.path)
        store.upsert_post(h, "2026-11-05", "T1", 10, "a.md", "a.html")
        store.upsert_post(h, "2026-11-05", "T2", 10, "b.md", "b.html")
        self.assertEqual(len(h["posts"]), 1)
        self.assertEqual(h["posts"][0]["title"], "T2")

    def test_day_selection_roundtrip(self):
        h = store.load(self.path)
        store.set_day_selection(h, "2026-11-05",
                                [_repo("a/b", 100, "finance")])
        got = store.get_day_selection(h, "2026-11-05")
        self.assertEqual(got[0]["full_name"], "a/b")
        self.assertEqual(got[0]["category"], "finance")

    def test_legacy_selection_is_not_reused(self):
        h = store.load(self.path)
        store.set_day_selection(h, "2026-11-05", [_repo("a/b", 100)])
        self.assertEqual(store.get_day_selection(h, "2026-11-05"), [])

    def test_legacy_history_is_migrated(self):
        h = store.load(self.path)
        store.mark_recommended(h, [_repo("a/b", 100)], "2026-11-05")
        store.save(h, self.path)
        self.assertEqual(store.load(self.path)["recommended"]["a/b"]["category"],
                         "legacy")

    def test_day_selection_keeps_last_14_days(self):
        h = store.load(self.path)
        for i in range(20):
            store.set_day_selection(h, f"2026-10-{i+1:02d}", [_repo("a/b", 1)])
        self.assertLessEqual(len(h["day_selection"]), 14)


class TestArticle(unittest.TestCase):
    def test_build_contains_sections(self):
        items = [(_repo("a/b", 1234), SUMMARY)]
        md = article.build_article(items, "2026-11-05", "今日一瞥")
        self.assertIn("## 数", md)          # 栏目只用一个字，不写专业分类名
        self.assertIn("### 01", md)
        self.assertIn("今日一瞥", md)
        self.assertIn("**这是什么**", md)
        self.assertIn("https://github.com/a/b", md)
        self.assertIn("人收藏", md)
        self.assertIn("**", md)
        # 读者看到的内容里不出现幕后过程与指标
        for banned in ("评分口径", "综合质量分", "评分依据", "本榜", "筛选"):
            self.assertNotIn(banned, md)

    def test_summary_before_technical_details(self):
        items = [(_repo("a/b", 1234), SUMMARY)]
        md = article.build_article(items, "2026-11-05")
        self.assertLess(md.index("**这是什么**"), md.index("项目页"))

    def test_save_filename_uses_date(self):
        with tempfile.TemporaryDirectory() as d:
            p = article.save_article("# hi", d, "2026-11-05")
            self.assertTrue(p.endswith("2026-11-05.md"))


class TestSite(unittest.TestCase):
    def _cfg(self, d):
        class C:
            SITE_DIR = d
            SITE_TITLE = "两仪"
            SITE_TAGLINE = "一边算得清，一边算不尽。"
            CATEGORIES = config.CATEGORIES
            PER_CATEGORY = config.PER_CATEGORY
            DAYS_BACK = 7
            TZ_OFFSET_HOURS = 8
            SITE_BASE_URL = ""
        return C()

    def test_render_produces_all_files(self):
        tmp = tempfile.mkdtemp()
        h = store.load(os.path.join(tmp, "h.json"))
        items = [(_repo("a/b", 1234), SUMMARY)]
        md = article.build_article(items, "2026-11-05", "今日一瞥")
        files = site.render_site(h, items, "今日一瞥", "2026-11-05", md,
                                 self._cfg(tmp))

        for p in (files["index"], files["html"], files["md"]):
            self.assertTrue(os.path.exists(p))
        self.assertTrue(os.path.exists(os.path.join(tmp, "style.css")))
        self.assertTrue(os.path.exists(os.path.join(tmp, ".nojekyll")))

        with open(files["index"], encoding="utf-8") as f:
            page = f.read()
        self.assertIn("a/b", page)
        self.assertIn('class="section"', page)
        self.assertIn("今日一瞥", page)
        self.assertIn("自动归拢文件", page)
        self.assertIn("<!DOCTYPE html>", page)
        self.assertNotIn("{css}", page)
        self.assertNotIn("⭐", page)          # 禁 emoji
        self.assertIn('class="bar"', page)    # 真实数据条形
        self.assertIn('id="cat-finance"', page)
        self.assertIn('id="cat-daoshu"', page)
        self.assertIn("两仪", page)
        self.assertIn("一边算得清", page)
        # 页面不出现幕后过程与指标口径
        for banned in ("筛选与评分口径", "综合质量分", "不追新", "轮播",
                       "自动生成", "GitHub 公共接口"):
            self.assertNotIn(banned, page)

        with open(os.path.join(tmp, "feed.json"), encoding="utf-8") as f:
            feed = json.load(f)
        self.assertEqual(feed["latest"], "2026-11-05")
        self.assertEqual(len(feed["categories"]), 2)
        self.assertEqual(feed["site"], "两仪")

    def test_design_system_constraints(self):
        """反通用设计约束：单一强调色、无霓虹、等宽数字、动效克制。"""
        self.assertIn("prefers-reduced-motion", site.CSS)
        self.assertIn("focus-visible", site.CSS)
        self.assertIn("IBM Plex Mono", site.CSS)
        self.assertIn("Outfit", site.CSS)
        self.assertNotIn("purple", site.CSS.lower())
        self.assertNotIn("#000000", site.CSS)
        self.assertNotIn("linear-gradient(90deg, #", site.CSS)
        self.assertIn("@media(max-width:640px)", site.CSS)

    def test_accessibility_and_reader_first(self):
        html = site._render_card(1, _repo("a/b", 1234), SUMMARY)
        self.assertIn("<h4", html)  # 字段是标题，读屏可导航
        self.assertIn('aria-labelledby="p1-title"', html)
        self.assertIn('class="metric"', html)
        self.assertIn('<details class="tech"', html)
        self.assertIn("再看一点", html)
        self.assertLess(html.index("这是什么"), html.index("再看一点"))
        self.assertIn("新窗口打开", html)
        self.assertIn("skip", site._head("t"))

    def test_html_escapes_injection(self):
        rendered = site.render_summary("**这是什么**\n<script>alert(1)</script>")
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_renderer_tolerates_llm_format_drift(self):
        drifted = "**这是什么**：一个整理资料的工具\n**能做什么**\n1. 归拢文件\n2. 生成摘要"
        rendered = site.render_summary(drifted)
        self.assertIn("这是什么", rendered)
        self.assertIn("一个整理资料的工具", rendered)
        self.assertIn("<li>归拢文件</li>", rendered)
        self.assertIn("<li>生成摘要</li>", rendered)

    def test_archive_excludes_current(self):
        h = {"recommended": {}, "posts": [
            {"date": "2026-11-05", "title": "本期", "count": 10,
             "md": "a.md", "html": "a.html"},
            {"date": "2026-11-04", "title": "往期", "count": 10,
             "md": "b.md", "html": "b.html"},
        ]}
        block = site._archive_block(h, "2026-11-05")
        self.assertNotIn("本期", block)
        self.assertIn("往期", block)
        self.assertIn("posts/2026-11-04.html", block)
        self.assertIn("<nav", block)

    def test_overview_placeholder_when_empty(self):
        """没有题记时留白，不塞占位说明文字。"""
        tmp = tempfile.mkdtemp()
        h = store.load(os.path.join(tmp, "h.json"))
        items = [(_repo("a/b", 100), SUMMARY)]
        md = article.build_article(items, "2026-11-05")
        f = site.render_site(h, items, "", "2026-11-05", md, self._cfg(tmp))
        with open(f["index"], encoding="utf-8") as fp:
            page = fp.read()
        self.assertNotIn("今日一瞥", page)
        self.assertIn('class="hero"', page)

    def test_placeholder_uses_same_design(self):
        tmp = tempfile.mkdtemp()
        path = site.render_placeholder(self._cfg(tmp))
        with open(path, encoding="utf-8") as f:
            page = f.read()
        self.assertIn("class=\"topbar\"", page)
        self.assertIn("两仪", page)
        self.assertIn("一边算得清", page)
        self.assertNotIn("双榜", page)

    def test_fallback_is_professional(self):
        from src import researcher
        fb = researcher._fallback(_repo("a/b", 100), "# English README\nfoo")
        self.assertIn("**这是什么**", fb)
        self.assertIn("**为什么值得关注**", fb)
        self.assertNotIn("见 README", fb)
        self.assertNotIn("English README", fb)
        self.assertNotIn("小助手", fb)


class TestConfig(unittest.TestCase):
    def test_defaults_sane(self):
        self.assertGreater(config.TOP_N, 0)
        self.assertEqual(config.PER_CATEGORY, 3)
        self.assertEqual(len(config.CATEGORIES), 2)
        self.assertEqual({c["key"] for c in config.CATEGORIES},
                         {"finance", "daoshu"})
        self.assertGreater(config.CATEGORIES[0]["min_stars"],
                           config.CATEGORIES[1]["min_stars"])
        self.assertEqual(config.TZ_OFFSET_HOURS, 8)

    def test_no_created_filter_in_categories(self):
        for c in config.CATEGORIES:
            self.assertTrue(c["keywords"])
            self.assertTrue(c["match"])
            self.assertTrue(c["strong"])
            self.assertGreaterEqual(c["min_stars"], 0)


if __name__ == "__main__":
    unittest.main()
