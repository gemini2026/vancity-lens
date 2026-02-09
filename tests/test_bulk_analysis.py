"""
Tests for bulk parcel analysis (BIZ-015)

Covers:
- Pydantic request/response model validation
- Business logic (scoring, ranking, summary generation)
- FastAPI route structure and endpoint behaviour
- Job lifecycle (create -> process -> complete)
- Edge cases and error conditions

30+ tests organised by concern.
"""

import asyncio
import pathlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Paths used in structural assertions
# ---------------------------------------------------------------------------

API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"


# ---------------------------------------------------------------------------
# Helpers -- lightweight app & auth stub for TestClient usage
# ---------------------------------------------------------------------------

def _make_test_app():
    """Build a minimal FastAPI app with the bulk-analysis router mounted."""
    from api.bulk_analysis_routes import router
    app = FastAPI()
    app.include_router(router)
    return app


def _auth_override():
    """Return a fake user dict, bypassing real JWT/DB auth."""
    return {"id": 1, "email": "test@test.com", "role": "user", "is_active": True}


def _get_client():
    """Return a TestClient with auth dependency overridden."""
    from api.user_auth import get_current_user_from_request
    app = _make_test_app()
    app.dependency_overrides[get_current_user_from_request] = _auth_override
    return TestClient(app)


# ===========================================================================
# 1. Model validation tests
# ===========================================================================


class TestBulkAnalysisRequestValidation:
    """Validate BulkAnalysisRequest Pydantic model."""

    def test_valid_pids_only(self):
        from api.bulk_analysis import BulkAnalysisRequest
        req = BulkAnalysisRequest(pids=["PID-001", "PID-002"])
        assert len(req.pids) == 2
        assert req.addresses == []

    def test_valid_addresses_only(self):
        from api.bulk_analysis import BulkAnalysisRequest
        req = BulkAnalysisRequest(addresses=["123 Main St", "456 Oak Ave"])
        assert len(req.addresses) == 2
        assert req.pids == []

    def test_valid_mixed_pids_and_addresses(self):
        from api.bulk_analysis import BulkAnalysisRequest
        req = BulkAnalysisRequest(pids=["PID-001"], addresses=["123 Main St"])
        assert len(req.pids) == 1
        assert len(req.addresses) == 1

    def test_reject_empty_lists(self):
        from api.bulk_analysis import BulkAnalysisRequest
        with pytest.raises(ValueError, match="At least one"):
            BulkAnalysisRequest(pids=[], addresses=[])

    def test_reject_no_arguments(self):
        from api.bulk_analysis import BulkAnalysisRequest
        with pytest.raises(ValueError, match="At least one"):
            BulkAnalysisRequest()

    def test_reject_too_many_pids(self):
        from api.bulk_analysis import BulkAnalysisRequest
        with pytest.raises(ValueError):
            BulkAnalysisRequest(pids=[f"PID-{i}" for i in range(101)])

    def test_reject_too_many_addresses(self):
        from api.bulk_analysis import BulkAnalysisRequest
        with pytest.raises(ValueError):
            BulkAnalysisRequest(addresses=[f"{i} Elm St" for i in range(101)])

    def test_reject_combined_over_max(self):
        from api.bulk_analysis import BulkAnalysisRequest
        with pytest.raises(ValueError, match="exceeds maximum"):
            BulkAnalysisRequest(
                pids=[f"PID-{i}" for i in range(60)],
                addresses=[f"{i} Elm St" for i in range(50)],
            )

    def test_strips_whitespace(self):
        from api.bulk_analysis import BulkAnalysisRequest
        req = BulkAnalysisRequest(pids=["  PID-001  ", " PID-002 "])
        assert req.pids == ["PID-001", "PID-002"]

    def test_strips_empty_strings(self):
        from api.bulk_analysis import BulkAnalysisRequest
        with pytest.raises(ValueError, match="non-empty"):
            BulkAnalysisRequest(pids=["", "   "])

    def test_strips_empty_mixed(self):
        from api.bulk_analysis import BulkAnalysisRequest
        req = BulkAnalysisRequest(pids=["PID-001", "  ", "PID-002"])
        assert req.pids == ["PID-001", "PID-002"]

    def test_exactly_100_items_accepted(self):
        from api.bulk_analysis import BulkAnalysisRequest
        req = BulkAnalysisRequest(
            pids=[f"PID-{i}" for i in range(50)],
            addresses=[f"{i} Elm St" for i in range(50)],
        )
        assert len(req.pids) + len(req.addresses) == 100

    def test_model_config_uses_configdict(self):
        from api.bulk_analysis import BulkAnalysisRequest
        cfg = BulkAnalysisRequest.model_config
        assert cfg.get("str_strip_whitespace") is True


