"""
Main pipeline entry point.

Usage:
    python main.py                 # process today's news
    python main.py --date 2025-06-01   # reprocess a specific date (report only)
    python main.py --skip-fetch    # re-summarize articles already in DB (debug)
"""

import argparse
import logging
import sys
import time
from datetime import date

import config  # noqa: F401 — triggers dotenv load


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _step(label: str):
    """Context manager that logs step start/finish with elapsed time."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        logger = logging.getLogger("main")
        logger.info("▶ %s …", label)
        t0 = time.monotonic()
        yield
        logger.info("✔ %s  (%.1fs)", label, time.monotonic() - t0)

    return _ctx()


def run(report_date: date | None = None, skip_fetch: bool = False) -> str:
    """
    Execute the full pipeline and return the path to the generated report.

    Steps:
        1. Init DB
        2. Fetch articles (unless --skip-fetch)
        3. Deduplicate (URL hash + optional embedding clustering)
        4. Summarize with DeepSeek
        5. Save to DB
        6. Generate Markdown report
    """
    logger = logging.getLogger("main")

    if report_date is None:
        report_date = date.today()

    logger.info("=" * 60)
    logger.info("News Agent — %s", report_date.isoformat())
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 1. Init DB
    # ------------------------------------------------------------------
    with _step("Initialise database"):
        import storage
        storage.init_db()

    # ------------------------------------------------------------------
    # 2. Fetch
    # ------------------------------------------------------------------
    articles: list[dict] = []
    if not skip_fetch:
        with _step("Fetch articles from RSS / News APIs"):
            import fetcher
            articles = fetcher.fetch_all()
            logger.info("  Total fetched: %d", len(articles))
    else:
        logger.info("⚠ --skip-fetch active: skipping fetch stage.")

    # ------------------------------------------------------------------
    # 3. Deduplicate
    # ------------------------------------------------------------------
    if articles:
        with _step("Deduplicate"):
            import dedup
            articles = dedup.deduplicate(articles, storage.make_is_seen())
            logger.info("  After dedup: %d articles", len(articles))
    else:
        logger.info("No new articles to deduplicate.")

    # ------------------------------------------------------------------
    # 4. Summarize
    # ------------------------------------------------------------------
    if articles:
        if not config.DEEPSEEK_API_KEY:
            logger.warning(
                "DEEPSEEK_API_KEY not set — skipping summarization. "
                "Articles will be saved without summaries."
            )
            for a in articles:
                a.setdefault("summary", "未配置 DeepSeek API Key，摘要不可用。")
                a.setdefault("category", "其他")
        else:
            with _step("Summarize with DeepSeek"):
                import summarizer
                articles = summarizer.summarize(articles)
    else:
        logger.info("No articles to summarize.")

    # ------------------------------------------------------------------
    # 5. Save to DB
    # ------------------------------------------------------------------
    if articles:
        with _step("Save to database"):
            storage.save_articles(articles)

    # ------------------------------------------------------------------
    # 6. Generate report
    # ------------------------------------------------------------------
    with _step("Generate Markdown report"):
        import report
        report_path = report.generate_report(report_date)

    logger.info("=" * 60)
    logger.info("Pipeline complete → %s", report_path)
    logger.info("=" * 60)
    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Global financial news agent")
    parser.add_argument(
        "--date",
        default=None,
        help="Report date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip fetching; regenerate report from existing DB entries",
    )
    return parser.parse_args()


if __name__ == "__main__":
    _setup_logging()
    args = _parse_args()

    report_date = None
    if args.date:
        try:
            report_date = date.fromisoformat(args.date)
        except ValueError:
            logging.getLogger("main").error("Invalid date format: %s (expected YYYY-MM-DD)", args.date)
            sys.exit(1)

    report_path = run(report_date=report_date, skip_fetch=args.skip_fetch)
    print(report_path)
