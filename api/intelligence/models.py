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
    addresses: list[str] = []
    neighborhood: Optional[str] = None
    decision: Optional[str] = None
    vote_for: Optional[int] = None
    vote_against: Optional[int] = None
    sentiment: Optional[str] = None
    severity: str = "info"
    confidence: float = 0.5
    event_date: Optional[date] = None
    # Source info (joined)
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    source_date: Optional[date] = None


# ── Chat models ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Chat request with input validation (SEC-007 / VCL-17)."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Chat query (max 2000 characters)",
    )
    session_id: Optional[str] = None
    neighborhood_filter: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    @classmethod
    def __get_validators__(cls):
        yield from super().__get_validators__()

    def model_post_init(self, __context) -> None:
        """Strip whitespace from query after validation."""
        object.__setattr__(self, 'query', self.query.strip())


class SourceCitation(BaseModel):
    document_title: str
    document_url: str
    source_type: str
    published_date: Optional[date] = None
    relevance_score: float
    excerpt: str  # the chunk text that was used
    # RAG-005: Provenance chain fields
    document_id: Optional[int] = None
    chunk_id: Optional[int] = None
    url_status: Optional[str] = None
    archive_url: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[SourceCitation] = Field(default_factory=list)
    related_signals: list[SignalResponse] = Field(default_factory=list)
    session_id: str
    mode: str = Field(default="full", description="Operating mode: full, partial, or demo")


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


# ── Neighborhood Scorecard models ─────────────────────────────

class MetricCategory(str, Enum):
    SAFETY = "safety"
    SCHOOLS = "schools"
    TRANSIT = "transit"
    PARKS = "parks"
    DEVELOPMENT = "development"
    AIR_QUALITY = "air_quality"
    AFFORDABILITY = "affordability"
    WALKABILITY = "walkability"


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class NeighborhoodBase(BaseModel):
    name: str
    slug: str


class CategoryScore(BaseModel):
    """Score for a single dimension (e.g., safety, schools)."""
    category: MetricCategory
    score: float = Field(ge=0.0, le=10.0)
    raw_value: Optional[float] = None
    percentile: Optional[float] = None
    trend: TrendDirection = TrendDirection.STABLE
    trend_delta: Optional[float] = None


class NeighborhoodScorecard(BaseModel):
    """Full scorecard for a single neighborhood (Madlan-style)."""
    neighborhood: NeighborhoodBase
    overall_score: float = Field(ge=0.0, le=10.0)
    rank: Optional[int] = None
    category_scores: list[CategoryScore] = Field(default_factory=list)
    # Contextual stats from intelligence layer
    active_rezonings: int = 0
    recent_permits: int = 0


class NeighborhoodSummary(BaseModel):
    """Compact summary for list/map views."""
    name: str
    slug: str
    overall_score: float = Field(ge=0.0, le=10.0)
    rank: Optional[int] = None
    top_category: Optional[str] = None
    bottom_category: Optional[str] = None


class NeighborhoodComparison(BaseModel):
    """Side-by-side comparison of 2-3 neighborhoods."""
    neighborhoods: list[NeighborhoodScorecard]
    categories: list[MetricCategory]


class MetricIngestion(BaseModel):
    """Model for ingesting raw metrics from open data."""
    neighborhood_name: str
    category: MetricCategory
    metric_name: str
    metric_value: float
    period_start: date
    period_end: date
    source_name: str
    source_url: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


# ── Chat Session Management models ───────────────────────────

# ── URL Ingestion models ──────────────────────────────────────

class DocumentViewResponse(BaseModel):
    """RAG-001: Archived document viewer response."""
    id: int
    title: Optional[str] = None
    source_url: str
    source_type: str
    published_date: Optional[date] = None
    raw_text: str
    text_length: int = 0
    page_count: int = 0
    url_status: Optional[str] = None
    archive_url: Optional[str] = None


class SearchConfigRequest(BaseModel):
    """RAG-007: Search configuration update request."""
    vector_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    text_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rrf_k: Optional[int] = Field(default=None, ge=1, le=200)
    rerank_enabled: Optional[bool] = None


class SearchConfigResponse(BaseModel):
    """RAG-007: Search configuration response."""
    vector_weight: float
    text_weight: float
    rrf_k: int
    rerank_enabled: bool
    updated_at: Optional[datetime] = None


class DocumentStatusResponse(BaseModel):
    """RAG-011: Document processing status for polling."""
    document_id: int
    title: Optional[str] = None
    status: str = Field(description="'pending', 'processing', 'completed', or 'failed'")
    has_raw_text: bool = False
    chunk_count: int = 0
    signal_count: int = 0
    scraped_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class IngestUrlRequest(BaseModel):
    """Request body for URL document ingestion."""
    url: str = Field(..., min_length=10, max_length=2048, description="URL to download and analyze")
    source_type: str = Field(default="external", description="Document source type")
    title: Optional[str] = Field(default=None, max_length=500, description="Optional title override")


class IngestUrlResponse(BaseModel):
    """Response from URL document ingestion."""
    document_id: int
    title: Optional[str] = None
    text_length: int = 0
    page_count: int = 0
    status: str = Field(description="'new' if freshly ingested, 'exists' if already in DB")
    processing: bool = Field(default=False, description="True if background processing was triggered")


# ── Chat Session Management models ───────────────────────────

class ChatHistoryMessage(BaseModel):
    """A single message in chat history."""
    id: int
    role: str  # 'user' or 'assistant'
    content: str
    source_chunks: list[int] = Field(default_factory=list)
    source_signals: list[int] = Field(default_factory=list)
    created_at: datetime


class ChatMessageHistory(BaseModel):
    """Full conversation history for a session."""
    session_id: str
    messages: list[ChatHistoryMessage] = Field(default_factory=list)


class ChatSession(BaseModel):
    """Chat session metadata."""
    id: int
    session_id: str
    user_label: str
    created_at: datetime
    message_count: int = 0
    last_message_at: Optional[datetime] = None


class ChatSessionList(BaseModel):
    """Paginated list of chat sessions."""
    sessions: list[ChatSession] = Field(default_factory=list)
    total_count: int
    has_more: bool
