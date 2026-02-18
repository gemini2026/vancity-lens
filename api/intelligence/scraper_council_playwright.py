"""Playwright-based council meeting agenda scraper for vancouver.ca."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

COUNCIL_URL = "https://vancouver.ca/your-government/council-meetings.aspx"


class AgendaItemType(str, Enum):
    """Classification of council agenda items."""
    public_hearing = "public_hearing"
    bylaw = "bylaw"
    regular = "regular"


@dataclass
class AgendaItem:
    """A single council meeting agenda item."""
    title: str
    item_type: AgendaItemType
    pdf_urls: list[str]
    meeting_date: Optional[date]
    description: str


def parse_agenda_items(html: str) -> list[AgendaItem]:
    """Parse agenda items from HTML content.

    Args:
        html: Raw HTML content to parse

    Returns:
        List of AgendaItem objects
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Find all divs that might contain agenda items
    # Looking for divs with "agenda" in class name
    agenda_divs = soup.find_all("div", class_=lambda x: x and "agenda" in x.lower())

    for div in agenda_divs:
        # Extract title from h3 or other heading
        heading = div.find(["h3", "h4", "h2"])
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title:
            continue

        # Classify item type based on title content
        title_lower = title.lower()
        if "public hearing" in title_lower or "rezone" in title_lower or "rezoning" in title_lower:
            item_type = AgendaItemType.public_hearing
        elif "bylaw" in title_lower:
            item_type = AgendaItemType.bylaw
        else:
            item_type = AgendaItemType.regular

        # Extract PDF links
        pdf_urls = []
        for link in div.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf") or "pdf" in href.lower():
                # Make absolute URL if needed
                if href.startswith("/"):
                    href = f"https://vancouver.ca{href}"
                pdf_urls.append(href)

        # Extract description from div text (excluding heading)
        description = ""
        if div.get_text():
            full_text = div.get_text(strip=True)
            # Remove the heading text from description
            description = full_text.replace(title, "").strip()

        items.append(AgendaItem(
            title=title,
            item_type=item_type,
            pdf_urls=pdf_urls,
            meeting_date=None,  # Would need date parsing logic
            description=description
        ))

    return items


async def scrape_council_agendas(max_pages: int = 3) -> list[AgendaItem]:
    """Scrape council meeting agendas using Playwright.

    Args:
        max_pages: Maximum number of pages to scrape (default 3)

    Returns:
        List of AgendaItem objects

    Raises:
        ImportError: If playwright is not installed
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed, cannot scrape council agendas")
        raise ImportError(
            "playwright is not installed. Install with: pip install playwright && playwright install"
        )

    all_items = []
    retries = 3

    for attempt in range(retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                try:
                    # Navigate to council meetings page
                    await page.goto(COUNCIL_URL, wait_until="domcontentloaded", timeout=30000)

                    # Get the HTML content
                    html = await page.content()

                    # Parse the items
                    items = parse_agenda_items(html)
                    all_items.extend(items)

                    logger.info(f"Scraped {len(items)} agenda items from {COUNCIL_URL}")

                finally:
                    await browser.close()

                # Success - break retry loop
                break

        except (TimeoutError, ConnectionError) as e:
            logger.error(f"Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            # Catch Playwright-specific errors (e.g. playwright._impl._errors.TimeoutError)
            # which do NOT inherit from builtins.TimeoutError
            if "Timeout" in type(e).__name__ or "playwright" in type(e).__module__:
                logger.error(f"Attempt {attempt + 1}/{retries} failed (playwright): {e}")
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
            else:
                raise

    return all_items
