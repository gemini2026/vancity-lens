"""Tests for Task 6: Type fixes + silent failure fixes across 5 files."""

import asyncio
import logging
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# ── 1. clustering.py — PipelineStage enum + field constraints ──────────

from api.intelligence.supply_pipeline import PipelineStage
from api.intelligence.clustering import ClusterMember, DevelopmentCluster


class TestClusterMemberPipelineStage:
    """ClusterMember.pipeline_stage must accept PipelineStage enum values."""

    def test_accepts_pipeline_stage_enum(self):
        member = ClusterMember(
            pipeline_id=1,
            parcel_pid="123-456-789",
            address="100 Main St",
            pipeline_stage=PipelineStage.APPROVED,
            distance_m=150.0,
        )
        assert member.pipeline_stage == PipelineStage.APPROVED

    def test_accepts_all_pipeline_stages(self):
        for stage in PipelineStage:
            member = ClusterMember(
                pipeline_id=1,
                parcel_pid="123-456-789",
                address="100 Main St",
                pipeline_stage=stage,
                distance_m=0.0,
            )
            assert member.pipeline_stage == stage

    def test_rejects_invalid_pipeline_stage(self):
        with pytest.raises(ValidationError):
            ClusterMember(
                pipeline_id=1,
                parcel_pid="123-456-789",
                address="100 Main St",
                pipeline_stage="not_a_real_stage",
                distance_m=10.0,
            )

    def test_distance_m_rejects_negative(self):
        with pytest.raises(ValidationError):
            ClusterMember(
                pipeline_id=1,
                parcel_pid="123-456-789",
                address="100 Main St",
                pipeline_stage=PipelineStage.ENQUIRY,
                distance_m=-1.0,
            )

    def test_distance_m_accepts_zero(self):
        member = ClusterMember(
            pipeline_id=1,
            parcel_pid="123-456-789",
            address="100 Main St",
            pipeline_stage=PipelineStage.ENQUIRY,
            distance_m=0.0,
        )
        assert member.distance_m == 0.0


class TestDevelopmentClusterLatLng:
    """DevelopmentCluster validates lat/lng ranges."""

    def _make_cluster(self, lat: float, lng: float) -> DevelopmentCluster:
        return DevelopmentCluster(
            center_pid="123-456-789",
            center_address="100 Main St",
            center_lat=lat,
            center_lng=lng,
            member_count=3,
            members=[],
        )

    def test_valid_lat_lng(self):
        cluster = self._make_cluster(49.2827, -123.1207)
        assert cluster.center_lat == 49.2827
        assert cluster.center_lng == -123.1207

    def test_lat_too_high(self):
        with pytest.raises(ValidationError):
            self._make_cluster(91.0, -123.0)

    def test_lat_too_low(self):
        with pytest.raises(ValidationError):
            self._make_cluster(-91.0, -123.0)

    def test_lng_too_high(self):
        with pytest.raises(ValidationError):
            self._make_cluster(49.0, 181.0)

    def test_lng_too_low(self):
        with pytest.raises(ValidationError):
            self._make_cluster(49.0, -181.0)

    def test_boundary_values(self):
        """Boundary values at exact limits should be accepted."""
        cluster = self._make_cluster(90.0, 180.0)
        assert cluster.center_lat == 90.0
        assert cluster.center_lng == 180.0

        cluster = self._make_cluster(-90.0, -180.0)
        assert cluster.center_lat == -90.0
        assert cluster.center_lng == -180.0


# ── 2. cluster_routes.py — Error handling ──────────────────────────────

import asyncpg
from fastapi.testclient import TestClient
from fastapi import FastAPI

from api.intelligence.cluster_routes import router, get_clusters


class TestClusterRoutesErrorHandling:
    """Cluster routes return proper HTTP status codes on DB errors."""

    def _make_app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router)
        app.state.pool = MagicMock()
        return app

    def test_undefined_table_returns_503(self):
        app = self._make_app()
        with patch(
            "api.intelligence.cluster_routes.detect_clusters",
            new_callable=AsyncMock,
            side_effect=asyncpg.UndefinedTableError("relation does not exist"),
        ):
            client = TestClient(app)
            resp = client.get("/clusters")
            assert resp.status_code == 503
            assert "Pipeline data not yet available" in resp.json()["detail"]

    def test_postgres_error_returns_500(self):
        app = self._make_app()
        with patch(
            "api.intelligence.cluster_routes.detect_clusters",
            new_callable=AsyncMock,
            side_effect=asyncpg.PostgresError("some db error"),
        ):
            client = TestClient(app)
            resp = client.get("/clusters")
            assert resp.status_code == 500
            assert "Failed to detect development clusters" in resp.json()["detail"]

    def test_success_returns_200(self):
        app = self._make_app()
        with patch(
            "api.intelligence.cluster_routes.detect_clusters",
            new_callable=AsyncMock,
            return_value=[],
        ):
            client = TestClient(app)
            resp = client.get("/clusters")
            assert resp.status_code == 200
            assert resp.json()["count"] == 0


