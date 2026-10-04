import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config
from src import database
from src.scraper import ScrapeError, ScrapedArticle, extract_article, validate_public_url


class TestSafeScraper(unittest.TestCase):
    def test_rejects_internal_destinations(self):
        for url in ("http://127.0.0.1/admin", "http://10.0.0.2", "http://localhost/", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ScrapeError):
                validate_public_url(url)

    def test_revalidates_redirect_target_syntax(self):
        with patch("src.scraper.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 80))]):
            self.assertEqual(validate_public_url("https://example.org/story"), "https://example.org/story")

    def test_extracts_metadata_and_article_body(self):
        paragraph = "The national research group reported that the annual survey found a measurable increase across several regions this year."
        html = f'''<html lang="en"><head><meta property="og:title" content="Study reports annual increase"><meta name="author" content="R. Author"><script type="application/ld+json">{{"@type":"NewsArticle","headline":"Study reports annual increase","datePublished":"2025-02-03","author":{{"name":"R. Author"}}}}</script></head><body><article><p>{paragraph}</p><p>{paragraph}</p></article></body></html>'''
        article = extract_article("https://example.org/story", html)
        self.assertEqual(article.headline, "Study reports annual increase")
        self.assertEqual(article.published_at, "2025-02-03")
        self.assertIn("annual survey", article.body_text)

    def test_rejects_pages_without_meaningful_article_text(self):
        with self.assertRaises(ScrapeError):
            extract_article("https://example.org", "<html><h1>Headline</h1><p>Short.</p></html>")


class TestFlaskRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import flask  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Flask is not installed")
        import app as webapp
        cls.webapp = webapp

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_path = config.DB_PATH
        config.DB_PATH = Path(self.tmp.name) / "web-test.db"
        database.init_db()
        self.client = self.webapp.app.test_client()

    def tearDown(self):
        config.DB_PATH = self.previous_path
        self.tmp.cleanup()

    def test_home_demo_and_history_render(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn(b"Verify before", self.client.get("/").data)
        self.assertEqual(self.client.get("/demo").status_code, 200)
        self.assertEqual(self.client.get("/history").status_code, 200)

    def test_api_rejects_empty_input_and_returns_explained_assessment(self):
        empty = self.client.post("/analyze", json={"input_mode": "text"})
        self.assertEqual(empty.status_code, 400)
        good = self.client.post("/analyze", json={"input_mode": "text", "headline": "Council publishes annual budget findings", "source_url": "https://example.org/report", "body": "The municipal council reported that annual budget data shows revenues increased during the year, according to the published financial report. " * 5})
        self.assertEqual(good.status_code, 200)
        payload = good.get_json()
        self.assertIn("credibility_score", payload)
        self.assertTrue(payload["components"])
        self.assertEqual(payload["claims"][0]["status"], "UNVERIFIED")
        self.assertEqual(self.client.get("/api/history").status_code, 200)

    def test_response_has_basic_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    def test_url_mode_handles_internal_and_unavailable_targets(self):
        internal = self.client.post("/analyze", data={"input_mode": "url", "url": "http://127.0.0.1/admin"})
        self.assertEqual(internal.status_code, 400)
        self.assertIn(b"internal network", internal.data)
        with patch.object(self.webapp, "scrape_article", side_effect=ScrapeError("The article page was not found. Paste text instead.")):
            unavailable = self.client.post("/analyze", data={"input_mode": "url", "url": "https://publisher.example/missing"})
        self.assertEqual(unavailable.status_code, 400)
        self.assertIn(b"Paste text instead", unavailable.data)

    def test_url_analysis_route_returns_extracted_report_and_metadata(self):
        paragraph = "The research institute reported that annual data showed a measured increase across several regional sectors this year. " * 4
        article = ScrapedArticle("https://publisher.example/story", "Research institute reports annual figures", paragraph, author="A. Writer", published_at="2025-04-01")
        with patch.object(self.webapp, "scrape_article", return_value=article):
            response = self.client.post("/analyze", data={"input_mode": "url", "url": "https://publisher.example/story"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Research institute reports annual figures", response.data)
        self.assertIn(b"A. Writer", response.data)


if __name__ == "__main__":
    unittest.main()
