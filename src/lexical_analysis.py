"""
lexical_analysis.py
====================
NLP module measuring how repetitive an article's vocabulary is. Low-quality
/ fabricated news tends to lean on a small pool of high-emotion words
repeated over and over, which shows up as a low unique-word ratio.

Two metrics are implemented:

  * Type-Token Ratio (TTR)        - unique_words / total_words. Simple, but
                                     biased downward for longer texts (more
                                     text -> more chances to repeat "the").
  * MATTR (Moving-Average TTR)    - TTR averaged over a sliding window of
                                     fixed size, which corrects for the
                                     length bias above. This is the metric
                                     used for scoring; plain TTR is reported
                                     alongside it for transparency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from . import config

_TOKEN_RE = re.compile(r"[A-Za-z']+")


@dataclass
class LexicalResult:
    total_words: int
    unique_words: int
    ttr: float                  # raw type-token ratio, 0-1
    mattr: float                # moving-average TTR, 0-1 (used for scoring)
    diversity_trust_score: float  # mattr normalised onto 0-100
    reasons: List[str] = field(default_factory=list)


def tokenize(text: str) -> List[str]:
    """Lowercase word tokenizer; strips punctuation, keeps internal apostrophes."""
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def type_token_ratio(words: List[str]) -> float:
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def moving_average_ttr(words: List[str], window_size: int = None) -> float:
    """
    MATTR: average TTR computed over every sliding window of `window_size`
    words. Falls back to plain TTR when the article is shorter than one
    window, so short articles still get a sensible (if less robust) score.
    """
    window_size = window_size or config.MATTR_WINDOW_SIZE
    n = len(words)
    if n == 0:
        return 0.0
    if n < window_size:
        return type_token_ratio(words)

    ratios = []
    for start in range(0, n - window_size + 1):
        window = words[start:start + window_size]
        ratios.append(len(set(window)) / window_size)
    return sum(ratios) / len(ratios)


def _normalise_to_trust_score(mattr: float) -> float:
    """Linearly map MATTR from [floor, ceiling] onto [0, 100], clipped."""
    floor = config.LEXICAL_MATTR_FLOOR
    ceiling = config.LEXICAL_MATTR_CEILING
    if ceiling <= floor:
        return 50.0
    fraction = (mattr - floor) / (ceiling - floor)
    return round(min(100.0, max(0.0, fraction * 100.0)), 1)


def analyze(text: str) -> LexicalResult:
    """Run the full lexical diversity analysis on a body of article text."""
    words = tokenize(text)
    total = len(words)
    unique = len(set(words))

    ttr = round(type_token_ratio(words), 4)
    mattr = round(moving_average_ttr(words), 4)
    diversity_trust_score = _normalise_to_trust_score(mattr)

    reasons = [
        f"{total} total words, {unique} unique ({ttr * 100:.1f}% raw TTR).",
        f"MATTR (window={config.MATTR_WINDOW_SIZE}): {mattr:.3f} "
        f"-> diversity trust score {diversity_trust_score:.0f}/100.",
    ]
    if mattr < 0.40 and total >= 20:
        reasons.append(
            "Vocabulary is notably repetitive for this article's length - "
            "a common signature of low-quality, high-emotion copy."
        )

    return LexicalResult(
        total_words=total,
        unique_words=unique,
        ttr=ttr,
        mattr=mattr,
        diversity_trust_score=diversity_trust_score,
        reasons=reasons,
    )