# ===========================================================================
# 2. ParcelResult model tests
# ===========================================================================


class TestParcelResultModel:
    """Validate the ParcelResult model."""

    def test_create_valid_result(self):
        from api.bulk_analysis import ParcelResult
        r = ParcelResult(
            identifier="PID-001",
            identifier_type="pid",
            deal_score=75.0,
            grade="B",
        )
        assert r.deal_score == 75.0
        assert r.grade == "B"

    def test_deal_score_lower_bound(self):
        from api.bulk_analysis import ParcelResult
        r = ParcelResult(
            identifier="PID-001",
            identifier_type="pid",
            deal_score=0,
            grade="F",
        )
        assert r.deal_score == 0

    def test_deal_score_upper_bound(self):
        from api.bulk_analysis import ParcelResult
        r = ParcelResult(
            identifier="PID-001",
            identifier_type="pid",
            deal_score=100,
            grade="A",
        )
        assert r.deal_score == 100

    def test_deal_score_below_zero_rejected(self):
        from api.bulk_analysis import ParcelResult
        with pytest.raises(ValueError):
            ParcelResult(
                identifier="PID-001",
                identifier_type="pid",
                deal_score=-1,
                grade="F",
            )

    def test_deal_score_above_100_rejected(self):
        from api.bulk_analysis import ParcelResult
        with pytest.raises(ValueError):
            ParcelResult(
                identifier="PID-001",
                identifier_type="pid",
                deal_score=101,
                grade="A",
            )

    def test_optional_fields_default_none(self):
        from api.bulk_analysis import ParcelResult
        r = ParcelResult(
            identifier="PID-001",
            identifier_type="pid",
            deal_score=50.0,
            grade="C",
        )
        assert r.zoning is None
        assert r.lot_area_sqm is None
        assert r.error is None

    def test_serialization_round_trip(self):
        from api.bulk_analysis import ParcelResult
        r = ParcelResult(
            identifier="PID-001",
            identifier_type="pid",
            deal_score=88.5,
            grade="A",
            zoning="RS-1",
        )
        data = r.model_dump()
        restored = ParcelResult(**data)
        assert restored.deal_score == 88.5
        assert restored.zoning == "RS-1"


# ===========================================================================
# 3. BulkAnalysisResult model tests
# ===========================================================================


class TestBulkAnalysisResultModel:
    """Validate the BulkAnalysisResult response model."""

    def test_create_pending_result(self):
        from api.bulk_analysis import BulkAnalysisResult
        r = BulkAnalysisResult(
            job_id="abc-123",
            status="pending",
            total=5,
            completed=0,
        )
        assert r.status == "pending"
        assert r.results == []
        assert r.summary is None

    def test_create_completed_result(self):
        from api.bulk_analysis import BulkAnalysisResult
        r = BulkAnalysisResult(
            job_id="abc-123",
            status="completed",
            total=2,
            completed=2,
            results=[{"deal_score": 80}, {"deal_score": 60}],
            summary={"avg_score": 70.0},
        )
        assert r.status == "completed"
        assert len(r.results) == 2
        assert r.summary is not None


# ===========================================================================
# 4. Helper / scoring function tests
# ===========================================================================


