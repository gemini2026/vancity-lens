"""
Sprint 4 tests — New Data Source Integrations

Tests cover:
- BC Laws scraper (discovery, deduplication, storage)
- BC Gazette scraper (relevance filtering, storage)
- BC Contaminated Sites scraper (parsing, geocoding, PID matching)
- StatsCan WDS client (validation rules, data parsing)
- CMHC CSV ingestion (validation rules, CSV parsing)
- Data source routes (contaminated sites, demographics, housing market)
- Census geography lookup
"""

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── StatsCan Validation Tests ────────────────────────────────────

from api.statscan_client import (
    validate_census_year,
    validate_population,
    validate_income,
    validate_percentage,
    validate_household_size,
    _safe_int,
    _safe_decimal,
)


class TestStatsCancValidation:
    """DV-DS008-001..005: StatsCan data validation rules."""

    def test_valid_census_year(self):
        assert validate_census_year(2021) is True
        assert validate_census_year(2016) is True
        assert validate_census_year(2026) is True

    def test_invalid_census_year(self):
        assert validate_census_year(2015) is False
        assert validate_census_year(2027) is False
        assert validate_census_year(1990) is False

    def test_valid_population(self):
        assert validate_population(0) is True
        assert validate_population(700_000) is True
        assert validate_population(3_000_000) is True

    def test_invalid_population(self):
        assert validate_population(-1) is False
        assert validate_population(11_000_000) is False

    def test_valid_income(self):
        assert validate_income(0) is True
        assert validate_income(65_000) is True
        assert validate_income(200_000) is True

    def test_invalid_income(self):
        assert validate_income(-1) is False
        assert validate_income(600_000) is False

    def test_valid_percentage(self):
        assert validate_percentage(0.0) is True
        assert validate_percentage(50.5) is True
        assert validate_percentage(100.0) is True

    def test_invalid_percentage(self):
        assert validate_percentage(-0.1) is False
        assert validate_percentage(100.1) is False

    def test_valid_household_size(self):
        assert validate_household_size(1.0) is True
        assert validate_household_size(2.5) is True
        assert validate_household_size(5.0) is True

    def test_invalid_household_size(self):
        assert validate_household_size(0.3) is False
        assert validate_household_size(11.0) is False

    def test_safe_int(self):
        assert _safe_int(42) == 42
        assert _safe_int("42") == 42
        assert _safe_int("42.7") == 42
        assert _safe_int(None) is None
        assert _safe_int("abc") is None

    def test_safe_decimal(self):
        assert _safe_decimal("42.5") == Decimal("42.5")
        assert _safe_decimal(42) == Decimal("42")
        assert _safe_decimal(None) is None
        assert _safe_decimal("abc") is None


# ── CMHC Validation Tests ───────────────────────────────────────

from api.cmhc_client import (
    validate_metric,
    validate_value,
    validate_dwelling_type,
    validate_ref_date,
    validate_cma_code,
    validate_completeness,
    CMHCClient,
)


class TestCMHCValidation:
    """DV-DS009-001..006: CMHC data validation rules."""

    def test_valid_metrics(self):
        assert validate_metric("starts") is True
        assert validate_metric("completions") is True
        assert validate_metric("under_construction") is True
        assert validate_metric("absorptions") is True

    def test_invalid_metric(self):
        assert validate_metric("unknown") is False
        assert validate_metric("") is False

    def test_valid_value(self):
        assert validate_value(0) is True
        assert validate_value(5000) is True
        assert validate_value(99_999) is True

    def test_invalid_value(self):
        assert validate_value(-1) is False
        assert validate_value(100_001) is False

    def test_valid_dwelling_type(self):
        assert validate_dwelling_type("single") is True
        assert validate_dwelling_type("apartment") is True
        assert validate_dwelling_type("total") is True

    def test_invalid_dwelling_type(self):
        assert validate_dwelling_type("mansion") is False
        assert validate_dwelling_type("") is False

    def test_valid_ref_date(self):
        assert validate_ref_date("2025-01") is True
        assert validate_ref_date("2024") is True
        assert validate_ref_date("2020-12") is True

    def test_invalid_ref_date(self):
        assert validate_ref_date("") is False
        assert validate_ref_date("1980-01") is False
        assert validate_ref_date("abc") is False

    def test_valid_cma_code(self):
        assert validate_cma_code("933") is True
        assert validate_cma_code("462") is True

    def test_invalid_cma_code(self):
        assert validate_cma_code("") is False
        assert validate_cma_code("ab") is False
        assert validate_cma_code("1234") is False

    def test_completeness(self):
        assert validate_completeness({
            "cma_code": "933", "ref_date": "2025-01",
            "metric": "starts", "value": 100,
        }) is True

    def test_incomplete_record(self):
        assert validate_completeness({"cma_code": "933"}) is False
        assert validate_completeness({}) is False


