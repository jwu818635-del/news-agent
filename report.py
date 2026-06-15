"""
Generate the daily Markdown report from articles stored in the database.

Output format (per article):
    ### <title>
    > <Chinese summary — our own rewording, not original text>
    来源：<Source Name> | [原文链接](<url>)

Articles are grouped by category; categories with no articles are omitted.
"""

import logging
import os
from datetime import date

import config
import storage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------


def _category_section(category: str, articles: list[dict]) -> str:
    lines = [f"\n## {category}\n"]
    for a in articles:
        title = a.get("title", "(无标题)")
        summary = a.get("summary", "")
        source = a.get("source", "")
        url = a.get("url", "")
        published_at = a.get("published_at", "")
        time_str = f" · {published_at[:10]}" if published_at else ""

        lines.append(f"### {title}\n")
        lines.append(f"> {summary}\n")
        lines.append(f"来源：{source}{time_str} | [原文链接]({url})\n")
    return "\n".join(lines)


def generate_report(report_date: date | None = None) -> str:
    """
    Build and write the daily Markdown report for *report_date* (defaults to today).

    Returns the file path of the generated report.
    """
    if report_date is None:
        report_date = date.today()
    date_str = report_date.isoformat()

    articles = storage.get_articles_for_date(date_str)
    logger.info("Report: %d articles for %s", len(articles), date_str)

    # Group by category preserving config order
    by_category: dict[str, list[dict]] = {c: [] for c in config.CATEGORIES}
    for a in articles:
        cat = a.get("category", "其他")
        if cat not in by_category:
            cat = "其他"
        by_category[cat].append(a)

    # Header
    sections = [
        f"# 全球财经新闻日报 · {date_str}\n",
        f"> 自动生成 | 共 {len(articles)} 条新闻 | 覆盖 "
        + "、".join(c for c in config.CATEGORIES if by_category[c])
        + "\n",
        "---\n",
    ]

    for category in config.CATEGORIES:
        cat_articles = by_category[category]
        if cat_articles:
            sections.append(_category_section(category, cat_articles))

    if not any(by_category.values()):
        sections.append("\n*今日暂无财经新闻入库。*\n")

    content = "\n".join(sections)

    # Write to file
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    file_path = os.path.join(config.REPORTS_DIR, f"daily_{date_str}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Report written to %s", file_path)
    return file_path
