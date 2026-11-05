"""端到端编排测试：mock 掉网络，验证 run.main() 全链路产物与幂等性。"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import run
from tests.test_pipeline import SUMMARY, _repo


def _pools() -> dict:
    """每类 4 个候选，便于验证每类取 3 个与跨天轮播。"""
    out = {
        "finance": [_repo(f"fin/repo{i}", 1000 - i * 100, "finance")
                    for i in range(4)],
        "daoshu": [_repo(f"dao/repo{i}", 300 - i * 30, "daoshu")
                   for i in range(4)],
    }
    for r in out["finance"]:
        r["_queries"] = ["quant"]
    for r in out["daoshu"]:
        r["_queries"] = ["bazi"]
    return out


class TestEndToEnd(unittest.TestCase):
    def _run_main(self, date: str, per: int = 3):
        argv = ["run.py", "--date", date]
        if per:
            argv += ["--top", str(per)]
        with mock.patch.object(sys, "argv", argv):
            run.main()

    def _patches(self, d, pools=None, **overrides):
        patches = dict(
            OUTPUT_DIR=os.path.join(d, "output"),
            SITE_DIR=os.path.join(d, "docs"),
            HISTORY_FILE=os.path.join(d, "data", "history.json"),
            LLM_ENABLED=False,
        )
        patches.update(overrides)
        return patches

    def test_full_pipeline_and_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            out_dir = os.path.join(d, "output")
            site_dir = os.path.join(d, "docs")
            hist = os.path.join(d, "data", "history.json")

            with mock.patch.multiple(
                run.config, **self._patches(d)
            ), mock.patch.object(
                run.github_client, "fetch_candidates", return_value=_pools()
            ), mock.patch.object(
                run.github_client, "fetch_readme", return_value="# README\n内容"
            ), mock.patch.object(
                run.researcher, "research", return_value=SUMMARY
            ), mock.patch.object(
                run.researcher, "generate_overview",
                return_value="本期看点：两类各有依据。"
            ), mock.patch.object(run.time, "sleep"):

                self._run_main("2026-11-05", 3)

                # Markdown 产物含双分类与评分依据
                with open(os.path.join(out_dir, "2026-11-05.md"),
                          encoding="utf-8") as f:
                    md = f.read()
                self.assertIn("## 金融与量化", md)
                self.assertIn("## 道术 · 玄学术数", md)
                self.assertIn("综合质量分", md)
                self.assertIn("评分依据", md)
                self.assertIn("评分口径", md)
                self.assertNotIn("近 7 天", md)

                # 站点产物
                for rel in ("index.html", "style.css", ".nojekyll",
                            os.path.join("posts", "2026-11-05.html"),
                            os.path.join("posts", "2026-11-05.md")):
                    self.assertTrue(os.path.exists(os.path.join(site_dir, rel)))
                with open(os.path.join(site_dir, "index.html"),
                          encoding="utf-8") as f:
                    html = f.read()
                self.assertIn('id="cat-finance"', html)
                self.assertIn('id="cat-daoshu"', html)
                self.assertIn('class="score"', html)
                self.assertIn("筛选与评分口径", html)
                self.assertIn("fin/repo0", html)
                self.assertIn("dao/repo0", html)

                # 历史：每类 3 个，共 6 个，且带分类
                with open(hist, encoding="utf-8") as f:
                    h = json.load(f)
                self.assertEqual(len(h["posts"]), 1)
                self.assertEqual(len(h["recommended"]), 6)
                self.assertEqual(
                    sum(1 for v in h["recommended"].values()
                        if v["category"] == "finance"), 3)
                self.assertEqual(
                    sum(1 for v in h["recommended"].values()
                        if v["category"] == "daoshu"), 3)
                self.assertEqual(len(h["day_selection"]["2026-11-05"]), 6)

                with open(os.path.join(site_dir, "feed.json"),
                          encoding="utf-8") as f:
                    feed = json.load(f)
                self.assertEqual(feed["latest"], "2026-11-05")
                self.assertEqual(len(feed["posts"]), 1)
                self.assertEqual(len(feed["categories"]), 2)

                # 同日重跑：幂等，文章索引不重复，选中批次不变
                self._run_main("2026-11-05", 3)
                with open(hist, encoding="utf-8") as f:
                    h2 = json.load(f)
                self.assertEqual(len(h2["posts"]), 1)
                self.assertEqual(len(h2["recommended"]), 6)
                self.assertEqual(
                    {r["full_name"] for r in h2["day_selection"]["2026-11-05"]},
                    {r["full_name"] for r in h["day_selection"]["2026-11-05"]})

                # 跨天轮播：优先本类从未推荐过的高分项目
                self._run_main("2026-11-06", 3)
                with open(os.path.join(site_dir, "posts", "2026-11-06.html"),
                          encoding="utf-8") as f:
                    html2 = f.read()
                self.assertIn("fin/repo3", html2)
                self.assertIn("dao/repo3", html2)
                with open(hist, encoding="utf-8") as f:
                    h3 = json.load(f)
                self.assertEqual(len(h3["posts"]), 2)

    def test_auth_error_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.multiple(
                run.config, **self._patches(d)
            ), mock.patch.object(
                run.github_client, "fetch_candidates",
                side_effect=run.github_client.AuthError("bad credentials")
            ):
                with self.assertRaises(SystemExit) as ctx:
                    self._run_main("2026-11-05", 3)
                self.assertEqual(ctx.exception.code, 3)

    def test_empty_category_without_history_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            pools = {"finance": _pools()["finance"], "daoshu": []}
            with mock.patch.multiple(
                run.config, **self._patches(d)
            ), mock.patch.object(
                run.github_client, "fetch_candidates", return_value=pools
            ):
                with self.assertRaises(SystemExit) as ctx:
                    self._run_main("2026-11-05", 3)
                self.assertEqual(ctx.exception.code, 1)

    def test_supabase_failure_is_strict_in_cloud(self):
        env = {"SUPABASE_REQUIRED": "1",
               "SUPABASE_URL": "https://x.supabase.co",
               "SUPABASE_SERVICE_KEY": "k"}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, env), mock.patch.multiple(
                run.config, **self._patches(d)
            ), mock.patch.object(
                run.github_client, "fetch_candidates", return_value=_pools()
            ), mock.patch.object(
                run.github_client, "fetch_readme", return_value=""
            ), mock.patch.object(
                run.researcher, "research", return_value=SUMMARY
            ), mock.patch.object(
                run.researcher, "generate_overview", return_value=""
            ), mock.patch.object(run.time, "sleep"), mock.patch.object(
                run.supabase_store, "_postgrest",
                side_effect=RuntimeError("Supabase down")):
                with self.assertRaises(RuntimeError):
                    self._run_main("2026-11-05", 3)


if __name__ == "__main__":
    unittest.main()
