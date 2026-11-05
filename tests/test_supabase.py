"""Supabase 持久化层离线测试（mock REST，无需真实网络）。"""

import os
import unittest
from unittest import mock

from src import supabase_store
from tests.test_pipeline import SUMMARY, _repo


class TestParseSections(unittest.TestCase):
    def test_parse_five_fields(self):
        s = supabase_store.parse_sections(SUMMARY)
        self.assertEqual(list(s.keys()),
                         ["这是什么", "能做什么", "上手难不难",
                          "谁最适合用", "为什么火"])
        self.assertIn("整理资料", s["这是什么"])

    def test_parse_tolerates_inline_label(self):
        s = supabase_store.parse_sections("**这是什么**：一个工具\n**能做什么**\n- 归拢文件")
        self.assertEqual(s["这是什么"], "一个工具")
        self.assertIn("归拢文件", s["能做什么"])

    def test_parse_empty(self):
        self.assertEqual(supabase_store.parse_sections(""), {})


class TestConfig(unittest.TestCase):
    def test_disabled_without_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(supabase_store.enabled())
            r = supabase_store.persist("2026-11-05", "t", "", [], "", "", "",
                                       "", {})
            self.assertTrue(r["skipped"])

    def test_enabled_with_env(self):
        with mock.patch.dict(os.environ, {
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_KEY": "k",
        }):
            self.assertTrue(supabase_store.enabled())
            self.assertEqual(supabase_store.url(), "https://x.supabase.co")


class TestPersist(unittest.TestCase):
    def _env(self):
        return mock.patch.dict(os.environ, {
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_KEY": "k",
            "SUPABASE_REQUIRED": "1",
        })

    def test_persist_calls_all_endpoints(self):
        items = [(_repo("a/b", 100), SUMMARY)]
        history = {"recommended": {"a/b": {"stars": 100,
                                            "language": "Python",
                                            "first_seen": "2026-11-05"}}}
        calls = []

        def fake(path, method="GET", params=None, payload=None, extra=None):
            calls.append((path, method, params, payload))

        with self._env(), mock.patch.object(supabase_store, "_postgrest",
                                            side_effect=fake):
            r = supabase_store.persist(
                "2026-11-05", "标题", "看点", items, "# md",
                "posts/2026-11-05.md", "posts/2026-11-05.html",
                "https://x/posts/2026-11-05.html", history)

        self.assertEqual(r, {"articles": 1, "projects": 1,
                             "history": 1, "skipped": False})
        paths = [c[0] for c in calls]
        self.assertIn("daily_articles", paths)
        self.assertIn("daily_projects", paths)
        self.assertIn("recommended_history", paths)
        self.assertTrue(any(c[1] == "DELETE" for c in calls))
        article_payload = next(c[3] for c in calls if c[0] == "daily_articles")
        self.assertEqual(article_payload["project_count"], 1)
        proj_payload = next(c[3] for c in calls
                            if c[0] == "daily_projects" and c[1] == "POST")
        self.assertEqual(proj_payload[0]["rank"], 1)
        self.assertIn("sections", proj_payload[0])

    def test_strict_mode_raises(self):
        with self._env(), mock.patch.object(
                supabase_store, "_postgrest",
                side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                supabase_store.persist("2026-11-05", "t", "", [], "", "", "",
                                       "", {})

    def test_non_strict_returns_error(self):
        env = {"SUPABASE_URL": "https://x.supabase.co",
               "SUPABASE_SERVICE_KEY": "k", "SUPABASE_REQUIRED": "0"}
        with mock.patch.dict(os.environ, env), mock.patch.object(
                supabase_store, "_postgrest",
                side_effect=RuntimeError("boom")):
            r = supabase_store.persist("2026-11-05", "t", "", [], "", "", "",
                                       "", {})
            self.assertIn("error", r)
            self.assertFalse(r["skipped"])


if __name__ == "__main__":
    unittest.main()
