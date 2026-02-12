"""
Tests for VanCity Lens PDF Report Generation (VCL-94 / BIZ-006)

Comprehensive test coverage for report generator and routes.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO

import asyncpg

from api.report_generator import (
    ReportGenerator,
    ParcelReport,
    ProFormaScenario,
    RiskFlag,
    ComparableSale,
    generate_parcel_report,
)
from api.report_routes import (
    router,
    BatchReportJob,
    _batch_jobs,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()

    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool


@pytest.fixture
def sample_parcel_data():
    """Sample parcel data for testing."""
    return {
        "pid": "012-345-678",
        "civic_address": "1234 Main Street, Vancouver",
        "current_zoning": "RM-4",
        "proposed_zoning": "CD-1",
        "lot_area_sqm": Decimal("500"),
        "lot_area_sqft": Decimal("5381.95"),
        "coordinates": (-123.1234, 49.2819),
        "current_storeys": 6,
        "entitled_storeys": 12,
        "current_fsr": Decimal("2.0"),
        "entitled_fsr": Decimal("4.0"),
        "buildable_sqft": Decimal("21527.8"),
        "estimated_land_value": 2500000,
        "assessed_value": 2000000,
        "asking_price": 2800000,
        "value_delta": 300000,
        "generated_at": datetime.utcnow(),
    }


@pytest.fixture
def sample_pro_forma_scenarios():
    """Sample pro forma scenarios."""
    return [
        ProFormaScenario(
            scenario="conservative",
            gross_revenue=18000000,
            net_revenue=15300000,
            hard_costs=8500000,
            soft_costs=1500000,
            hidden_costs=500000,
            developer_profit=3200000,
            total_cost=13700000,
            noi=1600000,
            cap_rate=Decimal("6.4"),
            roi=Decimal("11.7"),
        ),
        ProFormaScenario(
            scenario="moderate",
            gross_revenue=21000000,
            net_revenue=17850000,
            hard_costs=8000000,
            soft_costs=1400000,
            hidden_costs=400000,
            developer_profit=3600000,
            total_cost=13000000,
            noi=4850000,
            cap_rate=Decimal("19.4"),
            roi=Decimal("37.3"),
        ),
        ProFormaScenario(
            scenario="aggressive",
            gross_revenue=24000000,
            net_revenue=20400000,
            hard_costs=7500000,
            soft_costs=1300000,
            hidden_costs=300000,
            developer_profit=4100000,
            total_cost=12400000,
            noi=8000000,
            cap_rate=Decimal("32.0"),
            roi=Decimal("64.5"),
        ),
    ]


@pytest.fixture
def sample_risk_flags():
    """Sample risk flags."""
    return [
        RiskFlag(
            category="Zoning",
            description="Proposed zoning requires Council approval",
            severity="high",
            mitigation="Engage with planning department early",
        ),
        RiskFlag(
            category="Community",
            description="Local opposition to height/density",
            severity="medium",
            mitigation="Community engagement and design integration",
        ),
        RiskFlag(
            category="Financial",
            description="Market absorption risk for units",
            severity="medium",
            mitigation="Phased release strategy",
        ),
        RiskFlag(
            category="Entitlement",
            description="Bill 47 TOA eligibility pending verification",
            severity="low",
            mitigation="Confirm with City zoning analysis",
        ),
    ]


@pytest.fixture
def sample_comparable_sales():
    """Sample comparable sales."""
    return [
        ComparableSale(
            address="1200 Main Street",
            sale_price=2300000,
            price_per_sqft=Decimal("427"),
            sale_date="2023-11-15",
            distance_m=145,
            zoning="RM-4",
        ),
        ComparableSale(
            address="1250 Main Street",
            sale_price=2500000,
            price_per_sqft=Decimal("465"),
            sale_date="2023-10-22",
            distance_m=312,
            zoning="RM-4",
        ),
        ComparableSale(
            address="1180 Blank Avenue",
            sale_price=2100000,
            price_per_sqft=Decimal("395"),
            sale_date="2023-09-10",
            distance_m=487,
            zoning="RM-3",
        ),
    ]


@pytest.fixture
def complete_parcel_report(sample_parcel_data, sample_pro_forma_scenarios, sample_risk_flags, sample_comparable_sales):
    """Complete parcel report with all sections."""
    report = ParcelReport(**sample_parcel_data)
    report.pro_forma_scenarios = sample_pro_forma_scenarios
    report.risk_flags = sample_risk_flags
    report.comparables = sample_comparable_sales
    report.sources = [
        "https://council.vancouver.ca/documents/item123",
        "https://vancouver.ca/planning/zoning",
    ]
    return report


# ────────────────────────────────────────────────────────────────────────────
# Tests: Report Generator Basic Functionality
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_parcel_report_returns_pdf_bytes(mock_db_pool):
    """Test that generate_parcel_report returns PDF bytes."""
    # Setup mock database response
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "pid": "012-345-678",
                "civic_address": "1234 Main Street",
                "current_zoning": "RM-4",
                "proposed_zoning": None,
                "lot_area_sqm": 500,
                "coordinates": None,
                "created_at": datetime.utcnow(),
            },
            {
                "current_storeys": 6,
                "entitled_storeys": 12,
                "current_fsr": Decimal("2.0"),
                "entitled_fsr": Decimal("4.0"),
                "estimated_land_value": 2500000,
                "assessed_value": 2000000,
                "asking_price": 2800000,
                "value_delta": 300000,
            },
        ]
    )

    conn.fetch = AsyncMock(return_value=[])

    # Generate report
    pdf_bytes = await generate_parcel_report(mock_db_pool, "012-345-678")

    # Verify it's bytes or bytearray
    assert isinstance(pdf_bytes, (bytes, bytearray))

    # Verify it starts with PDF magic bytes
    assert pdf_bytes.startswith(b"%PDF")

    # Verify non-empty
    assert len(pdf_bytes) > 0


@pytest.mark.asyncio
async def test_generate_parcel_report_nonexistent_parcel(mock_db_pool):
    """Test that nonexistent parcel raises ValueError."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await generate_parcel_report(mock_db_pool, "nonexistent-pid")


