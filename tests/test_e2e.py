"""端到端编排测试：mock 掉网络，验证 run.main() 全链路产物与幂等性。"""

import os
import sys
import tempfile
import unittest
from unittest import mock

import run
from tests.test_pipeline import SUMMARY, _repo


class TestEndToEnd(unittest.TestCase):
    def _run_main(self, date: str, top: int = 3):
        argv = ["run.py", "--date", date]
        if top:
            argv += ["--top", str(top)]
        with mock.patch.object(sys, "argv", argv):
            run.main()

    def test_full_pipeline_and_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            out_dir = os.path.join(d, "output")
            site_dir = os.path.join(d, "docs")
            hist = os.path.join(d, "data", "history.json")

            cands = [_repo(f"org/repo{i}", 1000 - i * 100) for i in range(6)]
            with mock.patch.multiple(
                run.config,
                OUTPUT_DIR=out_dir,
                SITE_DIR=site_dir,
                HISTORY_FILE=hist,
                LLM_ENABLED=False,
            ), mock.patch.object(
                run.github_client, "search_recent_stars", return_value=cands
            ), mock.patch.object(
                run.github_client, "fetch_readme", return_value="# README\n内容"
            ), mock.patch.object(
                run.researcher, "research", return_value=SUMMARY
            ), mock.patch.object(
                run.researcher, "generate_overview", return_value="本期看点：AI 工具很火。"
            ), mock.patch.object(run.time, "sleep"):

                self._run_main("2026-11-05", 3)

                # Markdown 产物
                self.assertTrue(os.path.exists(os.path.join(out_dir, "2026-11-05.md")))
                # 站点产物
                self.assertTrue(os.path.exists(os.path.join(site_dir, "index.html")))
                self.assertTrue(os.path.exists(os.path.join(site_dir, "style.css")))
                self.assertTrue(os.path.exists(os.path.join(site_dir, ".nojekyll")))
                self.assertTrue(os.path.exists(
                    os.path.join(site_dir, "posts", "2026-11-05.html")))
                self.assertTrue(os.path.exists(
                    os.path.join(site_dir, "posts", "2026-11-05.md")))
                # 历史
                with open(hist, encoding="utf-8") as f:
                    import json
                    h = json.load(f)
                self.assertEqual(len(h["posts"]), 1)
                self.assertEqual(len(h["recommended"]), 3)
                # feed.json 必须包含当期（防止索引登记顺序错误）
                with open(os.path.join(site_dir, "feed.json"), encoding="utf-8") as f:
                    import json
                    feed = json.load(f)
                self.assertEqual(feed["latest"], "2026-11-05")
                self.assertEqual(len(feed["posts"]), 1)

                # 再跑一次同样日期：幂等 —— 文章索引不重复，且项目列表保持不变
                self._run_main("2026-11-05", 3)
                with open(hist, encoding="utf-8") as f:
                    import json
                    h2 = json.load(f)
                self.assertEqual(len(h2["posts"]), 1)
                self.assertEqual(len(h2["recommended"]), 3)

                # 首页包含看点、项目名；同日重跑后仍是同一批项目
                with open(os.path.join(site_dir, "index.html"), encoding="utf-8") as f:
                    html = f.read()
                self.assertIn("本期看点", html)
                self.assertIn("org/repo0", html)
                self.assertNotIn("org/repo3", html)

    def test_auth_error_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.multiple(
                run.config,
                OUTPUT_DIR=os.path.join(d, "output"),
                SITE_DIR=os.path.join(d, "docs"),
                HISTORY_FILE=os.path.join(d, "data", "history.json"),
            ), mock.patch.object(
                run.github_client, "search_recent_stars",
                side_effect=run.github_client.AuthError("bad credentials")
            ):
                with self.assertRaises(SystemExit) as ctx:
                    self._run_main("2026-11-05", 3)
                self.assertEqual(ctx.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
