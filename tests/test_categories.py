"""双分类与透明质量分专项测试（离线，无网络）。"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import config
from src import article, github_client, scoring, site, store
from tests.test_pipeline import SUMMARY, _repo

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
FIN = config.CATEGORIES[0]
DAO = config.CATEGORIES[1]


def _pool(key: str, n: int = 5, base: int = 1000):
    rows = [_repo(f"{key}/repo{i}", base - i * 100, key) for i in range(n)]
    for r in rows:
        r["_queries"] = ["quant"] if key == "finance" else ["bazi"]
    return scoring.rank(rows, FIN if key == "finance" else DAO, now=NOW)


class TestQualityScore(unittest.TestCase):
    def test_weights_sum_to_100(self):
        self.assertEqual(sum(scoring.WEIGHTS.values()), 100)
        self.assertIn("收藏/复制比", scoring.FORMULA)

    def test_score_is_bounded_and_transparent(self):
        s = scoring.score_repo(_repo("a/b", 2340, "finance"), now=NOW)
        self.assertGreaterEqual(s["total"], 0)
        self.assertLessEqual(s["total"], 100)
        self.assertEqual(set(s["parts"]), set(scoring.WEIGHTS))
        self.assertIn("2,340", s["evidence"])
        self.assertIn("收藏/复制比", s["evidence"])
        self.assertIn("天前更新", s["evidence"])
        self.assertEqual(s["parts"]["stars"]["max"], 40)

    def test_more_stars_scores_higher(self):
        low = scoring.score_repo(_repo("a/b", 100), now=NOW)["total"]
        high = scoring.score_repo(_repo("a/b", 10000), now=NOW)["total"]
        self.assertGreater(high, low)

    def test_stale_repo_loses_activity_points(self):
        r = _repo("a/b", 1000)
        r["pushed_at"] = "2020-01-01T00:00:00Z"
        s = scoring.score_repo(r, now=NOW)
        self.assertEqual(s["parts"]["activity"]["score"], 2.5)

    def test_archived_repo_scores_zero_activity(self):
        r = _repo("a/b", 1000)
        r["archived"] = True
        self.assertEqual(scoring.score_repo(r, now=NOW)
                         ["parts"]["activity"]["score"], 0)

    def test_missing_docs_scores_zero(self):
        r = {"full_name": "a/b", "stargazers_count": 10,
             "forks_count": 1, "topics": [], "description": "",
             "license": None, "homepage": "",
             "pushed_at": "2026-11-01T00:00:00Z"}
        self.assertEqual(scoring.score_repo(r, now=NOW)
                         ["parts"]["docs"]["score"], 0)

    def test_ratio_uses_grades_not_linear_amplification(self):
        base = {"full_name": "a/b", "forks_count": 100, "topics": [],
                "description": "", "license": None, "homepage": "",
                "pushed_at": "2026-11-01T00:00:00Z"}
        normal = {**base, "stargazers_count": 1200}   # ratio 12
        extreme = {**base, "stargazers_count": 100000}  # ratio 1000
        self.assertGreater(
            scoring.score_repo(normal, now=NOW)["parts"]["ratio"]["score"],
            scoring.score_repo(extreme, now=NOW)["parts"]["ratio"]["score"])

    def test_matches_category_by_chinese_keywords(self):
        r = {"full_name": "x/八字排盘", "description": "基于八字命理的排盘工具",
             "topics": []}
        self.assertTrue(scoring.matches_category(r, DAO))
        self.assertFalse(scoring.matches_category(r, FIN))

    def test_search_query_alone_is_not_evidence(self):
        """GitHub 中文分词很宽松，被关键词搜到不等于属于这个分类。"""
        r = {"full_name": "x/q", "description": "", "topics": [],
             "_queries": ["quant"]}
        self.assertFalse(scoring.matches_category(r, FIN))
        self.assertFalse(scoring.matches_category(r, DAO))

    def test_word_boundary_blocks_false_positives(self):
        self.assertFalse(scoring.matches_category({
            "full_name": "DefinitelyTyped/DefinitelyTyped",
            "description": "The repository for high quality TypeScript type definition",
            "topics": []}, FIN))          # defi ⊂ definition
        self.assertFalse(scoring.matches_category({
            "full_name": "emmabostian/developer-portfolios",
            "description": "A list of developer portfolios for your inspiration",
            "topics": []}, FIN))          # portfolio ⊂ portfolios
        self.assertFalse(scoring.matches_category({
            "full_name": "xiaolincoder/CS-Base",
            "description": "图解计算机网络、操作系统，共 50 万字",
            "topics": []}, DAO))          # 「八字」只是分词误命中

    def test_word_boundary_keeps_real_projects(self):
        self.assertTrue(scoring.matches_category({
            "full_name": "freqtrade/freqtrade",
            "description": "Free, open source crypto trading bot",
            "topics": []}, FIN))
        self.assertTrue(scoring.matches_category({
            "full_name": "SylarLong/iztro",
            "description": "紫微斗数排盘库",
            "topics": []}, DAO))

    def test_exclude_keywords_use_word_boundary(self):
        from types import SimpleNamespace
        cfg = SimpleNamespace(EXCLUDE_KEYWORDS=config.EXCLUDE_KEYWORDS)
        self.assertFalse(github_client.should_exclude(
            {"full_name": "x/orderbook", "description": ""}, cfg))
        self.assertTrue(github_client.should_exclude(
            {"full_name": "a/awesome-quant", "description": ""}, cfg))
        self.assertTrue(github_client.should_exclude(
            {"full_name": "x/Summer2027-Internships", "description": ""}, cfg))

    def test_rank_tags_and_sorts(self):
        ranked = _pool("finance", 3)
        self.assertEqual([r["full_name"] for r in ranked],
                         ["finance/repo0", "finance/repo1", "finance/repo2"])
        self.assertTrue(all(r["category"] == "finance" and "_score" in r
                            for r in ranked))

    def test_group_items_keeps_category_order(self):
        items = [(_repo("dao/a", 80, "daoshu"), SUMMARY),
                 (_repo("fin/b", 2000, "finance"), SUMMARY)]
        groups = scoring.group_items(items, config.CATEGORIES)
        self.assertEqual([c["key"] for c, _ in groups], ["finance", "daoshu"])
        self.assertEqual(groups[0][1][0][0]["full_name"], "fin/b")
        self.assertEqual(groups[1][1][0][0]["full_name"], "dao/a")


class TestRotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "history.json")

    def test_dedupe_rotates_within_category(self):
        h = store.load(self.path)
        pool = _pool("finance", 5)
        first = store.dedupe_for_category(h, pool, "finance", 3)
        store.mark_recommended(h, first, "2026-11-05")
        second = store.dedupe_for_category(h, pool, "finance", 3)
        names = [r["full_name"] for r in second]
        self.assertIn("finance/repo3", names)
        self.assertIn("finance/repo4", names)
        self.assertEqual(len(names), 3)

    def test_legacy_history_does_not_block_new_category(self):
        h = store.load(self.path)
        store.mark_recommended(h, [_repo("old/a", 100)], "2026-11-01")
        self.assertEqual(h["recommended"]["old/a"]["category"], "legacy")
        out = store.dedupe_for_category(h, _pool("finance", 4), "finance", 3)
        self.assertEqual(len(out), 3)

    def test_cross_category_dedupe_is_independent(self):
        h = store.load(self.path)
        pool = _pool("finance", 4)
        store.mark_recommended(h, pool[:3], "2026-11-05")
        dao_out = store.dedupe_for_category(h, _pool("daoshu", 3), "daoshu", 3)
        self.assertEqual(len(dao_out), 3)
        self.assertTrue(all(r["category"] == "daoshu" for r in dao_out))

    def test_recent_names_only_looks_back_within_window(self):
        h = store.load(self.path)
        rows = _pool("finance", 3)[:2]
        store.set_day_selection(h, "2026-11-04", rows)
        store.set_day_selection(h, "2026-10-20", rows)
        expected = {r["full_name"] for r in rows}
        self.assertEqual(store.recent_names(h, "finance", "2026-11-05", 7),
                         expected)
        self.assertEqual(store.recent_names(h, "finance", "2026-11-05", 1),
                         expected)
        self.assertEqual(store.recent_names(h, "finance", "2026-11-01", 7),
                         set())

    def test_recent_window_prevents_consecutive_repeats(self):
        """候选轮完一圈后，昨天上过榜的仍排在最后，不会连续重复。"""
        h = store.load(self.path)
        pool = _pool("finance", 5)
        store.mark_recommended(h, pool, "2026-11-01")
        store.set_day_selection(h, "2026-11-04", pool[:3])
        recent = store.recent_names(h, "finance", "2026-11-05", 7)
        out = store.dedupe_for_category(h, pool, "finance", 3, recent)
        self.assertEqual({r["full_name"] for r in out},
                         {"finance/repo3", "finance/repo4",
                          "finance/repo0"})
        self.assertNotIn("finance/repo1", [r["full_name"] for r in out])

    def test_last_selection_fallback(self):
        h = store.load(self.path)
        picked = _pool("daoshu", 3)[:2]
        store.set_day_selection(h, "2026-11-04", picked)
        got = store.last_selection_for_category(h, "daoshu", "2026-11-05")
        self.assertEqual(len(got), 2)
        self.assertTrue(all("_score" in r for r in got))
        self.assertEqual(store.last_selection_for_category(
            h, "daoshu", "2026-11-04"), [])


class TestCategorySearch(unittest.TestCase):
    class _Cfg:
        GITHUB_TOKEN = "t"
        GITHUB_API_BASE = "https://api.github.test"
        PER_PAGE = 50
        MAX_PAGES = 1
        MAX_CANDIDATES = 400
        SEARCH_INTERVAL = 0
        EXCLUDE_FORKS = True
        EXCLUDE_KEYWORDS = []
        HTTP_MAX_RETRIES = 3
        HTTP_RETRY_BASE_DELAY = 0

    @staticmethod
    def _cat():
        return {"key": "finance", "label": "金融与量化", "min_stars": 500,
                "keywords": ["quant", "trading"], "match": ["quant"]}

    @staticmethod
    def _resp():
        resp = mock.Mock()
        resp.status_code = 200
        resp.json.return_value = {"items": [
            {"full_name": "a/b", "stargazers_count": 900},
            {"full_name": "c/d", "stargazers_count": 700},
        ]}
        return resp

    def test_query_has_no_created_filter_and_merges_keywords(self):
        with mock.patch.object(
            github_client, "_request_with_retry", return_value=self._resp()
        ) as m, mock.patch.object(github_client.time, "sleep"):
            rows = github_client.search_category(self._Cfg(), self._cat())
        self.assertEqual(len(rows), 2)  # 两个关键词命中同一仓库，已合并
        self.assertEqual(rows[0]["_queries"], ["quant", "trading"])
        q = m.call_args.kwargs["params"]["q"]
        self.assertIn("stars:>500", q)
        self.assertIn("fork:false", q)
        self.assertIn("archived:false", q)
        self.assertIn("in:name,description", q)
        self.assertNotIn("created:", q)

    def test_single_keyword_failure_does_not_break_batch(self):
        with mock.patch.object(
            github_client, "_request_with_retry",
            side_effect=[github_client.RateLimitError("limited"), self._resp()]
        ), mock.patch.object(github_client.time, "sleep"):
            rows = github_client.search_category(self._Cfg(), self._cat())
        self.assertEqual([r["full_name"] for r in rows], ["a/b", "c/d"])

    def test_secondary_rate_limit_is_retried(self):
        limited = mock.Mock(status_code=403, ok=False,
                            text="You have exceeded a secondary rate limit")
        ok = mock.Mock(status_code=200, ok=True)
        ok.raise_for_status = mock.Mock()
        with mock.patch.object(
            github_client.requests.Session, "request",
            side_effect=[limited, ok]
        ), mock.patch.object(github_client.time, "sleep") as sleep:
            resp = github_client._request_with_retry(
                "GET", "https://api.github.test/x", headers={},
                config=self._Cfg())
        self.assertIs(resp, ok)
        sleep.assert_called_once()

    def test_fetch_candidates_excludes_list_repos(self):
        cfg = self._Cfg()
        cfg.CATEGORIES = [self._cat()]
        cfg.EXCLUDE_KEYWORDS = ["awesome"]
        resp = mock.Mock()
        resp.status_code = 200
        resp.json.return_value = {"items": [
            {"full_name": "a/awesome-quant", "description": "",
             "stargazers_count": 900},
            {"full_name": "c/quant-lib", "description": "",
             "stargazers_count": 700},
        ]}
        with mock.patch.object(
            github_client, "_request_with_retry", return_value=resp
        ), mock.patch.object(github_client.time, "sleep"):
            pools = github_client.fetch_candidates(cfg)
        self.assertEqual([r["full_name"] for r in pools["finance"]],
                         ["c/quant-lib"])


class TestScoreIsVisible(unittest.TestCase):
    def _cfg(self, d):
        class C:
            SITE_DIR = d
            SITE_TITLE = "GitHub 双榜 · 金融与道术"
            CATEGORIES = config.CATEGORIES
            PER_CATEGORY = 3
            TZ_OFFSET_HOURS = 8
            SITE_BASE_URL = ""
        return C()

    def test_article_and_site_show_score_and_evidence(self):
        items = [(_repo("fin/a", 2000, "finance"), SUMMARY),
                 (_repo("dao/b", 80, "daoshu"), SUMMARY)]
        md = article.build_article(items, "2026-11-05", "看点", config)
        self.assertIn("综合质量分", md)
        self.assertIn("评分依据：", md)
        self.assertIn("2,000 收藏", md)
        self.assertIn("## 道术 · 玄学术数", md)

        with tempfile.TemporaryDirectory() as d:
            files = site.render_site(store.load(os.path.join(d, "h.json")),
                                     items, "看点", "2026-11-05", md,
                                     self._cfg(d))
            with open(files["index"], encoding="utf-8") as f:
                page = f.read()
        self.assertEqual(page.count('class="score"'), 2)
        self.assertIn("评分依据：", page)
        self.assertIn('id="cat-finance"', page)
        self.assertIn('id="cat-daoshu"', page)
        self.assertIn("累计收藏", page)
        self.assertIn("最近维护", page)


class TestMobileCompatibility(unittest.TestCase):
    """移动端：三档断点、分类导航不丢、多列折叠、触摸目标、长文本不溢出。"""

    @staticmethod
    def _block(width: int) -> str:
        marker = f"@media(max-width:{width}px){{"
        return site.CSS.split(marker, 1)[1].split("\n}", 1)[0]

    def test_breakpoints_cover_tablet_phone_narrow(self):
        for w in (880, 640, 380):
            self.assertIn(f"@media(max-width:{w}px)", site.CSS)

    def test_category_navigation_survives_on_mobile(self):
        tablet = self._block(880)
        self.assertNotIn(".jump{display:none}", tablet)
        self.assertIn(".num-link{display:none}", tablet)
        self.assertIn("justify-content:flex-end", tablet)
        nav = site._topbar("GitHub 双榜 · 金融与道术", [None] * 2,
                           "2026-11-05", False, config.CATEGORIES)
        self.assertIn('class="cat-link"', nav)
        self.assertIn('class="num-link"', nav)
        self.assertIn("#cat-finance", nav)
        self.assertIn("#cat-daoshu", nav)
        self.assertIn('title="GitHub 双榜 · 金融与道术"', nav)

    def test_all_multi_column_blocks_collapse_on_phone(self):
        phone = self._block(640)
        for frag in (".entry{grid-template-columns:1fr",
                     ".cat-head{grid-template-columns:1fr",
                     ".method dl{grid-template-columns:1fr",
                     ".section{grid-template-columns:1fr",
                     ".live{display:none}",
                     ".tools a{display:inline-flex"):
            self.assertIn(frag, phone)

    def test_touch_targets_and_overflow_guards(self):
        self.assertIn("min-height:44px", site.CSS)
        self.assertIn("minmax(0,1fr)", site.CSS)
        self.assertIn("overflow-wrap:anywhere", site.CSS)
        self.assertIn("overflow-x:auto", site.CSS)
        self.assertIn('name="viewport" content="width=device-width,initial-scale=1"',
                      site._head("t"))

    def test_article_score_lines_are_short_for_phone(self):
        """评分依据按分项拆行，避免手机上出现一整屏长的单行数字。"""
        items = [(_repo("fin/a", 2000, "finance"), SUMMARY)]
        md = article.build_article(items, "2026-11-05", "", config)
        score_lines = [ln for ln in md.splitlines() if ln.startswith("> - ")]
        self.assertEqual(len(score_lines), 4)
        self.assertTrue(all(len(ln) < 60 for ln in score_lines))
        self.assertIn("累计收藏", md)
        self.assertIn("最近维护", md)


if __name__ == "__main__":
    unittest.main()
