"""Tests for HBU Engine — Automated Highest & Best Use Analysis."""

import json
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestHBUPrompts:
    """HBU prompt module exists and exports required constants."""

    def test_module_exists(self):
        assert os.path.exists("api/intelligence/hbu_prompts.py")

    def test_exports_system_prompt(self):
        from api.intelligence.hbu_prompts import HBU_SYSTEM_PROMPT
        assert "highest and best use" in HBU_SYSTEM_PROMPT.lower()
        assert "zoning" in HBU_SYSTEM_PROMPT.lower()

    def test_exports_context_template(self):
        from api.intelligence.hbu_prompts import build_hbu_context
        assert callable(build_hbu_context)

    def test_context_template_includes_parcel_data(self):
        from api.intelligence.hbu_prompts import build_hbu_context
        context = build_hbu_context(
            parcel_info={"pid": "123", "address": "Test St", "zoning": "RS-1", "lot_area_sqm": 600},
            entitlement_data={"best_entitlement": {"tier": 1, "max_storeys": 20, "max_fsr": 5.5}},
            pro_forma_data={"land_value_estimate": 1000000},
            regulatory_chunks=[{"chunk_text": "Section 4.7 allows...", "document_title": "Zoning Bylaw"}],
        )
        assert "123" in context
        assert "RS-1" in context
        assert "Zoning Bylaw" in context

    def test_system_prompt_requests_json(self):
        from api.intelligence.hbu_prompts import HBU_SYSTEM_PROMPT
        assert "JSON" in HBU_SYSTEM_PROMPT


class TestHBUEngine:
    """HBU Engine orchestrator tests."""

    def test_module_exists(self):
        assert os.path.exists("api/intelligence/hbu_engine.py")

    def test_exports_analyze_function(self):
        from api.intelligence.hbu_engine import analyze_hbu
        assert callable(analyze_hbu)

    def test_exports_get_cached_function(self):
        from api.intelligence.hbu_engine import get_cached_hbu
        assert callable(get_cached_hbu)

    @pytest.mark.asyncio
    async def test_get_cached_returns_none_when_empty(self):
        from api.intelligence.hbu_engine import get_cached_hbu

        mock_pool = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = AsyncMock(return_value=None)

        result = await get_cached_hbu(mock_pool, "999-999-999")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_hbu_returns_structured_response(self):
        """analyze_hbu returns dict with required keys."""
        from api.intelligence.hbu_engine import analyze_hbu

        mock_pool = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock: no cached result
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        # Mock entitlement
        mock_entitlement = {
            "pid": "100-001-006",
            "civic_address": "3838 Cambie Street",
            "current_zoning": "RS-1",
            "in_toa": True,
            "best_entitlement": {
                "station_name": "King Edward",
                "tier": 1,
                "max_storeys": 20,
                "max_fsr": 5.5,
                "distance_m": 165.2,
                "current_storeys": 10,
                "current_fsr": 0.6,
                "storey_uplift": 10,
                "fsr_uplift": 4.9,
                "zoning_already_exceeds": False,
            },
            "value_estimate": {
                "lot_area_sqm": 600,
                "buildable_sqft": 35521,
                "estimated_land_value": 28416696,
            },
        }

        # Mock K2 retrieval
        mock_chunks = [
            {"chunk_text": "RS-1 zoning allows max 0.6 FSR...", "document_title": "Zoning Bylaw"},
        ]

        # Mock LLM response
        mock_llm_response = json.dumps({
            "recommended_use": "20-storey mixed-use",
            "zoning_basis": "Bill 47 Tier 1 TOD",
            "max_height_storeys": 20,
            "max_fsr": 5.5,
            "estimated_units": 85,
            "unit_mix": {"studio": 15, "1br": 35, "2br": 25, "3br": 10},
            "buildable_sqft": 35521,
            "key_constraints": [],
            "feasibility_verdict": "pencils",
            "narrative": "This RS-1 lot qualifies for Tier 1 TOD...",
            "cited_sources": [{"title": "Zoning Bylaw", "section": "4.7", "relevance": "base zoning"}],
        })

        with patch("api.intelligence.hbu_engine.compute_entitlement") as mock_ent, \
             patch("api.intelligence.hbu_engine.retrieve_document_chunks") as mock_ret, \
             patch("api.intelligence.hbu_engine.generate_chat") as mock_llm:
            mock_ent.return_value = MagicMock()
            mock_ent.return_value.__class__.__name__ = "ParcelEntitlementResponse"
            mock_ent.return_value.model_dump = MagicMock(return_value=mock_entitlement)

            mock_ret.return_value = mock_chunks
            mock_llm.return_value = (mock_llm_response, "gemini-2.0-flash", 1.5)

            result = await analyze_hbu(mock_pool, "100-001-006")

        assert result is not None
        assert result["pid"] == "100-001-006"
        assert "highest_best_use" in result
        hbu = result["highest_best_use"]
        assert hbu["recommended_use"] == "20-storey mixed-use"
        assert hbu["max_height_storeys"] == 20
        assert "confidence_score" in result

    def test_parse_llm_response_clean_json(self):
        """_parse_llm_response handles clean JSON."""
        from api.intelligence.hbu_engine import _parse_llm_response
        raw = '{"recommended_use": "12-storey mixed-use", "max_fsr": 4.0}'
        result = _parse_llm_response(raw)
        assert result["recommended_use"] == "12-storey mixed-use"
        assert result["max_fsr"] == 4.0

    def test_parse_llm_response_with_code_fences(self):
        """_parse_llm_response strips markdown code fences."""
        from api.intelligence.hbu_engine import _parse_llm_response
        raw = '```json\n{"recommended_use": "6-storey rental"}\n```'
        result = _parse_llm_response(raw)
        assert result["recommended_use"] == "6-storey rental"

    def test_parse_llm_response_embedded_json(self):
        """_parse_llm_response extracts JSON from surrounding text."""
        from api.intelligence.hbu_engine import _parse_llm_response
        raw = 'Here is the analysis:\n{"recommended_use": "townhouse"}\nEnd of analysis.'
        result = _parse_llm_response(raw)
        assert result["recommended_use"] == "townhouse"

    def test_parse_llm_response_fallback(self):
        """_parse_llm_response returns fallback for unparseable text."""
        from api.intelligence.hbu_engine import _parse_llm_response
        result = _parse_llm_response("This is not JSON at all.")
        assert result["feasibility_verdict"] == "unknown"
        assert "narrative" in result

    def test_compute_confidence_high(self):
        """_compute_confidence returns high score for good data."""
        from api.intelligence.hbu_engine import _compute_confidence
        ent = {"in_toa": True, "best_entitlement": {"zoning_already_exceeds": False}}
        chunks = [{"chunk_text": f"chunk {i}"} for i in range(6)]
        hbu = {"max_height_storeys": 20, "max_fsr": 5.5, "feasibility_verdict": "pencils"}
        score = _compute_confidence(ent, chunks, hbu)
        assert score >= 0.9

    def test_compute_confidence_low(self):
        """_compute_confidence returns lower score with no data."""
        from api.intelligence.hbu_engine import _compute_confidence
        ent = {"in_toa": False}
        chunks = []
        hbu = {}
        score = _compute_confidence(ent, chunks, hbu)
        assert score == 0.5

    def test_build_fallback_response(self):
        """_build_fallback_response returns a valid structure."""
        from api.intelligence.hbu_engine import _build_fallback_response
        ent = {
            "civic_address": "123 Test St",
            "current_zoning": "RS-1",
            "best_entitlement": {"max_storeys": 20, "tier": 1, "max_fsr": 5.5},
        }
        result = _build_fallback_response("100-001-006", ent, {"buildable_sqft": 35000})
        assert result["pid"] == "100-001-006"
        assert result["confidence_score"] == 0.4
        assert "rule-engine" in result["highest_best_use"]["recommended_use"].lower()


