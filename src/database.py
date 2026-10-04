"""
database.py
============
The "Relational Evidence Store". Two tables:

  Articles      - one row per scraped/submitted article (the raw evidence).
  Scoring_Log   - one row per scoring run against an article, storing every
                  sub-score plus a JSON breakdown of *why* it was flagged.
                  An article can be re-scored over time (e.g. after the
                  whitelist/blacklist is updated), so this is 1-to-many
                  rather than folded into the Articles table.

Using a foreign key ties the audit trail (the "why") back to the source
evidence (the "what"), which is the point of calling this an evidence store
rather than just a cache.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS Articles (
    article_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE NOT NULL,
    domain       TEXT NOT NULL,
    headline     TEXT NOT NULL,
    body_text    TEXT NOT NULL,
    word_count   INTEGER NOT NULL,
    scraped_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Scoring_Log (
    log_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id              INTEGER NOT NULL,
    clickbait_score         REAL NOT NULL,
    clickbait_breakdown     TEXT NOT NULL,   -- JSON
    source_score            REAL NOT NULL,
    source_status           TEXT NOT NULL,
    source_reason           TEXT NOT NULL,
    lexical_diversity_score REAL NOT NULL,
    lexical_breakdown       TEXT NOT NULL,   -- JSON
    final_trust_score       REAL NOT NULL,
    verdict                 TEXT NOT NULL,
    scored_at               TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES Articles(article_id)
);

CREATE INDEX IF NOT EXISTS idx_scoring_log_article_id
    ON Scoring_Log(article_id);
"""


@dataclass
class ArticleRecord:
    article_id: int
    url: str
    domain: str
    headline: str
    body_text: str
    word_count: int
    scraped_at: str


@dataclass
class ScoringLogRecord:
    log_id: int
    article_id: int
    clickbait_score: float
    clickbait_breakdown: dict
    source_score: float
    source_status: str
    source_reason: str
    lexical_diversity_score: float
    lexical_breakdown: dict
    final_trust_score: float
    verdict: str
    scored_at: str


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    db_path = db_path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Create the Articles / Scoring_Log tables if they don't already exist."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def upsert_article(
    url: str,
    domain: str,
    headline: str,
    body_text: str,
    word_count: int,
    db_path: Optional[Path] = None,
) -> int:
    """
    Insert an article, or if the URL already exists, refresh its content
    (an article can be re-scraped/re-submitted). Returns the article_id.
    """
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO Articles (url, domain, headline, body_text, word_count, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                domain=excluded.domain,
                headline=excluded.headline,
                body_text=excluded.body_text,
                word_count=excluded.word_count,
                scraped_at=excluded.scraped_at
            """,
            (url, domain, headline, body_text, word_count, _utcnow_iso()),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT article_id FROM Articles WHERE url = ?", (url,)).fetchone()
        return row["article_id"]


def insert_scoring_log(
    article_id: int,
    clickbait_score: float,
    clickbait_breakdown: dict,
    source_score: float,
    source_status: str,
    source_reason: str,
    lexical_diversity_score: float,
    lexical_breakdown: dict,
    final_trust_score: float,
    verdict: str,
    db_path: Optional[Path] = None,
) -> int:
    """Insert one scoring run's full breakdown into the evidence store."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO Scoring_Log (
                article_id, clickbait_score, clickbait_breakdown,
                source_score, source_status, source_reason,
                lexical_diversity_score, lexical_breakdown,
                final_trust_score, verdict, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id,
                clickbait_score,
                json.dumps(clickbait_breakdown),
                source_score,
                source_status,
                source_reason,
                lexical_diversity_score,
                json.dumps(lexical_breakdown),
                final_trust_score,
                verdict,
                _utcnow_iso(),
            ),
        )
        return cur.lastrowid


