"""
VCL-76 [DATA-003] Scraper Deduplication Logic

In-memory deduplication engine for scraped documents. Supports multiple
detection strategies:

- URL_EXACT: Exact normalized URL match
- CONTENT_HASH: SHA-256 of normalized content
- URL_AND_DATE: URL + publication date combination
- TITLE_SIMILARITY: Fuzzy title matching via SequenceMatcher (>0.9 threshold)

Key components:
- DedupStrategy: Enum of available dedup strategies
- DedupResult: Result of a single dedup check
- DedupStats: Aggregate statistics for a batch run
- DedupEngine: Core deduplication engine with register/check/batch workflow
"""

import hashlib
import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Tracking query parameters to strip during URL normalization
_TRACKING_PARAMS = frozenset([
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
])


class DedupStrategy(str, Enum):
    """Available deduplication strategies."""

    URL_EXACT = "url_exact"              # Exact URL match (after normalization)
    CONTENT_HASH = "content_hash"        # SHA-256 of normalized content
    URL_AND_DATE = "url_and_date"        # URL + publication date combo
    TITLE_SIMILARITY = "title_similarity"  # Fuzzy title matching (>0.9 similarity)


@dataclass
class DedupResult:
    """Result of a deduplication check for a single document."""

    is_duplicate: bool
    strategy_matched: Optional[str] = None
    existing_id: Optional[str] = None
    content_hash: str = ""


@dataclass
class DedupStats:
    """Aggregate statistics for a deduplication batch run."""

    total_processed: int = 0
    new_items: int = 0
    duplicates_skipped: int = 0
    duplicates_updated: int = 0
    errors: int = 0

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return (
            f"{self.new_items} new, "
            f"{self.duplicates_skipped} duplicates skipped, "
            f"{self.duplicates_updated} updated, "
            f"{self.errors} errors"
        )


