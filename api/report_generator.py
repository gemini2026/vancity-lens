"""
VanCity Lens — PDF Report Generation (VCL-94 / BIZ-006)

Professional parcel validation reports for client presentations.
Includes branded header, parcel overview, entitlement analysis,
pro forma financials, risk assessment, due diligence checklist,
and comparable sales with source citations.
"""

import logging
from decimal import Decimal
from typing import Optional, List
from datetime import datetime

from fpdf import FPDF
from pydantic import BaseModel, Field
import asyncpg

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models for Report Data
# ────────────────────────────────────────────────────────────────────────────


class ProFormaScenario(BaseModel):
    """Financial projection for a single scenario (conservative/moderate/aggressive)."""
    scenario: str = Field(..., description="conservative, moderate, or aggressive")
    gross_revenue: int = Field(..., description="Gross revenue in dollars")
    net_revenue: int = Field(..., description="Net revenue after absorption discount")
    hard_costs: int = Field(..., description="Hard construction costs in dollars")
    soft_costs: int = Field(..., description="Soft costs (permits, design, etc.)")
    hidden_costs: int = Field(..., description="Hidden costs (studies, conditions, etc.)")
    developer_profit: int = Field(..., description="Developer profit amount")
    total_cost: int = Field(..., description="Total project cost")
    noi: int = Field(..., description="Net operating income")
    cap_rate: Decimal = Field(..., description="Capitalization rate %")
    roi: Decimal = Field(..., description="Return on investment %")


class RiskFlag(BaseModel):
    """A single risk assessment item with color coding."""
    category: str = Field(..., description="e.g., 'Zoning', 'Community', 'Financial'")
    description: str = Field(..., description="Risk description")
    severity: str = Field(..., description="low, medium, high, or critical")
    mitigation: Optional[str] = Field(None, description="Suggested mitigation")


class ComparableSale(BaseModel):
    """A single comparable sale record."""
    address: str = Field(..., description="Property address")
    sale_price: int = Field(..., description="Sale price in dollars")
    price_per_sqft: Decimal = Field(..., description="Price per buildable sqft")
    sale_date: str = Field(..., description="Sale date (YYYY-MM-DD)")
    distance_m: int = Field(..., description="Distance from subject property in meters")
    zoning: str = Field(..., description="Zoning classification")


class ParcelReport(BaseModel):
    """Complete parcel report data."""
    pid: str = Field(..., description="BC Land Title PID")
    civic_address: Optional[str] = None
    current_zoning: Optional[str] = None
    proposed_zoning: Optional[str] = None
    lot_area_sqm: Decimal = Field(..., description="Lot area in square meters")
    lot_area_sqft: Decimal = Field(..., description="Lot area in square feet")
    coordinates: Optional[tuple[float, float]] = None
    current_storeys: Optional[int] = None
    entitled_storeys: Optional[int] = None
    current_fsr: Optional[Decimal] = None
    entitled_fsr: Optional[Decimal] = None
    buildable_sqft: Decimal = Field(..., description="Buildable square footage")
    estimated_land_value: Optional[int] = None
    assessed_value: Optional[int] = None
    asking_price: Optional[int] = None
    value_delta: Optional[int] = None
    pro_forma_scenarios: List[ProFormaScenario] = Field(default_factory=list)
    risk_flags: List[RiskFlag] = Field(default_factory=list)
    comparables: List[ComparableSale] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ────────────────────────────────────────────────────────────────────────────
# PDF Report Generator
# ────────────────────────────────────────────────────────────────────────────