class TestScoringHelpers:
    """Test helper functions in bulk_analysis module."""

    def test_score_to_grade_A(self):
        from api.bulk_analysis import _score_to_grade
        assert _score_to_grade(95) == "A"
        assert _score_to_grade(80) == "A"

    def test_score_to_grade_B(self):
        from api.bulk_analysis import _score_to_grade
        assert _score_to_grade(79) == "B"
        assert _score_to_grade(60) == "B"

    def test_score_to_grade_C(self):
        from api.bulk_analysis import _score_to_grade
        assert _score_to_grade(59) == "C"
        assert _score_to_grade(40) == "C"

    def test_score_to_grade_D(self):
        from api.bulk_analysis import _score_to_grade
        assert _score_to_grade(39) == "D"
        assert _score_to_grade(20) == "D"

    def test_score_to_grade_F(self):
        from api.bulk_analysis import _score_to_grade
        assert _score_to_grade(19) == "F"
        assert _score_to_grade(0) == "F"

    def test_compute_median_odd(self):
        from api.bulk_analysis import _compute_median
        assert _compute_median([1, 3, 5]) == 3

    def test_compute_median_even(self):
        from api.bulk_analysis import _compute_median
        assert _compute_median([1, 3, 5, 7]) == 4.0

    def test_compute_median_single(self):
        from api.bulk_analysis import _compute_median
        assert _compute_median([42]) == 42

    def test_compute_median_empty(self):
        from api.bulk_analysis import _compute_median
        assert _compute_median([]) == 0.0

    def test_mock_score_parcel_deterministic(self):
        from api.bulk_analysis import _mock_score_parcel
        a = _mock_score_parcel("PID-001", "pid")
        b = _mock_score_parcel("PID-001", "pid")
        assert a.deal_score == b.deal_score
        assert a.grade == b.grade

    def test_mock_score_parcel_returns_parcel_result(self):
        from api.bulk_analysis import _mock_score_parcel, ParcelResult
        r = _mock_score_parcel("PID-001", "pid")
        assert isinstance(r, ParcelResult)
        assert r.identifier == "PID-001"
        assert r.identifier_type == "pid"

    def test_mock_score_parcel_score_bounds(self):
        from api.bulk_analysis import _mock_score_parcel
        for i in range(50):
            r = _mock_score_parcel(f"PID-{i}", "pid")
            assert 0 <= r.deal_score <= 100

    def test_generate_summary_all_success(self):
        from api.bulk_analysis import _generate_summary
        results = [
            {"deal_score": 90, "grade": "A", "error": None},
            {"deal_score": 70, "grade": "B", "error": None},
            {"deal_score": 50, "grade": "C", "error": None},
        ]
        summary = _generate_summary(results)
        assert summary["total_analyzed"] == 3
        assert summary["total_errors"] == 0
        assert summary["avg_score"] == pytest.approx(70.0, abs=0.01)
        assert summary["min_score"] == 50
        assert summary["max_score"] == 90

    def test_generate_summary_with_errors(self):
        from api.bulk_analysis import _generate_summary
        results = [
            {"deal_score": 80, "grade": "A", "error": None},
            {"deal_score": 0, "grade": "F", "error": "not found"},
        ]
        summary = _generate_summary(results)
        assert summary["total_analyzed"] == 1
        assert summary["total_errors"] == 1
        assert summary["avg_score"] == 80.0

    def test_generate_summary_all_errors(self):
        from api.bulk_analysis import _generate_summary
        results = [
            {"deal_score": 0, "grade": "F", "error": "not found"},
        ]
        summary = _generate_summary(results)
        assert summary["total_analyzed"] == 0
        assert summary["total_errors"] == 1
        assert summary["avg_score"] == 0.0

    def test_generate_summary_count_by_grade(self):
        from api.bulk_analysis import _generate_summary
        results = [
            {"deal_score": 90, "grade": "A", "error": None},
            {"deal_score": 85, "grade": "A", "error": None},
            {"deal_score": 65, "grade": "B", "error": None},
            {"deal_score": 15, "grade": "F", "error": None},
        ]
        summary = _generate_summary(results)
        assert summary["count_by_grade"]["A"] == 2
        assert summary["count_by_grade"]["B"] == 1
        assert summary["count_by_grade"]["F"] == 1
        assert summary["count_by_grade"]["C"] == 0


