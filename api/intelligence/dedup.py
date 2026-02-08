"""
VCL-76 [DATA-003] Scraper Deduplication Logic
Deduplicates documents across multiple scrapers using content hashing,
URL matching, and fuzzy similarity detection.

Key components:
- ContentHasher: SHA-256 fingerprinting of normalized text
- TextNormalizer: Whitespace/punctuation/case normalization
- DuplicateDetector: Core deduplication engine with 4 detection methods
- SimHash: Locality-sensitive hashing for fast near-duplicate detection
- deduplicate_document: Main entry point for dedupe workflow
"""

import hashlib
import re
import logging
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
import asyncpg

logger = logging.getLogger(__name__)


class DeduplicationResult(Enum):
    """Deduplication result types."""
    NEW = "new"
    EXACT_DUPLICATE = "exact_duplicate"
    NEAR_DUPLICATE = "near_duplicate"
    UPDATED = "updated"


class TextNormalizer:
    """Normalize text for consistent comparison."""

    @staticmethod
    def normalize(text: str) -> str:
        """
        Normalize text by:
        - Converting to lowercase
        - Removing punctuation
        - Normalizing whitespace
        - Removing common HTML entities

        Args:
            text: Raw text to normalize

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Remove HTML entities and special characters
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")

        # Remove URLs
        text = re.sub(r'http[s]?://\S+', '', text)

        # Remove email addresses
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text)

        # Remove punctuation and symbols, keep alphanumeric and whitespace
        text = re.sub(r'[^\w\s]', '', text)

        # Normalize whitespace: replace multiple spaces/newlines with single space
        text = re.sub(r'\s+', ' ', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text


class ContentHasher:
    """Generate content fingerprints using SHA-256."""

    @staticmethod
    def hash_content(text: str) -> str:
        """
        Generate SHA-256 hash of normalized text.

        Args:
            text: Raw text to hash

        Returns:
            Hexadecimal SHA-256 hash string
        """
        if not text:
            return hashlib.sha256(b"").hexdigest()

        normalized = TextNormalizer.normalize(text)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    @staticmethod
    def hash_title_and_text(title: Optional[str], text: str) -> str:
        """
        Generate combined hash of title and text (for strict matching).

        Args:
            title: Document title
            text: Document text

        Returns:
            Hexadecimal SHA-256 hash string
        """
        combined = f"{title or ''}\n{text}"
        normalized = TextNormalizer.normalize(combined)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


class SimHash:
    """Locality-sensitive hash for fast approximate duplicate detection.

    Uses 64-bit simhash based on token shingles.
    Simhash allows distance-based similarity (Hamming distance).
    """

    @staticmethod
    def _hash_token(token: str) -> int:
        """Hash a single token to a 64-bit integer."""
        h = hashlib.md5(token.encode('utf-8')).digest()
        return int.from_bytes(h[:8], byteorder='big')

    @staticmethod
    def compute(text: str, shingle_size: int = 4) -> int:
        """
        Compute simhash fingerprint for text.

        Uses shingle-based approach:
        1. Generate k-grams (shingles) of tokens
        2. Hash each shingle
        3. Compute bit vectors and aggregate

        Args:
            text: Text to hash
            shingle_size: Token shingle size (default 4)

        Returns:
            64-bit simhash integer
        """
        if not text:
            return 0

        normalized = TextNormalizer.normalize(text)
        tokens = normalized.split()

        if len(tokens) < shingle_size:
            tokens = tokens + [''] * (shingle_size - len(tokens))

        # Create token shingles
        shingles = []
        for i in range(len(tokens) - shingle_size + 1):
            shingle = ' '.join(tokens[i:i + shingle_size])
            shingles.append(shingle)

        if not shingles:
            return 0

        # Compute bit vector aggregation
        bit_vector = [0] * 64
        for shingle in shingles:
            h = SimHash._hash_token(shingle)
            for i in range(64):
                if (h >> i) & 1:
                    bit_vector[i] += 1

        # Create simhash: bits with more votes become 1
        simhash = 0
        for i in range(64):
            if bit_vector[i] > len(shingles) / 2:
                simhash |= (1 << i)

        return simhash

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        """
        Calculate Hamming distance between two simhashes.

        Args:
            hash1: First simhash
            hash2: Second simhash

        Returns:
            Hamming distance (0-64)
        """
        xor = hash1 ^ hash2
        distance = 0
        while xor:
            distance += xor & 1
            xor >>= 1
        return distance

    @staticmethod
    def similarity(hash1: int, hash2: int) -> float:
        """
        Calculate similarity score (0-1) between two simhashes.

        Args:
            hash1: First simhash
            hash2: Second simhash

        Returns:
            Similarity score (1.0 = identical, 0.0 = completely different)
        """
        if hash1 == hash2:
            return 1.0
        distance = SimHash.hamming_distance(hash1, hash2)
        return 1.0 - (distance / 64.0)


class DuplicateDetector:
    """Core deduplication detector using multiple strategies."""

    @staticmethod
    async def check_url_exists(db_pool: asyncpg.Pool, url: str) -> bool:
        """
        Check if URL already exists in documents table.

        Args:
            db_pool: asyncpg connection pool
            url: Source URL to check

        Returns:
            True if URL exists, False otherwise
        """
        try:
            async with db_pool.acquire() as conn:
                result = await conn.fetchval(
                    """
                    SELECT id FROM documents WHERE source_url = $1 LIMIT 1
                    """,
                    url
                )
                return result is not None
        except Exception as e:
            logger.error(f"Error checking URL existence: {e}")
            return False

    @staticmethod
    async def check_content_hash(db_pool: asyncpg.Pool, content_hash: str) -> Optional[int]:
        """
        Check if content hash exists and return existing document ID.

        Args:
            db_pool: asyncpg connection pool
            content_hash: SHA-256 hash of normalized content

        Returns:
            Existing document ID if found, None otherwise
        """
        try:
            async with db_pool.acquire() as conn:
                result = await conn.fetchval(
                    """
                    SELECT id FROM documents WHERE content_hash = $1 LIMIT 1
                    """,
                    content_hash
                )
                return result
        except Exception as e:
            logger.error(f"Error checking content hash: {e}")
            return None

    @staticmethod
    async def find_near_duplicates(
        db_pool: asyncpg.Pool,
        text: str,
        threshold: float = 0.85
    ) -> List[Tuple[int, float]]:
        """
        Find documents with similar content using PostgreSQL trigram similarity.

        Requires pg_trgm extension (added in migration 011).
        Uses normalized title and text for fuzzy matching.

        Args:
            db_pool: asyncpg connection pool
            text: Text to compare
            threshold: Similarity threshold (0.0-1.0), default 0.85

        Returns:
            List of (doc_id, similarity_score) tuples sorted by similarity desc
        """
        try:
            # Extract first 200 chars as representative text
            normalized = TextNormalizer.normalize(text)
            search_text = normalized[:200] if normalized else ""

            if not search_text:
                return []

            async with db_pool.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT id, similarity(%s, COALESCE(title, '') || ' ' || COALESCE(raw_text, '')) as sim
                    FROM documents
                    WHERE similarity(%s, COALESCE(title, '') || ' ' || COALESCE(raw_text, '')) > %s
                    ORDER BY sim DESC
                    LIMIT 10
                    """,
                    search_text,
                    search_text,
                    threshold
                )
                return [(row['id'], float(row['sim'])) for row in results]
        except Exception as e:
            logger.error(f"Error finding near duplicates: {e}")
            return []

    @staticmethod
    async def get_existing_doc_by_url(
        db_pool: asyncpg.Pool,
        url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch existing document by URL.

        Args:
            db_pool: asyncpg connection pool
            url: Source URL

        Returns:
            Document dict or None if not found
        """
        try:
            async with db_pool.acquire() as conn:
                doc = await conn.fetchrow(
                    """
                    SELECT id, source_url, raw_text, content_hash, simhash, processed_at
                    FROM documents WHERE source_url = $1 LIMIT 1
                    """,
                    url
                )
                return dict(doc) if doc else None
        except Exception as e:
            logger.error(f"Error fetching document by URL: {e}")
            return None


async def deduplicate_document(
    db_pool: asyncpg.Pool,
    source_url: str,
    raw_text: str,
    metadata: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None
) -> DeduplicationResult:
    """
    Main deduplication workflow.

    Checks in order:
    1. Exact URL match -> EXACT_DUPLICATE
    2. Content hash match -> EXACT_DUPLICATE
    3. Fuzzy text match (>85% similarity) -> NEAR_DUPLICATE
    4. No match -> NEW
    5. URL exists but content changed -> UPDATED

    Args:
        db_pool: asyncpg connection pool
        source_url: URL of document to check
        raw_text: Full text content
        metadata: Optional metadata dict
        title: Optional document title

    Returns:
        DeduplicationResult enum value
    """
    if not raw_text or not raw_text.strip():
        logger.warning("Empty raw_text provided for deduplication")
        return DeduplicationResult.NEW

    # Step 1: Check exact URL match
    url_exists = await DuplicateDetector.check_url_exists(db_pool, source_url)
    if url_exists:
        existing_doc = await DuplicateDetector.get_existing_doc_by_url(db_pool, source_url)
        if existing_doc:
            # Check if content changed
            existing_hash = existing_doc.get('content_hash')
            new_hash = ContentHasher.hash_content(raw_text)

            if existing_hash == new_hash:
                logger.info(f"URL {source_url}: exact URL + content match")
                return DeduplicationResult.EXACT_DUPLICATE

            # Content changed, mark for re-processing
            logger.info(f"URL {source_url}: content changed since last scrape")
            return DeduplicationResult.UPDATED

        logger.info(f"URL {source_url}: exact URL match found")
        return DeduplicationResult.EXACT_DUPLICATE

    # Step 2: Check content hash match
    content_hash = ContentHasher.hash_content(raw_text)
    existing_id = await DuplicateDetector.check_content_hash(db_pool, content_hash)
    if existing_id:
        logger.info(f"Content hash match: duplicate of document {existing_id}")
        return DeduplicationResult.EXACT_DUPLICATE

    # Step 3: Check fuzzy text match (trigram similarity)
    near_dupes = await DuplicateDetector.find_near_duplicates(db_pool, raw_text, threshold=0.85)
    if near_dupes:
        best_match_id, similarity = near_dupes[0]
        logger.info(f"Near duplicate found: doc {best_match_id} with similarity {similarity:.2f}")
        return DeduplicationResult.NEAR_DUPLICATE

    # Step 4: New document
    logger.info(f"No duplicates found for {source_url}: new document")
    return DeduplicationResult.NEW


async def should_scrape(db_pool: asyncpg.Pool, url: str) -> bool:
    """
    Determine if a URL should be scraped based on dedup status.

    Returns True for NEW or UPDATED documents, False for duplicates.

    Args:
        db_pool: asyncpg connection pool
        url: URL to check

    Returns:
        True if URL should be scraped, False otherwise
    """
    url_exists = await DuplicateDetector.check_url_exists(db_pool, url)
    return not url_exists


async def mark_scraped(db_pool: asyncpg.Pool, doc_id: int) -> None:
    """
    Update document's scraped_at timestamp.

    Args:
        db_pool: asyncpg connection pool
        doc_id: Document ID to update
    """
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE documents SET scraped_at = now() WHERE id = $1
                """,
                doc_id
            )
            logger.debug(f"Marked document {doc_id} as scraped")
    except Exception as e:
        logger.error(f"Error marking document {doc_id} as scraped: {e}")


