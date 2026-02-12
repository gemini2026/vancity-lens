"""SDK types for FTK dataset onboarding."""

from __future__ import annotations

try:  # Python 3.11+
    from typing import NotRequired, TypedDict
except ImportError:  # pragma: no cover - Python < 3.11
    from typing_extensions import NotRequired, TypedDict

# =============================================================================
# Gold Labels
# =============================================================================


class GoldLabelDocumentReference(TypedDict, total=False):
    """Reference to a document for gold label resolution."""

    type: str  # "filename" | "document_id" | "text_match"
    value: str


class GoldLabelChunkReference(TypedDict, total=False):
    """Reference to a chunk within a document."""

    type: str  # "line_range" | "text_excerpt" | "chunk_index" | "offset_range"
    value: str | int | dict


class GoldLabelEntry(TypedDict, total=False):
    """A single gold label entry (query-chunk pair)."""

    query: str
    document_reference: NotRequired[GoldLabelDocumentReference]
    chunk_reference: NotRequired[GoldLabelChunkReference]
    relevant_text: NotRequired[str]
    metadata: NotRequired[dict]


class GoldLabelsUploadRequest(TypedDict, total=False):
    """Request to upload gold labels for a corpus."""

    labels: list[GoldLabelEntry]
    description: NotRequired[str]


class ResolvedLabelInfo(TypedDict):
    """Information about a resolved gold label."""

    label_id: str
    query: str
    chunk_id: str | None
    document_id: str | None
    confidence: float
    resolution_method: str


class GoldLabelsUploadResponse(TypedDict):
    """Response after uploading gold labels."""

    corpus_id: str
    total_uploaded: int
    resolved_count: int
    unmatched_count: int
    labels: list[ResolvedLabelInfo]


class GoldLabelListItem(TypedDict):
    """Gold label item for listing."""

    id: str
    query: str
    chunk_id: str | None
    document_id: str | None
    source: str | None
    confidence: float | None
    created_at: str


class GoldLabelsListResponse(TypedDict):
    """Response listing gold labels for a corpus."""

    corpus_id: str
    total: int
    labels: list[GoldLabelListItem]


# =============================================================================
# Dataset Analysis
# =============================================================================


class DatasetAnalysisRequest(TypedDict, total=False):
    """Request to start dataset analysis pipeline."""

    description: NotRequired[str]
    auto_bootstrap: NotRequired[bool]
    bootstrap_num_samples: NotRequired[int]
    queries_per_chunk: NotRequired[int]


class DatasetAnalysisResponse(TypedDict):
    """Response after starting dataset analysis."""

    analysis_id: str
    corpus_id: str
    status: str
    job_id: str | None
    estimated_duration_seconds: int | None
    created_at: str


class DatasetAnalysisSummary(TypedDict):
    """Summary of a dataset analysis run."""

    analysis_id: str
    status: str
    current_stage: str | None
    stages_completed: list[str]
    has_prompt: bool
    has_evaluation: bool
    bootstrap_enabled: bool
    bootstrap_labels_count: int | None
    documents_at_analysis: int | None
    created_at: str
    completed_at: str | None
    error_message: str | None
    domain: str | None
    lexical_strategy: str | None
    quality_score: float | None


class OnboardingStatusResponse(TypedDict):
    """Response showing onboarding status for a corpus."""

    corpus_id: str
    latest_analysis: DatasetAnalysisSummary | None
    gold_labels_count: int
    synthetic_batches_count: int
    has_summaries: bool
    analysis_stale: bool


class SearcherPersona(TypedDict):
    """Searcher persona from Stage 1 analysis."""

    who: str
    goal: str
    knowledge_state: str


class LexicalStrategy(TypedDict):
    """Lexical strategy recommendation."""

    recommendation: str
    rationale: str
    techniques: list[str]


class DatasetAnalysisDetails(TypedDict):
    """Detailed results of a dataset analysis run."""

    analysis_id: str
    corpus_id: str
    status: str
    created_at: str
    completed_at: str | None
    config: dict
    schema_analysis: dict | None
    domain: str | None
    expertise_level: str | None
    data_relationship: str | None
    searcher_persona: SearcherPersona | None
    lexical_strategy: LexicalStrategy | None
    stage1_analysis: dict | None
    artifact_uri: str | None
    prompt_uri: str | None
    bootstrap_enabled: bool
    bootstrap_labels_count: int | None
    error_message: str | None


# =============================================================================
# Synthetic Query Generation
# =============================================================================


