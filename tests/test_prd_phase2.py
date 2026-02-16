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
