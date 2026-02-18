"""Prompts and patterns for LLM-based regulatory change extraction."""

import re

CHANGE_EXTRACTION_PROMPT = """You are a regulatory change analyst for Vancouver real estate development.

Extract structured regulatory change information from the provided document chunk.

Return a JSON object with these exact fields:
{
  "change_type": "bylaw_amendment | policy_update | council_vote | public_hearing | plan_amendment | other",
  "geographic_scope": "citywide | neighbourhood | district | site_specific",
  "affected_areas": ["List of neighbourhood/area names if geographic_scope is neighbourhood/district/site_specific"],
  "entitlement_change": {
    "field": "max_fsr | max_height | permitted_uses | setback | parking_requirements | other",
    "before_value": "Previous value or null if not mentioned",
    "after_value": "New value or null if not mentioned"
  },
  "plain_english_summary": "1-2 sentence summary of the change and its development implications",
  "confidence": 0.0-1.0 (your confidence in this extraction)
}

Rules:
- If no clear entitlement change is mentioned, set entitlement_change to empty object {}
- For geographic_scope, prefer the most specific level mentioned
- affected_areas should use official neighbourhood names when possible
- confidence should reflect data quality, specificity, and clarity
- Be conservative with confidence: prefer 0.7-0.85 for typical documents
- Only use confidence > 0.9 when all fields are explicitly stated

Examples:

Input: "City Council approved bylaw amendment 12345 increasing FSR from 3.0 to 5.0 in Downtown"
Output:
{
  "change_type": "bylaw_amendment",
  "geographic_scope": "neighbourhood",
  "affected_areas": ["Downtown"],
  "entitlement_change": {
    "field": "max_fsr",
    "before_value": "3.0",
    "after_value": "5.0"
  },
  "plain_english_summary": "Downtown FSR increased from 3.0 to 5.0, enabling larger developments.",
  "confidence": 0.95
}

Input: "A public hearing is scheduled to discuss potential zoning changes in Kitsilano"
Output:
{
  "change_type": "public_hearing",
  "geographic_scope": "neighbourhood",
  "affected_areas": ["Kitsilano"],
  "entitlement_change": {},
  "plain_english_summary": "Public hearing scheduled for potential Kitsilano zoning changes; specific changes TBD.",
  "confidence": 0.75
}
"""

# Patterns that suggest regulatory/zoning content (case-insensitive)
CHANGE_CANDIDATE_PATTERNS = [
    re.compile(r"\bbylaw\b", re.IGNORECASE),
    re.compile(r"\bzoning\b", re.IGNORECASE),
    re.compile(r"\brezoning\b", re.IGNORECASE),
    re.compile(r"\bFSR\b"),
    re.compile(r"\bfloor\s+space\s+ratio\b", re.IGNORECASE),
    re.compile(r"\bheight\s+limit\b", re.IGNORECASE),
    re.compile(r"\bcouncil\s+(vote|approved|decision)\b", re.IGNORECASE),
    re.compile(r"\bpublic\s+hearing\b", re.IGNORECASE),
    re.compile(r"\bofficial\s+community\s+plan\b", re.IGNORECASE),
    re.compile(r"\bOCP\b"),
    re.compile(r"\bpermitted\s+use", re.IGNORECASE),
    re.compile(r"\bdensity\s+bonus\b", re.IGNORECASE),
    re.compile(r"\bsetback\b", re.IGNORECASE),
    re.compile(r"\bparking\s+requirement", re.IGNORECASE),
    re.compile(r"\bsite\s+coverage\b", re.IGNORECASE),
    re.compile(r"\bamendment\b.*\bzoning\b", re.IGNORECASE),
    re.compile(r"\bRS-\d+\b"),  # Zoning districts like RS-1
    re.compile(r"\bRM-\d+\b"),
    re.compile(r"\bC-\d+\b"),
    re.compile(r"\bI-\d+\b"),
]