async def get_scrape_history(
    db_pool: asyncpg.Pool,
    source_type: str,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get scraping statistics for a source type over N days.

    Args:
        db_pool: asyncpg connection pool
        source_type: Source type to filter (e.g., 'council_minutes')
        days: Look back this many days (default 30)

    Returns:
        Dict with statistics:
        {
            'total_documents': int,
            'new_documents': int,
            'duplicate_documents': int,
            'updated_documents': int,
            'source_type': str,
            'period_days': int,
            'documents_per_day': float
        }
    """
    try:
        async with db_pool.acquire() as conn:
            # Get counts
            total_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM documents
                WHERE source_type = $1
                AND scraped_at >= now() - interval '1 day' * $2
                """,
                source_type,
                days
            )

            # Count documents not matching duplicates
            # This is a rough approximation - actual duplicate tracking needs more metadata
            new_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM documents
                WHERE source_type = $1
                AND scraped_at >= now() - interval '1 day' * $2
                AND processed_at IS NULL
                """,
                source_type,
                days
            )

            # Calculate rate
            docs_per_day = total_count / max(days, 1)

            return {
                'total_documents': total_count or 0,
                'new_documents': new_count or 0,
                'duplicate_documents': (total_count or 0) - (new_count or 0),
                'updated_documents': 0,  # Would require explicit tracking
                'source_type': source_type,
                'period_days': days,
                'documents_per_day': round(docs_per_day, 2)
            }

    except Exception as e:
        logger.error(f"Error retrieving scrape history: {e}")
        return {
            'total_documents': 0,
            'new_documents': 0,
            'duplicate_documents': 0,
            'updated_documents': 0,
            'source_type': source_type,
            'period_days': days,
            'documents_per_day': 0.0
        }
