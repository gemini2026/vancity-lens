"""LLM-powered intelligence extraction pipeline for VanCity Lens.

This module takes document chunks and uses Claude (Anthropic API) to extract
structured intelligence signals about Vancouver real estate development,
rezoning decisions, permits, and policy changes.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple
from difflib import SequenceMatcher

import aiohttp
import asyncpg

from .llm_backend import generate_extraction
from .models import ExtractedSignal

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT FOR LLM
# ──────────────────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a Vancouver real estate intelligence analyst with deep expertise in city planning, zoning, development permits, and real estate markets.

Your task is to extract actionable intelligence signals from Vancouver government documents (council minutes, rezoning reports, development permit reports, public hearings, etc.).

## What you're looking for:

Extract every actionable real estate intelligence signal in the document chunk, including:
- Rezoning decisions (site-specific zoning changes)
- Density changes (FAR, height, unit count changes)
- Permit approvals (development permits, building permits)
- Policy changes (ODP updates, zoning bylaw amendments)
- Community opposition or support
- Infrastructure announcements affecting development
- Land sales or acquisitions
- Court rulings affecting development

## For each signal, provide:

For EVERY field below:
1. **signal_type**: One of: rezoning_decision, permit_approval, policy_change, infrastructure_announcement, legal_precedent, community_opposition, density_change, land_sale, other
2. **summary**: 2-3 sentences explaining the signal and its development implications
3. **headline**: 1 concise line (max 12 words) suitable for a news feed
4. **addresses**: Array of specific street addresses mentioned. Be very precise — include house numbers and street names exactly as written in the document.
5. **neighborhood**: The Vancouver neighborhood (Kitsilano, Downtown, West End, etc.) or "Unknown"
6. **zoning_from**: Current or previous zoning designation (e.g., "RS-1", "RM-4", "CD-1 (123)")
7. **zoning_to**: New zoning designation if changed
8. **height_before**: Height limit before change (in meters)
9. **height_after**: Height limit after change (in meters)
10. **fsr_before**: Floor Space Ratio before change
11. **fsr_after**: Floor Space Ratio after change
12. **unit_count**: Number of units mentioned (residential, total, or proposed)
13. **project_value_dollars**: Project value in dollars if mentioned
14. **decision**: Decision status (approved, denied, deferred, referred, pending)
15. **vote_for**: Number of votes in favor
16. **vote_against**: Number of votes against
17. **conditions**: Array of conditions or requirements (e.g., ["Public plaza required", "Rental housing 20%"])
18. **sentiment**: positive_for_development, negative_for_development, or neutral
19. **severity**: info, low, medium, high, or critical (based on development impact/market significance)
20. **confidence**: 0.0-1.0 confidence score reflecting certainty about the extracted data
21. **event_date**: The date this signal became actionable (meeting date, hearing date, etc.) in YYYY-MM-DD format

## Precision Requirements:

- **Specific addresses**: Colin needs precise data, not vague summaries. Include exact street addresses with house numbers.
- **Exact numbers**: Use actual vote counts, heights, FSR values, unit counts — never approximate.
- **Confidence scores**: Reflect how certain you are. If text says "approximately 200 units", confidence is lower than "exactly 200 units". If details are vague, lower confidence.
- **No hallucination**: Only extract what's explicitly stated. Use null/None for fields with no information.
- **Sentiment**: positive_for_development = facilitates or promotes development; negative_for_development = opposes or constrains development

## If no actionable intelligence:

If the chunk contains no real estate development signals, return an empty JSON array: []

## Output Format:

Return ONLY valid JSON. If there are multiple signals in the chunk, return a JSON array with one object per signal.
Example for one signal:
[{
  "signal_type": "rezoning_decision",
  "summary": "City Council approved rezoning of 1234 Main St from RS-1 to CD-1, permitting a 25-storey mixed-use tower with 300 units and 15,000 sq ft of retail.",
  "headline": "1234 Main rezoned to 25-storey mixed-use",
  "addresses": ["1234 Main Street"],
  "neighborhood": "Downtown",
  "zoning_from": "RS-1",
  "zoning_to": "CD-1 (123)",
  "height_before": 10.5,
  "height_after": 80.0,
  "fsr_before": 1.0,
  "fsr_after": 8.5,
  "unit_count": 300,
  "project_value_dollars": 150000000,
  "decision": "approved",
  "vote_for": 10,
  "vote_against": 1,
  "conditions": ["Public plaza minimum 1500 sq m", "Rental housing 20% of units"],
  "sentiment": "positive_for_development",
  "severity": "high",
  "confidence": 0.95,
  "event_date": "2024-01-15"
}]

Be thorough. Extract multiple signals if the chunk contains multiple actionable items."""