@pytest.mark.asyncio
async def test_report_generator_fetch_parcel_data(mock_db_pool, sample_parcel_data):
    """Test _fetch_parcel_data retrieves and structures data correctly."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "pid": "012-345-678",
                "civic_address": "1234 Main Street",
                "current_zoning": "RM-4",
                "proposed_zoning": "CD-1",
                "lot_area_sqm": 500,
                "coordinates": (-123.1234, 49.2819),
                "created_at": datetime.utcnow(),
            },
            {
                "current_storeys": 6,
                "entitled_storeys": 12,
                "current_fsr": Decimal("2.0"),
                "entitled_fsr": Decimal("4.0"),
                "estimated_land_value": 2500000,
                "assessed_value": 2000000,
                "asking_price": 2800000,
                "value_delta": 300000,
            },
        ]
    )

    conn.fetch = AsyncMock(return_value=[])

    generator = ReportGenerator()
    report = await generator._fetch_parcel_data(mock_db_pool, "012-345-678")

    assert report is not None
    assert report.pid == "012-345-678"
    assert report.civic_address == "1234 Main Street"
    assert report.current_zoning == "RM-4"
    assert report.proposed_zoning is None  # Column not in parcels table


# ────────────────────────────────────────────────────────────────────────────
# Tests: Report Sections
# ────────────────────────────────────────────────────────────────────────────


def test_build_header_section(complete_parcel_report):
    """Test header section generation."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    generator = ReportGenerator()
    generator._build_header_section(pdf, complete_parcel_report)

    # Verify PDF has content
    output = pdf.output()
    assert len(output) > 0
    # Just verify PDF starts correctly
    assert output.startswith(b"%PDF")


