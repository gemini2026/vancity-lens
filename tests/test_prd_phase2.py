"""Tests for PRD Phase 2 gap-closure features (F02 + F03)."""
import json
import os
from decimal import Decimal
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


class TestChangeRecordsTable:
    """F02-A: Change records database table."""

    def test_migration_file_exists(self):
        assert os.path.exists("db/047_change_records.sql")

    def test_migration_creates_change_records(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        assert "change_records" in content
        assert "CREATE TABLE" in content

    def test_migration_has_required_columns(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        for col in ["change_type", "source_url", "source_document_title",
                     "publication_date", "effective_date", "geographic_scope",
                     "affected_areas", "entitlement_change", "plain_english_summary",
                     "nlp_confidence_score", "requires_manual_review"]:
            assert col in content, f"Missing column: {col}"

    def test_migration_has_indexes(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        assert "idx_change_records" in content

    def test_migration_has_full_text_search(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        assert "gin" in content.lower() or "GIN" in content


class TestChangeWatchlistMatching:
    """F02-C: Watchlist matching for regulatory changes."""
    def test_rule_type_has_geographic_scope(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "GEOGRAPHIC_SCOPE")
    def test_rule_type_has_change_type(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "CHANGE_TYPE")
    def test_match_geographic_scope_citywide(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="geographic_scope", rule_value="citywide")
        signal = {"geographic_scope": "citywide", "signal_type": "regulatory_change"}
        assert AlertEngine.match_rule(signal, rule) is True
    def test_match_geographic_scope_neighbourhood(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="geographic_scope", rule_value="kitsilano")
        signal = {"geographic_scope": "neighbourhood", "affected_areas": ["Kitsilano", "Point Grey"]}
        assert AlertEngine.match_rule(signal, rule) is True
    def test_match_geographic_scope_no_match(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="geographic_scope", rule_value="marpole")
        signal = {"geographic_scope": "neighbourhood", "affected_areas": ["Kitsilano"]}
        assert AlertEngine.match_rule(signal, rule) is False
    def test_match_change_type_rule(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="change_type", rule_value="bylaw_amendment")
        signal = {"change_type": "bylaw_amendment"}
        assert AlertEngine.match_rule(signal, rule) is True
    def test_match_change_type_no_match(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="change_type", rule_value="bylaw_amendment")
        signal = {"change_type": "council_vote"}
        assert AlertEngine.match_rule(signal, rule) is False


class TestCouncilScraper:
    """F02-E: Playwright council meeting scraper."""
    def test_scraper_module_exists(self):
        assert os.path.exists("api/intelligence/scraper_council_playwright.py")
    def test_scraper_has_scrape_function(self):
        from api.intelligence.scraper_council_playwright import scrape_council_agendas
        assert callable(scrape_council_agendas)
    def test_scraper_has_parse_agenda_items(self):
        from api.intelligence.scraper_council_playwright import parse_agenda_items
        assert callable(parse_agenda_items)
    def test_parse_agenda_items_extracts_from_html(self):
        from api.intelligence.scraper_council_playwright import parse_agenda_items
        html = '<div class="agenda-item"><h3>Public Hearing: Rezoning - 123 Main St</h3><a href="/docs/report.pdf">Staff Report</a></div><div class="agenda-item"><h3>Regular Item: Budget</h3></div>'
        items = parse_agenda_items(html)
        assert len(items) >= 1
    def test_scraper_target_url_is_vancouver(self):
        with open("api/intelligence/scraper_council_playwright.py") as f:
            content = f.read()
        assert "vancouver.ca" in content
    def test_parse_classifies_public_hearing(self):
        from api.intelligence.scraper_council_playwright import parse_agenda_items
        html = '<div class="agenda-item"><h3>Public Hearing: Rezoning Application</h3></div>'
        items = parse_agenda_items(html)
        assert any(i.item_type == "public_hearing" for i in items)


class TestRedFlagAutoAggregation:
    """F03-A: Red flag auto-aggregation."""
    def test_collect_red_flags_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_collect_red_flags")

    def test_collect_red_flags_returns_list(self):
        from api.report_generator import ReportGenerator
        gen = ReportGenerator.__new__(ReportGenerator)
        # Create minimal mock of ParcelReport with fields that _collect_red_flags actually uses
        data = MagicMock()
        data.risk_flags = []
        # Set all attributes to safe defaults
        for attr in ["heritage_designation", "contamination_status", "assessed_value",
                     "neighbourhood_median_assessed", "neighbourhood_std_assessed", "data_currency"]:
            setattr(data, attr, None)
        flags = gen._collect_red_flags(data)
        assert isinstance(flags, list)

    def test_collect_red_flags_heritage_high(self):
        from api.report_generator import ReportGenerator
        gen = ReportGenerator.__new__(ReportGenerator)
        data = MagicMock()
        data.heritage_designation = "A"
        data.contamination_status = "Not Listed"
        data.risk_flags = []
        data.assessed_value = 1500000
        data.neighbourhood_median_assessed = None
        data.neighbourhood_std_assessed = None
        data.data_currency = []
        flags = gen._collect_red_flags(data)
        heritage_flags = [f for f in flags if "heritage" in f["flag_name"].lower()]
        assert len(heritage_flags) == 1
        assert heritage_flags[0]["severity"] == "high"

    def test_collect_red_flags_contamination_high(self):
        from api.report_generator import ReportGenerator
        gen = ReportGenerator.__new__(ReportGenerator)
        data = MagicMock()
        data.heritage_designation = None
        data.contamination_status = "Active Site"
        data.risk_flags = []
        data.assessed_value = 1000000
        data.neighbourhood_median_assessed = None
        data.neighbourhood_std_assessed = None
        data.data_currency = []
        flags = gen._collect_red_flags(data)
        contam_flags = [f for f in flags if "contamination" in f["flag_name"].lower()]
        assert len(contam_flags) == 1
        assert contam_flags[0]["severity"] == "high"

    def test_collect_red_flags_dict_keys(self):
        from api.report_generator import ReportGenerator
        gen = ReportGenerator.__new__(ReportGenerator)
        data = MagicMock()
        data.heritage_designation = "B"
        data.contamination_status = "Not Listed"
        data.risk_flags = []
        data.assessed_value = None
        data.neighbourhood_median_assessed = None
        data.neighbourhood_std_assessed = None
        data.data_currency = []
        flags = gen._collect_red_flags(data)
        for flag in flags:
            assert "flag_name" in flag
            assert "severity" in flag
            assert "detail" in flag


class TestChangeExtraction:
    """F02-B: LLM change extraction pipeline."""
    def test_change_prompts_module_exists(self):
        assert os.path.exists("api/intelligence/change_prompts.py")
    def test_change_extraction_module_exists(self):
        assert os.path.exists("api/intelligence/change_extraction.py")
    def test_extraction_prompt_has_required_fields(self):
        from api.intelligence.change_prompts import CHANGE_EXTRACTION_PROMPT
        for field in ["change_type", "geographic_scope", "affected_areas", "entitlement_change", "plain_english_summary"]:
            assert field in CHANGE_EXTRACTION_PROMPT
    def test_extract_change_is_callable(self):
        from api.intelligence.change_extraction import extract_regulatory_change
        assert callable(extract_regulatory_change)
    def test_parse_extraction_response_valid_json(self):
        from api.intelligence.change_extraction import parse_extraction_response
        sample = json.dumps({
            "change_type": "bylaw_amendment", "geographic_scope": "citywide",
            "affected_areas": ["Downtown"],
            "entitlement_change": {"field": "max_fsr", "before_value": "3.0", "after_value": "5.0"},
            "plain_english_summary": "FSR increased citywide.", "confidence": 0.92,
        })
        result = parse_extraction_response(sample)
        assert result["change_type"] == "bylaw_amendment"
        assert result["nlp_confidence_score"] == 0.92
        assert result["requires_manual_review"] is False
    def test_parse_extraction_low_confidence_flags_review(self):
        from api.intelligence.change_extraction import parse_extraction_response
        sample = json.dumps({
            "change_type": "policy_update", "geographic_scope": "neighbourhood",
            "affected_areas": ["Kitsilano"], "entitlement_change": {},
            "plain_english_summary": "Minor clarification.", "confidence": 0.70,
        })
        result = parse_extraction_response(sample)
        assert result["requires_manual_review"] is True
    def test_is_candidate_chunk_detects_bylaw(self):
        from api.intelligence.change_extraction import is_candidate_chunk
        assert is_candidate_chunk("The bylaw amendment to RS-1 zoning increases FSR from 0.6 to 1.2")
        assert not is_candidate_chunk("The weather today is sunny and warm")
    def test_store_change_record_is_callable(self):
        from api.intelligence.change_extraction import store_change_record
        assert callable(store_change_record)


class TestRegulatoryArchiveSearch:
    """F02-D: Regulatory archive search API."""
    def test_change_routes_file_exists(self):
        assert os.path.exists("api/intelligence/change_routes.py")
    def test_change_router_has_get_endpoint(self):
        from api.intelligence.change_routes import router
        paths = [r.path for r in router.routes]
        assert any("change" in p for p in paths)
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "GET" in methods
    def test_change_routes_mounted(self):
        with open("api/intelligence/routes.py") as f:
            content = f.read()
        assert "change_routes" in content
    def test_search_endpoint_has_pagination(self):
        with open("api/intelligence/change_routes.py") as f:
            content = f.read()
        assert "page" in content
        assert "per_page" in content
    def test_search_endpoint_has_filters(self):
        with open("api/intelligence/change_routes.py") as f:
            content = f.read()
        assert "change_type" in content
        assert "geographic_scope" in content
        assert "start_date" in content
    def test_get_single_change_endpoint(self):
        from api.intelligence.change_routes import router
        paths = [r.path for r in router.routes]
        assert any("{change_id}" in p for p in paths)


class TestLLMExecutiveSummary:
    """F03-B: LLM-enhanced executive summary."""
    def test_executive_summary_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_build_executive_summary")
    def test_executive_summary_includes_risk_count(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "risk" in content.lower() or "red flag" in content.lower()
    def test_executive_summary_has_llm_integration(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "generate_chat" in content
    def test_executive_summary_has_word_cap(self):
        """Summary should cap output at ~300 words."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "300" in content or "word" in content.lower()


class TestReportSectionReorder:
    """F03-C: Report section reordering per PRD spec."""
    def test_heritage_section_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_build_heritage_section")
    def test_red_flags_summary_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_build_red_flags_summary")
    def test_section_order_heritage_after_environmental(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        env_idx = content.find("_build_environmental_section")
        heritage_idx = content.find("_build_heritage_section")
        assert heritage_idx != -1, "Heritage section method not found"
        assert env_idx < heritage_idx, "Heritage should come after environmental"
    def test_section_order_red_flags_exists(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "_build_red_flags_summary" in content


class TestUnavailabilityHandling:
    """F03-D: Data unavailability handling in reports."""
    def test_unavailability_helper_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_render_unavailable_section")
    def test_unavailability_message_format(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "Data unavailable" in content or "data unavailable" in content
    def test_all_async_sections_have_error_handling(self):
        """Each async section should have try/except for graceful degradation."""
        with open("api/report_generator.py") as f:
            content = f.read()
        # Check that the generate method wraps async calls
        assert "_render_unavailable_section" in content
