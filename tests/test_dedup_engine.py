"""
Tests for DATA-003: Scraper Deduplication Engine

Comprehensive tests covering:
- URL normalization (trailing slashes, query params, tracking params, scheme/netloc casing)
- Content hash computation (SHA-256, normalization, empty content)
- Duplicate detection by URL (exact match after normalization)
- Duplicate detection by content hash
- Duplicate detection by URL + date combo
- Duplicate detection by title similarity
- Non-duplicate detection
- Multiple strategies (ordering, first-match semantics)
- Register and re-check workflow
- Batch processing (mix of new and duplicates)
- Stats tracking (new, skipped, updated, error counts)
- Summary string formatting
- Edge cases (empty content, empty URL, very long URLs, unicode, whitespace)
- Title similarity threshold tuning
- Engine clear / reset
"""

import hashlib
import pytest

from api.intelligence.dedup import (
    DedupEngine,
    DedupResult,
    DedupStats,
    DedupStrategy,
)


# ============================================================
# URL Normalization Tests
# ============================================================

class TestURLNormalization:
    """Tests for DedupEngine.normalize_url."""

    def test_strips_trailing_slash(self):
        url = "https://example.com/page/"
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_strips_multiple_trailing_slashes(self):
        url = "https://example.com/page///"
        # rstrip("/") removes all trailing slashes
        normalized = DedupEngine.normalize_url(url)
        assert not normalized.endswith("/")

    def test_strips_whitespace(self):
        url = "  https://example.com/page  "
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_removes_utm_source(self):
        url = "https://example.com/page?utm_source=twitter"
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_removes_utm_medium(self):
        url = "https://example.com/page?utm_medium=social"
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_removes_utm_campaign(self):
        url = "https://example.com/page?utm_campaign=launch"
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_removes_fbclid(self):
        url = "https://example.com/page?fbclid=abc123"
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_removes_ref(self):
        url = "https://example.com/page?ref=homepage"
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_removes_gclid(self):
        url = "https://example.com/page?gclid=xyz789"
        assert DedupEngine.normalize_url(url) == "https://example.com/page"

    def test_preserves_non_tracking_params(self):
        url = "https://example.com/search?q=rezoning&page=2"
        normalized = DedupEngine.normalize_url(url)
        assert "q=rezoning" in normalized
        assert "page=2" in normalized

    def test_removes_tracking_preserves_legitimate(self):
        url = "https://example.com/page?q=test&utm_source=twitter&page=1"
        normalized = DedupEngine.normalize_url(url)
        assert "q=test" in normalized
        assert "page=1" in normalized
        assert "utm_source" not in normalized

    def test_sorts_query_params(self):
        url_a = "https://example.com/search?b=2&a=1"
        url_b = "https://example.com/search?a=1&b=2"
        assert DedupEngine.normalize_url(url_a) == DedupEngine.normalize_url(url_b)

    def test_lowercases_scheme(self):
        url = "HTTPS://Example.com/Page"
        normalized = DedupEngine.normalize_url(url)
        assert normalized.startswith("https://")

    def test_lowercases_netloc(self):
        url = "https://EXAMPLE.COM/Page"
        normalized = DedupEngine.normalize_url(url)
        assert "example.com" in normalized

    def test_preserves_path_case(self):
        # Path components are case-sensitive per RFC 3986
        url = "https://example.com/CaseSensitive"
        normalized = DedupEngine.normalize_url(url)
        assert "/CaseSensitive" in normalized

    def test_empty_url(self):
        result = DedupEngine.normalize_url("")
        assert isinstance(result, str)

    def test_url_without_query(self):
        url = "https://example.com/simple/path"
        assert DedupEngine.normalize_url(url) == "https://example.com/simple/path"

    def test_very_long_url(self):
        url = "https://example.com/" + "a" * 5000
        normalized = DedupEngine.normalize_url(url)
        assert isinstance(normalized, str)
        assert len(normalized) > 100


# ============================================================
# Content Hash Computation Tests
# ============================================================

