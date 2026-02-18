"""SDK resource for FTK dataset onboarding operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    DatasetAnalysisDetails,
    DatasetAnalysisRequest,
    DatasetAnalysisResponse,
    DocumentSummaryResponse,
    EvaluationDetails,
    EvaluationListResponse,
    EvaluationReportResponse,
    EvaluationRequest,
    EvaluationResponse,
    GoldLabelEntry,
    GoldLabelsListResponse,
    GoldLabelsUploadResponse,
    OnboardingStatusResponse,
    SummarizationRequest,
    SummarizationResponse,
    SummarizationStatusResponse,
    SyntheticQueryBatchDetails,
    SyntheticQueryBatchListResponse,
    SyntheticQueryBatchResponse,
    SyntheticQueryGenerationRequest,
)


class OnboardingMixin(RequesterMixin):
    """Mixin providing FTK dataset onboarding operations."""

    # =========================================================================
    # Dataset Analysis
    # =========================================================================

    def start_analysis(
        self,
        corpus_id: str,
        *,
        description: str | None = None,
        auto_bootstrap: bool = True,
        bootstrap_num_samples: int | None = None,
        queries_per_chunk: int | None = None,
    ) -> DatasetAnalysisResponse:
        """Start the dataset analysis pipeline for a corpus.

        Args:
            corpus_id: ID of the corpus to analyze
            description: Optional dataset description for analysis context
            auto_bootstrap: Automatically bootstrap if no gold labels exist
            bootstrap_num_samples: Override bootstrap sample count
            queries_per_chunk: Override queries per chunk

        Returns:
            DatasetAnalysisResponse with analysis_id and job_id
        """
        payload: dict[str, Any] = {"auto_bootstrap": auto_bootstrap}
        if description is not None:
            payload["description"] = description
        if bootstrap_num_samples is not None:
            payload["bootstrap_num_samples"] = bootstrap_num_samples
        if queries_per_chunk is not None:
            payload["queries_per_chunk"] = queries_per_chunk

        data = self._request("POST", f"/v1/corpora/{corpus_id}/onboard:analyze", json=payload)
        return cast("DatasetAnalysisResponse", data)

    def get_onboarding_status(self, corpus_id: str) -> OnboardingStatusResponse:
        """Get current onboarding status for a corpus.

        Args:
            corpus_id: ID of the corpus

        Returns:
            OnboardingStatusResponse with latest analysis and counts
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/onboard/status")
        return cast("OnboardingStatusResponse", data)

    def get_analysis(self, corpus_id: str, analysis_id: str) -> DatasetAnalysisDetails:
        """Get detailed results of an analysis run.

        Args:
            corpus_id: ID of the corpus
            analysis_id: ID of the analysis run

        Returns:
            DatasetAnalysisDetails with full analysis results
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/onboard/analysis/{analysis_id}")
        return cast("DatasetAnalysisDetails", data)

    # =========================================================================
    # Gold Labels
    # =========================================================================

    def upload_gold_labels(
        self,
        corpus_id: str,
        labels: list[GoldLabelEntry],
        *,
        description: str | None = None,
    ) -> GoldLabelsUploadResponse:
        """Upload gold labels for a corpus.

        Args:
            corpus_id: ID of the corpus
            labels: List of gold label entries (query-chunk pairs)
            description: Optional description of the labels source

        Returns:
            GoldLabelsUploadResponse with resolution results
        """
        payload: dict[str, Any] = {"labels": labels}
        if description is not None:
            payload["description"] = description

        data = self._request("POST", f"/v1/corpora/{corpus_id}/onboard:upload-labels", json=payload)
        return cast("GoldLabelsUploadResponse", data)

    def upload_gold_labels_file(
        self,
        corpus_id: str,
        file_path: str | Path,
        *,
        description: str | None = None,
    ) -> GoldLabelsUploadResponse:
        """Upload gold labels from a JSONL file.

        Args:
            corpus_id: ID of the corpus
            file_path: Path to JSONL file with gold labels
            description: Optional description of the labels source

        Returns:
            GoldLabelsUploadResponse with resolution results
        """
        import json

        labels: list[GoldLabelEntry] = []
        with open(file_path, "r") as f:
            for line in f:
                if line.strip():
                    labels.append(json.loads(line))

        return self.upload_gold_labels(corpus_id, labels, description=description)

    def list_gold_labels(
        self,
        corpus_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> GoldLabelsListResponse:
        """List gold labels for a corpus.

        Args:
            corpus_id: ID of the corpus
            limit: Maximum number of labels to return
            offset: Offset for pagination

        Returns:
            GoldLabelsListResponse with labels list
        """
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/gold-labels",
            params={"limit": limit, "offset": offset},
        )
        return cast("GoldLabelsListResponse", data)

    def iter_gold_labels(self, corpus_id: str, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Iterate over gold labels, automatically paginating."""
        return self._paginate(
            "GET",
            f"/v1/corpora/{corpus_id}/gold-labels",
            items_key="labels",
            limit=limit,
        )

    # =========================================================================
    # Synthetic Query Generation
    # =========================================================================

    def generate_synthetic_queries(
        self,
        corpus_id: str,
        analysis_id: str,
        *,
        sample_size: int = 0,
        queries_per_chunk: int = 3,
        use_document_context: bool = True,
        eval_sample_size: int | None = None,
    ) -> SyntheticQueryBatchResponse:
        """Start synthetic query generation.

        Args:
            corpus_id: ID of the corpus
            analysis_id: ID of the analysis run to use
            sample_size: Chunks to sample (0 = all chunks)
            queries_per_chunk: Queries to generate per chunk
            use_document_context: Inject document summaries into prompts
            eval_sample_size: Override eval sample size (None = use default)

        Returns:
            SyntheticQueryBatchResponse with batch_id and job_id
        """
        payload: dict[str, Any] = {
            "analysis_id": analysis_id,
            "sample_size": sample_size,
            "queries_per_chunk": queries_per_chunk,
            "use_document_context": use_document_context,
        }
        if eval_sample_size is not None:
            payload["eval_sample_size"] = eval_sample_size

        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/synthetic-queries:generate",
            json=payload,
        )
        return cast("SyntheticQueryBatchResponse", data)

    def list_synthetic_batches(self, corpus_id: str) -> SyntheticQueryBatchListResponse:
        """List synthetic query batches for a corpus.

        Args:
            corpus_id: ID of the corpus

        Returns:
            SyntheticQueryBatchListResponse with batches list
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/synthetic-queries/batches")
        return cast("SyntheticQueryBatchListResponse", data)

    def get_synthetic_batch(self, corpus_id: str, batch_id: str) -> SyntheticQueryBatchDetails:
        """Get details of a synthetic query batch.

        Args:
            corpus_id: ID of the corpus
            batch_id: ID of the batch

        Returns:
            SyntheticQueryBatchDetails with full batch info
        """
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/synthetic-queries/batches/{batch_id}",
        )
        return cast("SyntheticQueryBatchDetails", data)

    def download_synthetic_queries(
        self,
        corpus_id: str,
        batch_id: str,
        output_path: str | Path,
    ) -> str:
        """Download synthetic queries from a batch.

        Args:
            corpus_id: ID of the corpus
            batch_id: ID of the batch
            output_path: Path to save downloaded queries

        Returns:
            Path to the downloaded file
        """
        # Get batch details to find artifact URI
        batch = self.get_synthetic_batch(corpus_id, batch_id)

        if not batch.get("artifact_uri"):
            raise ValueError("Batch does not have an artifact URI")

        # Download from S3
        # Note: This would need to be implemented with S3 download
        # For now, just return the artifact URI
        return str(batch.get("artifact_uri"))

    # =========================================================================
    # Evaluation
    # =========================================================================

    def evaluate_synthetic_queries(
        self,
        corpus_id: str,
        batch_id: str,
        *,
        sample_size: int | None = None,
        generate_report: bool = True,
        report_formats: list[str] | None = None,
    ) -> EvaluationResponse:
        """Start evaluation of synthetic queries.

        Args:
            corpus_id: ID of the corpus
            batch_id: ID of the synthetic query batch
            sample_size: Sample for evaluation (None = all)
            generate_report: Generate HTML/JSON report
            report_formats: Report formats to generate

        Returns:
            EvaluationResponse with eval_id and job_id
        """
        payload: dict[str, Any] = {
            "batch_id": batch_id,
            "generate_report": generate_report,
        }
        if sample_size is not None:
            payload["sample_size"] = sample_size
        if report_formats is not None:
            payload["report_formats"] = report_formats

        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/synthetic-queries:evaluate",
            json=payload,
        )
        return cast("EvaluationResponse", data)

    def list_evaluations(self, corpus_id: str) -> EvaluationListResponse:
        """List evaluations for a corpus.

        Args:
            corpus_id: ID of the corpus

        Returns:
            EvaluationListResponse with evaluations list
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/evaluations")
        return cast("EvaluationListResponse", data)

    def get_evaluation(self, corpus_id: str, eval_id: str) -> EvaluationDetails:
        """Get details of an evaluation.

        Args:
            corpus_id: ID of the corpus
            eval_id: ID of the evaluation

        Returns:
            EvaluationDetails with full evaluation results
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/evaluations/{eval_id}")
        return cast("EvaluationDetails", data)

    def get_evaluation_report(
        self,
        corpus_id: str,
        eval_id: str,
        *,
        format: str = "json",
    ) -> EvaluationReportResponse:
        """Get evaluation report.

        Args:
            corpus_id: ID of the corpus
            eval_id: ID of the evaluation
            format: Report format ("json" or "html")

        Returns:
            EvaluationReportResponse with report URI and metrics
        """
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/evaluations/{eval_id}/report",
            params={"format": format},
        )
        return cast("EvaluationReportResponse", data)

    # =========================================================================
    # Document Summarization
    # =========================================================================

    def summarize_documents(
        self,
        corpus_id: str,
        *,
        force_regenerate: bool = False,
    ) -> SummarizationResponse:
        """Start document summarization.

        Args:
            corpus_id: ID of the corpus
            force_regenerate: Regenerate summaries for all documents

        Returns:
            SummarizationResponse with job_id and stats
        """
        payload: dict[str, Any] = {"force_regenerate": force_regenerate}
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/documents:summarize",
            json=payload,
        )
        return cast("SummarizationResponse", data)

    def get_summarization_status(self, corpus_id: str) -> SummarizationStatusResponse:
        """Get summarization status for a corpus.

        Args:
            corpus_id: ID of the corpus

        Returns:
            SummarizationStatusResponse with coverage stats
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/summaries/status")
        return cast("SummarizationStatusResponse", data)

    def get_document_summary(self, corpus_id: str, doc_id: str) -> DocumentSummaryResponse:
        """Get summary for a specific document.

        Args:
            corpus_id: ID of the corpus
            doc_id: ID of the document

        Returns:
            DocumentSummaryResponse with summary and entities
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/documents/{doc_id}/summary")
        return cast("DocumentSummaryResponse", data)
