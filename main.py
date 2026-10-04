#!/usr/bin/env python3
"""
main.py
=======
Command-line entry point for TRUSTMETER News Credibility Analyzer.

Usage
-----
    # Fully offline demo using two bundled sample articles:
    python main.py --demo

    # Score a live article (requires network access):
    python main.py --url https://example.com/some-article

    # Score manually-supplied content (no network / no scraping needed):
    python main.py --url https://example.com/some-article \\
                    --headline "Some Headline" \\
                    --body "Full article body text..."

    # Show every article scored so far, from the SQLite evidence store:
    python main.py --history
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from src import config, database, pipeline, source_reputation, visualizer
from src.scraper import ScrapeError, scrape_article

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("fake_news_detector")


def _load_sample_articles() -> dict:
    with open(config.SAMPLE_ARTICLES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _print_report(result: pipeline.AnalysisResult) -> None:
    bar = "=" * 72
    print(f"\n{bar}")
    print(f" TRUSTMETER CREDIBILITY ASSESSMENT")
    print(bar)
    print(f" Headline : {result.headline}")
    print(f" URL      : {result.url}")
    print(f" Domain   : {result.domain}  [{result.reputation.status}]")
    print("-" * 72)
    print(f" Clickbait score (0-100, higher=worse) : {result.clickbait.score}")
    for reason in result.clickbait.reasons:
        print(f"     - {reason}")
    print(f" Source reputation score (0-100)        : {result.reputation.score}")
    print(f"     - {result.reputation.reason}")
    print(f" Lexical diversity score (0-100)        : {result.lexical.diversity_trust_score}")
    for reason in result.lexical.reasons:
        print(f"     - {reason}")
    print("-" * 72)
    print(f" CREDIBILITY SCORE : {result.final_trust_score} / 100")
    print(f" ASSESSMENT         : {result.verdict}")
    print(" Note: this estimates credibility from available signals; it does not determine truth.")
    print(" RADAR PROFILE:")
    for axis, value in result.radar_profile.items():
        print(f"     - {axis:<24s}: {value}")
    print(bar)


def _score_baseline(whitelist, blacklist) -> pipeline.AnalysisResult:
    samples = _load_sample_articles()
    baseline = samples["reference_sample_article"]
    return pipeline.analyze_article(
        url=baseline["url"],
        headline=baseline["headline"],
        body_text=baseline["body_text"],
        whitelist=whitelist,
        blacklist=blacklist,
        persist=True,
    )


def run_demo(whitelist, blacklist) -> None:
    samples = _load_sample_articles()
    suspicious_raw = samples["suspicious_article"]

    suspicious = pipeline.analyze_article(
        url=suspicious_raw["url"],
        headline=suspicious_raw["headline"],
        body_text=suspicious_raw["body_text"],
        whitelist=whitelist,
        blacklist=blacklist,
        persist=True,
    )
    baseline = _score_baseline(whitelist, blacklist)

    _print_report(suspicious)
    _print_report(baseline)

    js_path = visualizer.export_gverify_js(suspicious, baseline)
    html_path = visualizer.export_dashboard_html(suspicious, baseline)
    print(f"\nExported: {js_path}")
    print(f"Exported: {html_path}")


def run_url(url: str, headline: str | None, body: str | None, whitelist, blacklist) -> None:
    if headline and body:
        # Manual override: skip network entirely.
        article_headline, article_body = headline, body
    else:
        try:
            scraped = scrape_article(url)
            article_headline, article_body = scraped.headline, scraped.body_text
        except ScrapeError as exc:
            logger.error(str(exc))
            logger.error(
                "Scrape failed. Retry with --headline and --body to supply "
                "content manually, or run `python main.py --demo` for an "
                "offline example."
            )
            sys.exit(1)

    suspicious = pipeline.analyze_article(
        url=url,
        headline=article_headline,
        body_text=article_body,
        whitelist=whitelist,
        blacklist=blacklist,
        persist=True,
    )
    baseline = _score_baseline(whitelist, blacklist)

    _print_report(suspicious)

    js_path = visualizer.export_gverify_js(suspicious, baseline)
    html_path = visualizer.export_dashboard_html(suspicious, baseline)
    print(f"\nExported: {js_path}")
    print(f"Exported: {html_path}")


def run_history() -> None:
    database.init_db()
    rows = database.fetch_all_scored_articles()
    if not rows:
        print("No articles have been scored yet. Try `python main.py --demo` first.")
        return

    print(f"\n{'TRUST':>6}  {'VERDICT':<24} {'DOMAIN':<28} HEADLINE")
    print("-" * 100)
    for row in rows:
        print(
            f"{row['final_trust_score']:>6.1f}  "
            f"{row['verdict']:<24} "
            f"{row['domain']:<28} "
            f"{row['headline'][:60]}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TRUSTMETER - explainable news credibility assessment from available signals."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true", help="Run fully offline on bundled sample articles.")
    mode.add_argument("--url", type=str, help="Article URL to scrape and score.")
    mode.add_argument("--history", action="store_true", help="List every article scored so far.")

    parser.add_argument("--headline", type=str, default=None, help="Manually supply the headline (skips scraping).")
    parser.add_argument("--body", type=str, default=None, help="Manually supply the body text (skips scraping).")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    database.init_db()
    whitelist = source_reputation.load_whitelist()
    blacklist = source_reputation.load_blacklist()

    if args.history:
        run_history()
    elif args.demo:
        run_demo(whitelist, blacklist)
    elif args.url:
        run_url(args.url, args.headline, args.body, whitelist, blacklist)


if __name__ == "__main__":
    main()