class TestContentHash:
    """Tests for DedupEngine.compute_content_hash."""

    def test_returns_sha256_hex(self):
        h = DedupEngine.compute_content_hash("Hello World")
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_consistency(self):
        h1 = DedupEngine.compute_content_hash("test content")
        h2 = DedupEngine.compute_content_hash("test content")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = DedupEngine.compute_content_hash("content A")
        h2 = DedupEngine.compute_content_hash("content B")
        assert h1 != h2

    def test_case_insensitive(self):
        h1 = DedupEngine.compute_content_hash("HELLO WORLD")
        h2 = DedupEngine.compute_content_hash("hello world")
        assert h1 == h2

    def test_strips_whitespace(self):
        h1 = DedupEngine.compute_content_hash("  hello  ")
        h2 = DedupEngine.compute_content_hash("hello")
        assert h1 == h2

    def test_empty_string(self):
        h = DedupEngine.compute_content_hash("")
        expected = hashlib.sha256(b"").hexdigest()
        assert h == expected

    def test_whitespace_only(self):
        h = DedupEngine.compute_content_hash("   \n\t   ")
        expected = hashlib.sha256(b"").hexdigest()
        assert h == expected

    def test_unicode_content(self):
        h = DedupEngine.compute_content_hash("cafe\u0301 re\u0301sume\u0301")
        assert isinstance(h, str)
        assert len(h) == 64

    def test_very_long_content(self):
        content = "word " * 100_000
        h = DedupEngine.compute_content_hash(content)
        assert len(h) == 64

    def test_matches_manual_sha256(self):
        content = "test content"
        normalized = content.strip().lower()
        expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        assert DedupEngine.compute_content_hash(content) == expected


# ============================================================
# Title Similarity Tests
# ============================================================

class TestTitleSimilarity:
    """Tests for DedupEngine.title_similarity."""

    def test_identical_titles(self):
        assert DedupEngine.title_similarity("Hello World", "Hello World") == 1.0

    def test_identical_case_insensitive(self):
        sim = DedupEngine.title_similarity("HELLO WORLD", "hello world")
        assert sim == 1.0

    def test_very_similar_titles(self):
        sim = DedupEngine.title_similarity(
            "Council Meeting Jan 2024",
            "Council Meeting Jan 2024 Minutes",
        )
        assert sim > 0.7

    def test_completely_different(self):
        sim = DedupEngine.title_similarity(
            "Rezoning Decision 1234 Main St",
            "Annual Budget Report 2025",
        )
        assert sim < 0.5

    def test_empty_title_a(self):
        assert DedupEngine.title_similarity("", "Hello") == 0.0

    def test_empty_title_b(self):
        assert DedupEngine.title_similarity("Hello", "") == 0.0

    def test_both_empty(self):
        assert DedupEngine.title_similarity("", "") == 0.0

    def test_strips_whitespace(self):
        sim = DedupEngine.title_similarity("  Hello  ", "Hello")
        assert sim == 1.0


# ============================================================
# Duplicate Detection by URL Tests
# ============================================================

