# Knowledge2 Document Upload Error Report

**Date:** February 18, 2026
**Reporter:** VanCity Lens Development Team
**Issue:** Persistent upload failures with "Invalid non-printable ASCII character in URL" error
**Severity:** Critical - Blocking production RAG implementation

---

## Executive Summary

We are unable to upload documents to our Knowledge2 corpus using the Python SDK's `upload_documents_batch()` method. All upload attempts fail with the error:

```
Invalid non-printable ASCII character in URL, '\n' at position 48.
```

**However, extensive debugging has confirmed that our data is completely clean** - no newlines, no non-printable characters, and all fields properly sanitized. This suggests either:
1. A bug in the K2 SDK serialization logic
2. An undocumented API constraint we're hitting
3. A misleading error message pointing to the wrong field

---

## Environment Details

### Software Versions
- **K2 SDK:** `knowledge2` Python SDK (latest from PyPI)
- **Python Version:** 3.12
- **K2 API Host:** `https://api-dev.knowledge2.ai`
- **K2 Corpus ID:** `bb158585-b616-4aed-ab63-55604093a3b8`

### Infrastructure
- **Runtime:** Kubernetes (GKE)
- **Database:** PostgreSQL 16 with PostGIS + pgvector
- **Document Count:** 195 documents ready to sync
- **Document Sources:** Web scrapers (Tavily API, news feeds, government sites)

---

## SDK Method Usage

### Code Implementation

```python
from sdk import Knowledge2

# Client initialization
k2_client = Knowledge2(
    api_host="https://api-dev.knowledge2.ai",
    api_key=os.environ["K2_API_KEY"],
    timeout=60.0,
)

# Chunking configuration
DEFAULT_CHUNKING = {
    "strategy": "semantic",
    "chunk_size": 512,
    "overlap": 50,
}

# Upload attempt
response = k2_client.upload_documents_batch(
    corpus_id="bb158585-b616-4aed-ab63-55604093a3b8",
    documents=k2_batch,  # List of document dicts (see data sample below)
    chunking=DEFAULT_CHUNKING,
    auto_index=True,
    wait=True,
    poll_s=5,
)
```

### Document Format

Each document in the batch is a Python dict with this structure:

```python
{
    "raw_text": str,      # Document content (single line, newlines replaced with spaces)
    "source_uri": str,    # Document URL (sanitized, no newlines)
    "metadata": dict,     # Additional metadata fields
}
```

---

## Actual Data Samples

### Sample Document 1 (Tavily Search Source)

```json
{
  "raw_text": "The curtain rises on the evening of Tuesday, March 10, 2026, at Vancouver City Hall, for what is billed as a public hearing.",
  "source_uri": "https://cityhallwatch.wordpress.com/2026/02/17/vancouver-final-performance-of-democracy-odp-hearing/",
  "metadata": {
    "source_type": "tavily_search",
    "title": "The Last Act: Vancouver's final performance of Democracy (Official ...",
    "published_date": null,
    "scraped_at": "2026-02-18T07:55:21.402902+00:00",
    "postgres_id": 10485,
    "source": "tavily",
    "search_query": "Vancouver density development news",
    "discovered_at": "2026-02-18T07:55:21.402881+00:00"
  }
}
```

**Hex dump of source_uri[40:60]:**
```
'/02/17/vancouver-fin'
Hex: 2f 30 32 2f 31 37 2f 76 61 6e 63 6f 75 76 65 72 2d 66 69 6e
```
All characters are standard ASCII. No `0a` (LF) or `0d` (CR) bytes present.

### Sample Document 2 (News Source)

```json
{
  "raw_text": "An investigation by The Tyee has found that at least 340 long-term renters have been displaced from low-rise apartment buildings along the Broadway corridor to make way for tower developments approved under the Broadway Plan. Many displaced tenants are seniors who had lived in their units for over a decade paying rents well below market rate. While developers are required to offer right of first refusal for new units, tenant advocates say the gap between old and new rents makes return unaffordable. The City's tenant relocation policy covers moving costs and provides interim rent supplements, but critics argue the support is insufficient.",
  "source_uri": "https://thetyee.ca/analysis/2025/08/vancouver-renters-broadway-displacement",
  "metadata": {
    "source_type": "news",
    "title": "Broadway Boom Displacing Hundreds of Long-Term Renters",
    "published_date": "2025-08-22",
    "scraped_at": "2026-02-15T06:42:30.304931+00:00",
    "postgres_id": 10288
  }
}
```

