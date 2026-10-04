"""
source_reputation.py
=====================
Parses the URL of an article and looks its domain up against a local
whitelist / blacklist of news domains, returning a 0-100 trust score.

Whitelist/blacklist are stored as small JSON files under data/ so they're
easy to hand-edit or swap out for a larger curated list (e.g. exported
from NewsGuard or Media Bias/Fact Check) without touching code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Set
from urllib.parse import urlparse

from . import config


@dataclass
class ReputationResult:
    domain: str
    status: str          # "whitelisted" | "blacklisted" | "unknown"
    score: float          # 0-100 trust score
    reason: str


def _load_domain_set(path: Path) -> Set[str]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return {d.lower().strip() for d in payload.get("domains", [])}


def load_whitelist() -> Set[str]:
    return _load_domain_set(config.WHITELIST_PATH)


def load_blacklist() -> Set[str]:
    return _load_domain_set(config.BLACKLIST_PATH)


def extract_domain(url: str) -> str:
    """Return a normalized hostname; ports and credentials never enter lookup."""
    try:
        parsed = urlparse(url if "://" in url else f"//{url}")
        domain = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
    except (ValueError, UnicodeError):
        domain = ""
    return domain[4:] if domain.startswith("www.") else domain


def _matches(domain: str, domain_set: Set[str]) -> bool:
    """Exact match, or match on a registrable parent (e.g. 'news.bbc.co.uk' -> 'bbc.co.uk')."""
    if domain in domain_set:
        return True
    return any(domain.endswith("." + d) for d in domain_set)


def lookup_reputation(
    url: str,
    whitelist: Set[str] | None = None,
    blacklist: Set[str] | None = None,
) -> ReputationResult:
    """Look a URL's domain up against the whitelist/blacklist and return a trust score."""
    whitelist = whitelist if whitelist is not None else load_whitelist()
    blacklist = blacklist if blacklist is not None else load_blacklist()

    domain = extract_domain(url)

    if _matches(domain, blacklist):
        return ReputationResult(
            domain=domain,
            status="blacklisted",
            score=config.BLACKLIST_TRUST_SCORE,
            reason=f"'{domain}' matches an entry on the local blacklist.",
        )

    if _matches(domain, whitelist):
        return ReputationResult(
            domain=domain,
            status="whitelisted",
            score=config.WHITELIST_TRUST_SCORE,
            reason=f"'{domain}' matches an entry on the local whitelist.",
        )

    return ReputationResult(
        domain=domain,
        status="unknown",
        score=config.UNKNOWN_DOMAIN_TRUST_SCORE,
            reason=f"No local reputation record is available for '{domain}'. Unknown does not mean unreliable; source evidence is insufficient.",
    )
