"""
News feed scraper for Vancouver real estate and development news.

Monitors RSS feeds and news sources relevant to Vancouver real estate:
- City of Vancouver news releases
- Vancouver Sun / Province real estate sections
- Business in Vancouver
- Urban YVR / Daily Hive Vancouver (development coverage)
- BC Housing announcements
- Metro Vancouver regional planning

Architecture:
  - RSS/Atom feed parsing (aiohttp + feedparser)
  - Configurable feed list with source categorization
  - Article content extraction (parser.py for clean text)
  - Deduplication by URL
  - Rate-limited async fetching
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

import aiohttp
import asyncpg

logger = logging.getLogger(__name__)

# ── Feed Configuration ────────────────────────────────────────

NEWS_FEEDS = [
    # City of Vancouver official feeds
    {
        'name': 'City of Vancouver News',
        'url': 'https://vancouver.ca/news-calendar/news-releases.aspx',
        'rss_url': None,  # Will scrape HTML listing
        'source_type': 'community_plan',
        'priority': 'high',
    },
    # Vancouver Sun real estate
    {
        'name': 'Vancouver Sun Real Estate',
        'url': 'https://vancouversun.com/category/business/real-estate',
        'rss_url': 'https://vancouversun.com/category/business/real-estate/feed',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
    # Business in Vancouver
    {
        'name': 'Business in Vancouver',
        'url': 'https://biv.com/topic/real-estate',
        'rss_url': 'https://biv.com/topic/real-estate/feed',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
    # Daily Hive Vancouver - Development
    {
        'name': 'Daily Hive Vancouver',
        'url': 'https://dailyhive.com/vancouver/category/city',
        'rss_url': 'https://dailyhive.com/vancouver/feed',
        'source_type': 'community_plan',
        'priority': 'low',
    },
    # BC Government housing announcements
    {
        'name': 'BC Housing News',
        'url': 'https://www.bchousing.org/about/news',
        'rss_url': None,
        'source_type': 'community_plan',
        'priority': 'high',
    },
    # Metro Vancouver regional planning
    {
        'name': 'Metro Vancouver',
        'url': 'http://www.metrovancouver.org/boards/regional-planning/Pages/default.aspx',
        'rss_url': None,
        'source_type': 'community_plan',
        'priority': 'medium',
    },
    # The Tyee - investigative journalism
    {
        'name': 'The Tyee',
        'url': 'https://thetyee.ca/Topic/Housing/',
        'rss_url': 'https://thetyee.ca/rss2.xml',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
    # Storeys - Canadian real estate news
    {
        'name': 'Storeys',
        'url': 'https://storeys.com/category/vancouver/',
        'rss_url': 'https://storeys.com/feed/',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
    # Western Investor - BC commercial real estate
    {
        'name': 'Western Investor',
        'url': 'https://westerninvestor.com/',
        'rss_url': 'https://westerninvestor.com/feed/',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
]

# Keywords that indicate articles relevant to real estate intelligence
RELEVANCE_KEYWORDS = [
    'rezoning', 'zoning', 'development permit', 'building permit',
    'density', 'housing', 'affordable housing', 'rental',
    'tower', 'condo', 'strata', 'townhouse', 'duplex',
    'broadway plan', 'transit-oriented', 'community plan',
    'public hearing', 'council vote', 'council meeting',
    'real estate', 'property', 'construction',
    'infrastructure', 'skytrain', 'transit',
    'gentrification', 'displacement', 'tenant',
    'land value', 'assessment', 'property tax',
    'heritage', 'demolition',
    'vancouver', 'burnaby', 'surrey', 'richmond', 'coquitlam',
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VanCityLens/1.0)"
}
REQUEST_DELAY = 1.5  # Be polite


# ── RSS Feed Parsing ─────────────────────────────────────────

async def fetch_rss_feed(
    session: aiohttp.ClientSession,
    feed_url: str,
    max_items: int = 20,
) -> List[Dict[str, str]]:
    """
    Fetch and parse an RSS/Atom feed.

    Args:
        session: aiohttp ClientSession
        feed_url: URL of the RSS feed
        max_items: Maximum items to return

    Returns:
        List of dicts with 'title', 'url', 'published', 'summary'
    """
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed — RSS parsing unavailable")
        return []

    try:
        async with session.get(
            feed_url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"RSS feed returned HTTP {resp.status}: {feed_url}")
                return []

            content = await resp.text()

        feed = feedparser.parse(content)
        articles = []

        for entry in feed.entries[:max_items]:
            article = {
                'title': entry.get('title', ''),
                'url': entry.get('link', ''),
                'published': '',
                'summary': entry.get('summary', entry.get('description', '')),
            }

            # Parse published date
            if entry.get('published_parsed'):
                try:
                    article['published'] = datetime(
                        *entry.published_parsed[:6]
                    ).isoformat()
                except Exception:
                    pass

            if article['url']:
                articles.append(article)

        logger.info(f"Fetched {len(articles)} articles from {feed_url}")
        return articles

    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching RSS feed: {feed_url}")
        return []
    except Exception as e:
        logger.error(f"Error fetching RSS feed {feed_url}: {e}")
        return []


# ── Article Content Fetching ─────────────────────────────────

async def fetch_article_content(
    session: aiohttp.ClientSession,
    url: str,
) -> Optional[str]:
    """
    Fetch the full text content of a news article.

    Uses parser.py for clean text extraction.

    Args:
        session: aiohttp ClientSession
        url: Article URL

    Returns:
        Clean text content or None
    """
    try:
        async with session.get(
            url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Article returned HTTP {resp.status}: {url}")
                return None

            html = await resp.text()

        # Use our parser module for clean extraction
        from .parser import parse_html
        result = parse_html(html, source_url=url)

        if result and result.get('text'):
            return result['text']

        return None

    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching article: {url}")
        return None
    except Exception as e:
        logger.error(f"Error fetching article {url}: {e}")
        return None


# ── Relevance Filtering ──────────────────────────────────────

def is_relevant_article(title: str, summary: str = "") -> bool:
    """
    Check if an article is relevant to Vancouver real estate intelligence.

    Args:
        title: Article title
        summary: Article summary/description

    Returns:
        True if the article matches relevance criteria
    """
    combined = (title + ' ' + summary).lower()
    matches = sum(1 for kw in RELEVANCE_KEYWORDS if kw in combined)
    # Require at least 2 keyword matches for relevance
    return matches >= 2


# ── Main Orchestrator ─────────────────────────────────────────

async def scrape_news_feeds(
    db_pool: asyncpg.Pool,
    max_articles_per_feed: int = 15,
    fetch_full_text: bool = True,
    days_back: int = 30,
) -> Dict[str, Any]:
    """
    Main orchestrator: fetch RSS feeds, filter for relevance, extract content,
    and store in the documents table.

    Args:
        db_pool: asyncpg connection pool
        max_articles_per_feed: Max articles to process per feed
        fetch_full_text: Whether to fetch full article content
        days_back: Only process articles from the last N days

    Returns:
        Statistics dict with counts
    """
    stats = {
        'feeds_checked': 0,
        'articles_found': 0,
        'articles_relevant': 0,
        'articles_stored': 0,
        'articles_duplicate': 0,
        'errors': [],
    }

    connector = aiohttp.TCPConnector(limit=5)
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for feed_config in NEWS_FEEDS:
            stats['feeds_checked'] += 1
            rss_url = feed_config.get('rss_url')

            if not rss_url:
                logger.debug(f"Skipping feed without RSS URL: {feed_config['name']}")
                continue

            try:
                articles = await fetch_rss_feed(session, rss_url, max_articles_per_feed)
                stats['articles_found'] += len(articles)

                for article in articles:
                    # Check relevance
                    if not is_relevant_article(article['title'], article.get('summary', '')):
                        continue

                    stats['articles_relevant'] += 1

                    # Check for duplicates
                    async with db_pool.acquire() as conn:
                        exists = await conn.fetchval(
                            "SELECT id FROM documents WHERE source_url = $1",
                            article['url']
                        )

                    if exists:
                        stats['articles_duplicate'] += 1
                        continue

                    # Fetch full article text if requested
                    raw_text = article.get('summary', '')
                    if fetch_full_text:
                        full_text = await fetch_article_content(session, article['url'])
                        if full_text:
                            raw_text = full_text
                        await asyncio.sleep(REQUEST_DELAY)

                    # Parse published date
                    published_date = None
                    if article.get('published'):
                        try:
                            published_date = datetime.fromisoformat(
                                article['published']
                            ).date()
                        except Exception:
                            pass

                    # Check date filter
                    if published_date:
                        cutoff = (datetime.now() - timedelta(days=days_back)).date()
                        if published_date < cutoff:
                            continue

                    # Store in database
                    try:
                        async with db_pool.acquire() as conn:
                            await conn.execute(
                                """
                                INSERT INTO documents (
                                    source_type, source_url, title,
                                    published_date, raw_text, text_length,
                                    file_format, metadata
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                                ON CONFLICT (source_url) DO NOTHING
                                """,
                                feed_config['source_type'],
                                article['url'],
                                article['title'],
                                published_date,
                                raw_text,
                                len(raw_text),
                                'html',
                                {
                                    'feed_name': feed_config['name'],
                                    'priority': feed_config['priority'],
                                    'summary': article.get('summary', '')[:500],
                                }
                            )
                            stats['articles_stored'] += 1
                    except Exception as e:
                        logger.error(f"Error storing article {article['url']}: {e}")
                        stats['errors'].append(str(e))

            except Exception as e:
                logger.error(f"Error processing feed {feed_config['name']}: {e}")
                stats['errors'].append(f"{feed_config['name']}: {str(e)}")

    logger.info(f"News scraping complete. Stats: {stats}")
    return stats


# ── Convenience functions ─────────────────────────────────────

async def get_configured_feeds() -> List[Dict[str, str]]:
    """Return the list of configured news feeds."""
    return [
        {
            'name': f['name'],
            'url': f['url'],
            'rss_url': f.get('rss_url', ''),
            'source_type': f['source_type'],
            'priority': f['priority'],
        }
        for f in NEWS_FEEDS
    ]