class ReportGenerator:
    """Generate professional PDF reports for parcel validation."""

    def __init__(self):
        """Initialize report generator."""
        self.page_width = 210  # A4 width in mm
        self.page_height = 297  # A4 height in mm
        self.left_margin = 12
        self.right_margin = 12
        self.top_margin = 12
        self.y_cursor = self.top_margin

    async def generate_parcel_report(
        self,
        db_pool: asyncpg.Pool,
        pid: str,
        user_id: Optional[str] = None,
    ) -> bytes:
        """
        Generate a complete PDF report for a parcel.

        Args:
            db_pool: Database connection pool
            pid: Parcel ID
            user_id: Optional user ID for access control

        Returns:
            PDF content as bytes
        """
        # Fetch parcel data from database
        parcel_data = await self._fetch_parcel_data(db_pool, pid)
        if not parcel_data:
            raise ValueError(f"Parcel {pid} not found")

        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        pdf.set_margins(self.left_margin, self.top_margin, self.right_margin)

        # Build report sections
        self._build_header_section(pdf, parcel_data)
        self._build_parcel_overview(pdf, parcel_data)
        self._build_entitlement_analysis(pdf, parcel_data)
        self._build_pro_forma(pdf, parcel_data)
        self._build_risk_assessment(pdf, parcel_data)
        self._build_due_diligence(pdf)
        if parcel_data.comparables:
            self._build_comparable_sales(pdf, parcel_data)
        self._build_sources(pdf, parcel_data)
        self._build_footer(pdf, parcel_data)

        # Return PDF as bytes
        pdf_bytes = pdf.output()
        if isinstance(pdf_bytes, str):
            return pdf_bytes.encode('utf-8')
        return pdf_bytes

    async def _fetch_parcel_data(
        self,
        db_pool: asyncpg.Pool,
        pid: str,
    ) -> Optional[ParcelReport]:
        """Fetch parcel data from database."""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    pid, civic_address, current_zoning,
                    lot_area_sqm, created_at
                FROM parcels
                WHERE pid = $1
                LIMIT 1
                """,
                pid,
            )

            if not row:
                return None

            # Convert lot_area_sqm to both units
            lot_area_sqm = Decimal(str(row["lot_area_sqm"]))
            lot_area_sqft = lot_area_sqm * Decimal("10.7639")

            # Fetch entitlement data (table may not exist)
            try:
                entitlement_row = await conn.fetchrow(
                    """
                    SELECT
                        current_storeys, entitled_storeys,
                        current_fsr, entitled_fsr,
                        estimated_land_value, assessed_value, asking_price, value_delta
                    FROM parcel_entitlements
                    WHERE pid = $1
                    LIMIT 1
                    """,
                    pid,
                )
            except Exception:
                entitlement_row = None

            # Build report data
            data = ParcelReport(
                pid=pid,
                civic_address=row.get("civic_address"),
                current_zoning=row.get("current_zoning"),
                proposed_zoning=None,
                lot_area_sqm=lot_area_sqm,
                lot_area_sqft=lot_area_sqft,
                buildable_sqft=self._compute_buildable_sqft(
                    lot_area_sqm,
                    Decimal(str(entitlement_row["entitled_fsr"]))
                    if entitlement_row and entitlement_row["entitled_fsr"]
                    else Decimal("1"),
                ),
                coordinates=(
                    row["coordinates"][0], row["coordinates"][1]
                )
                if row.get("coordinates")
                else None,
                current_storeys=(
                    entitlement_row["current_storeys"]
                    if entitlement_row
                    else None
                ),
                entitled_storeys=(
                    entitlement_row["entitled_storeys"]
                    if entitlement_row
                    else None
                ),
                current_fsr=(
                    Decimal(str(entitlement_row["current_fsr"]))
                    if entitlement_row and entitlement_row["current_fsr"]
                    else None
                ),
                entitled_fsr=(
                    Decimal(str(entitlement_row["entitled_fsr"]))
                    if entitlement_row
                    else None
                ),
                estimated_land_value=(
                    entitlement_row["estimated_land_value"]
                    if entitlement_row
                    else None
                ),
                assessed_value=(
                    entitlement_row["assessed_value"]
                    if entitlement_row
                    else None
                ),
                asking_price=(
                    entitlement_row["asking_price"]
                    if entitlement_row
                    else None
                ),
                value_delta=(
                    entitlement_row["value_delta"]
                    if entitlement_row
                    else None
                ),
            )

            # Fetch pro forma scenarios
            scenarios = await conn.fetch(
                """
                SELECT scenario, gross_revenue, net_revenue, hard_costs,
                       soft_costs, hidden_costs, developer_profit, total_cost,
                       noi, cap_rate, roi
                FROM parcel_pro_forma
                WHERE pid = $1
                ORDER BY CASE scenario
                    WHEN 'conservative' THEN 1
                    WHEN 'moderate' THEN 2
                    WHEN 'aggressive' THEN 3
                END
                """,
                pid,
            )
            data.pro_forma_scenarios = [
                ProFormaScenario(
                    scenario=s["scenario"],
                    gross_revenue=s["gross_revenue"],
                    net_revenue=s["net_revenue"],
                    hard_costs=s["hard_costs"],
                    soft_costs=s["soft_costs"],
                    hidden_costs=s["hidden_costs"],
                    developer_profit=s["developer_profit"],
                    total_cost=s["total_cost"],
                    noi=s["noi"],
                    cap_rate=Decimal(str(s["cap_rate"])),
                    roi=Decimal(str(s["roi"])),
                )
                for s in scenarios
            ]

            # Fetch risk flags
            risks = await conn.fetch(
                """
                SELECT category, description, severity, mitigation
                FROM risk_assessments
                WHERE pid = $1
                ORDER BY severity DESC, category
                """,
                pid,
            )
            data.risk_flags = [
                RiskFlag(
                    category=r["category"],
                    description=r["description"],
                    severity=r["severity"],
                    mitigation=r.get("mitigation"),
                )
                for r in risks
            ]

            # Fetch comparable sales
            comps = await conn.fetch(
                """
                SELECT address, sale_price, price_per_sqft, sale_date,
                       distance_m, zoning
                FROM comparable_sales
                WHERE pid = $1
                ORDER BY distance_m ASC
                LIMIT 5
                """,
                pid,
            )
            data.comparables = [
                ComparableSale(
                    address=c["address"],
                    sale_price=c["sale_price"],
                    price_per_sqft=Decimal(str(c["price_per_sqft"])),
                    sale_date=str(c["sale_date"]),
                    distance_m=c["distance_m"],
                    zoning=c.get("zoning", "N/A"),
                )
                for c in comps
            ]

            # Fetch sources
            sources = await conn.fetch(
                """
                SELECT DISTINCT source_url, source_type
                FROM intelligence_signals
                WHERE pid = $1
                LIMIT 10
                """,
                pid,
            )
            data.sources = [s["source_url"] for s in sources if s["source_url"]]

            return data

    def _compute_buildable_sqft(
        self,
        lot_area_sqm: Decimal,
        entitled_fsr: Decimal,
    ) -> Decimal:
        """Compute buildable square footage from FSR."""
        return lot_area_sqm * entitled_fsr * Decimal("10.7639")

    def _build_header_section(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build branded header with VanCity Lens logo and title."""
        # Title
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 10, "VanCity Lens", ln=True, align="C")

        # Subtitle
        pdf.set_font("Helvetica", "I", 12)
        pdf.cell(0, 6, "Parcel Validation Report", ln=True, align="C")

        # Divider
        pdf.set_draw_color(200, 200, 200)
        pdf.line(self.left_margin, pdf.get_y() + 2, self.page_width - self.right_margin, pdf.get_y() + 2)
        pdf.ln(8)

        # Generated date
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 4, f"Generated: {parcel_data.generated_at.strftime('%B %d, %Y')}", ln=True, align="R")
        pdf.ln(3)

    def _build_parcel_overview(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build parcel overview section with address, PID, zoning, lot area."""
        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Parcel Overview", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 10)

        # Address
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, "Address:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, parcel_data.civic_address or "N/A", ln=True)

        # PID
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, "PID:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, parcel_data.pid, ln=True)

        # Zoning
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, "Current Zoning:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, parcel_data.current_zoning or "N/A", ln=True)

        # Lot area
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, "Lot Area:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"{parcel_data.lot_area_sqm:.0f} sqm ({parcel_data.lot_area_sqft:.0f} sqft)", ln=True)

        # Proposed zoning if available
        if parcel_data.proposed_zoning:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(40, 6, "Proposed Zoning:")
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, parcel_data.proposed_zoning, ln=True)

        pdf.ln(3)

    def _build_entitlement_analysis(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build entitlement analysis section with zoning, height, density."""
        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Entitlement Analysis", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 10)

        # Current vs Entitled
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(50, 6, "Density Entitlements:", ln=True)

        pdf.set_font("Helvetica", "", 9)
        pdf.cell(10, 5, "")  # Indent
        pdf.cell(35, 5, "Current:")
        if parcel_data.current_storeys and parcel_data.current_fsr:
            pdf.cell(0, 5, f"{parcel_data.current_storeys} storeys, {parcel_data.current_fsr} FSR", ln=True)
        else:
            pdf.cell(0, 5, "N/A", ln=True)

        pdf.cell(10, 5, "")  # Indent
        pdf.cell(35, 5, "Entitled:")
        if parcel_data.entitled_storeys and parcel_data.entitled_fsr:
            pdf.cell(0, 5, f"{parcel_data.entitled_storeys} storeys, {parcel_data.entitled_fsr} FSR", ln=True)
        else:
            pdf.cell(0, 5, "N/A", ln=True)

        # Buildable area
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(50, 6, "Buildable Area:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"{parcel_data.buildable_sqft:,.0f} sqft", ln=True)

        pdf.ln(3)

    def _build_pro_forma(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build pro forma section with three-scenario financial projections."""
        if not parcel_data.pro_forma_scenarios:
            return

        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Pro Forma Summary (Three Scenarios)", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        # Table header
        pdf.set_font("Helvetica", "B", 9)
        col_width = (self.page_width - self.left_margin - self.right_margin) / 5

        pdf.cell(col_width, 6, "Scenario", border=1)
        pdf.cell(col_width, 6, "Revenue", border=1)
        pdf.cell(col_width, 6, "Total Cost", border=1)
        pdf.cell(col_width, 6, "NOI", border=1)
        pdf.cell(col_width, 6, "ROI", border=1, ln=True)

        # Rows
        pdf.set_font("Helvetica", "", 8)
        for scenario in parcel_data.pro_forma_scenarios:
            pdf.cell(col_width, 5, scenario.scenario.capitalize(), border=1)
            pdf.cell(col_width, 5, f"${scenario.net_revenue:,}", border=1)
            pdf.cell(col_width, 5, f"${scenario.total_cost:,}", border=1)
            pdf.cell(col_width, 5, f"${scenario.noi:,}", border=1)
            pdf.cell(col_width, 5, f"{scenario.roi:.1f}%", border=1, ln=True)

        pdf.ln(4)

    def _build_risk_assessment(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build risk assessment section with color-coded flags."""
        if not parcel_data.risk_flags:
            return

        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Risk Assessment", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 9)

        severity_colors = {
            "critical": (255, 100, 100),
            "high": (255, 180, 100),
            "medium": (255, 230, 100),
            "low": (200, 255, 200),
        }

        for risk in parcel_data.risk_flags[:8]:  # Limit to 8 risks to avoid page overflow
            color = severity_colors.get(risk.severity, (200, 200, 200))
            pdf.set_fill_color(*color)

            pdf.cell(
                30,
                6,
                f"[{risk.severity.upper()}]",
                fill=True,
                border=1,
            )
            pdf.cell(0, 6, f"{risk.category}: {risk.description}", border=1, ln=True)

            if risk.mitigation:
                pdf.set_font("Helvetica", "I", 8)
                pdf.cell(10, 4, "")  # Indent
                pdf.cell(0, 4, f"Mitigation: {risk.mitigation}", ln=True)
                pdf.set_font("Helvetica", "", 9)

        pdf.ln(3)

    def _build_comparable_sales(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build comparable sales section."""
        if not parcel_data.comparables:
            return

        # Add page break if needed
        if pdf.get_y() > 240:
            pdf.add_page()

        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Comparable Sales", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        # Table header
        pdf.set_font("Helvetica", "B", 9)
        col_widths = [50, 35, 35, 30, 30]

        pdf.cell(col_widths[0], 6, "Address", border=1)
        pdf.cell(col_widths[1], 6, "Sale Price", border=1)
        pdf.cell(col_widths[2], 6, "Price/Sqft", border=1)
        pdf.cell(col_widths[3], 6, "Distance", border=1)
        pdf.cell(col_widths[4], 6, "Date", border=1, ln=True)

        # Rows
        pdf.set_font("Helvetica", "", 8)
        for comp in parcel_data.comparables[:5]:
            pdf.cell(col_widths[0], 5, comp.address[:25], border=1)
            pdf.cell(col_widths[1], 5, f"${comp.sale_price:,}", border=1)
            pdf.cell(col_widths[2], 5, f"${comp.price_per_sqft:.0f}", border=1)
            pdf.cell(col_widths[3], 5, f"{comp.distance_m}m", border=1)
            pdf.cell(col_widths[4], 5, comp.sale_date, border=1, ln=True)

        pdf.ln(3)

    def _build_due_diligence(self, pdf: FPDF):
        """Build due diligence checklist section."""
        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Due Diligence Checklist", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 9)

        checklist_items = [
            "Confirm parcel dimensions and lot area with BC Land Titles",
            "Verify current zoning with City of Vancouver zoning map",
            "Review OCP (Official Community Plan) for proposed zoning changes",
            "Check for soil/environmental contamination records",
            "Confirm utility servicing (water, sewer, electrical, gas)",
            "Verify no BC Assessment tax arrears or encumbrances",
            "Review neighborhood rezoning patterns and pipeline",
            "Assess community opposition risk via council minutes",
            "Validate comparable sales used in valuation",
            "Confirm Bill 47 transit-oriented development eligibility",
        ]

        for i, item in enumerate(checklist_items, 1):
            pdf.cell(4, 5, "[ ]")  # Checkbox (ASCII compatible)
            pdf.cell(0, 5, item, ln=True)

        pdf.ln(3)

    def _build_sources(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build sources section with citations and links."""
        if not parcel_data.sources:
            return

        # Add page break if needed
        if pdf.get_y() > 250:
            pdf.add_page()

        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Sources & Citations", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 8)

        for i, source in enumerate(parcel_data.sources[:5], 1):
            pdf.cell(10, 4, f"{i}. ")
            # Truncate long URLs for display
            display_url = source[:70] + "..." if len(source) > 70 else source
            pdf.cell(0, 4, display_url, ln=True)

        pdf.ln(3)

    def _build_footer(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build footer with report metadata."""
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(150, 150, 150)

        # Footer text
        footer_y = self.page_height - self.top_margin - 5
        if pdf.get_y() < footer_y:
            pdf.set_y(footer_y)

        pdf.cell(
            0,
            4,
            f"VanCity Lens - Parcel {parcel_data.pid} - {parcel_data.generated_at.strftime('%Y-%m-%d %H:%M')} UTC",
            align="C",
        )
        pdf.ln(4)
        pdf.cell(
            0,
            4,
            "This report is for informational purposes only. Not investment advice.",
            align="C",
        )


# ────────────────────────────────────────────────────────────────────────────
# Report Generator Instance
# ────────────────────────────────────────────────────────────────────────────

_report_generator = ReportGenerator()


async def generate_parcel_report(
    db_pool: asyncpg.Pool,
    pid: str,
    user_id: Optional[str] = None,
) -> bytes:
    """
    Public function to generate a PDF report for a parcel.

    Args:
        db_pool: Database connection pool
        pid: Parcel ID
        user_id: Optional user ID for access control

    Returns:
        PDF content as bytes
    """
    return await _report_generator.generate_parcel_report(db_pool, pid, user_id)
