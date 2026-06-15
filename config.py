"""
Central configuration: RSS sources, API endpoints, classification labels, and tunable parameters.
All secrets are read from environment variables — never hardcoded here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# RSS feed sources
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    # English — business / macro
    {
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "source": "Reuters Business",
        "lang": "en",
    },
    {
        "url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",
        "source": "CNBC",
        "lang": "en",
    },
    {
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/",
        "source": "MarketWatch",
        "lang": "en",
    },
    # Central banks / international institutions
    {
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "source": "Federal Reserve",
        "lang": "en",
    },
    {
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "source": "ECB",
        "lang": "en",
    },
    {
        "url": "https://www.imf.org/en/News/rss",
        "source": "IMF",
        "lang": "en",
    },
    # Chinese — financial news (via RSSHub, two instances as primary/fallback)
    # Primary: rsshub.rssforever.com  Fallback: rsshub.app  (or vice-versa)
    {
        "url": "https://rsshub.rssforever.com/wallstreetcn/live",
        "fallback_url": "https://rsshub.app/wallstreetcn/live",
        "source": "华尔街见闻-快讯",
        "lang": "zh",
    },
    {
        "url": "https://rsshub.rssforever.com/wallstreetcn/news",
        "fallback_url": "https://rsshub.app/wallstreetcn/news",
        "source": "华尔街见闻-资讯",
        "lang": "zh",
    },
    {
        "url": "https://rsshub.rssforever.com/yicai/brief",
        "fallback_url": "https://rsshub.app/yicai/brief",
        "source": "第一财经-简讯",
        "lang": "zh",
    },
    {
        "url": "https://rsshub.rssforever.com/yicai/headline",
        "fallback_url": "https://rsshub.app/yicai/headline",
        "source": "第一财经-头条",
        "lang": "zh",
    },
    {
        "url": "https://rsshub.rssforever.com/caixin/latest",
        "fallback_url": "https://rsshub.app/caixin/latest",
        "source": "财新网",
        "lang": "zh",
    },
    {
        "url": "https://rsshub.rssforever.com/gelonghui/live",
        "fallback_url": "https://rsshub.app/gelonghui/live",
        "source": "格隆汇-快讯",
        "lang": "zh",
    },
    {
        "url": "https://rsshub.rssforever.com/36kr/newsflashes",
        "fallback_url": "https://rsshub.app/36kr/newsflashes",
        "source": "36氪-快讯",
        "lang": "zh",
    },
]

# ---------------------------------------------------------------------------
# News API — reserved, disabled by default; enabled when key is present
# ---------------------------------------------------------------------------

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY", "")

# Set to True to attempt News API calls (requires valid keys above)
ENABLE_NEWS_API = False

FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"
MARKETAUX_NEWS_URL = "https://api.marketaux.com/v1/news/all"

# ---------------------------------------------------------------------------
# DeepSeek LLM
# ---------------------------------------------------------------------------

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_MAX_TOKENS = 4096
DEEPSEEK_TEMPERATURE = 0.3

# Summarizer batch size (articles per LLM call)
SUMMARIZER_BATCH_SIZE = 25

# Retry settings for DeepSeek calls
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 2.0  # seconds; doubled each retry

# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

# Cosine similarity threshold: articles above this are considered the same event
SIMILARITY_THRESHOLD = 0.85

# sentence-transformers model for multilingual embedding (EN + ZH)
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# ---------------------------------------------------------------------------
# Classification labels
# ---------------------------------------------------------------------------

CATEGORIES = [
    "货币政策",
    "贸易",
    "能源",
    "股市",
    "地缘政治",
    "宏观数据",
    "其他",
]

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

DB_PATH = os.getenv("DB_PATH", "news_agent.db")

# ---------------------------------------------------------------------------
# Report output directory
# ---------------------------------------------------------------------------

REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")

# ---------------------------------------------------------------------------
# HTTP fetch settings
# ---------------------------------------------------------------------------

FETCH_TIMEOUT = 20  # seconds
FETCH_MAX_ARTICLES_PER_FEED = 50