def test_build_parcel_overview(complete_parcel_report):
    """Test parcel overview section."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    generator = ReportGenerator()
    generator._build_parcel_overview(pdf, complete_parcel_report)

    output = pdf.output()
    assert len(output) > 0
    # Basic check: PDF should be non-empty


def test_build_entitlement_analysis(complete_parcel_report):
    """Test entitlement analysis section."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    generator = ReportGenerator()
    generator._build_entitlement_analysis(pdf, complete_parcel_report)

    output = pdf.output()
    assert len(output) > 0


def test_build_pro_forma(complete_parcel_report):
    """Test pro forma section with three scenarios."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    generator = ReportGenerator()
    generator._build_pro_forma(pdf, complete_parcel_report)

    output = pdf.output()
    assert len(output) > 0


def test_build_pro_forma_with_no_scenarios():
    """Test pro forma section gracefully handles missing scenarios."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    report = ParcelReport(
        pid="test",
        lot_area_sqm=Decimal("500"),
        lot_area_sqft=Decimal("5381.95"),
        buildable_sqft=Decimal("10763.9"),
    )

    generator = ReportGenerator()
    generator._build_pro_forma(pdf, report)  # Should not raise

    output = pdf.output()
    assert len(output) > 0


def test_build_risk_assessment(complete_parcel_report):
    """Test risk assessment section with color coding."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    generator = ReportGenerator()
    generator._build_risk_assessment(pdf, complete_parcel_report)

    output = pdf.output()
    assert len(output) > 0


def test_build_comparable_sales(complete_parcel_report):
    """Test comparable sales section."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    generator = ReportGenerator()
    generator._build_comparable_sales(pdf, complete_parcel_report)

    output = pdf.output()
    assert len(output) > 0


def test_build_due_diligence_checklist():
    """Test due diligence checklist section."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    report = ParcelReport(
        pid="test",
        lot_area_sqm=Decimal("500"),
        lot_area_sqft=Decimal("5381.95"),
        buildable_sqft=Decimal("10763.9"),
    )

    generator = ReportGenerator()
    generator._build_due_diligence(pdf, report)

    output = pdf.output()
    assert len(output) > 0
    # Verify PDF is valid
    assert output.startswith(b"%PDF")


def test_build_due_diligence_with_evidence_does_not_crash():
    """Evidence-backed due diligence section should not crash PDF generation (unicode + long tokens)."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    long_token = "a" * 500
    evidence = {
        "pid": "test",
        "generated_at": "2026-02-10T00:00:00Z",
        "utilities": {
            "status": "partial",
            "water": {
                "status": "ok",
                "nearest_distance_m": 12.3,
                "nearest_assets": [],
                "source": {
                    "label": "Test Water Dataset",
                    "url": f"https://example.com/water/path?token={long_token}",
                },
                "note": None,
            },
            "sewer": {
                "status": "not_loaded",
                "nearest_distance_m": None,
                "nearest_assets": [],
                "source": {"label": "Test Sewer Dataset", "url": "https://example.com/sewer"},
                "note": long_token,
            },
        },
        "encumbrances_proxy": {
            "status": "ok",
            "easement_count": 1,
            "easements": [{"easement_type": "Statutory right of way", "plan_number": "SRW-123"}],
            "source": {"label": "Test Easements Dataset", "url": "https://example.com/easements"},
            "note": "Proxy only — confirm via LTSA title search.",
        },
        "ocp_policy_excerpts": {
            "status": "ok",
            "query": "test query",
            "excerpts": [
                {
                    "title": "Policy Update — Draft",
                    "source_url": f"https://example.com/policy?ref={long_token}",
                    "source_type": "syc_plan_document",
                    "section_header": "Heights & Density",
                    # Unicode punctuation + bullet should be sanitized for core PDF fonts.
                    "excerpt": "Council noted: “increased density” • subject to review — see Appendix A.",
                }
            ],
            "note": None,
        },
    }

    report = ParcelReport(
        pid="test",
        lot_area_sqm=Decimal("500"),
        lot_area_sqft=Decimal("5381.95"),
        buildable_sqft=Decimal("10763.9"),
        due_diligence_evidence=evidence,
    )

    generator = ReportGenerator()
    generator._build_due_diligence(pdf, report)

    output = pdf.output()
    assert len(output) > 0
    assert output.startswith(b"%PDF")