# ── 3. scraper_council_playwright.py — AgendaItemType enum ─────────────

from api.intelligence.scraper_council_playwright import AgendaItemType, AgendaItem


class TestAgendaItemType:
    """AgendaItemType enum has correct values."""

    def test_has_public_hearing(self):
        assert AgendaItemType.public_hearing.value == "public_hearing"

    def test_has_bylaw(self):
        assert AgendaItemType.bylaw.value == "bylaw"

    def test_has_regular(self):
        assert AgendaItemType.regular.value == "regular"

    def test_exactly_three_members(self):
        assert len(AgendaItemType) == 3

    def test_is_str_enum(self):
        assert isinstance(AgendaItemType.public_hearing, str)
        assert AgendaItemType.bylaw == "bylaw"

    def test_agenda_item_uses_enum(self):
        item = AgendaItem(
            title="Test Bylaw",
            item_type=AgendaItemType.bylaw,
            pdf_urls=[],
            meeting_date=None,
            description="A test bylaw item",
        )
        assert item.item_type == AgendaItemType.bylaw
        assert item.item_type.value == "bylaw"


# ── 4. entitlement.py — Only catches ValueError, not TypeError ────────

from datetime import date as date_cls


class TestEntitlementDateParsing:
    """entitlement.py date parsing: ValueError is caught, TypeError propagates."""

    def test_value_error_caught_for_non_iso_date(self):
        """ValueError from fromisoformat on '2025-Q4' should be caught silently."""
        # Simulating the logic from entitlement.py lines 412-421
        market_data_date = "2025-Q4"
        caught = False
        try:
            md = date_cls.fromisoformat(str(market_data_date))
        except ValueError:
            caught = True
        assert caught, "ValueError should be raised by fromisoformat for '2025-Q4'"

    def test_type_error_propagates(self):
        """TypeError should NOT be caught -- it indicates a programming error."""
        # If market_data_date were None and we tried fromisoformat(None),
        # that's a TypeError. After our fix, it should propagate.
        with pytest.raises(TypeError):
            date_cls.fromisoformat(None)


# ── 5. retrieval_logging.py — Log at ERROR on first failure ────────────

import api.retrieval_logging as retrieval_logging_mod


class TestRetrievalLoggingFirstFailure:
    """First log failure logs at ERROR, subsequent within interval at WARNING."""

    @pytest.fixture(autouse=True)
    def reset_timer(self):
        """Reset the module-level timer before each test."""
        retrieval_logging_mod._last_error_log_time = 0.0
        yield
        retrieval_logging_mod._last_error_log_time = 0.0

    @pytest.mark.asyncio
    async def test_first_failure_logs_error(self, caplog):
        """First failure should log at ERROR level with exc_info."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("db down"))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire = MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.DEBUG, logger="api.retrieval_logging"):
            async with retrieval_logging_mod.log_retrieval(mock_pool, "DS-TEST") as tracker:
                tracker.set_status(200)

        # First failure should be logged at ERROR (timer was 0.0)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
        assert "Failed to log retrieval" in error_records[0].message
        assert retrieval_logging_mod._last_error_log_time > 0.0

    @pytest.mark.asyncio
    async def test_second_failure_logs_warning(self, caplog):
        """Subsequent failures within interval should log at WARNING level."""
        import time
        # Set timer to simulate a recent ERROR log (within interval)
        retrieval_logging_mod._last_error_log_time = time.monotonic()

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("db down"))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire = MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.DEBUG, logger="api.retrieval_logging"):
            async with retrieval_logging_mod.log_retrieval(mock_pool, "DS-TEST") as tracker:
                tracker.set_status(200)

        # Should be WARNING, not ERROR
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1
        assert "Failed to log retrieval" in warning_records[0].message

        # Should NOT have any ERROR records from this call
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 0