class TestHBURoutes:
    """HBU API route registration tests."""

    def test_routes_file_exists(self):
        assert os.path.exists("api/intelligence/hbu_routes.py")

    def test_router_has_analyze_endpoint(self):
        from api.intelligence.hbu_routes import router
        paths = [r.path for r in router.routes]
        assert any("hbu" in p for p in paths)

    def test_router_has_get_endpoint(self):
        from api.intelligence.hbu_routes import router
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "GET" in methods

    def test_router_has_post_endpoint(self):
        from api.intelligence.hbu_routes import router
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "POST" in methods

    def test_hbu_routes_mounted_in_intelligence(self):
        with open("api/intelligence/routes.py") as f:
            content = f.read()
        assert "hbu_routes" in content


class TestHBUFrontend:
    """HBU frontend component tests."""

    def test_component_exists(self):
        assert os.path.exists("frontend/src/components/HBUAnalysis.tsx")

    def test_is_client_component(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert '"use client"' in content

    def test_api_client_exists(self):
        assert os.path.exists("frontend/src/lib/hbu-api.ts")

    def test_api_client_exports_functions(self):
        with open("frontend/src/lib/hbu-api.ts") as f:
            content = f.read()
        assert "getHBUAnalysis" in content
        assert "runHBUAnalysis" in content

    def test_component_shows_key_metrics(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "max_height_storeys" in content
        assert "max_fsr" in content
        assert "estimated_units" in content
        assert "buildable_sqft" in content

    def test_component_shows_feasibility(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "feasibility_verdict" in content
        assert "pencils" in content.lower()

    def test_component_has_analyze_button(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "Analyze" in content
        assert "handleAnalyze" in content

    def test_component_shows_narrative(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "narrative" in content
        assert "AI Analysis" in content

    def test_component_shows_constraints(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "key_constraints" in content
        assert "Constraints" in content

    def test_component_shows_confidence(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "confidence_score" in content
        assert "confidence" in content.lower()

    def test_integrated_in_detail_panel(self):
        with open("frontend/src/components/ParcelDetailPanel.tsx") as f:
            content = f.read()
        assert "HBUAnalysis" in content

    def test_component_has_loading_state(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "loading" in content.lower()
        assert "animate-pulse" in content

    def test_component_has_error_state(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "error" in content
        assert "Retry" in content


class TestHBUPDFSection:
    """HBU section in PDF report."""

    def test_report_has_hbu_method(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "_build_hbu_section" in content

    def test_hbu_method_called_in_generate(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "self._build_hbu_section" in content

    def test_hbu_section_has_header(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "Highest & Best Use" in content

    def test_hbu_section_shows_recommendation(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "recommended_use" in content

    def test_hbu_section_shows_feasibility(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "feasibility_verdict" in content or "Feasibility" in content