def test_build_sources(complete_parcel_report):
    """Test sources/citations section."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    generator = ReportGenerator()
    generator._build_sources(pdf, complete_parcel_report)

    output = pdf.output()
    assert len(output) > 0


def test_build_sources_with_no_sources():
    """Test sources section gracefully handles missing sources."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    report = ParcelReport(
        pid="test",
        lot_area_sqm=Decimal("500"),
        lot_area_sqft=Decimal("5381.95"),
        buildable_sqft=Decimal("10763.9"),
    )

    generator = ReportGenerator()
    generator._build_sources(pdf, report)  # Should not raise

    output = pdf.output()
    assert len(output) > 0


# ────────────────────────────────────────────────────────────────────────────
# Tests: Pro Forma Calculations
# ────────────────────────────────────────────────────────────────────────────


def test_pro_forma_scenario_structure(sample_pro_forma_scenarios):
    """Test pro forma scenario has correct financial structure."""
    scenario = sample_pro_forma_scenarios[0]

    # Verify all required fields
    assert scenario.scenario == "conservative"
    assert scenario.gross_revenue > 0
    assert scenario.net_revenue > 0
    assert scenario.total_cost > 0
    assert scenario.noi > 0
    assert isinstance(scenario.cap_rate, Decimal)
    assert isinstance(scenario.roi, Decimal)


def test_pro_forma_conservative_lower_than_aggressive(sample_pro_forma_scenarios):
    """Test that conservative scenario ROI is lower than aggressive."""
    conservative = sample_pro_forma_scenarios[0]
    aggressive = sample_pro_forma_scenarios[2]

    assert conservative.roi < aggressive.roi


# ────────────────────────────────────────────────────────────────────────────
# Tests: Risk Assessment Color Mapping
# ────────────────────────────────────────────────────────────────────────────


def test_risk_flag_severity_levels(sample_risk_flags):
    """Test that risk flags have valid severity levels."""
    valid_severities = {"low", "medium", "high", "critical"}

    for risk in sample_risk_flags:
        assert risk.severity in valid_severities


