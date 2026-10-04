"""Claim extraction and evidence-provider boundary.

The bundled provider deliberately returns no external evidence. This keeps
heuristics from being presented as fact checking while making future providers
easy to add behind a small interface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Claim:
    text: str
    status: str = "UNVERIFIED"
    evidence: list[str] | None = None
    confidence: str = "Unavailable"


class EvidenceProvider(Protocol):
    def find_evidence(self, claim: str) -> list[dict]: ...


class NoEvidenceProvider:
    def find_evidence(self, claim: str) -> list[dict]:
        return []


def extract_claims(text: str, limit: int = 5) -> list[Claim]:
    """Surface candidate factual sentences for review; this does not verify them."""
    factual_cues = re.compile(r"\b(?:said|reported|found|shows|according to|data|study|percent|million|billion|will|caused|increased|decreased|announced|confirmed)\b", re.I)
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or ""))
    claims = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence.split()) >= 9 and factual_cues.search(sentence):
            claims.append(Claim(sentence[:600], evidence=[]))
            if len(claims) >= limit:
                break
    return claims


def get_claim_evidence(claim: str, provider: EvidenceProvider | None = None) -> list[dict]:
    return (provider or NoEvidenceProvider()).find_evidence(claim)