class SyntheticQueryGenerationRequest(TypedDict, total=False):
    """Request to generate synthetic queries."""

    analysis_id: str
    sample_size: NotRequired[int]
    queries_per_chunk: NotRequired[int]
    use_document_context: NotRequired[bool]
    eval_sample_size: NotRequired[int]


class SyntheticQueryBatchResponse(TypedDict):
    """Response after starting synthetic query generation."""

    batch_id: str
    corpus_id: str
    analysis_id: str
    status: str
    job_id: str | None
    sample_size: int | None
    queries_per_chunk: int
    estimated_queries: int | None
    created_at: str


class SyntheticQueryBatchSummary(TypedDict):
    """Summary of a synthetic query batch."""

    batch_id: str
    status: str
    sample_size: int | None
    queries_per_chunk: int
    total_chunks_processed: int | None
    total_queries_generated: int | None
    created_at: str
    completed_at: str | None


class SyntheticQueryBatchListResponse(TypedDict):
    """Response listing synthetic query batches."""

    corpus_id: str
    batches: list[SyntheticQueryBatchSummary]


class SyntheticQuerySample(TypedDict):
    """Sample synthetic query for preview."""

    chunk_id: str
    chunk_text_preview: str
    queries: list[str]


class SyntheticQueryBatchDetails(TypedDict):
    """Detailed information about a synthetic query batch."""

    batch_id: str
    corpus_id: str
    analysis_id: str
    status: str
    created_at: str
    completed_at: str | None
    sample_size: int | None
    queries_per_chunk: int
    use_document_context: bool
    config: dict
    total_chunks_processed: int | None
    total_queries_generated: int | None
    stats: dict
    artifact_uri: str | None
    sample_queries: list[SyntheticQuerySample]
    error_message: str | None


# =============================================================================
# Evaluation
# =============================================================================


class EvaluationRequest(TypedDict, total=False):
    """Request to evaluate synthetic queries."""

    batch_id: str
    sample_size: NotRequired[int]
    generate_report: NotRequired[bool]
    report_formats: NotRequired[list[str]]


class EvaluationResponse(TypedDict):
    """Response after starting evaluation."""

    eval_id: str
    corpus_id: str
    batch_id: str
    status: str
    job_id: str | None
    created_at: str


class EvaluationMetrics(TypedDict, total=False):
    """Aggregated evaluation metrics."""

    total_evaluated: int
    avg_relevance: NotRequired[float]
    avg_groundedness: NotRequired[float]
    avg_style: NotRequired[float]
    avg_lexical_diversity: NotRequired[float]
    pass_rate: NotRequired[float]
    score_distribution: NotRequired[dict]


class EvaluationSummary(TypedDict):
    """Summary of an evaluation run."""

    eval_id: str
    batch_id: str
    status: str
    sample_size: int | None
    metrics: EvaluationMetrics | None
    created_at: str
    completed_at: str | None


class EvaluationListResponse(TypedDict):
    """Response listing evaluations for a corpus."""

    corpus_id: str
    evaluations: list[EvaluationSummary]


class EvaluationDetails(TypedDict):
    """Detailed evaluation results."""

    eval_id: str
    corpus_id: str
    batch_id: str
    status: str
    created_at: str
    completed_at: str | None
    sample_size: int | None
    config: dict
    metrics: EvaluationMetrics | None
    artifact_uri: str | None
    report_uri: str | None
    sample_results: list[dict]
    error_message: str | None


class EvaluationReportResponse(TypedDict):
    """Response with evaluation report."""

    eval_id: str
    corpus_id: str
    format: str
    report_uri: str | None
    metrics: EvaluationMetrics | None
    recommendations: list[str]


# =============================================================================
# Document Summarization
# =============================================================================


class SummarizationRequest(TypedDict, total=False):
    """Request to generate document summaries."""

    force_regenerate: NotRequired[bool]


class SummarizationResponse(TypedDict):
    """Response after starting summarization."""

    corpus_id: str
    job_id: str | None
    status: str
    total_documents: int
    documents_with_summaries: int
    documents_to_summarize: int
    created_at: str


class SummarizationStatusResponse(TypedDict):
    """Response showing summarization status for a corpus."""

    corpus_id: str
    total_documents: int
    documents_with_summaries: int
    coverage_percent: float
    latest_job_status: str | None
    latest_job_completed_at: str | None


class DocumentSummaryResponse(TypedDict):
    """Response with a document's summary."""

    document_id: str
    corpus_id: str
    summary: str
    document_type: str | None
    entities: dict
    key_facts: list[str]
    generation_model: str | None
    created_at: str