class TestCMHCParsing:
    """Test CMHC CSV parsing logic."""

    def test_parse_csv_filters_to_vancouver(self):
        csv_text = (
            "Date,Geography,CMA/CA,Dwelling Type,Value\n"
            "2025-01,Vancouver,933,Single,150\n"
            "2025-01,Toronto,535,Single,200\n"
            "2025-01,Vancouver,933,Apartment,500\n"
        )
        client = CMHCClient(MagicMock())
        records = client._parse_csv(csv_text, "starts")
        assert len(records) == 2
        assert all(r["cma_code"] == "933" for r in records)

    def test_parse_csv_normalizes_dwelling_type(self):
        csv_text = (
            "Date,Geography,CMA/CA,Dwelling Type,Value\n"
            "2025-01,Vancouver,933,Single-Detached,50\n"
            "2025-01,Vancouver,933,Apartment and Other,300\n"
        )
        client = CMHCClient(MagicMock())
        records = client._parse_csv(csv_text, "starts")
        assert records[0]["dwelling_type"] == "single"
        assert records[1]["dwelling_type"] == "apartment"

    def test_parse_csv_handles_empty(self):
        client = CMHCClient(MagicMock())
        records = client._parse_csv("", "starts")
        assert records == []

    def test_parse_csv_validates_ref_date(self):
        csv_text = (
            "Date,Geography,CMA/CA,Dwelling Type,Value\n"
            "2025-01,Vancouver,933,Total,100\n"
            "bad-date,Vancouver,933,Total,50\n"
        )
        client = CMHCClient(MagicMock())
        records = client._parse_csv(csv_text, "starts")
        # Only the valid date should be included
        assert len(records) == 1
        assert records[0]["ref_date"] == "2025-01"


# ── BC Laws Scraper Tests ───────────────────────────────────────

from api.intelligence.scraper_bclaws import BCLawsScraper, SEARCH_TERMS


