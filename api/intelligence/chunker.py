"""
Semantic text chunking for VanCity Lens intelligence layer.

Uses semchunk for intelligent, semantically-aware text splitting that
preserves meaning across chunk boundaries. Falls back to a simple
splitter if semchunk is unavailable.

Architecture:
  - Primary: semchunk with tiktoken tokenizer (gpt-4 encoding)
  - Chunk size: 800 tokens (balances retrieval precision vs context)
  - Overlap: ~10% handled by semchunk's hierarchical splitting
  - Section headers detected and attached to each chunk
"""

import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────
CHUNK_SIZE = 800       # tokens per chunk (sweet spot for retrieval)
TOKENIZER_MODEL = "gpt-4"  # tiktoken encoding name

# ── Lazy-loaded chunker singleton ─────────────────────────────

_chunker = None
_use_semchunk = True


def _get_chunker():
    """Lazy-initialize the semchunk chunker."""
    global _chunker, _use_semchunk
    if _chunker is not None:
        return _chunker

    try:
        import semchunk
        _chunker = semchunk.chunkerify(TOKENIZER_MODEL, chunk_size=CHUNK_SIZE)
        _use_semchunk = True
        logger.info(f"semchunk initialized: model={TOKENIZER_MODEL}, chunk_size={CHUNK_SIZE}")
    except ImportError:
        logger.warning("semchunk not installed — falling back to simple splitter")
        _use_semchunk = False
        _chunker = _simple_chunker
    except Exception as e:
        logger.warning(f"semchunk init failed ({e}) — falling back to simple splitter")
        _use_semchunk = False
        _chunker = _simple_chunker

    return _chunker


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken, with a fast fallback."""
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(TOKENIZER_MODEL)
        return len(enc.encode(text))
    except ImportError:
        # Approximate: ~4 chars per token for English
        return len(text) // 4


# ── Fallback simple chunker ──────────────────────────────────

def _simple_chunker(text: str) -> List[str]:
    """
    Simple paragraph-based chunker as fallback when semchunk is unavailable.

    Splits on double newlines (paragraphs), then merges small paragraphs
    until the chunk reaches ~CHUNK_SIZE tokens.
    """
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current_parts = []
    current_tokens = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_tokens = _count_tokens(para)

        if current_tokens + para_tokens > CHUNK_SIZE and current_parts:
            chunks.append('\n\n'.join(current_parts))
            current_parts = []
            current_tokens = 0

        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunks.append('\n\n'.join(current_parts))

    return chunks


# ── Section header detection ─────────────────────────────────

# Patterns for government document section headers
_HEADER_PATTERNS = [
    re.compile(r'^(?:ITEM|SECTION|ARTICLE|PART|CHAPTER)\s+\d+[:.]*\s*(.+)$', re.IGNORECASE),
    re.compile(r'^(\d+\.)\s+(.+)$'),
    re.compile(r'^[A-Z]\.\s+(.+)$'),
    re.compile(r'^([A-Z][A-Z\s]{3,})$'),          # ALL CAPS HEADER (min 4 chars)
    re.compile(r'^(.{5,80}):\s*$'),                 # Short line ending with colon
]


def detect_section_header(text: str) -> Optional[str]:
    """
    Detect the nearest section header from the beginning of a chunk.

    Scans the first few lines for patterns common in government documents:
    numbered items, ALL CAPS headers, colon-terminated headings, etc.

    Args:
        text: The chunk text to analyze

    Returns:
        Detected section header string, or None
    """
    lines = text.split('\n')

    # Check first 5 lines for a header
    for line in lines[:5]:
        line = line.strip()
        if not line or len(line) > 200:
            continue

        for pattern in _HEADER_PATTERNS:
            match = pattern.match(line)
            if match:
                # Extract the meaningful part
                groups = match.groups()
                header = groups[-1] if groups else line
                header = header.strip().rstrip(':').strip()
                if header and len(header) > 2:
                    return header

    return None


# ── Main chunking pipeline ───────────────────────────────────

def chunk_document(
    text: str,
    chunk_size: int = CHUNK_SIZE,
) -> List[Dict]:
    """
    Split document text into semantically coherent chunks for embedding.

    Uses semchunk for intelligent splitting that respects sentence and
    paragraph boundaries. Each chunk is annotated with:
    - chunk_text: the actual text content
    - chunk_index: sequential position in the document
    - section_header: nearest detected section header (or None)
    - approx_token_count: token count for the chunk

    Args:
        text: Raw document text to chunk
        chunk_size: Target maximum tokens per chunk

    Returns:
        List of chunk dicts ready for embedding and storage
    """
    if not text or not isinstance(text, str):
        logger.warning("Invalid text provided to chunk_document")
        return []

    # Normalize whitespace but preserve paragraph structure
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    text = text.strip()

    if not text:
        return []

    # Get the chunker (semchunk or fallback)
    chunker = _get_chunker()

    # Split text into chunks
    if _use_semchunk and chunk_size != CHUNK_SIZE:
        # If custom chunk_size requested, create a one-off chunker
        try:
            import semchunk
            custom_chunker = semchunk.chunkerify(TOKENIZER_MODEL, chunk_size=chunk_size)
            raw_chunks = custom_chunker(text)
        except Exception:
            raw_chunks = chunker(text)
    else:
        raw_chunks = chunker(text)

    if not raw_chunks:
        logger.warning("Chunker produced no chunks")
        return []

    # Build structured chunk list with metadata
    result = []
    for idx, chunk_text in enumerate(raw_chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue

        section_header = detect_section_header(chunk_text)
        token_count = _count_tokens(chunk_text)

        result.append({
            'chunk_text': chunk_text,
            'chunk_index': idx,
            'section_header': section_header,
            'approx_token_count': token_count,
        })

    logger.info(
        f"Chunked document into {len(result)} chunks "
        f"(method={'semchunk' if _use_semchunk else 'simple'}, "
        f"target={chunk_size} tokens)"
    )
    return result
