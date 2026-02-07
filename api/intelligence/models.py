"""Pydantic models for the intelligence layer."""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    COUNCIL_MINUTES = "council_minutes"
    REZONING_REPORT = "rezoning_report"
    DPB_MINUTES = "dpb_minutes"
    COURT_RULING = "court_ruling"
    COMMUNITY_PLAN = "community_plan"
    STAFF_REPORT = "staff_report"
    PUBLIC_HEARING = "public_hearing"


class SignalType(str, Enum):
    REZONING_DECISION = "rezoning_decision"
    PERMIT_APPROVAL = "permit_approval"
    POLICY_CHANGE = "policy_change"
    INFRASTRUCTURE = "infrastructure_announcement"
    LEGAL_PRECEDENT = "legal_precedent"
    COMMUNITY_OPPOSITION = "community_opposition"
    DENSITY_CHANGE = "density_change"
    LAND_SALE = "land_sale"
    OTHER = "other"


class Decision(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    DEFERRED = "deferred"
    REFERRED = "referred"
    PENDING = "pending"
    UNKNOWN = "unknown"


class Sentiment(str, Enum):
    POSITIVE = "positive_for_development"
    NEGATIVE = "negative_for_development"
    NEUTRAL = "neutral"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Document models ──────────────────────────────────────────

class DocumentCreate(BaseModel):
    source_type: SourceType
    source_url: str
    title: Optional[str] = None
    published_date: Optional[date] = None
    meeting_date: Optional[date] = None
    raw_text: Optional[str] = None
    text_length: Optional[int] = None
    page_count: Optional[int] = None
    file_format: str = "html"
    metadata: dict = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    id: int
    source_type: str
    source_url: str
    title: Optional[str] = None
    published_date: Optional[date] = None
    meeting_date: Optional[date] = None
    text_length: Optional[int] = None
    page_count: Optional[int] = None
    file_format: str
    metadata: dict
    processed_at: Optional[datetime] = None
    scraped_at: datetime


# ── Intelligence Signal models ───────────────────────────────

class ExtractedSignal(BaseModel):
    """What the LLM outputs for each chunk it processes."""
    signal_type: SignalType
    summary: str
    headline: Optional[str] = None
    addresses: list[str] = Field(default_factory=list)
    neighborhood: Optional[str] = None
    zoning_from: Optional[str] = None
    zoning_to: Optional[str] = None
    height_before: Optional[float] = None
    height_after: Optional[float] = None
    fsr_before: Optional[float] = None
    fsr_after: Optional[float] = None
    unit_count: Optional[int] = None
    project_value_dollars: Optional[float] = None
    decision: Optional[Decision] = None
    vote_for: Optional[int] = None
    vote_against: Optional[int] = None
    conditions: list[str] = Field(default_factory=list)
    sentiment: Sentiment = Sentiment.NEUTRAL
    severity: Severity = Severity.INFO
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    event_date: Optional[date] = None


class SignalResponse(BaseModel):
    id: int
    document_id: int
    signal_type: str
    summary: str
    headline: Optional[str] = None
    addresses: list[str]
    neighborhood: Optional[str] = None
    decision: Optional[str] = None
    vote_for: Optional[int] = None
    vote_against: Optional[int] = None
    sentiment: str
    severity: str
    confidence: float
    event_date: Optional[date] = None
    # Source info (joined)
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    source_date: Optional[date] = None


# ── Chat models ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    neighborhood_filter: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class SourceCitation(BaseModel):
    document_title: str
    document_url: str
    source_type: str
    published_date: Optional[date] = None
    relevance_score: float
    excerpt: str  # the chunk text that was used


class ChatResponse(BaseModel):
    answer: str
    citations: list[SourceCitation] = Field(default_factory=list)
    related_signals: list[SignalResponse] = Field(default_factory=list)
    session_id: str


# ── Feed / Alert models ─────────────────────────────────────

class SignalFeedRequest(BaseModel):
    neighborhood: Optional[str] = None
    signal_type: Optional[SignalType] = None
    severity_min: Optional[Severity] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    limit: int = Field(default=20, le=100)
    offset: int = 0


class SignalFeedResponse(BaseModel):
    signals: list[SignalResponse]
    total_count: int
    has_more: bool