class TestBCLawsScraper:
    """Test BC Laws scraper logic."""

    def test_search_terms_non_empty(self):
        assert len(SEARCH_TERMS) > 5

    def test_search_terms_include_zoning(self):
        assert "zoning" in SEARCH_TERMS

    def test_search_terms_include_transit(self):
        assert "transit-oriented" in SEARCH_TERMS

    @pytest.mark.asyncio
    async def test_search_civix_parses_xml(self):
        """Test CIVIX XML response parsing."""
        mock_session = MagicMock()
        scraper = BCLawsScraper(mock_session)

        xml_response = """<?xml version="1.0"?>
        <CIVIXSearchResult>
            <results>
                <doc>
                    <CIVIX_DOCUMENT_ID>265_2023</CIVIX_DOCUMENT_ID>
                    <CIVIX_DOCUMENT_TITLE>Vancouver Transit-Oriented Areas Regulation</CIVIX_DOCUMENT_TITLE>
                </doc>
                <doc>
                    <CIVIX_DOCUMENT_ID>263_2023</CIVIX_DOCUMENT_ID>
                    <CIVIX_DOCUMENT_TITLE>Local Government TOA Regulation</CIVIX_DOCUMENT_TITLE>
                </doc>
            </results>
        </CIVIXSearchResult>"""

        scraper._fetch = AsyncMock(return_value=xml_response)
        results = await scraper.search_civix("transit-oriented")
        assert len(results) == 2
        assert results[0]["doc_id"] == "265_2023"
        assert results[0]["title"] == "Vancouver Transit-Oriented Areas Regulation"
        assert "bclaws.gov.bc.ca" in results[0]["url"]

    @pytest.mark.asyncio
    async def test_search_civix_handles_empty(self):
        mock_session = MagicMock()
        scraper = BCLawsScraper(mock_session)
        scraper._fetch = AsyncMock(return_value=None)
        results = await scraper.search_civix("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_document_text_strips_html(self):
        mock_session = MagicMock()
        scraper = BCLawsScraper(mock_session)

        html = "<html><body><p>This is <b>important</b> legislation.</p></body></html>"
        scraper._fetch = AsyncMock(return_value=html)
        text = await scraper.fetch_document_text("https://example.com/doc")
        assert "This is important legislation" in text
        assert "<b>" not in text

    @pytest.mark.asyncio
    async def test_discover_deduplicates(self):
        mock_session = MagicMock()
        scraper = BCLawsScraper(mock_session)

        # Return same doc from multiple search terms
        async def mock_search(query, max_results=10):
            return [{"doc_id": "265_2023", "title": "TOA Reg", "url": "https://example.com/265_2023"}]

        scraper.search_civix = mock_search
        docs = await scraper.discover_documents()
        # Should be deduplicated to 1
        assert len(docs) == 1


# ── BC Gazette Scraper Tests ────────────────────────────────────

from api.intelligence.scraper_gazette import BCGazetteScraper, RELEVANCE_KEYWORDS


class TestBCGazetteScraper:
    """Test BC Gazette scraper logic."""

    def test_relevance_keywords_non_empty(self):
        assert len(RELEVANCE_KEYWORDS) > 5

    def test_relevance_filter_matches(self):
        scraper = BCGazetteScraper(MagicMock())
        assert scraper._is_relevant("Order in Council: Zoning Amendment for Vancouver") is True
        assert scraper._is_relevant("Transit Service Changes for Metro Vancouver") is True

    def test_relevance_filter_rejects(self):
        scraper = BCGazetteScraper(MagicMock())
        assert scraper._is_relevant("Fisheries Quota Amendment") is False
        assert scraper._is_relevant("Mining Regulation Update") is False

    @pytest.mark.asyncio
    async def test_list_gazette_entries_parses_xml(self):
        scraper = BCGazetteScraper(MagicMock())

        xml_response = """<?xml version="1.0"?>
        <CIVIXBrowseResult>
            <CIVIX_INDEX_ENTRY>
                <CIVIX_DOCUMENT_ID>g2_2025_001</CIVIX_DOCUMENT_ID>
                <CIVIX_DOCUMENT_TITLE>Housing Density Regulation Amendment</CIVIX_DOCUMENT_TITLE>
            </CIVIX_INDEX_ENTRY>
            <CIVIX_INDEX_ENTRY>
                <CIVIX_DOCUMENT_ID>g2_2025_002</CIVIX_DOCUMENT_ID>
                <CIVIX_DOCUMENT_TITLE>Fisheries Act Amendment</CIVIX_DOCUMENT_TITLE>
            </CIVIX_INDEX_ENTRY>
        </CIVIXBrowseResult>"""

        scraper._fetch = AsyncMock(return_value=xml_response)
        entries = await scraper.list_gazette_entries("https://example.com/bcgaz2/bcgaz2")
        assert len(entries) == 2
        assert entries[0]["doc_id"] == "g2_2025_001"


# ── Contaminated Sites Scraper Tests ────────────────────────────

from api.intelligence.scraper_contaminated import ContaminatedSitesScraper, VANCOUVER_BBOX


class TestContaminatedSitesScraper:
    """Test contaminated sites scraper logic."""

    def test_vancouver_bbox_valid(self):
        assert VANCOUVER_BBOX["min_lat"] < VANCOUVER_BBOX["max_lat"]
        assert VANCOUVER_BBOX["min_lng"] < VANCOUVER_BBOX["max_lng"]

    def test_parse_api_site_valid(self):
        scraper = ContaminatedSitesScraper(MagicMock())
        item = {
            "site_id": "12345",
            "site_name": "Former Gas Station",
            "address": "123 Main St",
            "city": "Vancouver",
            "latitude": 49.25,
            "longitude": -123.10,
            "classification": "Independent Remediation",
            "status": "Active",
            "contamination_type": "Petroleum",
        }
        result = scraper._parse_api_site(item)
        assert result is not None
        assert result["site_id"] == "12345"
        assert result["latitude"] == 49.25
        assert result["classification"] == "Independent Remediation"

    def test_parse_api_site_outside_bbox(self):
        scraper = ContaminatedSitesScraper(MagicMock())
        item = {
            "site_id": "99999",
            "latitude": 48.0,  # Way south of Vancouver
            "longitude": -123.10,
        }
        result = scraper._parse_api_site(item)
        assert result is None  # Filtered out

    def test_parse_api_site_no_coords_passes(self):
        scraper = ContaminatedSitesScraper(MagicMock())
        item = {
            "site_id": "11111",
            "address": "456 Oak St",
            "city": "Vancouver",
        }
        result = scraper._parse_api_site(item)
        assert result is not None  # No coords = no bbox filter
        assert result["latitude"] is None

    def test_parse_api_site_no_id(self):
        scraper = ContaminatedSitesScraper(MagicMock())
        result = scraper._parse_api_site({})
        assert result is None


# ── Scraper Integration Tests (scrape_and_store) ────────────────

def _make_async_pool_mock():
    """Create a properly mocked asyncpg pool with async context manager support."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()

    # Create a proper async context manager for pool.acquire()
    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=mock_conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    mock_pool.acquire.return_value = acm

    return mock_pool, mock_conn


class TestScraperIntegration:
    """Test scrape_and_store functions return correct stats structure."""

    @pytest.mark.asyncio
    async def test_bclaws_scrape_and_store_returns_stats(self):
        from api.intelligence.scraper_bclaws import scrape_and_store

        mock_pool, mock_conn = _make_async_pool_mock()

        with patch("api.intelligence.scraper_bclaws.aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(BCLawsScraper, "discover_documents", return_value=[]):
                stats = await scrape_and_store(mock_pool, datetime.now(), datetime.now())

        assert "documents_found" in stats
        assert "documents_new" in stats
        assert "documents_skipped" in stats
        assert "errors" in stats

    @pytest.mark.asyncio
    async def test_gazette_scrape_and_store_returns_stats(self):
        from api.intelligence.scraper_gazette import scrape_and_store

        mock_pool, mock_conn = _make_async_pool_mock()

        with patch("api.intelligence.scraper_gazette.aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(BCGazetteScraper, "discover_documents", return_value=[]):
                stats = await scrape_and_store(mock_pool, datetime.now(), datetime.now())

        assert "documents_found" in stats
        assert stats["documents_found"] == 0

    @pytest.mark.asyncio
    async def test_contaminated_scrape_and_store_returns_stats(self):
        from api.intelligence.scraper_contaminated import scrape_and_store

        mock_pool, mock_conn = _make_async_pool_mock()

        with patch("api.intelligence.scraper_contaminated.aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(ContaminatedSitesScraper, "search_sites", return_value=[]):
                stats = await scrape_and_store(mock_pool, datetime.now(), datetime.now())

        assert "documents_found" in stats
        assert stats["documents_found"] == 0

    @pytest.mark.asyncio
    async def test_statscan_scrape_and_store_returns_stats(self):
        from api.statscan_client import scrape_and_store, ingest_population, ingest_building_permits

        mock_pool = AsyncMock()

        with patch("api.statscan_client.ingest_population", return_value={"found": 5, "stored": 5, "errors": 0}):
            with patch("api.statscan_client.ingest_building_permits", return_value={"found": 3, "stored": 3, "errors": 0}):
                stats = await scrape_and_store(mock_pool, datetime.now(), datetime.now())

        assert stats["documents_found"] == 8
        assert stats["documents_new"] == 8
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_cmhc_scrape_and_store_returns_stats(self):
        from api.cmhc_client import scrape_and_store, ingest_all_metrics

        mock_pool = AsyncMock()

        mock_metrics = {
            "starts": {"found": 10, "stored": 10, "errors": 0},
            "completions": {"found": 10, "stored": 10, "errors": 0},
            "under_construction": {"found": 10, "stored": 10, "errors": 0},
            "absorptions": {"found": 10, "stored": 10, "errors": 0},
        }

        with patch("api.cmhc_client.ingest_all_metrics", return_value=mock_metrics):
            stats = await scrape_and_store(mock_pool, datetime.now(), datetime.now())

        assert stats["documents_found"] == 40
        assert stats["documents_new"] == 40
        assert stats["errors"] == 0


# ── Census Geography Tests ──────────────────────────────────────

class TestCensusGeography:
    """Test census geography lookup table design."""

    def test_migration_file_exists(self):
        import os
        assert os.path.exists("db/037_data_sources_sprint4.sql")

    def test_migration_creates_tables(self):
        with open("db/037_data_sources_sprint4.sql") as f:
            sql = f.read()
        assert "contaminated_sites" in sql
        assert "statscan_demographics" in sql
        assert "statscan_population" in sql
        assert "statscan_building_permits" in sql
        assert "cmhc_housing" in sql
        assert "parcel_census_lookup" in sql

    def test_migration_has_indexes(self):
        with open("db/037_data_sources_sprint4.sql") as f:
            sql = f.read()
        assert "idx_contaminated_sites_geom" in sql
        assert "idx_contaminated_sites_pid" in sql
        assert "idx_statscan_census_tract" in sql
        assert "idx_cmhc_cma_metric" in sql
        assert "idx_parcel_census_tract" in sql


# ── Sources YAML Tests ──────────────────────────────────────────

class TestSourcesYAML:
    """Test that sources.yaml includes Sprint 4 sources."""

    def test_sources_yaml_has_bclaws(self):
        import yaml
        with open("pipeline/sources.yaml") as f:
            config = yaml.safe_load(f)
        ids = [s["id"] for s in config["sources"]]
        assert "bc_laws_rss" in ids

    def test_sources_yaml_has_gazette(self):
        import yaml
        with open("pipeline/sources.yaml") as f:
            config = yaml.safe_load(f)
        ids = [s["id"] for s in config["sources"]]
        assert "bc_gazette" in ids

    def test_sources_yaml_has_contaminated(self):
        import yaml
        with open("pipeline/sources.yaml") as f:
            config = yaml.safe_load(f)
        ids = [s["id"] for s in config["sources"]]
        assert "bc_contaminated_sites" in ids

    def test_sources_yaml_has_statscan(self):
        import yaml
        with open("pipeline/sources.yaml") as f:
            config = yaml.safe_load(f)
        ids = [s["id"] for s in config["sources"]]
        assert "statscan_wds" in ids

    def test_sources_yaml_has_cmhc(self):
        import yaml
        with open("pipeline/sources.yaml") as f:
            config = yaml.safe_load(f)
        ids = [s["id"] for s in config["sources"]]
        assert "cmhc_open_canada" in ids

    def test_sources_yaml_has_translink(self):
        import yaml
        with open("pipeline/sources.yaml") as f:
            config = yaml.safe_load(f)
        ids = [s["id"] for s in config["sources"]]
        assert "translink_gtfs" in ids


# ── Data Sources Router Tests ───────────────────────────────────

class TestDataSourcesRouter:
    """Test data_sources_routes.py router configuration."""

    def test_router_has_prefix(self):
        from api.data_sources_routes import router
        assert router.prefix == "/api/v1"

    def _get_paths(self):
        from api.data_sources_routes import router
        return [r.path for r in router.routes]

    def test_router_has_contaminated_sites_route(self):
        paths = self._get_paths()
        assert any("contaminated-sites" in p for p in paths)

    def test_router_has_demographics_route(self):
        paths = self._get_paths()
        assert any("demographics" in p and "census_tract" in p for p in paths)

    def test_router_has_housing_market_route(self):
        paths = self._get_paths()
        assert any("housing-market" in p for p in paths)

    def test_router_has_building_permits_route(self):
        paths = self._get_paths()
        assert any("building-permits" in p for p in paths)

    def test_router_has_data_source_status(self):
        paths = self._get_paths()
        assert any("data-sources/status" in p for p in paths)

    def test_router_has_parcel_contaminated_route(self):
        paths = self._get_paths()
        assert any("parcels" in p and "contaminated-sites" in p for p in paths)

    def test_router_has_parcel_demographics_route(self):
        paths = self._get_paths()
        assert any("parcels" in p and "demographics" in p for p in paths)
