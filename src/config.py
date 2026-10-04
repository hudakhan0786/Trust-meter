"""
config.py
=========
Single source of truth for every tunable constant in the detection engine:
scoring weights, thresholds, the clickbait phrase lexicon, and the seed
whitelist/blacklist of news domains.

Keeping these in one module means the scoring logic in the other files stays
readable (no magic numbers) and means a reviewer can audit "why did this get
flagged?" by reading one file, rather than hunting through the codebase.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

DB_PATH = DATA_DIR / "fake_news_detector.db"
WHITELIST_PATH = DATA_DIR / "domains_whitelist.json"
BLACKLIST_PATH = DATA_DIR / "domains_blacklist.json"
SAMPLE_ARTICLES_PATH = DATA_DIR / "sample_articles.json"

GVERIFY_JS_PATH = OUTPUT_DIR / "gverify.js"
DASHBOARD_HTML_PATH = OUTPUT_DIR / "dashboard.html"

# ---------------------------------------------------------------------------
# Clickbait lexicon
# ---------------------------------------------------------------------------
# Case-insensitive substrings. Kept lowercase; matching lowercases the input.
CLICKBAIT_TRIGGER_PHRASES = [
    "you won't believe", "you wont believe", "won't believe what",
    "shocking", "mind-blowing", "mind blowing", "this one trick",
    "one weird trick", "doctors hate", "what happens next",
    "gone wrong", "gone viral", "goes viral", "the truth about",
    "secret they don't want", "will blow your mind", "number will shock you",
    "this is why", "breaks the internet", "epic fail", "exposed",
    "banned", "outrageous", "jaw-dropping", "jaw dropping",
    "unbelievable", "you need to see", "before it's deleted",
    "before it is deleted", "they don't want you to know",
    "scientists hate", "destroys", "obliterates", "slams",
    "instantly regret", "changed forever", "will never be the same",
    "click here", "find out why", "the reason will",
]

# Short, legitimate all-caps acronyms that should NOT count as "shouting"
KNOWN_ACRONYMS = {
    "US", "UK", "EU", "UN", "FBI", "CIA", "CEO", "CFO", "CTO", "NASA",
    "WHO", "COVID", "GDP", "AI", "IPO", "NATO", "FDA", "SEC", "IRS",
    "NYC", "LA", "USA", "UAE", "PM", "MP", "ID", "IT", "PhD", "OK",
}

# ---------------------------------------------------------------------------
# Clickbait sub-score weights (each sub-score is 0-100; higher = more
# sensational). Overall clickbait_score is a weighted blend of the three.
# ---------------------------------------------------------------------------
CLICKBAIT_WEIGHTS = {
    "all_caps": 0.40,
    "trigger_phrase": 0.35,
    "punctuation": 0.25,
}

# Points awarded per unit, each sub-score is capped at 100 individually.
ALL_CAPS_POINTS_PER_WORD = 25          # each shouted word adds this many points
TRIGGER_PHRASE_POINTS_PER_HIT = 35     # each matched phrase adds this many points
EXCLAMATION_POINTS_PER_MARK = 25       # each "!" beyond the first free one
QUESTION_MARK_POINTS_PER_MARK = 10     # each "?" beyond the first free one
FREE_EXCLAMATIONS = 1                  # first exclamation mark is not penalised
FREE_QUESTION_MARKS = 1                # first question mark is not penalised

# ---------------------------------------------------------------------------
# Source reputation scores (0-100 trust scale)
# ---------------------------------------------------------------------------
WHITELIST_TRUST_SCORE = 90
BLACKLIST_TRUST_SCORE = 10
UNKNOWN_DOMAIN_TRUST_SCORE = 50  # neutral prior; confidence remains low

# ---------------------------------------------------------------------------
# Lexical diversity normalisation
# ---------------------------------------------------------------------------
# MATTR (Moving-Average Type-Token Ratio) typically falls between ~0.30
# (very repetitive) and ~0.75+ (highly diverse) for English news prose.
# We linearly map that observed range onto a 0-100 "diversity trust" score.
LEXICAL_MATTR_FLOOR = 0.30
LEXICAL_MATTR_CEILING = 0.75
MATTR_WINDOW_SIZE = 50  # words per rolling window; falls back to plain TTR
                          # for articles shorter than this

# ---------------------------------------------------------------------------
# Final trust score blend (must sum to 1.0)
# ---------------------------------------------------------------------------
FINAL_SCORE_WEIGHTS = {
    "source": 0.25,
    "evidence": 0.10,
    "headline": 0.20,
    "linguistic": 0.15,
    "quality": 0.15,
    "consistency": 0.15,
}

# Verdict thresholds on the final 0-100 trust score
VERDICT_THRESHOLDS = [
    (80, "High Credibility"),
    (60, "Generally Credible"),
    (40, "Needs Verification"),
    (0, "Low Credibility"),
]

# ---------------------------------------------------------------------------
# Scraper behaviour
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "TrustMeterResearchDemo/2.0 (+article analysis; contact: admin@example.org)"
MIN_PARAGRAPH_LENGTH = 40  # ignore short boilerplate <p> tags (nav, ads, etc.)


def verdict_for_score(score: float) -> str:
    """Map a final 0-100 trust score onto a human-readable verdict label."""
    for threshold, label in VERDICT_THRESHOLDS:
        if score >= threshold:
            return label
    return VERDICT_THRESHOLDS[-1][1]