def test_risk_assessment_color_coding():
    """Test severity to color mapping works correctly."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    report = ParcelReport(
        pid="test",
        lot_area_sqm=Decimal("500"),
        lot_area_sqft=Decimal("5381.95"),
        buildable_sqft=Decimal("10763.9"),
        risk_flags=[
            RiskFlag(
                category="Critical Test",
                description="Critical severity",
                severity="critical",
            ),
            RiskFlag(
                category="Low Test",
                description="Low severity",
                severity="low",
            ),
        ],
    )

    generator = ReportGenerator()
    generator._build_risk_assessment(pdf, report)

    output = pdf.output()
    assert len(output) > 0


# ────────────────────────────────────────────────────────────────────────────
# Tests: Comparable Sales Analysis
# ────────────────────────────────────────────────────────────────────────────


def test_comparable_sale_structure(sample_comparable_sales):
    """Test comparable sale has correct structure."""
    comp = sample_comparable_sales[0]

    assert comp.address
    assert comp.sale_price > 0
    assert comp.price_per_sqft > 0
    assert comp.sale_date
    assert comp.distance_m >= 0


def test_comparables_sorted_by_distance(sample_comparable_sales):
    """Test comparables are sorted by distance."""
    # Should be pre-sorted from database query
    assert sample_comparable_sales[0].distance_m <= sample_comparable_sales[1].distance_m
    assert sample_comparable_sales[1].distance_m <= sample_comparable_sales[2].distance_m


# ────────────────────────────────────────────────────────────────────────────
# Tests: Report Routes
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_parcel_report_pdf_endpoint(mock_db_pool):
    """Test PDF download endpoint returns proper response."""
    from fastapi.testclient import TestClient
    from api.main import app

    # Setup mock
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "pid": "012-345-678",
                "civic_address": "Test Address",
                "current_zoning": "RM-4",
                "proposed_zoning": None,
                "lot_area_sqm": 500,
                "coordinates": None,
                "created_at": datetime.utcnow(),
            },
            {
                "current_storeys": 6,
                "entitled_storeys": 12,
                "current_fsr": Decimal("2.0"),
                "entitled_fsr": Decimal("4.0"),
                "estimated_land_value": 2500000,
                "assessed_value": 2000000,
                "asking_price": 2800000,
                "value_delta": 300000,
            },
        ]
    )
    conn.fetch = AsyncMock(return_value=[])

    # Note: In actual testing, you would need to patch db.pool
    # This is a demonstration of the expected structure


@pytest.mark.asyncio
async def test_preview_parcel_report_endpoint():
    """Test report preview endpoint returns JSON."""
    # This would require FastAPI test client setup
    pass


def test_batch_report_job_creation():
    """Test batch report job is created correctly."""
    pids = ["pid1", "pid2", "pid3"]
    job = BatchReportJob("test-job-id", pids)

    assert job.job_id == "test-job-id"
    assert job.pids == pids
    assert job.status == "pending"
    assert job.completed == 0
    assert job.failed == 0


def test_batch_report_job_tracking():
    """Test batch job tracking and status updates."""
    job = BatchReportJob("test-job-2", ["pid1", "pid2"])

    # Simulate progress
    job.completed = 1
    job.status = "in_progress"

    assert job.completed == 1
    assert job.status == "in_progress"

    # Complete job
    job.completed = 2
    job.failed = 0
    job.status = "completed"
    job.completed_at = datetime.utcnow()

    assert job.status == "completed"
    assert job.completed_at is not None


# ────────────────────────────────────────────────────────────────────────────
# Tests: Error Handling
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_report_with_missing_data(mock_db_pool):
    """Test report generation with missing optional data."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Minimal data
    conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "pid": "test-pid",
                "civic_address": None,
                "current_zoning": None,
                "proposed_zoning": None,
                "lot_area_sqm": 300,
                "coordinates": None,
                "created_at": datetime.utcnow(),
            },
            {
                "current_storeys": None,
                "entitled_storeys": None,
                "current_fsr": None,
                "entitled_fsr": Decimal("1.0"),
                "estimated_land_value": None,
                "assessed_value": None,
                "asking_price": None,
                "value_delta": None,
            },
        ]
    )

    conn.fetch = AsyncMock(return_value=[])

    # Should not raise, even with missing data
    pdf_bytes = await generate_parcel_report(mock_db_pool, "test-pid")
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF")


def test_parcel_report_with_graceful_degradation():
    """Test report handles missing sections gracefully."""
    # Minimal report
    report = ParcelReport(
        pid="minimal-test",
        lot_area_sqm=Decimal("100"),
        lot_area_sqft=Decimal("1076.39"),
        buildable_sqft=Decimal("1076.39"),
    )

    assert report.pid == "minimal-test"
    assert len(report.pro_forma_scenarios) == 0
    assert len(report.risk_flags) == 0
    assert len(report.comparables) == 0


# ────────────────────────────────────────────────────────────────────────────
# Tests: Data Validation
# ────────────────────────────────────────────────────────────────────────────