# ──────────────────────────────────────────────────────────────────────────
# EXTRACTION FUNCTION
# ──────────────────────────────────────────────────────────────────────────

async def extract_signals_from_chunk(
    chunk_text: str,
    document_context: dict,
    api_key: str,
    *,
    client=None,  # kept for signature compat; ignored when using llm_backend
) -> list[ExtractedSignal]:
    """Extract intelligence signals from a document chunk using the configured LLM.

    Args:
        chunk_text: The text content of the document chunk
        document_context: Dict with keys: source_type, source_url, title, meeting_date
        api_key: Anthropic API key (used only when LLM_BACKEND=anthropic)

    Returns:
        List of ExtractedSignal objects. Empty list if no signals found.
    """
    if not chunk_text or not chunk_text.strip():
        logger.debug("Empty chunk text, returning empty list")
        return []

    user_message = f"""Document Context:
- Source Type: {document_context.get('source_type', 'Unknown')}
- Title: {document_context.get('title', 'Unknown')}
- Meeting Date: {document_context.get('meeting_date', 'Unknown')}
- Source URL: {document_context.get('source_url', 'Unknown')}

Document Chunk:
{chunk_text}

Extract all real estate intelligence signals from this chunk. Return valid JSON only."""

    max_retries = 3
    backoff_factor = 2

    for attempt in range(max_retries):
        try:
            response_text, model_used, latency = await generate_extraction(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=2000,
                anthropic_api_key=api_key,
            )

            response_text = response_text.strip()
            # Strip markdown code fences if the model wraps JSON
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [line for line in lines if not line.startswith("```")]
                response_text = "\n".join(lines).strip()

            signals_data = json.loads(response_text)

            if not signals_data:
                logger.debug("LLM returned empty signal list for chunk")
                return []

            if not isinstance(signals_data, list):
                signals_data = [signals_data]

            signals: list[ExtractedSignal] = []
            for signal_dict in signals_data:
                try:
                    signal = ExtractedSignal(**signal_dict)
                    signals.append(signal)
                except Exception as e:
                    logger.warning("Failed to parse signal object: %s. Data: %s", e, signal_dict)
                    continue

            logger.info("Extracted %d signals from chunk in %.1fs (model=%s)", len(signals), latency, model_used)
            return signals

        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON response (attempt %d): %s", attempt + 1, e)
            if attempt < max_retries - 1:
                wait_time = backoff_factor ** attempt
                await asyncio.sleep(wait_time)
            else:
                logger.error("Max retries exceeded for JSON parsing")

        except Exception as e:
            logger.error("Extraction error (attempt %d): %s", attempt + 1, e)
            if attempt < max_retries - 1:
                wait_time = backoff_factor ** attempt
                await asyncio.sleep(wait_time)
            else:
                logger.error("Max retries exceeded")

    return []


# ──────────────────────────────────────────────────────────────────────────
# GEOCODING FUNCTION
# ──────────────────────────────────────────────────────────────────────────

async def geocode_address(db_pool: asyncpg.Pool, address: str) -> Optional[Tuple[float, float]]:
    """Geocode a Vancouver address using local parcel data or API.

    First tries to fuzzy match against the parcels table, then falls back
    to the BC Open Data geocoder API.

    Args:
        db_pool: asyncpg connection pool
        address: Street address to geocode

    Returns:
        Tuple of (latitude, longitude) or None if geocoding failed
    """
    if not address or not address.strip():
        logger.debug("Empty address provided to geocode_address")
        return None

    address = address.strip()
    logger.debug(f"Geocoding address: {address}")

    # Try fuzzy matching against parcels table
    try:
        async with db_pool.acquire() as conn:
            # Get all addresses from parcels table
            rows = await conn.fetch(
                "SELECT pid, civic_address, geom FROM parcels LIMIT 10000"  # reasonable limit
            )

        if rows:
            # Simple fuzzy match: find best match
            best_match = None
            best_score = 0.0

            for row in rows:
                parcel_address = row["civic_address"]
                if not parcel_address:
                    continue

                # Simple character-level similarity
                similarity = SequenceMatcher(None, address.lower(), parcel_address.lower()).ratio()

                if similarity > best_score and similarity > 0.7:  # require 70% match
                    best_score = similarity
                    best_match = row

            if best_match:
                # Extract coordinates from geometry (PostGIS point)
                geom = best_match["geom"]
                if geom:
                    logger.info(f"Found parcel match for '{address}' with {best_score:.2%} similarity")
                    # geom is already a point with (lon, lat), return as (lat, lon)
                    # Note: PostGIS uses (lon, lat) internally, but we return (lat, lon)
                    # This depends on how the geometry is stored. Typically:
                    try:
                        # PostGIS point geometry
                        lon, lat = geom["coordinates"] if isinstance(geom, dict) else (geom.x, geom.y)
                        return (lat, lon)
                    except (KeyError, AttributeError, TypeError):
                        logger.warning(f"Could not extract coordinates from geometry: {geom}")

    except Exception as e:
        logger.warning(f"Error querying parcels table: {e}")

    # Fall back to BC Open Data geocoder API
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://geocoder.api.gov.bc.ca/addresses.json"
            params = {
                "addressString": f"{address},Vancouver,BC",
            }

            logger.debug(f"Calling BC geocoder API for address: {address}")

            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    features = data.get("features", [])

                    if features:
                        # Take first result
                        feature = features[0]
                        coords = feature.get("geometry", {}).get("coordinates", [])
                        if coords and len(coords) >= 2:
                            lon, lat = coords[0], coords[1]
                            logger.info(f"Geocoded '{address}' via BC API: ({lat}, {lon})")
                            return (lat, lon)

                    logger.debug(f"BC geocoder returned no features for '{address}'")
                else:
                    logger.warning(f"BC geocoder API returned status {resp.status}")

    except asyncio.TimeoutError:
        logger.warning(f"BC geocoder API timeout for address '{address}'")
    except Exception as e:
        logger.warning(f"Error calling BC geocoder API: {e}")

    logger.debug(f"Could not geocode address: {address}")
    return None