**Hex dump of source_uri[40:60]:**
```
'ouver-renters-broadw'
Hex: 6f 75 76 65 72 2d 72 65 6e 74 65 72 73 2d 62 72 6f 61 64 77
```
All characters are standard ASCII. No non-printable characters present.

---

## Error Messages

### Batch Upload Error

```
2026-02-18 09:39:36,840 - ERROR - Failed to upload batch 1: Invalid non-printable ASCII character in URL, '\n' at position 48.
2026-02-18 09:39:36,840 - ERROR - Sample document from batch: source_uri='https://cityhallwatch.wordpress.com/2026/02/17/vancouver-final-performance-of-democracy-odp-hearing/'
```

### Single Document Upload Error

To isolate whether this was batch-related, we tested uploading just one document:

```python
# Single document test
response = k2_client.upload_documents_batch(
    corpus_id=corpus_id,
    documents=[k2_batch[0]],  # Only first document
    chunking=DEFAULT_CHUNKING,
    auto_index=True,
    wait=True,
    poll_s=5,
)
```

**Result:** Same error
```
2026-02-18 09:39:36,840 - ERROR - Single-document upload also failed: Invalid non-printable ASCII character in URL, '\n' at position 48.
```

This confirms the error is **not batch-related** and occurs even with minimal payloads.

---

## Sanitization Attempts

We have progressively sanitized the data to eliminate all possible sources of newlines:

### 1. Source URL Sanitization

```python
source_url = doc["source_url"] or ""
source_url = source_url.replace("\n", "").replace("\r", "").strip()
```

### 2. Raw Text Sanitization

```python
raw_text = doc["raw_text"] or ""
raw_text = raw_text.replace("\n", " ").replace("\r", " ").strip()
```

### 3. Metadata Field Validation

We validated that no metadata fields contain newlines:

```python
metadata = formatted.get("metadata", {})
for key, value in metadata.items():
    if isinstance(value, str) and ("\n" in value or "\r" in value):
        logger.warning(f"metadata.{key} has newlines")
```

**Result:** No warnings - all metadata fields are clean.

---

## Debugging Evidence

### Complete Logs from Latest Attempt

```
2026-02-18 09:39:35,828 - INFO - Starting K2 sync (force=True, dry_run=False, limit=None)
2026-02-18 09:39:35,840 - INFO - Fetched 195 documents to sync
2026-02-18 09:39:36,832 - INFO - HTTP Request: GET https://api-dev.knowledge2.ai/v1/auth/whoami "HTTP/1.1 200 OK"
2026-02-18 09:39:36,834 - INFO - Uploading batch 1/2 (100 documents)...
2026-02-18 09:39:36,836 - INFO - First document in batch:
{
  "raw_text": "The curtain rises on the evening of Tuesday, March 10, 2026, at Vancouver City Hall, for what is billed as a public hearing.",
  "source_uri": "https://cityhallwatch.wordpress.com/2026/02/17/vancouver-final-performance-of-democracy-odp-hearing/",
  "metadata": {
    "source_type": "tavily_search",
    "title": "The Last Act: Vancouver's final performance of Democracy (Official ...",
    "published_date": null,
    "scraped_at": "2026-02-18T07:55:21.402902+00:00",
    "postgres_id": 10485,
    "source": "tavily",
    "search_query": "Vancouver density development news",
    "discovered_at": "2026-02-18T07:55:21.402881+00:00"
  }
}
2026-02-18 09:39:36,838 - INFO - source_uri[40:60] = '/02/17/vancouver-fin' (hex: 2f 30 32 2f 31 37 2f 76 61 6e 63 6f 75 76 65 72 2d 66 69 6e)
2026-02-18 09:39:36,838 - INFO - Attempting single-document upload for debugging...
2026-02-18 09:39:36,840 - ERROR - Single-document upload also failed: Invalid non-printable ASCII character in URL, '\n' at position 48.
2026-02-18 09:39:36,840 - ERROR - Failed to upload batch 1: Invalid non-printable ASCII character in URL, '\n' at position 48.
```

### Hex Dump Analysis

We added byte-level inspection of the source_uri field around position 48:

| Position | Character | Hex Value | ASCII |
|----------|-----------|-----------|-------|
| 40 | `/` | `2f` | Standard |
| 41 | `0` | `30` | Standard |
| 42 | `2` | `32` | Standard |
| 43 | `/` | `2f` | Standard |
| 44 | `1` | `31` | Standard |
| 45 | `7` | `37` | Standard |
| 46 | `/` | `2f` | Standard |
| 47 | `v` | `76` | Standard |
| **48** | **`a`** | **`61`** | **Standard** |
| 49 | `n` | `6e` | Standard |
| 50 | `c` | `63` | Standard |

