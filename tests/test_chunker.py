"""Tests for the semantic text chunking pipeline (semchunk-based)."""

import pytest
from unittest.mock import patch, MagicMock
from api.intelligence.chunker import (
    detect_section_header,
    chunk_document,
    _count_tokens,
    _simple_chunker,
    CHUNK_SIZE,
)


# ── Token counting ────────────────────────────────────────────

class TestCountTokens:
    """Test token counting (tiktoken with fallback)."""

    def test_empty_string(self):
        """Test token count for empty string."""
        assert _count_tokens("") == 0

    def test_single_word(self):
        """Test token count for single word."""
        count = _count_tokens("word")
        assert count > 0

    def test_typical_text(self):
        """Test token count for typical text."""
        text = "The city council voted to approve rezoning"
        tokens = _count_tokens(text)
        assert tokens > 0
        assert tokens < 50  # Reasonable upper bound

    def test_long_text_scales(self):
        """Test token count scales with text length."""
        short = _count_tokens("hello world")
        long = _count_tokens("hello world " * 100)
        assert long > short

    def test_fallback_without_tiktoken(self):
        """Test fallback approximation when tiktoken unavailable."""
        import sys
        with patch.dict(sys.modules, {"tiktoken": None}):
            # Force fallback: ~4 chars per token
            text = "x" * 400
            tokens = _count_tokens(text)
            assert tokens == 100  # 400 / 4


# ── Section header detection ──────────────────────────────────

class TestDetectSectionHeader:
    """Test section header detection for government documents."""

    def test_detect_item_header(self):
        """Test detecting ITEM headers."""
        text = "ITEM 1: Regular Council Meeting\nContent here."
        header = detect_section_header(text)
        assert header is not None
        assert "Regular Council Meeting" in header or "ITEM 1" in header

    def test_detect_numbered_header(self):
        """Test detecting numbered headers."""
        text = "1. Approval of Minutes\nMinutes were approved."
        header = detect_section_header(text)
        assert header is not None
        assert "Approval of Minutes" in header or "1." in header

    def test_detect_lettered_header(self):
        """Test detecting lettered headers."""
        text = "A. Background and Context\nSome background info."
        header = detect_section_header(text)
        assert header is not None
        assert "Background" in header

    def test_detect_all_caps_header(self):
        """Test detecting ALL CAPS headers."""
        text = "REZONING DECISION\nCouncil voted to approve."
        header = detect_section_header(text)
        assert header is not None
        assert "REZONING" in header.upper()

    def test_not_detect_regular_text(self):
        """Test that regular paragraph text is not detected as header."""
        text = "This is a regular paragraph of text with no special formatting or structure that would indicate a section header."
        header = detect_section_header(text)
        # Regular text should not be detected as a header
        assert header is None

    def test_ignore_long_text(self):
        """Test that very long lines are not treated as headers."""
        long_text = "This is a very long paragraph that goes on and on " * 10
        header = detect_section_header(long_text)
        assert header is None

    def test_detect_section_header(self):
        """Test SECTION header pattern."""
        text = "SECTION 3: Community Plan Amendments\nDetails follow."
        header = detect_section_header(text)
        assert header is not None

    def test_detect_colon_terminated(self):
        """Test colon-terminated header."""
        text = "Policy Update:\nNew policies were introduced."
        header = detect_section_header(text)
        assert header is not None

    def test_returns_none_for_empty(self):
        """Test returns None for empty text."""
        assert detect_section_header("") is None
        assert detect_section_header("   ") is None


# ── Simple fallback chunker ──────────────────────────────────