class DedupEngine:
    """In-memory deduplication engine for scraped documents.

    Maintains dictionaries of seen URLs, content hashes, URL+date combos,
    and titles to detect duplicates across multiple check strategies.

    Usage::

        engine = DedupEngine()

        # Single-item workflow
        result = engine.check_duplicate(url="https://example.com/doc", content="...")
        if not result.is_duplicate:
            engine.register(doc_id="doc-1", url="https://example.com/doc", content="...")

        # Batch workflow
        new_items, stats = engine.process_batch(items)
    """

    def __init__(self, title_similarity_threshold: float = 0.9):
        self._seen_urls: dict[str, str] = {}           # normalized_url -> doc_id
        self._seen_hashes: dict[str, str] = {}          # content_hash -> doc_id
        self._seen_url_dates: dict[str, str] = {}       # "url|date" -> doc_id
        self._seen_titles: list[tuple[str, str]] = []   # [(title, doc_id), ...]
        self._title_threshold = title_similarity_threshold
        self._stats = DedupStats()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """SHA-256 hash of normalized (stripped + lowercased) content."""
        normalized = content.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize a URL for comparison.

        - Strip whitespace and trailing slash
        - Remove common tracking / analytics query parameters
        - Sort remaining query parameters for deterministic comparison
        - Lowercase the scheme and netloc
        """
        url = url.strip().rstrip("/")
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Remove tracking params
        for param in _TRACKING_PARAMS:
            params.pop(param, None)

        clean_query = urlencode(sorted(params.items()), doseq=True)
        normalized = urlunparse(
            parsed._replace(
                scheme=parsed.scheme.lower(),
                netloc=parsed.netloc.lower(),
                query=clean_query,
            )
        )
        return normalized

    @staticmethod
    def title_similarity(title_a: str, title_b: str) -> float:
        """Compute similarity ratio between two titles using SequenceMatcher.

        Returns a float in [0.0, 1.0].
        """
        if not title_a or not title_b:
            return 0.0
        return SequenceMatcher(
            None,
            title_a.strip().lower(),
            title_b.strip().lower(),
        ).ratio()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def check_duplicate(
        self,
        url: str,
        content: str = "",
        title: str = "",
        pub_date: Optional[str] = None,
        strategies: Optional[list[DedupStrategy]] = None,
    ) -> DedupResult:
        """Check whether a document is a duplicate using the given strategies.

        Strategies are evaluated in order; the first match wins.

        Args:
            url: Source URL of the document.
            content: Full text content (used for CONTENT_HASH strategy).
            title: Document title (used for TITLE_SIMILARITY strategy).
            pub_date: Publication date string (used for URL_AND_DATE strategy).
            strategies: Ordered list of strategies to apply.  Defaults to
                ``[URL_EXACT, CONTENT_HASH]``.

        Returns:
            A ``DedupResult`` indicating whether the document is a duplicate.
        """
        if strategies is None:
            strategies = [DedupStrategy.URL_EXACT, DedupStrategy.CONTENT_HASH]

        content_hash = self.compute_content_hash(content) if content else ""

        for strategy in strategies:
            if strategy == DedupStrategy.URL_EXACT:
                normalized = self.normalize_url(url)
                if normalized in self._seen_urls:
                    return DedupResult(
                        is_duplicate=True,
                        strategy_matched="url_exact",
                        existing_id=self._seen_urls[normalized],
                        content_hash=content_hash,
                    )

            elif strategy == DedupStrategy.CONTENT_HASH and content_hash:
                if content_hash in self._seen_hashes:
                    return DedupResult(
                        is_duplicate=True,
                        strategy_matched="content_hash",
                        existing_id=self._seen_hashes[content_hash],
                        content_hash=content_hash,
                    )

            elif strategy == DedupStrategy.URL_AND_DATE and pub_date:
                key = f"{self.normalize_url(url)}|{pub_date}"
                if key in self._seen_url_dates:
                    return DedupResult(
                        is_duplicate=True,
                        strategy_matched="url_and_date",
                        existing_id=self._seen_url_dates[key],
                        content_hash=content_hash,
                    )

            elif strategy == DedupStrategy.TITLE_SIMILARITY and title:
                for seen_title, doc_id in self._seen_titles:
                    if self.title_similarity(title, seen_title) >= self._title_threshold:
                        return DedupResult(
                            is_duplicate=True,
                            strategy_matched="title_similarity",
                            existing_id=doc_id,
                            content_hash=content_hash,
                        )

        return DedupResult(is_duplicate=False, content_hash=content_hash)

    def register(
        self,
        doc_id: str,
        url: str,
        content: str = "",
        title: str = "",
        pub_date: Optional[str] = None,
    ) -> None:
        """Register a document as seen so future checks can detect it.

        Args:
            doc_id: Unique identifier for this document.
            url: Source URL.
            content: Full text content.
            title: Document title.
            pub_date: Publication date string.
        """
        self._seen_urls[self.normalize_url(url)] = doc_id

        if content:
            content_hash = self.compute_content_hash(content)
            self._seen_hashes[content_hash] = doc_id

        if title:
            self._seen_titles.append((title, doc_id))

        if pub_date:
            key = f"{self.normalize_url(url)}|{pub_date}"
            self._seen_url_dates[key] = doc_id

    def process_batch(
        self,
        items: list[dict],
        strategies: Optional[list[DedupStrategy]] = None,
    ) -> tuple[list[dict], DedupStats]:
        """Process a batch of scraped items, returning only new (non-duplicate) ones.

        Each item dict should contain at least ``url``; optionally ``content``,
        ``title``, ``pub_date``, and ``id``.

        Args:
            items: List of scraped item dicts.
            strategies: Dedup strategies to apply (defaults to URL_EXACT + CONTENT_HASH).

        Returns:
            Tuple of (new_items_list, stats).
        """
        stats = DedupStats(total_processed=len(items))
        new_items: list[dict] = []

        for item in items:
            try:
                result = self.check_duplicate(
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    title=item.get("title", ""),
                    pub_date=item.get("pub_date"),
                    strategies=strategies,
                )

                if result.is_duplicate:
                    stats.duplicates_skipped += 1
                else:
                    new_items.append(item)
                    stats.new_items += 1
                    self.register(
                        doc_id=item.get("id", item.get("url", "")),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                        title=item.get("title", ""),
                        pub_date=item.get("pub_date"),
                    )
            except Exception as exc:
                logger.error("Error processing item %s: %s", item.get("url", "?"), exc)
                stats.errors += 1

        self._stats = stats
        return new_items, stats

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def stats(self) -> DedupStats:
        """Return the most recent batch stats."""
        return self._stats

    @property
    def seen_url_count(self) -> int:
        """Number of distinct URLs registered."""
        return len(self._seen_urls)

    @property
    def seen_hash_count(self) -> int:
        """Number of distinct content hashes registered."""
        return len(self._seen_hashes)

    def clear(self) -> None:
        """Reset all internal state."""
        self._seen_urls.clear()
        self._seen_hashes.clear()
        self._seen_url_dates.clear()
        self._seen_titles.clear()
        self._stats = DedupStats()