# ──────────────────────────────────────────────────────────────────────────
# DOCUMENT PROCESSING
# ──────────────────────────────────────────────────────────────────────────

# DV-REG-002: Confidence threshold for auto-approval vs manual review
CONFIDENCE_AUTO_APPROVE_THRESHOLD = 0.85


async def process_document(
    db_pool: asyncpg.Pool,
    document_id: int,
    api_key: str,
    confidence_threshold: float = CONFIDENCE_AUTO_APPROVE_THRESHOLD,
) -> int:
    """Process a document by extracting signals from all its chunks.

    Fetches the document and its chunks, extracts signals from each chunk,
    geocodes addresses, and stores results in intelligence_signals table.

    Signals with confidence < confidence_threshold are flagged for manual review
    (DV-REG-002).

    Args:
        db_pool: asyncpg connection pool
        document_id: ID of document to process
        api_key: Anthropic API key
        confidence_threshold: Signals below this confidence get flagged for review

    Returns:
        Count of signals extracted and stored
    """
    logger.info(f"Processing document {document_id}")

    try:
        async with db_pool.acquire() as conn:
            # Fetch document
            doc = await conn.fetchrow(
                """
                SELECT id, source_type, source_url, title, meeting_date
                FROM documents
                WHERE id = $1
                """,
                document_id,
            )

            if not doc:
                logger.error(f"Document {document_id} not found")
                return 0

            logger.debug(f"Document found: {doc['title']}")

            # Fetch all chunks for this document
            chunks = await conn.fetch(
                """
                SELECT id, chunk_index, chunk_text, section_header
                FROM document_chunks
                WHERE document_id = $1
                ORDER BY chunk_index ASC
                """,
                document_id,
            )

            if not chunks:
                logger.warning(f"Document {document_id} has no chunks")
                await conn.execute(
                    "UPDATE documents SET processed_at = $1 WHERE id = $2",
                    datetime.now(timezone.utc),
                    document_id,
                )
                return 0

            logger.info(f"Found {len(chunks)} chunks for document {document_id}")

        # Prepare document context
        doc_context = {
            "source_type": doc["source_type"],
            "source_url": doc["source_url"],
            "title": doc["title"],
            "meeting_date": doc["meeting_date"].isoformat() if doc["meeting_date"] else None,
        }

        # Extract signals from each chunk
        total_signals = 0
        extracted_signals_by_chunk = {}

        async def _extract_for_chunk(chunk_row):
            chunk_id = chunk_row["id"]
            chunk_text = chunk_row["chunk_text"]
            logger.debug(f"Extracting signals from chunk {chunk_id}")
            try:
                return await extract_signals_from_chunk(
                    chunk_text,
                    doc_context,
                    api_key,
                )
            except Exception as e:
                logger.error(f"Chunk {chunk_id} extraction failed: {e}")
                return []

        tasks = [_extract_for_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks)

        for chunk_row, signals in zip(chunks, results):
            chunk_id = chunk_row["id"]
            extracted_signals_by_chunk[chunk_id] = signals
            total_signals += len(signals)

        logger.info(f"Extracted {total_signals} total signals from document {document_id}")

        # Store signals in database
        async with db_pool.acquire() as conn:
            for chunk_id, signals in extracted_signals_by_chunk.items():
                for signal in signals:
                    try:
                        # Geocode addresses
                        geom = None
                        if signal.addresses:
                            for addr in signal.addresses:
                                coords = await geocode_address(db_pool, addr)
                                if coords:
                                    lat, lon = coords
                                    geom = f"SRID=4326;POINT({lon} {lat})"
                                    logger.debug(f"Geocoded {addr} to {lat}, {lon}")
                                    break  # Use first successful geocode

                        # DV-REG-002: Determine review status based on confidence
                        review_status = (
                            "auto_approved"
                            if signal.confidence >= confidence_threshold
                            else "pending_review"
                        )

                        # Insert signal into database
                        await conn.execute(
                            """
                            INSERT INTO intelligence_signals (
                                document_id, chunk_id, signal_type, summary, headline,
                                addresses, neighborhood, zoning_from, zoning_to,
                                height_before, height_after, fsr_before, fsr_after,
                                unit_count, project_value_dollars,
                                decision, vote_for, vote_against, conditions,
                                sentiment, severity, confidence, event_date,
                                geom, llm_model, extracted_at, review_status
                            ) VALUES (
                                $1, $2, $3, $4, $5,
                                $6, $7, $8, $9,
                                $10, $11, $12, $13,
                                $14, $15,
                                $16, $17, $18, $19,
                                $20, $21, $22, $23,
                                ST_GeomFromEWKT($24), $25, $26, $27
                            )
                            """,
                            document_id,
                            chunk_id,
                            signal.signal_type.value,
                            signal.summary,
                            signal.headline,
                            signal.addresses,
                            signal.neighborhood,
                            signal.zoning_from,
                            signal.zoning_to,
                            signal.height_before,
                            signal.height_after,
                            signal.fsr_before,
                            signal.fsr_after,
                            signal.unit_count,
                            signal.project_value_dollars,
                            signal.decision.value if signal.decision else None,
                            signal.vote_for,
                            signal.vote_against,
                            signal.conditions,
                            signal.sentiment.value,
                            signal.severity.value,
                            signal.confidence,
                            signal.event_date,
                            geom if geom else "SRID=4326;POINT(0 0)",  # default point if geocoding failed
                            os.environ.get("GEMINI_MODEL", os.environ.get("ANTHROPIC_MODEL", "gemini-2.5-flash")),
                            datetime.now(timezone.utc),
                            review_status,
                        )

                        logger.debug(f"Stored signal: {signal.signal_type} at {signal.addresses}")

                    except Exception as e:
                        logger.error(f"Error storing signal: {e}")
                        continue

            # Update document processed_at timestamp
            await conn.execute(
                "UPDATE documents SET processed_at = $1 WHERE id = $2",
                datetime.now(timezone.utc),
                document_id,
            )

            logger.info(f"Document {document_id} processing complete. {total_signals} signals stored.")

        return total_signals

    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
        return 0


