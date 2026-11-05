"""全链路离线测试：不依赖网络/API Key，验证核心逻辑正确。"""

import json
import os
import tempfile
import unittest

import config
from src import article, site, store


def _repo(name: str, stars: int) -> dict:
    return {
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "stargazers_count": stars,
        "forks_count": stars // 10,
        "language": "Python",
        "license": {"name": "MIT"},
        "topics": ["ai", "tool"],
        "description": "一个测试项目",
        "created_at": "2026-11-01T00:00:00Z",
        "pushed_at": "2026-11-05T00:00:00Z",
        "open_issues_count": 3,
        "id": stars,
    }


SUMMARY = (
    "**这是什么**\n"
    "一个帮你整理资料的小工具，不用懂技术也能用。\n\n"
    "**能做什么**\n"
    "- 自动归拢文件\n"
    "- 一键生成摘要\n\n"
    "**上手难不难**\n"
    "很简单，点开就能用。\n\n"
    "**谁最适合用**\n"
    "学生、写作者。\n\n"
    "**为什么火**\n"
    "暂不确定。"
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
        store.set_day_selection(h, "2026-11-05", [_repo("a/b", 100)])
        got = store.get_day_selection(h, "2026-11-05")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["full_name"], "a/b")

    def test_day_selection_keeps_last_14_days(self):
        h = store.load(self.path)
        for i in range(20):
            store.set_day_selection(h, f"2026-10-{i+1:02d}", [_repo("a/b", 1)])
        self.assertLessEqual(len(h["day_selection"]), 14)


class TestArticle(unittest.TestCase):
    def test_build_contains_sections(self):
        items = [(_repo("a/b", 1234), SUMMARY)]
        md = article.build_article(items, "2026-11-05", "本期看点测试")
        self.assertIn("Top1", md)
        self.assertIn("本期看点", md)
        self.assertIn("**这是什么**", md)
        self.assertIn("https://github.com/a/b", md)
        self.assertIn("人收藏", md)

    def test_summary_before_technical_details(self):
        """普通人先看到人话，技术信息在后。"""
        items = [(_repo("a/b", 1234), SUMMARY)]
        md = article.build_article(items, "2026-11-05")
        self.assertLess(md.index("**这是什么**"), md.index("主语言"))

    def test_save_filename_uses_date(self):
        with tempfile.TemporaryDirectory() as d:
            p = article.save_article("# hi", d, "2026-11-05")
            self.assertTrue(p.endswith("2026-11-05.md"))


class TestSite(unittest.TestCase):
    def _cfg(self, d):
        class C:
            SITE_DIR = d
            SITE_TITLE = "测试速览"
            DAYS_BACK = 7
            TZ_OFFSET_HOURS = 8
            SITE_BASE_URL = ""
        return C()

    def test_render_produces_all_files(self):
        tmp = tempfile.mkdtemp()
        h = store.load(os.path.join(tmp, "h.json"))
        items = [(_repo("a/b", 1234), SUMMARY)]
        md = article.build_article(items, "2026-11-05", "看点")
        files = site.render_site(h, items, "看点", "2026-11-05", md, self._cfg(tmp))

        self.assertTrue(os.path.exists(files["index"]))
        self.assertTrue(os.path.exists(files["html"]))
        self.assertTrue(os.path.exists(files["md"]))
        self.assertTrue(os.path.exists(os.path.join(tmp, "style.css")))
        self.assertTrue(os.path.exists(os.path.join(tmp, ".nojekyll")))

        with open(files["index"], encoding="utf-8") as f:
            page = f.read()
        self.assertIn("a/b", page)
        self.assertIn('class="section"', page)
        self.assertIn("本期看点", page)
        self.assertIn("自动归拢文件", page)
        self.assertIn("<!DOCTYPE html>", page)
        self.assertNotIn("{css}", page)

        with open(os.path.join(tmp, "feed.json"), encoding="utf-8") as f:
            feed = json.load(f)
        self.assertEqual(feed["latest"], "2026-11-05")

    def test_accessibility_and_reader_first(self):
        tmp = tempfile.mkdtemp()
        cfg = self._cfg(tmp)
        html = site._render_card(1, _repo("a/b", 1234), SUMMARY)
        self.assertIn("<h3", html)                       # 字段是标题，读屏可导航
        self.assertIn('aria-labelledby="p1"', html)
        self.assertIn("人收藏", html)                     # 收藏数说人话
        self.assertIn('<details class="tech"', html)     # 技术细节折叠
        self.assertIn("项目详情（给懂技术的人）", html)
        self.assertLess(html.index("这是什么"), html.index("项目详情"))
        self.assertIn('aria-hidden="true"', html)
        self.assertIn("新窗口打开", html)
        self.assertIn("skip", site._head("t"))
        self.assertIn("focus-visible", site.CSS)

    def test_html_escapes_injection(self):
        rendered = site.render_summary("**这是什么**\n<script>alert(1)</script>")
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_renderer_tolerates_llm_format_drift(self):
        """小标题同行带冒号、编号列表，都不能丢结构。"""
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
        self.assertIn('<nav', block)

    def test_overview_placeholder_when_empty(self):
        tmp = tempfile.mkdtemp()
        h = store.load(os.path.join(tmp, "h.json"))
        items = [(_repo("a/b", 100), SUMMARY)]
        md = article.build_article(items, "2026-11-05")
        f = site.render_site(h, items, "", "2026-11-05", md, self._cfg(tmp))
        with open(f["index"], encoding="utf-8") as fp:
            self.assertIn("本期看点整理中", fp.read())

    def test_fallback_is_plain_language(self):
        from src import researcher
        fb = researcher._fallback(_repo("a/b", 100), "# English README\nfoo")
        self.assertIn("**这是什么**", fb)
        self.assertNotIn("见 README", fb)
        self.assertNotIn("English README", fb)
        self.assertIn("人收藏", fb)


class TestConfig(unittest.TestCase):
    def test_defaults_sane(self):
        self.assertGreater(config.TOP_N, 0)
        self.assertGreater(config.DAYS_BACK, 0)
        self.assertEqual(config.TZ_OFFSET_HOURS, 8)


if __name__ == "__main__":
    unittest.main()
