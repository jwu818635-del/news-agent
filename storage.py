"""
SQLite persistence layer.

Tables
------
articles
    Stores every processed article with its summary and category.

processed_urls
    Tracks URL hashes across runs to prevent reprocessing the same article
    on subsequent days.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config
from dedup import url_hash

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


@contextmanager
def _connect(db_path: str = config.DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash     TEXT    NOT NULL UNIQUE,
    title        TEXT    NOT NULL,
    url          TEXT    NOT NULL,
    summary      TEXT,
    category     TEXT,
    source       TEXT,
    lang         TEXT,
    published_at TEXT,
    processed_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_urls (
    url_hash     TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_processed_at ON articles(processed_at);
CREATE INDEX IF NOT EXISTS idx_articles_category     ON articles(category);
"""


def init_db(db_path: str = config.DB_PATH) -> None:
    """Create tables if they do not exist."""
    with _connect(db_path) as conn:
        conn.executescript(_DDL)
    logger.info("Database initialised: %s", db_path)


# ---------------------------------------------------------------------------
# URL seen-check (used by dedup stage)
# ---------------------------------------------------------------------------


def is_seen(hash_str: str, db_path: str = config.DB_PATH) -> bool:
    """Return True if this URL hash has been processed before."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_urls WHERE url_hash = ?", (hash_str,)
        ).fetchone()
    return row is not None


def make_is_seen(db_path: str = config.DB_PATH):
    """Return a closure suitable for passing to dedup.filter_seen."""
    def _is_seen(hash_str: str) -> bool:
        return is_seen(hash_str, db_path)
    return _is_seen


# ---------------------------------------------------------------------------
# Write articles
# ---------------------------------------------------------------------------


def save_articles(articles: list[dict], db_path: str = config.DB_PATH) -> int:
    """
    Insert articles into the database and mark their URLs as processed.

    Articles that are already in processed_urls are skipped (race-condition safety).
    Returns the number of rows actually inserted.
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    with _connect(db_path) as conn:
        for a in articles:
            h = url_hash(a["url"])
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO articles
                        (url_hash, title, url, summary, category, source, lang, published_at, processed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        h,
                        a.get("title", ""),
                        a.get("url", ""),
                        a.get("summary", ""),
                        a.get("category", "其他"),
                        a.get("source", ""),
                        a.get("lang", ""),
                        a.get("published_at", ""),
                        now,
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO processed_urls (url_hash, processed_at) VALUES (?, ?)",
                    (h, now),
                )
                inserted += 1
            except Exception as exc:
                logger.error("Failed to insert article '%s': %s", a.get("url"), exc)

    logger.info("Saved %d / %d articles to DB.", inserted, len(articles))
    return inserted


# ---------------------------------------------------------------------------
# Read articles for report generation
# ---------------------------------------------------------------------------


def get_articles_for_date(date_str: str, db_path: str = config.DB_PATH) -> list[dict]:
    """
    Return all articles processed on a given UTC date (YYYY-MM-DD).
    Ordered by category then published_at descending.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT title, url, summary, category, source, published_at
            FROM   articles
            WHERE  processed_at LIKE ?
            ORDER  BY category, published_at DESC
            """,
            (f"{date_str}%",),
        ).fetchall()
    return [dict(r) for r in rows]
