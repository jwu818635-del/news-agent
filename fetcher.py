"""
Fetch articles from RSS feeds and (optionally) News APIs.

Every article is normalized to a common dict:
    {
        "title":        str,
        "url":          str,
        "content":      str,   # best available body / summary text
        "source":       str,
        "lang":         str,   # "en" | "zh"
        "published_at": str,   # ISO-8601, may be empty string
    }
"""

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(entry: feedparser.FeedParserDict) -> str:
    """Return ISO-8601 string from a feedparser entry, or empty string."""
    if hasattr(entry, "published"):
        try:
            dt = parsedate_to_datetime(entry.published)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    if hasattr(entry, "updated"):
        try:
            dt = parsedate_to_datetime(entry.updated)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    return ""


def _best_content(entry: feedparser.FeedParserDict) -> str:
    """Extract the richest available text from a feedparser entry."""
    # content[] list takes priority over summary
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    if hasattr(entry, "summary"):
        return entry.summary
    return ""


def _normalize_rss(entry: feedparser.FeedParserDict, feed_meta: dict) -> dict | None:
    """Convert a feedparser entry to the canonical article dict."""
    url = entry.get("link", "").strip()
    title = entry.get("title", "").strip()
    if not url or not title:
        return None
    return {
        "title": title,
        "url": url,
        "content": _best_content(entry),
        "source": feed_meta["source"],
        "lang": feed_meta.get("lang", "en"),
        "published_at": _parse_date(entry),
    }


# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------


def _fetch_one_feed(url: str, feed_meta: dict) -> tuple[list[dict], str]:
    """
    Attempt to fetch and parse a single RSS URL.
    Returns (articles, status_note) where status_note is a short log suffix.
    Raises on hard failure so the caller can try a fallback URL.
    """
    parsed = feedparser.parse(url, request_headers={"User-Agent": "news-agent/1.0"})
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"bozo feed: {parsed.bozo_exception}")
    articles = []
    for entry in parsed.entries[: config.FETCH_MAX_ARTICLES_PER_FEED]:
        article = _normalize_rss(entry, feed_meta)
        if article:
            articles.append(article)
    return articles, url


def fetch_rss() -> list[dict]:
    """
    Fetch all configured RSS feeds and return a flat list of articles.

    For each feed, the primary URL is tried first.  If it fails (timeout,
    bozo parse with 0 entries, or any exception), the optional ``fallback_url``
    from config is tried automatically.  Both rsshub.app and
    rsshub.rssforever.com are used as primary/fallback across different feeds
    to spread load and avoid single-instance rate limits.
    """
    articles: list[dict] = []
    for feed_meta in config.RSS_FEEDS:
        primary_url = feed_meta["url"]
        fallback_url = feed_meta.get("fallback_url")
        source = feed_meta["source"]
        fetched: list[dict] = []
        used_url = primary_url

        try:
            logger.info("Fetching RSS: %s  [%s]", source, primary_url)
            fetched, used_url = _fetch_one_feed(primary_url, feed_meta)
        except Exception as exc:
            if fallback_url:
                logger.warning(
                    "  Primary failed (%s) — retrying fallback: %s", exc, fallback_url
                )
                try:
                    fetched, used_url = _fetch_one_feed(fallback_url, feed_meta)
                except Exception as exc2:
                    logger.error("  Fallback also failed (%s): %s", fallback_url, exc2)
            else:
                logger.error("  Failed, no fallback configured: %s", exc)

        count = len(fetched)
        suffix = " [fallback]" if used_url != primary_url else ""
        logger.info("  → %d articles from %s%s", count, source, suffix)
        articles.extend(fetched)

    return articles


# ---------------------------------------------------------------------------
# News API fetching (Finnhub / MarketAux) — reserved, off by default
# ---------------------------------------------------------------------------


def fetch_finnhub() -> list[dict]:
    """
    Fetch general market news from Finnhub (free tier).
    Skipped when FINNHUB_API_KEY is not set.
    """
    if not config.FINNHUB_API_KEY:
        logger.debug("FINNHUB_API_KEY not set — skipping Finnhub")
        return []
    articles: list[dict] = []
    try:
        with httpx.Client(timeout=config.FETCH_TIMEOUT) as client:
            resp = client.get(
                config.FINNHUB_NEWS_URL,
                params={"category": "general", "token": config.FINNHUB_API_KEY},
            )
            resp.raise_for_status()
            for item in resp.json():
                url = item.get("url", "").strip()
                title = item.get("headline", "").strip()
                if not url or not title:
                    continue
                ts = item.get("datetime", 0)
                published_at = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
                )
                articles.append(
                    {
                        "title": title,
                        "url": url,
                        "content": item.get("summary", ""),
                        "source": "Finnhub/" + item.get("source", ""),
                        "lang": "en",
                        "published_at": published_at,
                    }
                )
        logger.info("Finnhub: %d articles", len(articles))
    except Exception as exc:
        logger.error("Finnhub fetch failed: %s", exc)
    return articles


def fetch_marketaux() -> list[dict]:
    """
    Fetch news from MarketAux (free tier).
    Skipped when MARKETAUX_API_KEY is not set.
    """
    if not config.MARKETAUX_API_KEY:
        logger.debug("MARKETAUX_API_KEY not set — skipping MarketAux")
        return []
    articles: list[dict] = []
    try:
        with httpx.Client(timeout=config.FETCH_TIMEOUT) as client:
            resp = client.get(
                config.MARKETAUX_NEWS_URL,
                params={
                    "api_token": config.MARKETAUX_API_KEY,
                    "language": "en",
                    "limit": 50,
                },
            )
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                url = item.get("url", "").strip()
                title = item.get("title", "").strip()
                if not url or not title:
                    continue
                articles.append(
                    {
                        "title": title,
                        "url": url,
                        "content": item.get("description", ""),
                        "source": "MarketAux/" + item.get("source", ""),
                        "lang": "en",
                        "published_at": item.get("published_at", ""),
                    }
                )
        logger.info("MarketAux: %d articles", len(articles))
    except Exception as exc:
        logger.error("MarketAux fetch failed: %s", exc)
    return articles


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def fetch_all() -> list[dict]:
    """
    Fetch from all enabled sources and return a combined, deduplicated-by-URL list.
    News APIs are only called when ENABLE_NEWS_API is True in config.
    """
    articles = fetch_rss()

    if config.ENABLE_NEWS_API:
        articles += fetch_finnhub()
        articles += fetch_marketaux()

    # Quick URL-level dedup before deeper processing
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique.append(a)

    logger.info("fetch_all: %d unique articles (raw total: %d)", len(unique), len(articles))
    return unique
