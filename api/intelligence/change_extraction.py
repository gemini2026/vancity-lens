"""LLM-powered extraction pipeline for regulatory changes."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from .change_prompts import CHANGE_CANDIDATE_PATTERNS, CHANGE_EXTRACTION_PROMPT
from .llm_backend import generate_chat

logger = logging.getLogger(__name__)


def is_candidate_chunk(text: str) -> bool:
    """Check if text chunk is likely to contain regulatory change information.

    Args:
        text: Document chunk text

    Returns:
        True if text matches any candidate patterns
    """
    if not text or len(text.strip()) < 50:
        return False

    for pattern in CHANGE_CANDIDATE_PATTERNS:
        if pattern.search(text):
            return True

    return False


def parse_extraction_response(answer_text: str) -> dict[str, Any]:
    """Parse and validate LLM extraction response.

    Args:
        answer_text: JSON string from LLM

    Returns:
        Validated dictionary with change record fields including:
        - All fields from LLM response
        - nlp_confidence_score: confidence value
        - requires_manual_review: bool (True if confidence < 0.85)

    Raises:
        ValueError: If JSON is invalid or missing required fields
    """
    try:
        data = json.loads(answer_text.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}")

    # Validate required fields
    required = ["change_type", "geographic_scope", "affected_areas",
                "entitlement_change", "plain_english_summary", "confidence"]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    # Extract confidence and determine review flag
    confidence = float(data.get("confidence", 0.0))

    # Build result with renamed fields
    result = {
        "change_type": data["change_type"],
        "geographic_scope": data["geographic_scope"],
        "affected_areas": data["affected_areas"],
        "entitlement_change": data["entitlement_change"],
        "plain_english_summary": data["plain_english_summary"],
        "nlp_confidence_score": confidence,
        "requires_manual_review": confidence < 0.85,
    }

    return result


async def extract_regulatory_change(
    chunk_text: str,
    source_url: str,
    source_title: str,
    max_tokens: int = 1000,
) -> dict[str, Any]:
    """Extract structured regulatory change from document chunk using LLM.

    Args:
        chunk_text: Text content to analyze
        source_url: Source document URL
        source_title: Source document title
        max_tokens: Max tokens for LLM response

    Returns:
        Dictionary with extracted fields plus metadata:
        - change_type, geographic_scope, affected_areas, entitlement_change,
          plain_english_summary, nlp_confidence_score, requires_manual_review
        - source_url, source_document_title
        - extraction_model, extraction_latency_ms

    Raises:
        ValueError: If extraction fails or response is invalid
    """
    if not is_candidate_chunk(chunk_text):
        raise ValueError("Text chunk does not appear to contain regulatory content")

    # Truncate chunk if too long (leave room for prompt + response)
    max_chunk_chars = 4000
    if len(chunk_text) > max_chunk_chars:
        chunk_text = chunk_text[:max_chunk_chars] + "..."
        logger.info("Truncated chunk to %d chars", max_chunk_chars)

    user_message = f"""Document title: {source_title}
Source URL: {source_url}

Text to analyze:
{chunk_text}
"""

    # Call LLM backend
    answer_text, model_used, latency = await generate_chat(
        system_prompt=CHANGE_EXTRACTION_PROMPT,
        user_message=user_message,
        max_tokens=max_tokens,
    )

    # Parse and validate response
    result = parse_extraction_response(answer_text)

    # Add metadata
    result["source_url"] = source_url
    result["source_document_title"] = source_title
    result["extraction_model"] = model_used
    result["extraction_latency_ms"] = int(latency * 1000)

    logger.info(
        "Extracted change: type=%s scope=%s confidence=%.2f review=%s model=%s latency=%dms",
        result["change_type"],
        result["geographic_scope"],
        result["nlp_confidence_score"],
        result["requires_manual_review"],
        model_used,
        result["extraction_latency_ms"],
    )

    return result


async def store_change_record(db_pool, record: dict[str, Any]) -> int:
    """Store change record in database with duplicate check.

    Args:
        db_pool: asyncpg connection pool
        record: Change record dictionary with fields:
            - change_type, source_url, source_document_title
            - publication_date (optional), effective_date (optional)
            - geographic_scope, affected_areas, entitlement_change
            - plain_english_summary, nlp_confidence_score
            - requires_manual_review

    Returns:
        Record ID (existing or newly inserted)

    Raises:
        ValueError: If required fields are missing
    """
    required = [
        "change_type", "source_url", "source_document_title",
        "geographic_scope", "affected_areas", "entitlement_change",
        "plain_english_summary", "nlp_confidence_score", "requires_manual_review"
    ]
    missing = [f for f in required if f not in record]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    async with db_pool.acquire() as conn:
        # Check for duplicate (same source_url + change_type + summary)
        existing = await conn.fetchval(
            """
            SELECT change_id FROM change_records
            WHERE source_url = $1
              AND change_type = $2
              AND plain_english_summary = $3
            LIMIT 1
            """,
            record["source_url"],
            record["change_type"],
            record["plain_english_summary"],
        )

        if existing:
            logger.info("Duplicate change record found: id=%s", existing)
            return existing

        # Insert new record
        record_id = await conn.fetchval(
            """
            INSERT INTO change_records (
                change_type, source_url, source_document_title,
                publication_date, effective_date,
                geographic_scope, affected_areas, entitlement_change,
                plain_english_summary, nlp_confidence_score,
                requires_manual_review, created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW()
            )
            RETURNING change_id
            """,
            record["change_type"],
            record["source_url"],
            record["source_document_title"],
            record.get("publication_date"),
            record.get("effective_date"),
            record["geographic_scope"],
            json.dumps(record["affected_areas"]),
            json.dumps(record["entitlement_change"]),
            record["plain_english_summary"],
            record["nlp_confidence_score"],
            record["requires_manual_review"],
        )

        logger.info(
            "Stored change record: id=%s type=%s scope=%s review=%s",
            record_id,
            record["change_type"],
            record["geographic_scope"],
            record["requires_manual_review"],
        )

        return record_id
