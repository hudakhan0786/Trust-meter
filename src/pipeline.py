"""Explainable, signal-based credibility assessment (not truth classification)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from . import clickbait_scorer, config, database, evidence, lexical_analysis, source_reputation


@dataclass
class Component:
    name: str
    score: float
    explanation: str
    confidence: str
    limitations: str


@dataclass
class AnalysisResult:
    url: str
    domain: str
    headline: str
    body_text: str
    word_count: int
    clickbait: clickbait_scorer.ClickbaitResult
    reputation: source_reputation.ReputationResult
    lexical: lexical_analysis.LexicalResult
    final_trust_score: float
    verdict: str
    radar_profile: Dict[str, float] = field(default_factory=dict)
    article_id: Optional[int] = None
    components: list[Component] = field(default_factory=list)
    claims: list[evidence.Claim] = field(default_factory=list)
    confidence: str = "Limited"
    analyzed_at: str = ""
    quality_signals: list[str] = field(default_factory=list)
    score_explanation: list[str] = field(default_factory=list)
    headline_consistency: float = 50.0
    metadata: dict = field(default_factory=dict)


RADAR_CATEGORIES = ["Source Reliability", "Linguistic Quality", "Headline Neutrality", "Article Quality", "Claim Evidence"]


def _headline_consistency(headline: str, body: str) -> tuple[float, str]:
    stop = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with", "as", "at", "by", "is", "are", "after", "from"}
    def words(value):
        terms = set()
        for raw in re.findall(r"[A-Za-z]{3,}", value):
            word = raw.lower()
            if word not in stop:
                terms.add(word[:-1] if len(word) > 4 and word.endswith("s") else word)
        return terms
    title_terms = words(headline)
    body_terms = words(body[:12000])
    if not title_terms or not body_terms:
        return 50.0, "Insufficient text to compare headline and body."
    overlap = len(title_terms & body_terms) / len(title_terms)
    score = round(min(70.0, max(30.0, 50 + (overlap - 0.5) * 40)), 1)
    return score, f"{len(title_terms & body_terms)} of {len(title_terms)} headline terms appear in the article text; this limited lexical check is not semantic verification."


def _quality(headline: str, body: str, reputation: source_reputation.ReputationResult) -> tuple[float, list[str]]:
    points, signals = 50.0, []
    if headline.strip():
        points += 10
    if len(body.split()) >= 100:
        points += 10
        signals.append("Substantive article text is available.")
    else:
        signals.append("Short article text limits assessment.")
    if re.search(r"\b(?:according to|said|study|report|data|source)\b", body, re.I):
        points += 10
        signals.append("Attribution or reference language appears in the text; links were not independently assessed.")
    if re.search(r"\b(?:by|author)\s+[A-Z][a-z]+", body):
        points += 5
        signals.append("Author attribution may be present in the text.")
    if reputation.status != "unknown":
        points += 5
        signals.append("A local source reputation entry is available.")
    return min(100, points), signals


def _build_radar_profile(components: list[Component]) -> Dict[str, float]:
    return {component.name: component.score for component in components}


def analyze_article(url: str, headline: str, body_text: str, whitelist=None, blacklist=None, persist: bool = True, db_path: Optional[Path] = None) -> AnalysisResult:
    headline, body_text = (headline or "").strip()[:1000], (body_text or "").strip()[:500_000]
    clickbait_result = clickbait_scorer.score_headline(headline)
    reputation_result = source_reputation.lookup_reputation(url, whitelist, blacklist)
    lexical_result = lexical_analysis.analyze(body_text)
    consistency, consistency_note = _headline_consistency(headline, body_text)
    quality_score, quality_signals = _quality(headline, body_text, reputation_result)
    claims = evidence.extract_claims(body_text)
    # A neutral evidence prior prevents absence of an API from being treated as evidence against an article.
    components = [
        Component("Source Reliability", reputation_result.score, reputation_result.reason, "Limited" if reputation_result.status == "unknown" else "Local list only", "Seeded local domain lists do not establish editorial quality or factual truth."),
        Component("Claim Evidence", 50.0, "No external fact-checking provider is configured; surfaced claims remain unverified.", "Unavailable", "A neutral placeholder is used. This component is not a fact check."),
        Component("Headline Neutrality", round(100-clickbait_result.score, 1), "; ".join(clickbait_result.reasons), "Moderate", "Lexical triggers can miss context and can flag legitimate reporting."),
        Component("Linguistic Quality", lexical_result.diversity_trust_score, "; ".join(lexical_result.reasons), "Limited", "Vocabulary diversity is not a measure of truth or writing quality by itself."),
        Component("Article Quality", quality_score, " ".join(quality_signals), "Limited", "Metadata, source links, and references may be missing or cannot be validated from pasted text."),
        Component("Headline Consistency", consistency, consistency_note, "Low", "Word overlap does not detect semantic contradiction."),
    ]
    weights = config.FINAL_SCORE_WEIGHTS
    weighted = [("Source Reliability", weights["source"]), ("Claim Evidence", weights["evidence"]), ("Headline Neutrality", weights["headline"]), ("Linguistic Quality", weights["linguistic"]), ("Article Quality", weights["quality"]), ("Headline Consistency", weights["consistency"])]
    final_score = round(sum(next(c.score for c in components if c.name == name) * weight for name, weight in weighted), 1)
    verdict = config.verdict_for_score(final_score)
    explanation = [c.explanation for c in sorted(components, key=lambda c: c.score, reverse=True)[:3]]
    word_count = lexical_result.total_words
    article_id = None
    if persist:
        database.init_db(db_path)
        article_id = database.upsert_article(url=url, domain=reputation_result.domain, headline=headline, body_text=body_text, word_count=word_count, db_path=db_path)
        database.insert_scoring_log(article_id=article_id, db_path=db_path, clickbait_score=clickbait_result.score, clickbait_breakdown={"all_caps_score": clickbait_result.all_caps_score, "trigger_phrase_score": clickbait_result.trigger_phrase_score, "punctuation_score": clickbait_result.punctuation_score, "all_caps_words": clickbait_result.all_caps_words, "trigger_phrases_found": clickbait_result.trigger_phrases_found, "exclamation_count": clickbait_result.exclamation_count, "question_mark_count": clickbait_result.question_mark_count, "reasons": clickbait_result.reasons}, source_score=reputation_result.score, source_status=reputation_result.status, source_reason=reputation_result.reason, lexical_diversity_score=lexical_result.diversity_trust_score, lexical_breakdown={"total_words": word_count, "unique_words": lexical_result.unique_words, "ttr": lexical_result.ttr, "mattr": lexical_result.mattr, "reasons": lexical_result.reasons, "components": [c.__dict__ for c in components], "claims": [c.__dict__ for c in claims], "body_text": body_text, "headline": headline, "url": url, "domain": reputation_result.domain, "word_count": word_count}, final_trust_score=final_score, verdict=verdict)
    return AnalysisResult(url, reputation_result.domain, headline, body_text, word_count, clickbait_result, reputation_result, lexical_result, final_score, verdict, _build_radar_profile(components), article_id, components, claims, "Limited", datetime.now(timezone.utc).isoformat(timespec="seconds"), quality_signals, explanation, consistency)