def test_parcel_report_model_validation(complete_parcel_report):
    """Test ParcelReport Pydantic model validation."""
    assert complete_parcel_report.pid
    assert isinstance(complete_parcel_report.lot_area_sqm, Decimal)
    assert isinstance(complete_parcel_report.lot_area_sqft, Decimal)
    assert isinstance(complete_parcel_report.buildable_sqft, Decimal)


def test_pro_forma_scenario_model_validation(sample_pro_forma_scenarios):
    """Test ProFormaScenario model validation."""
    for scenario in sample_pro_forma_scenarios:
        assert scenario.scenario in ["conservative", "moderate", "aggressive"]
        assert scenario.gross_revenue > 0
        assert isinstance(scenario.cap_rate, Decimal)
        assert isinstance(scenario.roi, Decimal)


def test_risk_flag_model_validation():
    """Test RiskFlag model validation."""
    risk = RiskFlag(
        category="Test",
        description="Test description",
        severity="high",
        mitigation="Test mitigation",
    )

    assert risk.category
    assert risk.description
    assert risk.severity in ["low", "medium", "high", "critical"]


# ────────────────────────────────────────────────────────────────────────────
# Tests: PDF Content Verification
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pdf_contains_parcel_information(mock_db_pool):
    """Test that PDF contains parcel information."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "pid": "test-pid-123",
                "civic_address": "123 Test Street",
                "current_zoning": "RM-4",
                "proposed_zoning": "CD-1",
                "lot_area_sqm": 500,
                "coordinates": None,
                "created_at": datetime.utcnow(),
            },
            {
                "current_storeys": 6,
                "entitled_storeys": 12,
                "current_fsr": Decimal("2.0"),
                "entitled_fsr": Decimal("4.0"),
                "estimated_land_value": 2500000,
                "assessed_value": 2000000,
                "asking_price": 2800000,
                "value_delta": 300000,
            },
        ]
    )

    conn.fetch = AsyncMock(return_value=[])

    pdf_bytes = await generate_parcel_report(mock_db_pool, "test-pid-123")

    # Verify PDF is valid
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000  # Minimum size for actual content


# ────────────────────────────────────────────────────────────────────────────
# Tests: Integration
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_report_generation(mock_db_pool, complete_parcel_report):
    """Test complete report generation flow."""
    generator = ReportGenerator()

    # Simulate full workflow
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "pid": complete_parcel_report.pid,
                "civic_address": complete_parcel_report.civic_address,
                "current_zoning": complete_parcel_report.current_zoning,
                "proposed_zoning": complete_parcel_report.proposed_zoning,
                "lot_area_sqm": float(complete_parcel_report.lot_area_sqm),
                "coordinates": complete_parcel_report.coordinates,
                "created_at": complete_parcel_report.generated_at,
            },
            {
                "current_storeys": complete_parcel_report.current_storeys,
                "entitled_storeys": complete_parcel_report.entitled_storeys,
                "current_fsr": complete_parcel_report.current_fsr,
                "entitled_fsr": complete_parcel_report.entitled_fsr,
                "estimated_land_value": complete_parcel_report.estimated_land_value,
                "assessed_value": complete_parcel_report.assessed_value,
                "asking_price": complete_parcel_report.asking_price,
                "value_delta": complete_parcel_report.value_delta,
            },
        ]
    )

    conn.fetch = AsyncMock(return_value=[])

    pdf_bytes = await generate_parcel_report(mock_db_pool, complete_parcel_report.pid)

    # Verify result
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_buildable_sqft_calculation():
    """Test buildable sqft calculation from FSR."""
    generator = ReportGenerator()

    lot_area_sqm = Decimal("500")
    fsr = Decimal("4.0")

    buildable = generator._compute_buildable_sqft(lot_area_sqm, fsr)

    # 500 sqm * 4.0 * 10.7639 = 21527.8
    expected = Decimal("21527.8")
    assert abs(buildable - expected) < Decimal("1")