# ===========================================================================
# 5. Job lifecycle tests (async)
# ===========================================================================


class TestJobLifecycle:
    """Test create -> process -> retrieve lifecycle."""

    @pytest.fixture(autouse=True)
    def _clear_store(self):
        from api.bulk_analysis import clear_jobs_store
        clear_jobs_store()
        yield
        clear_jobs_store()

    @pytest.mark.asyncio
    async def test_create_job_returns_uuid(self):
        from api.bulk_analysis import BulkAnalysisRequest, create_bulk_analysis_job
        req = BulkAnalysisRequest(pids=["PID-001"])
        job_id = await create_bulk_analysis_job(req)
        assert isinstance(job_id, str)
        assert len(job_id) == 36  # UUID4 format

    @pytest.mark.asyncio
    async def test_create_job_initial_status_pending(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
        )
        req = BulkAnalysisRequest(pids=["PID-001"])
        job_id = await create_bulk_analysis_job(req)
        result = get_job_result(job_id)
        assert result is not None
        assert result.status == "pending"
        assert result.total == 1
        assert result.completed == 0

    @pytest.mark.asyncio
    async def test_process_job_updates_to_completed(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
            process_bulk_analysis_job,
        )
        req = BulkAnalysisRequest(pids=["PID-001", "PID-002"])
        job_id = await create_bulk_analysis_job(req)
        await process_bulk_analysis_job(job_id)
        result = get_job_result(job_id)
        assert result.status == "completed"
        assert result.completed == 2
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_results_ranked_descending_by_deal_score(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
            process_bulk_analysis_job,
        )
        req = BulkAnalysisRequest(
            pids=[f"PID-{i}" for i in range(10)]
        )
        job_id = await create_bulk_analysis_job(req)
        await process_bulk_analysis_job(job_id)
        result = get_job_result(job_id)
        scores = [r["deal_score"] for r in result.results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_process_job_generates_summary(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
            process_bulk_analysis_job,
        )
        req = BulkAnalysisRequest(pids=["PID-001", "PID-002", "PID-003"])
        job_id = await create_bulk_analysis_job(req)
        await process_bulk_analysis_job(job_id)
        result = get_job_result(job_id)
        assert result.summary is not None
        assert "avg_score" in result.summary
        assert "count_by_grade" in result.summary
        assert "total_analyzed" in result.summary

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_returns_none(self):
        from api.bulk_analysis import get_job_result
        assert get_job_result("nonexistent-job-id") is None

    @pytest.mark.asyncio
    async def test_process_nonexistent_job_no_crash(self):
        from api.bulk_analysis import process_bulk_analysis_job
        # Should log an error but not raise
        await process_bulk_analysis_job("nonexistent-job-id")

    @pytest.mark.asyncio
    async def test_addresses_processed(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
            process_bulk_analysis_job,
        )
        req = BulkAnalysisRequest(addresses=["123 Main St", "456 Oak Ave"])
        job_id = await create_bulk_analysis_job(req)
        await process_bulk_analysis_job(job_id)
        result = get_job_result(job_id)
        assert result.status == "completed"
        assert result.completed == 2
        identifiers = [r["identifier"] for r in result.results]
        assert "123 Main St" in identifiers
        assert "456 Oak Ave" in identifiers

    @pytest.mark.asyncio
    async def test_mixed_pids_and_addresses_processed(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
            process_bulk_analysis_job,
        )
        req = BulkAnalysisRequest(pids=["PID-001"], addresses=["123 Main St"])
        job_id = await create_bulk_analysis_job(req)
        await process_bulk_analysis_job(job_id)
        result = get_job_result(job_id)
        assert result.status == "completed"
        assert result.total == 2
        assert result.completed == 2
        types = {r["identifier_type"] for r in result.results}
        assert types == {"pid", "address"}

    @pytest.mark.asyncio
    async def test_job_has_timestamps(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
        )
        req = BulkAnalysisRequest(pids=["PID-001"])
        job_id = await create_bulk_analysis_job(req)
        result = get_job_result(job_id)
        assert result.created_at is not None
        assert result.updated_at is not None


# ===========================================================================
# 6. Route structure tests
# ===========================================================================


class TestRouteStructure:
    """Verify API route configuration."""

    def test_routes_file_exists(self):
        assert (API_DIR / "bulk_analysis_routes.py").exists()

    def test_business_logic_file_exists(self):
        assert (API_DIR / "bulk_analysis.py").exists()

    def test_router_exists(self):
        from api.bulk_analysis_routes import router
        assert router is not None

    def test_router_prefix(self):
        from api.bulk_analysis_routes import router
        assert router.prefix == "/api/v1"

    def test_router_tags(self):
        from api.bulk_analysis_routes import router
        assert "bulk-analysis" in router.tags

    def test_submit_endpoint_exists(self):
        from api.bulk_analysis_routes import submit_bulk_analysis
        assert callable(submit_bulk_analysis)

    def test_status_endpoint_exists(self):
        from api.bulk_analysis_routes import get_bulk_analysis_status
        assert callable(get_bulk_analysis_status)

    def test_submit_endpoint_has_docstring(self):
        from api.bulk_analysis_routes import submit_bulk_analysis
        assert submit_bulk_analysis.__doc__ is not None
        assert len(submit_bulk_analysis.__doc__) > 0

    def test_status_endpoint_has_docstring(self):
        from api.bulk_analysis_routes import get_bulk_analysis_status
        assert get_bulk_analysis_status.__doc__ is not None
        assert len(get_bulk_analysis_status.__doc__) > 0


# ===========================================================================
# 7. TestClient endpoint integration tests
# ===========================================================================


class TestEndpointIntegration:
    """HTTP-level tests using FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def _clear_store(self):
        from api.bulk_analysis import clear_jobs_store
        clear_jobs_store()
        yield
        clear_jobs_store()

    def test_submit_returns_202(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001"]},
        )
        assert resp.status_code == 202

    def test_submit_returns_job_id(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001"]},
        )
        body = resp.json()
        assert "job_id" in body
        assert isinstance(body["job_id"], str)
        assert len(body["job_id"]) == 36

    def test_submit_returns_status_pending(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001"]},
        )
        body = resp.json()
        assert body["status"] == "pending"

    def test_submit_returns_total_count(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001", "PID-002"], "addresses": ["123 Main St"]},
        )
        body = resp.json()
        assert body["total"] == 3

    def test_submit_empty_body_returns_422(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={},
        )
        assert resp.status_code == 422

    def test_submit_empty_lists_returns_422(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": [], "addresses": []},
        )
        assert resp.status_code == 422

    def test_submit_over_max_returns_422(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": [f"PID-{i}" for i in range(101)]},
        )
        assert resp.status_code == 422

    def test_get_nonexistent_job_returns_404(self):
        client = _get_client()
        resp = client.get("/api/v1/parcels/bulk-analyze/does-not-exist")
        assert resp.status_code == 404

    def test_submit_then_get_returns_result(self):
        client = _get_client()
        # Submit
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001"]},
        )
        job_id = post_resp.json()["job_id"]

        # Retrieve -- background task runs synchronously in TestClient
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["job_id"] == job_id
        assert body["status"] in ("pending", "processing", "completed")

    def test_completed_job_has_results(self):
        """TestClient runs BackgroundTasks synchronously, so job should complete."""
        client = _get_client()
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001", "PID-002"]},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        assert body["status"] == "completed"
        assert len(body["results"]) == 2

    def test_completed_job_results_ranked(self):
        client = _get_client()
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": [f"PID-{i}" for i in range(5)]},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        scores = [r["deal_score"] for r in body["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_completed_job_has_summary(self):
        client = _get_client()
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001", "PID-002", "PID-003"]},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        assert body["summary"] is not None
        assert "avg_score" in body["summary"]
        assert "count_by_grade" in body["summary"]
        assert "total_analyzed" in body["summary"]
        assert "total_errors" in body["summary"]
        assert "min_score" in body["summary"]
        assert "max_score" in body["summary"]
        assert "median_score" in body["summary"]

    def test_submit_addresses_works(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"addresses": ["123 Main St", "456 Oak Ave"]},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 2

    def test_submit_mixed_works(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001"], "addresses": ["123 Main St"]},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 2

    def test_result_identifiers_match_request(self):
        client = _get_client()
        pids = ["PID-AAA", "PID-BBB"]
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": pids},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        result_ids = {r["identifier"] for r in body["results"]}
        assert result_ids == set(pids)

    def test_each_result_has_required_fields(self):
        client = _get_client()
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-001"]},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        for r in body["results"]:
            assert "identifier" in r
            assert "identifier_type" in r
            assert "deal_score" in r
            assert "grade" in r

    def test_grades_are_valid_letters(self):
        client = _get_client()
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": [f"PID-{i}" for i in range(20)]},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        valid_grades = {"A", "B", "C", "D", "F"}
        for r in body["results"]:
            assert r["grade"] in valid_grades


# ===========================================================================
# 8. Edge case tests
# ===========================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.fixture(autouse=True)
    def _clear_store(self):
        from api.bulk_analysis import clear_jobs_store
        clear_jobs_store()
        yield
        clear_jobs_store()

    def test_single_pid(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-ONLY"]},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        assert body["total"] == 1
        assert len(body["results"]) == 1

    def test_duplicate_pids_all_processed(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": ["PID-DUP", "PID-DUP", "PID-DUP"]},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        assert body["total"] == 3
        assert len(body["results"]) == 3

    def test_special_characters_in_address(self):
        client = _get_client()
        resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"addresses": ["1234 O'Brien-Way #501"]},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        assert body["results"][0]["identifier"] == "1234 O'Brien-Way #501"

    @pytest.mark.asyncio
    async def test_concurrent_jobs_isolated(self):
        from api.bulk_analysis import (
            BulkAnalysisRequest,
            create_bulk_analysis_job,
            get_job_result,
            process_bulk_analysis_job,
        )
        req_a = BulkAnalysisRequest(pids=["A-1", "A-2"])
        req_b = BulkAnalysisRequest(pids=["B-1", "B-2", "B-3"])
        job_a = await create_bulk_analysis_job(req_a)
        job_b = await create_bulk_analysis_job(req_b)

        await process_bulk_analysis_job(job_a)
        await process_bulk_analysis_job(job_b)

        result_a = get_job_result(job_a)
        result_b = get_job_result(job_b)

        assert result_a.total == 2
        assert result_b.total == 3
        assert result_a.job_id != result_b.job_id

    def test_summary_median_score_in_range(self):
        client = _get_client()
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": [f"PID-{i}" for i in range(10)]},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        summary = body["summary"]
        assert summary["min_score"] <= summary["median_score"] <= summary["max_score"]

    def test_summary_avg_score_in_range(self):
        client = _get_client()
        post_resp = client.post(
            "/api/v1/parcels/bulk-analyze",
            json={"pids": [f"PID-{i}" for i in range(10)]},
        )
        job_id = post_resp.json()["job_id"]
        get_resp = client.get(f"/api/v1/parcels/bulk-analyze/{job_id}")
        body = get_resp.json()
        summary = body["summary"]
        assert summary["min_score"] <= summary["avg_score"] <= summary["max_score"]
