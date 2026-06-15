"""
Convert all reports/*.md files into a static website under _site/.

Output:
    _site/index.html                  — landing page, reports listed newest-first
    _site/daily_YYYY-MM-DD.html       — one page per daily report
"""

import glob
import os
import re
import sys
from datetime import date

try:
    import markdown as md_lib  # type: ignore
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

REPORTS_DIR = os.environ.get("REPORTS_DIR", "reports")
SITE_DIR = os.environ.get("SITE_DIR", "_site")

# ---------------------------------------------------------------------------
# Shared HTML chrome
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
                 "Helvetica Neue", Arial, sans-serif;
    background: #f5f5f5;
    color: #222;
    line-height: 1.7;
}
.container {
    max-width: 780px;
    margin: 0 auto;
    padding: 16px;
}
header {
    background: #1a1a2e;
    color: #eee;
    padding: 20px 16px;
    margin-bottom: 24px;
}
header h1 { font-size: 1.4rem; font-weight: 700; }
header p  { font-size: 0.85rem; color: #aaa; margin-top: 4px; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Index cards */
.card {
    background: #fff;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
}
.card .date { font-weight: 600; font-size: 1rem; }
.card .meta { font-size: 0.82rem; color: #666; }
.card .btn {
    background: #2563eb;
    color: #fff;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 0.85rem;
    white-space: nowrap;
}
.card .btn:hover { background: #1d4ed8; text-decoration: none; }

/* Report page */
.report h1 { font-size: 1.3rem; margin-bottom: 8px; }
.report h2 {
    font-size: 1.05rem;
    color: #1a1a2e;
    border-left: 4px solid #2563eb;
    padding-left: 10px;
    margin: 28px 0 12px;
}
.report h3 { font-size: 0.95rem; margin: 16px 0 4px; color: #111; }
.report blockquote {
    background: #f0f4ff;
    border-left: 3px solid #2563eb;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    margin: 6px 0 4px;
    font-size: 0.93rem;
}
.report p { margin: 4px 0; font-size: 0.9rem; color: #444; }
.report hr { border: none; border-top: 1px solid #e5e7eb; margin: 20px 0; }
.back { margin-bottom: 20px; font-size: 0.88rem; }

/* Mobile */
@media (max-width: 500px) {
    header h1 { font-size: 1.15rem; }
    .card { flex-direction: column; align-items: flex-start; }
}
"""


def _html_page(title: str, body: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{extra_head}
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="container">
    <h1>📰 全球财经新闻日报</h1>
    <p>每日自动聚合 · DeepSeek 中文摘要</p>
  </div>
</header>
<div class="container">
{body}
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# MD → HTML conversion
# ---------------------------------------------------------------------------

def _md_to_html(text: str) -> str:
    if HAS_MARKDOWN:
        return md_lib.markdown(text, extensions=["nl2br", "tables"])
    # Minimal fallback: escape HTML then wrap paragraphs
    import html
    escaped = html.escape(text)
    lines = escaped.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("# "):
            out.append(f"<h1>{s[2:]}</h1>")
        elif s.startswith("## "):
            out.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("### "):
            out.append(f"<h3>{s[4:]}</h3>")
        elif s.startswith("&gt; "):
            out.append(f"<blockquote>{s[5:]}</blockquote>")
        elif s.startswith("---"):
            out.append("<hr>")
        else:
            # Linkify [text](url)
            s = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2" target="_blank" rel="noopener">\1</a>',
                s,
            )
            out.append(f"<p>{s}</p>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Build per-report pages
# ---------------------------------------------------------------------------

def _date_from_filename(fname: str) -> str:
    """Extract YYYY-MM-DD from 'daily_YYYY-MM-DD.md'."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
    return m.group(1) if m else ""


def _count_articles(md_text: str) -> int:
    """Count H3 headings as a proxy for article count."""
    return len(re.findall(r"^### ", md_text, re.MULTILINE))


def build_report_page(md_path: str) -> tuple[str, str, int]:
    """
    Convert a single .md report to HTML.
    Returns (date_str, output_html_path, article_count).
    """
    fname = os.path.basename(md_path)
    date_str = _date_from_filename(fname)
    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()

    article_count = _count_articles(md_text)
    content_html = _md_to_html(md_text)

    # Make external links open in new tab
    content_html = re.sub(
        r'<a href="(https?://[^"]+)"',
        r'<a href="\1" target="_blank" rel="noopener"',
        content_html,
    )

    body = (
        f'<p class="back"><a href="index.html">← 返回首页</a></p>\n'
        f'<div class="report">\n{content_html}\n</div>'
    )
    html = _html_page(f"财经日报 · {date_str}", body)

    out_path = os.path.join(SITE_DIR, fname.replace(".md", ".html"))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return date_str, out_path, article_count


# ---------------------------------------------------------------------------
# Build index page
# ---------------------------------------------------------------------------

def build_index(reports: list[tuple[str, str, int]]) -> None:
    """
    Build index.html from a list of (date_str, html_filename, article_count),
    sorted newest-first.
    """
    reports_sorted = sorted(reports, key=lambda x: x[0], reverse=True)

    if not reports_sorted:
        cards_html = "<p>暂无日报。</p>"
    else:
        cards = []
        for date_str, html_fname, count in reports_sorted:
            href = os.path.basename(html_fname)
            label = "今日" if date_str == date.today().isoformat() else date_str
            cards.append(
                f'<div class="card">'
                f'<div><div class="date">{label}</div>'
                f'<div class="meta">{count} 条新闻</div></div>'
                f'<a class="btn" href="{href}">查看日报</a>'
                f"</div>"
            )
        cards_html = "\n".join(cards)

    body = (
        f"<h2 style='margin-bottom:16px;font-size:1.1rem;'>历史日报 · 共 {len(reports_sorted)} 期</h2>\n"
        + cards_html
    )
    html = _html_page("全球财经新闻日报", body)
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html → {len(reports_sorted)} reports listed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    os.makedirs(SITE_DIR, exist_ok=True)

    md_files = sorted(glob.glob(os.path.join(REPORTS_DIR, "daily_*.md")))
    if not md_files:
        print(f"No .md files found in {REPORTS_DIR}/  — building empty index.")
        build_index([])
        return

    reports: list[tuple[str, str, int]] = []
    for md_path in md_files:
        date_str, html_path, count = build_report_page(md_path)
        print(f"  {date_str} → {os.path.basename(html_path)}  ({count} articles)")
        reports.append((date_str, html_path, count))

    build_index(reports)
    print(f"\nSite built in {SITE_DIR}/  ({len(reports)} report pages + index)")


if __name__ == "__main__":
    main()