class TestDuplicateDetectionByURL:
    """Tests for detecting duplicates via URL_EXACT strategy."""

    def test_detects_url_duplicate(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://example.com/page")
        result = engine.check_duplicate(
            url="https://example.com/page",
            strategies=[DedupStrategy.URL_EXACT],
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "url_exact"
        assert result.existing_id == "doc-1"

    def test_detects_url_duplicate_trailing_slash(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://example.com/page/")
        result = engine.check_duplicate(
            url="https://example.com/page",
            strategies=[DedupStrategy.URL_EXACT],
        )
        assert result.is_duplicate is True

    def test_detects_url_duplicate_with_tracking_stripped(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://example.com/page")
        result = engine.check_duplicate(
            url="https://example.com/page?utm_source=email",
            strategies=[DedupStrategy.URL_EXACT],
        )
        assert result.is_duplicate is True

    def test_no_duplicate_different_url(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://example.com/page-a")
        result = engine.check_duplicate(
            url="https://example.com/page-b",
            strategies=[DedupStrategy.URL_EXACT],
        )
        assert result.is_duplicate is False

    def test_no_duplicate_empty_engine(self):
        engine = DedupEngine()
        result = engine.check_duplicate(
            url="https://example.com/page",
            strategies=[DedupStrategy.URL_EXACT],
        )
        assert result.is_duplicate is False


# ============================================================
# Duplicate Detection by Content Hash Tests
# ============================================================

class TestDuplicateDetectionByContentHash:
    """Tests for detecting duplicates via CONTENT_HASH strategy."""

    def test_detects_content_hash_duplicate(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://a.com", content="Same content here")
        result = engine.check_duplicate(
            url="https://b.com",
            content="Same content here",
            strategies=[DedupStrategy.CONTENT_HASH],
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "content_hash"
        assert result.existing_id == "doc-1"

    def test_detects_content_hash_case_insensitive(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://a.com", content="SAME CONTENT")
        result = engine.check_duplicate(
            url="https://b.com",
            content="same content",
            strategies=[DedupStrategy.CONTENT_HASH],
        )
        assert result.is_duplicate is True

    def test_no_duplicate_different_content(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://a.com", content="Content A")
        result = engine.check_duplicate(
            url="https://b.com",
            content="Content B",
            strategies=[DedupStrategy.CONTENT_HASH],
        )
        assert result.is_duplicate is False

    def test_no_duplicate_empty_content(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://a.com", content="Real content")
        result = engine.check_duplicate(
            url="https://b.com",
            content="",
            strategies=[DedupStrategy.CONTENT_HASH],
        )
        assert result.is_duplicate is False

    def test_content_hash_returned_in_result(self):
        engine = DedupEngine()
        result = engine.check_duplicate(
            url="https://a.com",
            content="test content",
            strategies=[DedupStrategy.CONTENT_HASH],
        )
        assert result.content_hash != ""
        assert len(result.content_hash) == 64


# ============================================================
# Duplicate Detection by URL + Date Tests
# ============================================================

class TestDuplicateDetectionByURLAndDate:
    """Tests for detecting duplicates via URL_AND_DATE strategy."""

    def test_detects_url_and_date_duplicate(self):
        engine = DedupEngine()
        engine.register(
            doc_id="doc-1", url="https://example.com/page", pub_date="2024-01-15"
        )
        result = engine.check_duplicate(
            url="https://example.com/page",
            pub_date="2024-01-15",
            strategies=[DedupStrategy.URL_AND_DATE],
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "url_and_date"

    def test_no_duplicate_same_url_different_date(self):
        engine = DedupEngine()
        engine.register(
            doc_id="doc-1", url="https://example.com/page", pub_date="2024-01-15"
        )
        result = engine.check_duplicate(
            url="https://example.com/page",
            pub_date="2024-02-20",
            strategies=[DedupStrategy.URL_AND_DATE],
        )
        assert result.is_duplicate is False

    def test_no_duplicate_different_url_same_date(self):
        engine = DedupEngine()
        engine.register(
            doc_id="doc-1", url="https://example.com/page-a", pub_date="2024-01-15"
        )
        result = engine.check_duplicate(
            url="https://example.com/page-b",
            pub_date="2024-01-15",
            strategies=[DedupStrategy.URL_AND_DATE],
        )
        assert result.is_duplicate is False

    def test_skipped_when_no_pub_date(self):
        engine = DedupEngine()
        engine.register(
            doc_id="doc-1", url="https://example.com/page", pub_date="2024-01-15"
        )
        # No pub_date provided in check => strategy should be skipped
        result = engine.check_duplicate(
            url="https://example.com/page",
            strategies=[DedupStrategy.URL_AND_DATE],
        )
        assert result.is_duplicate is False


# ============================================================
# Duplicate Detection by Title Similarity Tests
# ============================================================

class TestDuplicateDetectionByTitleSimilarity:
    """Tests for detecting duplicates via TITLE_SIMILARITY strategy."""

    def test_detects_identical_title(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://a.com", title="Council Meeting Minutes")
        result = engine.check_duplicate(
            url="https://b.com",
            title="Council Meeting Minutes",
            strategies=[DedupStrategy.TITLE_SIMILARITY],
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "title_similarity"
        assert result.existing_id == "doc-1"

    def test_detects_near_identical_title(self):
        engine = DedupEngine()
        engine.register(
            doc_id="doc-1", url="https://a.com",
            title="Council Meeting Minutes January 2024",
        )
        result = engine.check_duplicate(
            url="https://b.com",
            title="Council Meeting Minutes January 2024 - Draft",
            strategies=[DedupStrategy.TITLE_SIMILARITY],
        )
        # With default 0.9 threshold, this should match (~0.91 similarity)
        assert result.is_duplicate is True

    def test_no_duplicate_very_different_title(self):
        engine = DedupEngine()
        engine.register(
            doc_id="doc-1", url="https://a.com", title="Budget Report 2024"
        )
        result = engine.check_duplicate(
            url="https://b.com",
            title="Rezoning Application 5678 Oak Street",
            strategies=[DedupStrategy.TITLE_SIMILARITY],
        )
        assert result.is_duplicate is False

    def test_skipped_when_no_title(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://a.com", title="Some Title")
        result = engine.check_duplicate(
            url="https://b.com",
            title="",
            strategies=[DedupStrategy.TITLE_SIMILARITY],
        )
        assert result.is_duplicate is False

    def test_custom_threshold(self):
        engine = DedupEngine(title_similarity_threshold=0.5)
        engine.register(doc_id="doc-1", url="https://a.com", title="Council Meeting")
        result = engine.check_duplicate(
            url="https://b.com",
            title="Council Budget Meeting Review",
            strategies=[DedupStrategy.TITLE_SIMILARITY],
        )
        # Lower threshold makes it easier to match
        assert result.is_duplicate is True


# ============================================================
# Multiple Strategies Tests
# ============================================================

class TestMultipleStrategies:
    """Tests for using multiple strategies together."""

    def test_url_checked_before_content_hash(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://example.com/page", content="content")
        result = engine.check_duplicate(
            url="https://example.com/page",
            content="content",
            strategies=[DedupStrategy.URL_EXACT, DedupStrategy.CONTENT_HASH],
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "url_exact"

    def test_falls_through_to_content_hash(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://a.com", content="Shared content")
        result = engine.check_duplicate(
            url="https://b.com",
            content="Shared content",
            strategies=[DedupStrategy.URL_EXACT, DedupStrategy.CONTENT_HASH],
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "content_hash"

    def test_all_four_strategies_no_match(self):
        engine = DedupEngine()
        engine.register(
            doc_id="doc-1",
            url="https://a.com",
            content="Content A",
            title="Title A",
            pub_date="2024-01-01",
        )
        result = engine.check_duplicate(
            url="https://b.com",
            content="Content B",
            title="Title B",
            pub_date="2024-06-15",
            strategies=[
                DedupStrategy.URL_EXACT,
                DedupStrategy.CONTENT_HASH,
                DedupStrategy.URL_AND_DATE,
                DedupStrategy.TITLE_SIMILARITY,
            ],
        )
        assert result.is_duplicate is False

    def test_default_strategies(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-1", url="https://example.com/page", content="content")
        # No explicit strategies => defaults to URL_EXACT + CONTENT_HASH
        result = engine.check_duplicate(
            url="https://example.com/page",
            content="different content",
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "url_exact"


# ============================================================
# Register and Re-check Tests
# ============================================================

class TestRegisterAndRecheck:
    """Tests for the register -> check_duplicate workflow."""

    def test_register_url_then_check(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-42", url="https://example.com/article")
        result = engine.check_duplicate(
            url="https://example.com/article",
            strategies=[DedupStrategy.URL_EXACT],
        )
        assert result.is_duplicate is True
        assert result.existing_id == "doc-42"

    def test_register_content_then_check(self):
        engine = DedupEngine()
        engine.register(doc_id="doc-99", url="https://a.com", content="unique text")
        result = engine.check_duplicate(
            url="https://b.com",
            content="unique text",
            strategies=[DedupStrategy.CONTENT_HASH],
        )
        assert result.is_duplicate is True
        assert result.existing_id == "doc-99"

    def test_register_multiple_then_check_each(self):
        engine = DedupEngine()
        for i in range(5):
            engine.register(
                doc_id=f"doc-{i}",
                url=f"https://example.com/page-{i}",
                content=f"Content number {i}",
            )
        for i in range(5):
            result = engine.check_duplicate(
                url=f"https://example.com/page-{i}",
                strategies=[DedupStrategy.URL_EXACT],
            )
            assert result.is_duplicate is True
            assert result.existing_id == f"doc-{i}"

    def test_seen_url_count(self):
        engine = DedupEngine()
        engine.register(doc_id="1", url="https://a.com")
        engine.register(doc_id="2", url="https://b.com")
        engine.register(doc_id="3", url="https://c.com")
        assert engine.seen_url_count == 3

    def test_seen_hash_count(self):
        engine = DedupEngine()
        engine.register(doc_id="1", url="https://a.com", content="Content A")
        engine.register(doc_id="2", url="https://b.com", content="Content B")
        assert engine.seen_hash_count == 2

    def test_seen_hash_count_no_content(self):
        engine = DedupEngine()
        engine.register(doc_id="1", url="https://a.com")
        assert engine.seen_hash_count == 0


# ============================================================
# Batch Processing Tests
# ============================================================

class TestBatchProcessing:
    """Tests for process_batch."""

    def test_all_new_items(self):
        engine = DedupEngine()
        items = [
            {"url": "https://example.com/a", "content": "Content A"},
            {"url": "https://example.com/b", "content": "Content B"},
            {"url": "https://example.com/c", "content": "Content C"},
        ]
        new_items, stats = engine.process_batch(items)
        assert len(new_items) == 3
        assert stats.total_processed == 3
        assert stats.new_items == 3
        assert stats.duplicates_skipped == 0

    def test_all_duplicates_by_url(self):
        engine = DedupEngine()
        # Pre-register
        engine.register(doc_id="pre-1", url="https://example.com/a")
        engine.register(doc_id="pre-2", url="https://example.com/b")

        items = [
            {"url": "https://example.com/a", "content": "X"},
            {"url": "https://example.com/b", "content": "Y"},
        ]
        new_items, stats = engine.process_batch(items)
        assert len(new_items) == 0
        assert stats.duplicates_skipped == 2
        assert stats.new_items == 0

    def test_mix_of_new_and_duplicates(self):
        engine = DedupEngine()
        engine.register(doc_id="pre-1", url="https://example.com/existing")

        items = [
            {"url": "https://example.com/existing", "content": "Old"},
            {"url": "https://example.com/new-1", "content": "Brand new A"},
            {"url": "https://example.com/new-2", "content": "Brand new B"},
        ]
        new_items, stats = engine.process_batch(items)
        assert len(new_items) == 2
        assert stats.new_items == 2
        assert stats.duplicates_skipped == 1
        assert stats.total_processed == 3

    def test_intra_batch_dedup(self):
        """Items within the same batch should deduplicate against each other."""
        engine = DedupEngine()
        items = [
            {"url": "https://example.com/page", "content": "Same"},
            {"url": "https://example.com/page", "content": "Same"},
        ]
        new_items, stats = engine.process_batch(items)
        assert len(new_items) == 1
        assert stats.new_items == 1
        assert stats.duplicates_skipped == 1

    def test_batch_uses_id_field(self):
        engine = DedupEngine()
        items = [{"id": "my-id", "url": "https://a.com", "content": "X"}]
        new_items, stats = engine.process_batch(items)
        assert stats.new_items == 1
        # Check it was registered with the "id" field
        result = engine.check_duplicate(url="https://a.com")
        assert result.existing_id == "my-id"

    def test_batch_falls_back_to_url_as_id(self):
        engine = DedupEngine()
        items = [{"url": "https://a.com/page", "content": "X"}]
        new_items, stats = engine.process_batch(items)
        result = engine.check_duplicate(url="https://a.com/page")
        assert result.existing_id == "https://a.com/page"

    def test_empty_batch(self):
        engine = DedupEngine()
        new_items, stats = engine.process_batch([])
        assert len(new_items) == 0
        assert stats.total_processed == 0
        assert stats.new_items == 0

    def test_batch_with_content_hash_dedup(self):
        """Items with different URLs but same content should deduplicate."""
        engine = DedupEngine()
        items = [
            {"url": "https://a.com/page", "content": "Identical content"},
            {"url": "https://b.com/page", "content": "Identical content"},
        ]
        new_items, stats = engine.process_batch(items)
        assert len(new_items) == 1
        assert stats.duplicates_skipped == 1

    def test_batch_updates_engine_stats(self):
        engine = DedupEngine()
        items = [{"url": "https://a.com", "content": "X"}]
        engine.process_batch(items)
        assert engine.stats.total_processed == 1
        assert engine.stats.new_items == 1


# ============================================================
# Stats Tracking Tests
# ============================================================

class TestStatsTracking:
    """Tests for DedupStats and stats property."""

    def test_initial_stats_are_zero(self):
        engine = DedupEngine()
        assert engine.stats.total_processed == 0
        assert engine.stats.new_items == 0
        assert engine.stats.duplicates_skipped == 0
        assert engine.stats.duplicates_updated == 0
        assert engine.stats.errors == 0

    def test_stats_after_batch(self):
        engine = DedupEngine()
        engine.register(doc_id="1", url="https://a.com")
        items = [
            {"url": "https://a.com", "content": "Dup"},
            {"url": "https://b.com", "content": "New"},
        ]
        _, stats = engine.process_batch(items)
        assert stats.total_processed == 2
        assert stats.new_items == 1
        assert stats.duplicates_skipped == 1

    def test_stats_overwritten_by_next_batch(self):
        engine = DedupEngine()
        engine.process_batch([{"url": "https://a.com"}])
        engine.process_batch([{"url": "https://b.com"}, {"url": "https://c.com"}])
        assert engine.stats.total_processed == 2
        assert engine.stats.new_items == 2


# ============================================================
# Summary String Formatting Tests
# ============================================================

class TestSummaryString:
    """Tests for DedupStats.summary()."""

    def test_summary_all_zeros(self):
        stats = DedupStats()
        summary = stats.summary()
        assert "0 new" in summary
        assert "0 duplicates skipped" in summary
        assert "0 updated" in summary
        assert "0 errors" in summary

    def test_summary_with_values(self):
        stats = DedupStats(
            total_processed=100,
            new_items=60,
            duplicates_skipped=35,
            duplicates_updated=3,
            errors=2,
        )
        summary = stats.summary()
        assert "60 new" in summary
        assert "35 duplicates skipped" in summary
        assert "3 updated" in summary
        assert "2 errors" in summary

    def test_summary_is_string(self):
        stats = DedupStats()
        assert isinstance(stats.summary(), str)


# ============================================================
# Edge Cases Tests
# ============================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_content_in_check(self):
        engine = DedupEngine()
        result = engine.check_duplicate(url="https://a.com", content="")
        assert result.is_duplicate is False
        assert result.content_hash == ""

    def test_empty_url_in_check(self):
        engine = DedupEngine()
        result = engine.check_duplicate(url="")
        assert result.is_duplicate is False

    def test_register_and_check_empty_url(self):
        engine = DedupEngine()
        engine.register(doc_id="empty", url="")
        result = engine.check_duplicate(url="")
        assert result.is_duplicate is True

    def test_very_long_url(self):
        engine = DedupEngine()
        long_url = "https://example.com/" + "x" * 10000
        engine.register(doc_id="long", url=long_url)
        result = engine.check_duplicate(url=long_url)
        assert result.is_duplicate is True

    def test_unicode_url(self):
        engine = DedupEngine()
        url = "https://example.com/page\u00e9"
        engine.register(doc_id="uni", url=url)
        result = engine.check_duplicate(url=url)
        assert result.is_duplicate is True

    def test_unicode_content(self):
        engine = DedupEngine()
        content = "Caf\u00e9 r\u00e9sum\u00e9 na\u00efve"
        engine.register(doc_id="uni", url="https://a.com", content=content)
        result = engine.check_duplicate(url="https://b.com", content=content)
        assert result.is_duplicate is True

    def test_clear_resets_engine(self):
        engine = DedupEngine()
        engine.register(doc_id="1", url="https://a.com", content="A", title="T")
        engine.clear()
        assert engine.seen_url_count == 0
        assert engine.seen_hash_count == 0
        result = engine.check_duplicate(url="https://a.com")
        assert result.is_duplicate is False

    def test_dedup_result_defaults(self):
        result = DedupResult(is_duplicate=False)
        assert result.strategy_matched is None
        assert result.existing_id is None
        assert result.content_hash == ""

    def test_dedup_result_with_values(self):
        result = DedupResult(
            is_duplicate=True,
            strategy_matched="url_exact",
            existing_id="doc-1",
            content_hash="abc123",
        )
        assert result.is_duplicate is True
        assert result.strategy_matched == "url_exact"
        assert result.existing_id == "doc-1"
        assert result.content_hash == "abc123"

    def test_strategy_enum_values(self):
        assert DedupStrategy.URL_EXACT.value == "url_exact"
        assert DedupStrategy.CONTENT_HASH.value == "content_hash"
        assert DedupStrategy.URL_AND_DATE.value == "url_and_date"
        assert DedupStrategy.TITLE_SIMILARITY.value == "title_similarity"

    def test_strategy_is_string(self):
        assert isinstance(DedupStrategy.URL_EXACT, str)

    def test_multiple_registers_same_url_overwrites(self):
        engine = DedupEngine()
        engine.register(doc_id="old", url="https://a.com")
        engine.register(doc_id="new", url="https://a.com")
        result = engine.check_duplicate(url="https://a.com")
        assert result.existing_id == "new"

    def test_batch_items_without_content(self):
        engine = DedupEngine()
        items = [
            {"url": "https://a.com"},
            {"url": "https://b.com"},
        ]
        new_items, stats = engine.process_batch(items)
        assert len(new_items) == 2
        assert stats.new_items == 2

    def test_batch_with_title_similarity_strategy(self):
        engine = DedupEngine()
        engine.register(doc_id="1", url="https://a.com", title="Council Meeting Jan 2024")
        items = [
            {
                "url": "https://b.com",
                "title": "Council Meeting Jan 2024",
            },
        ]
        new_items, stats = engine.process_batch(
            items, strategies=[DedupStrategy.TITLE_SIMILARITY]
        )
        assert len(new_items) == 0
        assert stats.duplicates_skipped == 1