# ──────────────────────────────────────────────────────────────────────────
# BATCH PROCESSING
# ──────────────────────────────────────────────────────────────────────────

async def process_all_unprocessed(
    db_pool: asyncpg.Pool,
    api_key: str,
    batch_size: int = 10,
) -> dict:
    """Process all documents that haven't been processed yet.

    Finds documents where processed_at IS NULL and processes them in batches.

    Args:
        db_pool: asyncpg connection pool
        api_key: Anthropic API key
        batch_size: Number of documents to process in parallel

    Returns:
        Dict with keys: documents_processed, signals_extracted, errors
    """
    logger.info("Starting batch processing of unprocessed documents")

    stats = {
        "documents_processed": 0,
        "signals_extracted": 0,
        "errors": 0,
    }

    try:
        async with db_pool.acquire() as conn:
            # Get all unprocessed documents
            unprocessed = await conn.fetch(
                """
                SELECT id FROM documents
                WHERE processed_at IS NULL
                ORDER BY id ASC
                """
            )

        if not unprocessed:
            logger.info("No unprocessed documents found")
            return stats

        document_ids = [doc["id"] for doc in unprocessed]
        logger.info(f"Found {len(document_ids)} unprocessed documents")

        # Process in batches
        for i in range(0, len(document_ids), batch_size):
            batch = document_ids[i : i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}: documents {batch}")

            # Process batch in parallel
            tasks = [process_document(db_pool, doc_id, api_key) for doc_id in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect stats
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Batch error: {result}")
                    stats["errors"] += 1
                else:
                    stats["documents_processed"] += 1
                    stats["signals_extracted"] += result

            # Small delay between batches to avoid rate limits
            if i + batch_size < len(document_ids):
                await asyncio.sleep(1)

        logger.info(
            f"Batch processing complete: {stats['documents_processed']} documents, "
            f"{stats['signals_extracted']} signals, {stats['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Error in batch processing: {e}", exc_info=True)
        stats["errors"] += 1

    return stats