class TestSimpleChunker:
    """Test the fallback paragraph-based chunker."""

    def test_empty_text(self):
        """Test simple chunker with empty text."""
        chunks = _simple_chunker("")
        assert chunks == []

    def test_single_paragraph(self):
        """Test single paragraph returns single chunk."""
        text = "This is a single paragraph."
        chunks = _simple_chunker(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_multiple_paragraphs(self):
        """Test multiple paragraphs are handled."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = _simple_chunker(text)
        assert len(chunks) >= 1
        # All text should be preserved
        combined = ' '.join(chunks)
        assert "Paragraph one" in combined
        assert "Paragraph three" in combined

    def test_long_text_produces_multiple_chunks(self):
        """Test that very long text produces multiple chunks."""
        # Create text long enough to exceed CHUNK_SIZE
        text = ("This is a paragraph with many words. " * 50 + "\n\n") * 20
        chunks = _simple_chunker(text)
        assert len(chunks) > 1


# ── Main chunk_document function ─────────────────────────────

class TestChunkDocument:
    """Test the main chunking pipeline."""

    def test_empty_document(self):
        """Test chunking empty document."""
        chunks = chunk_document("")
        assert chunks == []

    def test_none_input(self):
        """Test None input returns empty list."""
        chunks = chunk_document(None)
        assert chunks == []

    def test_non_string_input(self):
        """Test non-string input returns empty list."""
        chunks = chunk_document(123)
        assert chunks == []

    def test_short_document_single_chunk(self):
        """Test short document becomes single chunk."""
        text = "Short document. Only one chunk should be created."
        chunks = chunk_document(text)
        assert len(chunks) == 1
        assert chunks[0]["chunk_text"] == text

    def test_chunk_structure(self):
        """Test chunk dict structure is correct."""
        text = "ITEM 1: Header\nContent here. More content."
        chunks = chunk_document(text)
        assert len(chunks) > 0
        for chunk in chunks:
            assert "chunk_text" in chunk
            assert "chunk_index" in chunk
            assert "section_header" in chunk
            assert "approx_token_count" in chunk

    def test_chunk_indices_sequential(self):
        """Test chunk indices are sequential starting from 0."""
        text = "Item 1\nContent.\n\nItem 2\nContent.\n\nItem 3\nContent."
        chunks = chunk_document(text)
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_token_counts_positive(self):
        """Test all chunks have positive token counts."""
        text = "This is some content. " * 50
        chunks = chunk_document(text)
        for chunk in chunks:
            assert chunk["approx_token_count"] > 0

    def test_section_headers_tracked(self):
        """Test section headers are detected and tracked."""
        text = """ITEM 1: Rezoning Decision
This is content for item 1. Council voted to approve.

ITEM 2: Policy Update
This is content for item 2. New policies introduced."""
        chunks = chunk_document(text)
        # At least some chunks should have headers
        headers = [c["section_header"] for c in chunks if c["section_header"]]
        assert len(headers) > 0

    def test_whitespace_normalization(self):
        """Test whitespace is normalized."""
        text = "Line 1  \n  \nLine 2"
        chunks = chunk_document(text)
        assert len(chunks) > 0

    def test_custom_chunk_size(self):
        """Test custom chunk_size parameter."""
        text = "Sentence number one. " * 200  # Long text
        small_chunks = chunk_document(text, chunk_size=100)
        large_chunks = chunk_document(text, chunk_size=2000)
        # Smaller chunk_size should produce more chunks
        if len(small_chunks) > 1 and len(large_chunks) > 0:
            assert len(small_chunks) >= len(large_chunks)

    def test_realistic_council_minutes(self, sample_document):
        """Test chunking realistic council minutes."""
        chunks = chunk_document(sample_document["raw_text"])
        assert len(chunks) > 0
        assert all("chunk_text" in c for c in chunks)
        assert all(c["approx_token_count"] > 0 for c in chunks)

    def test_no_empty_chunks(self):
        """Test that no empty chunks are produced."""
        text = "Content here.\n\n\n\nMore content.\n\n\n\n"
        chunks = chunk_document(text)
        for chunk in chunks:
            assert len(chunk["chunk_text"].strip()) > 0

    def test_long_document_produces_multiple_chunks(self):
        """Test that a sufficiently long document produces multiple chunks."""
        # Generate text that will exceed one chunk
        text = ("The city council discussed the rezoning application at length. " * 100 + "\n\n") * 5
        chunks = chunk_document(text, chunk_size=200)
        assert len(chunks) > 1


# ── Integration tests ────────────────────────────────────────

class TestChunkerIntegration:
    """Integration tests for the full chunking pipeline."""

    def test_full_pipeline(self, sample_document):
        """Test full chunking pipeline with realistic data."""
        text = sample_document["raw_text"]
        chunks = chunk_document(text)

        # Verify results
        assert len(chunks) > 0
        assert all(c["chunk_index"] >= 0 for c in chunks)
        assert all(c["approx_token_count"] > 0 for c in chunks)

        # Verify no data loss (reconstructed text should contain original content)
        reconstructed = " ".join(c["chunk_text"] for c in chunks)
        assert "REZONING" in reconstructed.upper()

    def test_chunking_consistency(self):
        """Test that chunking the same text produces consistent results."""
        text = "Item 1\nContent.\n" * 50
        chunks1 = chunk_document(text)
        chunks2 = chunk_document(text)

        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1["chunk_text"] == c2["chunk_text"]

    def test_semchunk_fallback(self):
        """Test that chunker works even when semchunk is unavailable."""
        import api.intelligence.chunker as chunker_mod

        # Save original state
        original_chunker = chunker_mod._chunker
        original_use = chunker_mod._use_semchunk

        try:
            # Reset to force re-initialization with fallback
            chunker_mod._chunker = chunker_mod._simple_chunker
            chunker_mod._use_semchunk = False

            text = "Paragraph one content here.\n\nParagraph two content here."
            chunks = chunk_document(text)
            assert len(chunks) > 0
            assert all("chunk_text" in c for c in chunks)
        finally:
            # Restore
            chunker_mod._chunker = original_chunker
            chunker_mod._use_semchunk = original_use