def fetch_article_history(url: str, db_path: Optional[Path] = None) -> List[ScoringLogRecord]:
    """All scoring runs ever logged for a given article URL, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT sl.* FROM Scoring_Log sl
            JOIN Articles a ON a.article_id = sl.article_id
            WHERE a.url = ?
            ORDER BY sl.scored_at DESC
            """,
            (url,),
        ).fetchall()

    return [
        ScoringLogRecord(
            log_id=r["log_id"],
            article_id=r["article_id"],
            clickbait_score=r["clickbait_score"],
            clickbait_breakdown=json.loads(r["clickbait_breakdown"]),
            source_score=r["source_score"],
            source_status=r["source_status"],
            source_reason=r["source_reason"],
            lexical_diversity_score=r["lexical_diversity_score"],
            lexical_breakdown=json.loads(r["lexical_breakdown"]),
            final_trust_score=r["final_trust_score"],
            verdict=config.verdict_for_score(r["final_trust_score"]),
            scored_at=r["scored_at"],
        )
        for r in rows
    ]


def fetch_all_scored_articles(db_path: Optional[Path] = None) -> List[dict]:
    """Latest scoring result per article, for a CLI --history summary view."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT a.headline, a.domain, a.url,
                   sl.final_trust_score, sl.verdict, sl.scored_at
            FROM Scoring_Log sl
            JOIN Articles a ON a.article_id = sl.article_id
            WHERE sl.log_id IN (
                SELECT MAX(log_id) FROM Scoring_Log GROUP BY article_id
            )
            ORDER BY sl.scored_at DESC
            """
        ).fetchall()
    results = [dict(row) for row in rows]
    for row in results:
        # Existing databases can contain the retired truth-classification labels.
        row["verdict"] = config.verdict_for_score(row["final_trust_score"])
    return results


def _analysis_history_query(where: str = "", params: tuple = (), db_path: Optional[Path] = None) -> List[dict]:
    """Return saved analysis runs with their article details and stored explanations."""
    query = f"""
        SELECT sl.log_id, sl.article_id, sl.clickbait_score,
               sl.clickbait_breakdown, sl.source_score, sl.source_status,
               sl.source_reason, sl.lexical_diversity_score, sl.lexical_breakdown,
               sl.final_trust_score, sl.verdict, sl.scored_at,
               a.url, a.domain, a.headline, a.word_count, a.scraped_at
        FROM Scoring_Log sl
        JOIN Articles a ON a.article_id = sl.article_id
        {where}
        ORDER BY sl.scored_at DESC, sl.log_id DESC
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["clickbait_breakdown"] = json.loads(item["clickbait_breakdown"])
        item["lexical_breakdown"] = json.loads(item["lexical_breakdown"])
        for field in ("url", "domain", "headline", "word_count"):
            item[field] = item["lexical_breakdown"].get(field, item[field])
        item["verdict"] = config.verdict_for_score(item["final_trust_score"])
        results.append(item)
    return results


def fetch_analysis_history(db_path: Optional[Path] = None) -> List[dict]:
    """Every saved scoring run, newest first, for the in-app history page."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT sl.log_id, sl.article_id, sl.final_trust_score, sl.verdict,
                   sl.scored_at,
                   COALESCE(json_extract(sl.lexical_breakdown, '$.url'), a.url) AS url,
                   COALESCE(json_extract(sl.lexical_breakdown, '$.domain'), a.domain) AS domain,
                   COALESCE(json_extract(sl.lexical_breakdown, '$.headline'), a.headline) AS headline,
                   COALESCE(json_extract(sl.lexical_breakdown, '$.word_count'), a.word_count) AS word_count
            FROM Scoring_Log sl
            JOIN Articles a ON a.article_id = sl.article_id
            ORDER BY sl.scored_at DESC, sl.log_id DESC
            """
        ).fetchall()
    results = [dict(row) for row in rows]
    for row in results:
        row["verdict"] = config.verdict_for_score(row["final_trust_score"])
    return results


def fetch_scored_analysis(log_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    """Fetch one immutable scoring run for its in-app historical report."""
    rows = _analysis_history_query("WHERE sl.log_id = ?", (log_id,), db_path)
    return rows[0] if rows else None
