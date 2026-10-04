"""
clickbait_scorer.py
====================
Scores a headline for sensationalism on a 0-100 scale (0 = calm/neutral,
100 = maximally sensational). The score is built from three transparent
sub-scores so every flag can be explained in plain English:

    1. all_caps_score     - "shouted" words (ALL-CAPS, excluding acronyms)
    2. trigger_phrase_score - known clickbait phrases ("you won't believe"...)
    3. punctuation_score  - excessive "!" / "?" usage

Each sub-score is itself 0-100 and capped there; the overall score is a
weighted blend (weights live in config.py so they're auditable in one place).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from . import config

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


@dataclass
class ClickbaitResult:
    score: float                       # overall 0-100, higher = more sensational
    all_caps_score: float              # 0-100 sub-score
    trigger_phrase_score: float        # 0-100 sub-score
    punctuation_score: float           # 0-100 sub-score
    all_caps_words: List[str] = field(default_factory=list)
    trigger_phrases_found: List[str] = field(default_factory=list)
    exclamation_count: int = 0
    question_mark_count: int = 0
    reasons: List[str] = field(default_factory=list)


def _find_all_caps_words(headline: str) -> List[str]:
    """
    Return words that are fully uppercase, at least 3 letters long, and not
    in the known-acronym exclusion list (so "NASA" or "US" don't trigger
    false positives while "SHOCKING" or "SECRET" do).
    """
    found = []
    for match in _WORD_RE.finditer(headline):
        word = match.group(0)
        letters_only = re.sub(r"[^A-Za-z]", "", word)
        if len(letters_only) < 3:
            continue
        if word.upper() != word:
            continue  # not fully uppercase (mixed case)
        if word.upper() in config.KNOWN_ACRONYMS:
            continue
        found.append(word)
    return found


def _find_trigger_phrases(headline: str) -> List[str]:
    lowered = headline.lower()
    return [phrase for phrase in config.CLICKBAIT_TRIGGER_PHRASES if phrase in lowered]


def score_headline(headline: str) -> ClickbaitResult:
    """Compute the full clickbait breakdown for a single headline string."""
    headline = headline or ""

    all_caps_words = _find_all_caps_words(headline)
    trigger_phrases_found = _find_trigger_phrases(headline)
    exclamation_count = headline.count("!")
    question_mark_count = headline.count("?")

    # --- sub-score 1: shouted words -----------------------------------
    all_caps_score = min(100.0, len(all_caps_words) * config.ALL_CAPS_POINTS_PER_WORD)

    # --- sub-score 2: known clickbait phrases --------------------------
    trigger_phrase_score = min(
        100.0, len(trigger_phrases_found) * config.TRIGGER_PHRASE_POINTS_PER_HIT
    )

    # --- sub-score 3: punctuation spam (first mark of each type is free) ---
    billable_exclamations = max(0, exclamation_count - config.FREE_EXCLAMATIONS)
    billable_questions = max(0, question_mark_count - config.FREE_QUESTION_MARKS)
    punctuation_score = min(
        100.0,
        billable_exclamations * config.EXCLAMATION_POINTS_PER_MARK
        + billable_questions * config.QUESTION_MARK_POINTS_PER_MARK,
    )

    weights = config.CLICKBAIT_WEIGHTS
    overall = (
        all_caps_score * weights["all_caps"]
        + trigger_phrase_score * weights["trigger_phrase"]
        + punctuation_score * weights["punctuation"]
    )
    overall = round(min(100.0, overall), 1)

    reasons = []
    if all_caps_words:
        reasons.append(
            f"ALL-CAPS words detected: {all_caps_words} "
            f"(+{all_caps_score:.0f} sub-score)"
        )
    if trigger_phrases_found:
        reasons.append(
            f"Clickbait trigger phrase(s) matched: {trigger_phrases_found} "
            f"(+{trigger_phrase_score:.0f} sub-score)"
        )
    if billable_exclamations > 0 or billable_questions > 0:
        reasons.append(
            f"Excessive punctuation: {exclamation_count} '!' / "
            f"{question_mark_count} '?' (+{punctuation_score:.0f} sub-score)"
        )
    if not reasons:
        reasons.append("No sensationalism triggers detected in headline.")

    return ClickbaitResult(
        score=overall,
        all_caps_score=round(all_caps_score, 1),
        trigger_phrase_score=round(trigger_phrase_score, 1),
        punctuation_score=round(punctuation_score, 1),
        all_caps_words=all_caps_words,
        trigger_phrases_found=trigger_phrases_found,
        exclamation_count=exclamation_count,
        question_mark_count=question_mark_count,
        reasons=reasons,
    )
