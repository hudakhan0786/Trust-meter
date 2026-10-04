"""TrustMeter Flask web application and JSON API."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request

from src import config, database, pipeline, source_reputation
from src.scraper import ScrapeError, scrape_article


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 600_000
database.init_db()


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'")
    return response


def _analyze(payload: dict):
    mode = payload.get("input_mode", "text")
    if mode == "url":
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError("Enter an article URL to continue.")
        scraped = scrape_article(url)
        headline, body = scraped.headline, scraped.body_text
        source_url = scraped.canonical_url or scraped.url
        metadata = {"author": scraped.author, "published_at": scraped.published_at, "publisher": scraped.publisher, "description": scraped.description, "language": scraped.language}
    elif mode == "text":
        source_url = str(payload.get("source_url", "")).strip()
        headline = str(payload.get("headline", "")).strip()
        body = str(payload.get("body", "")).strip()
        if not headline:
            raise ValueError("Enter the article headline.")
        if not body:
            raise ValueError("Paste the article text to continue.")
        if len(headline) > 1000 or len(body) > 500_000:
            raise ValueError("The headline or article text exceeds the supported length.")
        if source_url:
            parsed = urlparse(source_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("Source URL must begin with http:// or https://.")
        else:
            source_url = "https://unknown-source.invalid/manual-article"
        metadata = {}
    else:
        raise ValueError("Choose URL or pasted text analysis.")
    result = pipeline.analyze_article(source_url, headline, body, source_reputation.load_whitelist(), source_reputation.load_blacklist())
    result.metadata = metadata
    return result


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/demo")
def demo():
    samples = json.loads(config.SAMPLE_ARTICLES_PATH.read_text(encoding="utf-8"))
    sample = samples["reference_sample_article"]
    result = pipeline.analyze_article(sample["url"], sample["headline"], sample["body_text"], persist=False)
    return render_template("result.html", result=result)


@app.post("/analyze")
def analyze():
    payload = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    payload = payload or {}
    try:
        result = _analyze(payload)
    except (ValueError, ScrapeError) as exc:
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        return render_template("index.html", error=str(exc), values=payload), 400
    except Exception:
        app.logger.exception("Analysis pipeline failed")
        if request.is_json:
            return jsonify({"error": "Analysis could not be completed. Please try again."}), 500
        return render_template("index.html", error="Analysis could not be completed. Please try again.", values=payload), 500
    if request.is_json:
        output = asdict(result)
        output["analysis_id"] = result.article_id
        output["credibility_score"] = result.final_trust_score
        return jsonify(output)
    return render_template("result.html", result=result)


@app.get("/history")
def history():
    return render_template("history.html", rows=database.fetch_analysis_history())


@app.get("/history/<int:log_id>")
def history_report(log_id: int):
    row = database.fetch_scored_analysis(log_id)
    if row is None:
        abort(404)
    lexical_breakdown = row["lexical_breakdown"]
    return render_template(
        "history_report.html",
        row=row,
        components=lexical_breakdown.get("components", []),
        claims=lexical_breakdown.get("claims", []),
        article_text=lexical_breakdown.get("body_text", ""),
    )


@app.get("/api/history")
def api_history():
    rows = database.fetch_analysis_history()
    return jsonify([dict(row) for row in rows])


@app.errorhandler(413)
def too_large(_error):
    message = "The submitted text is too large. Keep it under 500,000 characters."
    return (jsonify({"error": message}), 413) if request.is_json else (render_template("index.html", error=message), 413)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