**Position 48 is the letter 'a' (hex `61`)** - a completely normal ASCII character. No `0a` (newline) or `0d` (carriage return) present.

---

## Questions for K2 Support

1. **Is the error message misleading?** The error says "in URL" but could it be referring to:
   - The HTTP request URL (API endpoint)?
   - A different field we're not inspecting?
   - An internal K2 processing step?

2. **Are there undocumented constraints on:**
   - Maximum `raw_text` length?
   - Allowed characters in `source_uri`?
   - Metadata field formats?
   - JSON serialization format?

3. **Is there a known issue** with the Python SDK's `upload_documents_batch()` method that could cause this?

4. **Alternative upload methods?** Should we:
   - Use a different SDK method?
   - Call the REST API directly?
   - Upload documents one at a time instead of batching?

5. **Can you reproduce this error** with the sample data provided above?

---

## Impact

This issue is **blocking our production RAG implementation**. We have:
- ✅ 195 high-quality documents ready for indexing
- ✅ Complete scraper pipeline generating fresh content
- ✅ All supporting infrastructure deployed
- ❌ Unable to populate the K2 corpus due to this upload error

Our RAG backend is currently returning "insufficient information" to all queries because the corpus is empty.

---

## Request

We would greatly appreciate:

1. **Root cause analysis** of why clean, sanitized data triggers this error
2. **Workaround or fix** to unblock our production deployment
3. **SDK update** if this is a known serialization bug
4. **Documentation clarification** if we're missing a required data format constraint

---

## Contact Information

**Project:** VanCity Lens (Real Estate Intelligence Platform)
**K2 Account:** (to be provided)
**Corpus ID:** `bb158585-b616-4aed-ab63-55604093a3b8`
**Priority:** High - Production blocker

---

## Appendix: Full Source Code

### Document Formatting Function

```python
def format_for_k2(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a PostgreSQL document for K2 batch upload.

    Args:
        doc: Document dict from PostgreSQL

    Returns:
        K2-formatted document dict
    """
    # Build metadata for K2
    k2_metadata = {
        "source_type": doc["source_type"],
        "title": doc["title"],
        "published_date": doc["published_date"].isoformat() if doc["published_date"] else None,
        "scraped_at": doc["scraped_at"].isoformat() if doc["scraped_at"] else None,
        "postgres_id": doc["id"],
    }

    # Merge with original metadata
    if doc["metadata"]:
        k2_metadata.update(
            {k: v for k, v in doc["metadata"].items() if k != "postgres_id"}
        )

    # Sanitize source_url - remove newlines and whitespace
    source_url = doc["source_url"] or ""
    source_url = source_url.replace("\n", "").replace("\r", "").strip()

    # Sanitize raw_text - replace newlines with spaces
    raw_text = doc["raw_text"] or ""
    raw_text = raw_text.replace("\n", " ").replace("\r", " ").strip()

    return {
        "raw_text": raw_text,
        "source_uri": source_url,
        "metadata": k2_metadata,
    }
```

### Upload Function

```python
async def sync_to_k2(
    pool: asyncpg.Pool,
    *,
    force: bool = False,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Main sync orchestrator - fetch documents from PostgreSQL and upload to K2.
    """
    corpus_id = os.environ["K2_CORPUS_ID"]

    # Fetch documents to sync
    documents = await get_documents_to_sync(pool, force=force, limit=limit)

    if not documents:
        logger.info("No documents to sync")
        return {"documents_fetched": 0, "documents_uploaded": 0, "batches": 0}

    logger.info("Fetched %d documents to sync", len(documents))

    # Build K2 client
    k2_client = get_k2_client()

    # Upload in batches
    BATCH_SIZE = 100
    total_uploaded = 0
    batch_count = 0

    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i : i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1

        logger.info("Uploading batch %d/%d (%d documents)...",
                   batch_num, (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE, len(batch))

        # Format for K2
        k2_batch = [format_for_k2(doc) for doc in batch]

        try:
            response = k2_client.upload_documents_batch(
                corpus_id=corpus_id,
                documents=k2_batch,
                chunking=DEFAULT_CHUNKING,
                auto_index=True,
                wait=True,
                poll_s=5,
            )

            logger.info("Batch %d uploaded successfully", batch_num)
            total_uploaded += len(batch)
            batch_count += 1

        except Exception as e:
            logger.error("Failed to upload batch %d: %s", batch_num, e)
            continue

    return {
        "documents_fetched": len(documents),
        "documents_uploaded": total_uploaded,
        "batches": batch_count,
    }
```

---

**Generated:** 2026-02-18
**VanCity Lens Development Team**
