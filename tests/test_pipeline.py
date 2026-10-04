"""
test_pipeline.py
=================
Basic unit tests for each scoring module plus an end-to-end pipeline check.

Run with:
    python -m unittest discover tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import clickbait_scorer, config, database, lexical_analysis, pipeline, source_reputation


class TestClickbaitScorer(unittest.TestCase):
    def test_calm_headline_scores_low(self):
        result = clickbait_scorer.score_headline(
            "Federal Reserve Holds Interest Rates Steady"
        )
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.all_caps_words, [])
        self.assertEqual(result.trigger_phrases_found, [])

    def test_shouted_headline_scores_high(self):
        result = clickbait_scorer.score_headline(
            "YOU WON'T BELIEVE This SHOCKING Secret!!!"
        )
        self.assertGreater(result.score, 70)
        self.assertIn("SHOCKING", result.all_caps_words)
        self.assertIn("you won't believe", result.trigger_phrases_found)

    def test_known_acronyms_are_not_flagged(self):
        result = clickbait_scorer.score_headline("NASA and the FBI Meet With US Officials")
        self.assertEqual(result.all_caps_words, [])

    def test_first_exclamation_is_free(self):
        result = clickbait_scorer.score_headline("Local team wins championship!")
        self.assertEqual(result.punctuation_score, 0.0)


class TestSourceReputation(unittest.TestCase):
    def setUp(self):
        self.whitelist = {"apnews.com", "bbc.com"}
        self.blacklist = {"fakenews24.com"}

    def test_whitelisted_domain(self):
        result = source_reputation.lookup_reputation(
            "https://www.apnews.com/article/123", self.whitelist, self.blacklist
        )
        self.assertEqual(result.status, "whitelisted")
        self.assertEqual(result.domain, "apnews.com")

    def test_blacklisted_domain(self):
        result = source_reputation.lookup_reputation(
            "http://fakenews24.com/story", self.whitelist, self.blacklist
        )
        self.assertEqual(result.status, "blacklisted")

    def test_unknown_domain(self):
        result = source_reputation.lookup_reputation(
            "https://some-random-blog.example/post", self.whitelist, self.blacklist
        )
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.score, 50)
        self.assertIn("Unknown does not mean unreliable", result.reason)

    def test_subdomain_matches_parent_domain(self):
        result = source_reputation.lookup_reputation(
            "https://news.bbc.com/story", self.whitelist, self.blacklist
        )
        self.assertEqual(result.status, "whitelisted")


class TestLexicalAnalysis(unittest.TestCase):
    def test_repetitive_text_scores_lower_than_diverse_text(self):
        repetitive = "shocking shocking shocking miracle miracle miracle shocking miracle " * 5
        diverse = (
            "The committee reviewed several proposals covering infrastructure, "
            "education funding, and regional transportation before reaching a "
            "preliminary consensus on next steps for the upcoming fiscal year."
        )
        rep_result = lexical_analysis.analyze(repetitive)
        div_result = lexical_analysis.analyze(diverse)
        self.assertLess(rep_result.diversity_trust_score, div_result.diversity_trust_score)

    def test_empty_text_handled_gracefully(self):
        result = lexical_analysis.analyze("")
        self.assertEqual(result.total_words, 0)
        self.assertEqual(result.diversity_trust_score, 0.0)


class TestPipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        # Isolate the DB so tests never touch the real project database.
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test.db"
        database.init_db(self.db_path)
        self.whitelist = {"apnews.com"}
        self.blacklist = {"fakenews24.com"}

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_suspicious_article_flagged_low_trust(self):
        result = pipeline.analyze_article(
            url="http://fakenews24.com/miracle-cure",
            headline="SHOCKING Miracle Cure Doctors HATE!!!",
            body_text="shocking miracle shocking miracle shocking cure shocking " * 4,
            whitelist=self.whitelist,
            blacklist=self.blacklist,
            persist=False,
        )
        self.assertLess(result.final_trust_score, 40)
        self.assertEqual(result.verdict, "Low Credibility")

    def test_reliable_article_scores_high_trust(self):
        result = pipeline.analyze_article(
            url="https://apnews.com/article/economy",
            headline="Regional Employment Figures Rise Slightly in Third Quarter",
            body_text=(
                "Employment figures released Tuesday showed a modest increase "
                "across several regional sectors, according to newly published "
                "government data analyzed by independent economists this week."
            ),
            whitelist=self.whitelist,
            blacklist=self.blacklist,
            persist=False,
        )
        self.assertGreaterEqual(result.final_trust_score, 70)
        self.assertEqual(result.verdict, "High Credibility")

    def test_persisted_result_is_retrievable_from_evidence_store(self):
        url = "https://apnews.com/article/persisted-test"
        pipeline.analyze_article(
            url=url,
            headline="City Council Approves Annual Budget",
            body_text="The city council voted Tuesday to approve next year's operating budget.",
            whitelist=self.whitelist,
            blacklist=self.blacklist,
            persist=True,
            db_path=self.db_path,
        )

        history = database.fetch_article_history(url, db_path=self.db_path)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].verdict, "High Credibility")
        self.assertIn("total_words", history[0].lexical_breakdown)

    def test_scores_use_cautious_configured_bands_and_limited_confidence(self):
        self.assertEqual(config.verdict_for_score(80), "High Credibility")
        self.assertEqual(config.verdict_for_score(60), "Generally Credible")
        self.assertEqual(config.verdict_for_score(40), "Needs Verification")
        self.assertEqual(config.verdict_for_score(39.9), "Low Credibility")
        result = pipeline.analyze_article("https://apnews.com/story", "A headline", "The report said that annual figures showed a slight increase during this reporting period across different parts of the region." * 3, whitelist=self.whitelist, blacklist=self.blacklist, persist=False)
        self.assertEqual(result.confidence, "Limited")
        self.assertTrue(all(claim.status == "UNVERIFIED" for claim in result.claims))


if __name__ == "__main__":
    unittest.main()
