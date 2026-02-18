"""
VanCity Lens — Municipal Bylaw Amendment Detection

Detects bylaw amendments from ingested documents using keyword matching
and structured pattern recognition. Operates as a lightweight alternative
to full K2 RAG search for bylaw change detection.

Signal type: 'bylaw_amendment'
"""

import logging
import re
from datetime import datetime
from typing import Dict, List

import asyncpg

logger = logging.getLogger(__name__)

# Bylaw amendment patterns in document text
BYLAW_PATTERNS = [
    # Explicit bylaw references
    r"(?i)bylaw\s+(?:no\.?\s*)?(\d{4,5})",
    r"(?i)by-law\s+(?:no\.?\s*)?(\d{4,5})",
    # Amendment language
    r"(?i)(?:amend|repeal|enact|adopt)(?:s|ed|ing)?\s+(?:the\s+)?(?:zoning|land\s+use|development)\s+bylaw",
    # Specific Vancouver bylaw types
    r"(?i)zoning\s+and\s+development\s+bylaw",
    r"(?i)official\s+development\s+plan",
    r"(?i)(?:first|second|third)\s+reading",
    # Regulatory change signals
    r"(?i)(?:public\s+hearing|council\s+(?:vote|decision|approval))\s+(?:on|for|regarding)\s+(?:bylaw|rezoning|amendment)",
]

# Compiled patterns for performance
COMPILED_PATTERNS = [re.compile(p) for p in BYLAW_PATTERNS]

# Zoning change patterns
ZONING_CHANGE_PATTERN = re.compile(
    r"(?i)(?:rezone|rezoning|reclassif)\w*\s+"
    r"(?:from\s+)?([A-Z]{1,4}-?\d{0,2}[A-Z]?)"
    r"\s+to\s+([A-Z]{1,4}-?\d{0,2}[A-Z]?)"
)


def detect_bylaw_references(text: str) -> List[dict]:
    """
    Scan text for bylaw amendment references.

    Returns list of detected references with pattern match details.
    """
    references = []
    for i, pattern in enumerate(COMPILED_PATTERNS):
        matches = pattern.finditer(text)
        for match in matches:
            # Extract context (100 chars before and after)
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            references.append(
                {
                    "pattern_index": i,
                    "match_text": match.group(),
                    "bylaw_number": match.group(1) if match.lastindex else None,
                    "context": context,
                    "position": match.start(),
                }
            )

    return references


def detect_zoning_changes(text: str) -> List[dict]:
    """Detect zoning change references (from X to Y)."""
    changes = []
    for match in ZONING_CHANGE_PATTERN.finditer(text):
        changes.append(
            {
                "zoning_from": match.group(1),
                "zoning_to": match.group(2),
                "context": text[max(0, match.start() - 50) : match.end() + 50].strip(),
            }
        )
    return changes


async def scan_documents_for_bylaws(
    db_pool: asyncpg.Pool,
    days_back: int = 30,
    limit: int = 100,
) -> Dict[str, int]:
    """
    Scan recently ingested documents for bylaw amendment references.

    Creates 'bylaw_amendment' signals for detected references.
    """
    stats = {"documents_scanned": 0, "signals_created": 0, "errors": 0}

    async with db_pool.acquire() as conn:
        # Get recent documents not yet scanned for bylaws
        docs = await conn.fetch(
            """
            SELECT d.id, d.title, d.raw_text, d.source_type, d.source_url
            FROM documents d
            WHERE d.created_at >= NOW() - INTERVAL '%s days'
              AND d.raw_text IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM intelligence_signals s
                  WHERE s.document_id = d.id AND s.signal_type = 'bylaw_amendment'
              )
            ORDER BY d.created_at DESC
            LIMIT %s
        """
            % (days_back, limit)
        )

        stats["documents_scanned"] = len(docs)

        for doc in docs:
            try:
                text = doc["raw_text"] or ""
                if len(text) < 50:
                    continue

                references = detect_bylaw_references(text)
                if not references:
                    continue

                zoning_changes = detect_zoning_changes(text)

                # Create a bylaw_amendment signal
                summary_parts = [
                    f"Bylaw reference: {r['match_text']}" for r in references[:3]
                ]
                summary = "; ".join(summary_parts)
                if len(summary) > 500:
                    summary = summary[:497] + "..."

                zoning_from = (
                    zoning_changes[0]["zoning_from"] if zoning_changes else None
                )
                zoning_to = zoning_changes[0]["zoning_to"] if zoning_changes else None

                # Determine confidence based on number of matches
                confidence = min(0.5 + len(references) * 0.1, 0.95)

                review_status = (
                    "auto_approved" if confidence >= 0.85 else "pending_review"
                )

                await conn.execute(
                    """
                    INSERT INTO intelligence_signals (
                        document_id, signal_type, summary, headline,
                        zoning_from, zoning_to,
                        severity, confidence, review_status,
                        extracted_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT DO NOTHING
                """,
                    doc["id"],
                    "bylaw_amendment",
                    summary,
                    f"Bylaw amendment detected in: {doc['title'][:100]}"
                    if doc["title"]
                    else "Bylaw amendment detected",
                    zoning_from,
                    zoning_to,
                    "medium",
                    confidence,
                    review_status,
                    datetime.now(),
                )
                stats["signals_created"] += 1

            except Exception as e:
                logger.error("Error scanning document %d for bylaws: %s", doc["id"], e)
                stats["errors"] += 1

    logger.info("Bylaw scan complete: %s", stats)
    return stats
