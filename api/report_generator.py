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

from .due_diligence_evidence import DueDiligenceEvidenceResponse, build_due_diligence_evidence

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
    due_diligence_evidence: Optional[DueDiligenceEvidenceResponse] = None
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
        await self._build_executive_summary(pdf, parcel_data)
        self._build_title_ownership(pdf, parcel_data)
        self._build_entitlement_analysis(pdf, parcel_data)

        try:
            await self._build_environmental_section(pdf, parcel_data, db_pool)
        except Exception as e:
            self._render_unavailable_section(pdf, "Environmental", "Environmental data source", str(e))

        self._build_heritage_section(pdf, parcel_data)
        self._build_before_after_section(pdf, parcel_data)

        try:
            await self._build_nearby_development(pdf, parcel_data, db_pool)
        except Exception as e:
            self._render_unavailable_section(pdf, "Nearby Development", "Development pipeline data source", str(e))

        try:
            await self._build_market_context(pdf, db_pool)
        except Exception as e:
            self._render_unavailable_section(pdf, "Market Context", "CMHC housing data source", str(e))

        try:
            await self._build_demographic_profile(pdf, parcel_data, db_pool)
        except Exception as e:
            self._render_unavailable_section(pdf, "Demographic Profile", "StatsCan demographics data source", str(e))

        self._build_red_flags_summary(pdf, parcel_data)

        try:
            await self._build_data_currency(pdf, db_pool)
        except Exception as e:
            self._render_unavailable_section(pdf, "Data Currency", "Data currency tracking source", str(e))

        self._build_pro_forma(pdf, parcel_data)
        self._build_due_diligence(pdf, parcel_data)
        if parcel_data.comparables:
            self._build_comparable_sales(pdf, parcel_data)
        self._build_sources(pdf, parcel_data)
        self._build_footer(pdf, parcel_data)

        # Return PDF as bytes
        pdf_bytes = pdf.output()
        if isinstance(pdf_bytes, str):
            return pdf_bytes.encode("utf-8")
        if isinstance(pdf_bytes, bytearray):
            return bytes(pdf_bytes)
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
                    lot_area_sqm, geo_local_area, created_at
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
            try:
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
            except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.UndefinedColumnError):
                # Optional table in some local/dev schemas.
                scenarios = []
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
            try:
                risks = await conn.fetch(
                    """
                    SELECT category, description, severity, mitigation
                    FROM risk_assessments
                    WHERE pid = $1
                    ORDER BY severity DESC, category
                    """,
                    pid,
                )
            except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.UndefinedColumnError):
                risks = []
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
            try:
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
            except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.UndefinedColumnError):
                comps = []
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
            try:
                sources = await conn.fetch(
                    """
                    SELECT DISTINCT source_url, source_type
                    FROM intelligence_signals
                    WHERE pid = $1
                    LIMIT 10
                    """,
                    pid,
                )
            except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.UndefinedColumnError):
                sources = []
            data.sources = [s["source_url"] for s in sources if s.get("source_url")]

            # Due diligence evidence (optional; must not break report generation)
            try:
                data.due_diligence_evidence = await build_due_diligence_evidence(conn, pid)
            except Exception as e:
                logger.warning("Failed to build due diligence evidence for %s: %s", pid, str(e)[:200])
                data.due_diligence_evidence = None

            return data

    def _compute_buildable_sqft(
        self,
        lot_area_sqm: Decimal,
        entitled_fsr: Decimal,
    ) -> Decimal:
        """Compute buildable square footage from FSR."""
        return lot_area_sqm * entitled_fsr * Decimal("10.7639")

    def _render_unavailable_section(self, pdf: FPDF, section_name: str, source_name: str, error: str = ""):
        """Render a graceful degradation message when a section's data is unavailable."""
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"Data unavailable -- {source_name} timeout at {timestamp}"
        if error:
            msg += f" ({error})"
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(180, 0, 0)
        pdf.multi_cell(0, 5, msg)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(3)

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

    def _collect_red_flags(self, data: ParcelReport) -> list[dict]:
        """
        Collect red flags from parcel data for risk assessment.

        Auto-aggregates risk flags from:
        - Heritage designation (A/B/C)
        - Contamination status
        - Assessed value anomalies (outliers)
        - Data currency warnings

        Returns:
            List of dicts with keys: flag_name, severity, detail
        """
        flags = []

        # Heritage designation risk
        heritage = getattr(data, "heritage_designation", None)
        if heritage:
            severity_map = {"A": "high", "B": "medium", "C": "low"}
            severity = severity_map.get(heritage, "medium")
            flags.append({
                "flag_name": "Heritage Designation",
                "severity": severity,
                "detail": f"Property has heritage designation category {heritage}. "
                         f"Development may require heritage conservation approval."
            })

        # Contamination risk
        contamination = getattr(data, "contamination_status", None)
        if contamination and contamination not in ("Not Listed", "None", None):
            severity = "high" if "Active" in contamination else "medium"
            flags.append({
                "flag_name": "Environmental Contamination",
                "severity": severity,
                "detail": f"Site contamination status: {contamination}. "
                         f"May require environmental remediation."
            })

        # Assessed value anomaly (outlier detection)
        assessed = getattr(data, "assessed_value", None)
        median = getattr(data, "neighbourhood_median_assessed", None)
        std_dev = getattr(data, "neighbourhood_std_assessed", None)

        if assessed and median and std_dev:
            z_score = abs((assessed - median) / std_dev) if std_dev > 0 else 0
            if z_score > 2:  # More than 2 standard deviations
                severity = "medium"
                flags.append({
                    "flag_name": "Assessed Value Anomaly",
                    "severity": severity,
                    "detail": f"Assessed value (${assessed:,}) is {z_score:.1f} standard deviations "
                             f"from neighbourhood median (${median:,}). Verify assessment accuracy."
                })

        # Data currency warnings
        data_currency = getattr(data, "data_currency", [])
        if isinstance(data_currency, list):
            for warning in data_currency:
                if isinstance(warning, dict):
                    flags.append({
                        "flag_name": warning.get("source", "Data Currency"),
                        "severity": "low",
                        "detail": warning.get("message", "Data may be stale. Verify current status.")
                    })

        return flags

    def _build_before_after_section(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build before/after Bill 47 comparison table with colored uplift cells."""
        if not parcel_data.current_storeys and not parcel_data.entitled_storeys:
            return

        # Check if current zoning already exceeds Bill 47
        current_exceeds = (
            parcel_data.current_storeys
            and parcel_data.entitled_storeys
            and parcel_data.current_storeys > parcel_data.entitled_storeys
        )
        if current_exceeds:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_fill_color(200, 220, 255)
            pdf.cell(
                0, 8,
                "  Current zoning already exceeds Bill 47 entitlement",
                fill=True, ln=True,
            )
            pdf.ln(3)
            return

        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Before / After Bill 47", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(
            self.left_margin, pdf.get_y(),
            self.page_width - self.right_margin, pdf.get_y(),
        )
        pdf.ln(4)

        # Table header
        col_widths = [35, 45, 45, 40]
        total_w = sum(col_widths)
        # Scale to fit page
        avail = self.page_width - self.left_margin - self.right_margin
        scale = avail / total_w
        col_widths = [int(w * scale) for w in col_widths]

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(240, 240, 240)
        headers = ["Field", "Before Bill 47", "After Bill 47", "Uplift"]
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 6, h, border=1, fill=True)
        pdf.ln()

        # Compute before buildable SF
        current_fsr = parcel_data.current_fsr or Decimal("0")
        entitled_fsr = parcel_data.entitled_fsr or Decimal("1")
        lot_sqft = parcel_data.lot_area_sqft
        before_buildable = lot_sqft * current_fsr
        after_buildable = parcel_data.buildable_sqft
        buildable_delta = after_buildable - before_buildable

        storey_uplift = (
            (parcel_data.entitled_storeys - parcel_data.current_storeys)
            if parcel_data.entitled_storeys and parcel_data.current_storeys
            else 0
        )
        fsr_uplift = entitled_fsr - current_fsr

        rows = [
            (
                "Zoning",
                parcel_data.current_zoning or "N/A",
                f"TOD Tier (Bill 47)",
                "-",
                False,
            ),
            (
                "Max Height",
                f"{parcel_data.current_storeys or '?'} storeys",
                f"{parcel_data.entitled_storeys or '?'} storeys",
                f"+{max(0, storey_uplift)} st",
                storey_uplift > 0,
            ),
            (
                "Max FSR",
                f"{current_fsr}",
                f"{entitled_fsr}",
                f"+{max(Decimal('0'), fsr_uplift)}",
                fsr_uplift > 0,
            ),
            (
                "Buildable SF",
                f"{before_buildable:,.0f}",
                f"{after_buildable:,.0f}",
                f"+{max(Decimal('0'), buildable_delta):,.0f}",
                buildable_delta > 0,
            ),
        ]

        pdf.set_font("Helvetica", "", 9)
        for label, before, after, uplift, is_positive in rows:
            pdf.cell(col_widths[0], 6, label, border=1)
            pdf.cell(col_widths[1], 6, before, border=1)
            pdf.cell(col_widths[2], 6, after, border=1)
            if is_positive:
                pdf.set_fill_color(200, 255, 200)
                pdf.cell(col_widths[3], 6, uplift, border=1, fill=True)
            else:
                pdf.cell(col_widths[3], 6, uplift, border=1)
            pdf.ln()

        pdf.ln(4)

    def _build_hbu_section(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build Highest & Best Use analysis section."""
        hbu = getattr(parcel_data, "hbu_analysis", None)
        if not hbu:
            return

        analysis = hbu.get("highest_best_use", {}) if isinstance(hbu, dict) else {}
        if not analysis.get("recommended_use"):
            return

        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Highest & Best Use Analysis", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(
            self.left_margin, pdf.get_y(),
            self.page_width - self.right_margin, pdf.get_y(),
        )
        pdf.ln(4)

        # Recommendation
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(230, 230, 255)
        rec_text = f"  Recommended: {analysis['recommended_use']}"
        pdf.cell(0, 7, rec_text[:90], fill=True, ln=True)
        pdf.set_font("Helvetica", "", 8)
        basis = analysis.get("zoning_basis", "N/A")
        pdf.cell(0, 5, f"  Basis: {basis}", ln=True)
        pdf.ln(3)

        # Key metrics table
        avail = self.page_width - self.left_margin - self.right_margin
        col_w = int(avail / 4)
        headers = ["Height", "FSR", "Est. Units", "Buildable SF"]
        values = [
            f"{analysis.get('max_height_storeys', '?')} storeys",
            f"{analysis.get('max_fsr', '?')}",
            f"~{analysis.get('estimated_units', '?')}",
            f"{int(analysis.get('buildable_sqft', 0)):,}" if analysis.get("buildable_sqft") else "?",
        ]

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(240, 240, 240)
        for h in headers:
            pdf.cell(col_w, 6, h, border=1, fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for v in values:
            pdf.cell(col_w, 6, v, border=1)
        pdf.ln(4)

        # Feasibility verdict
        verdict = analysis.get("feasibility_verdict", "unknown")
        verdict_map = {
            "pencils": "Pencils",
            "marginal": "Marginal",
            "does_not_pencil": "Does Not Pencil",
        }
        verdict_label = verdict_map.get(verdict, verdict)
        if verdict == "pencils":
            pdf.set_fill_color(200, 255, 200)
        elif verdict == "marginal":
            pdf.set_fill_color(255, 255, 200)
        else:
            pdf.set_fill_color(255, 220, 220)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, f"  Feasibility: {verdict_label}", fill=True, ln=True)
        pdf.ln(3)

        # Constraints
        constraints = analysis.get("key_constraints", [])
        if constraints:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, "Constraints:", ln=True)
            pdf.set_font("Helvetica", "", 8)
            for c in constraints[:5]:
                text = c[:120] if isinstance(c, str) else str(c)[:120]
                pdf.cell(0, 4, f"  - {text}", ln=True)
            pdf.ln(2)

        # Narrative (truncated)
        narrative = analysis.get("narrative", "")
        if narrative:
            pdf.set_font("Helvetica", "I", 8)
            truncated = narrative[:800] if len(narrative) > 800 else narrative
            pdf.multi_cell(0, 4, truncated)
            pdf.ln(2)

        # Sources
        sources = hbu.get("sources", []) if isinstance(hbu, dict) else []
        if sources:
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(120, 120, 120)
            source_titles = [s.get("title", "") for s in sources[:5] if isinstance(s, dict)]
            source_text = "Sources: " + ", ".join(source_titles)
            pdf.cell(0, 4, source_text[:120], ln=True)
            pdf.set_text_color(0, 0, 0)

        pdf.ln(4)

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

    def _build_due_diligence(self, pdf: FPDF, parcel_data: ParcelReport):
        """Build due diligence checklist section (plus evidence with source links when available)."""
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

        pdf.ln(4)

        evidence = parcel_data.due_diligence_evidence
        if not evidence:
            return

        # fpdf2's multi_cell uses the "remaining width" from the current X position when w=0.
        # If X is at (or past) the right margin, it can throw:
        #   FPDFException: Not enough horizontal space to render a single character
        # Reset X defensively before we start emitting multi_cell content.
        pdf.set_x(self.left_margin)

        def _trunc(s: str, max_len: int = 160) -> str:
            s = (s or "").strip()
            return s if len(s) <= max_len else s[: max_len - 3].rstrip() + "..."

        def _wrap_url(url: str) -> str:
            # Insert soft break opportunities for long, unbroken URLs.
            u = (url or "").strip()
            if not u:
                return u
            return (
                u.replace("://", ":// ")
                .replace("/", "/ ")
                .replace("?", "? ")
                .replace("&", "& ")
                .replace("=", "= ")
            )

        def _pdf_safe(text: str) -> str:
            # Core fonts are Latin-1. Normalize common Unicode punctuation and replace the rest.
            t = (text or "").replace("\u00a0", " ")  # nbsp
            t = (
                t.replace("\u2014", "-")  # em dash
                .replace("\u2013", "-")  # en dash
                .replace("\u2212", "-")  # minus sign
                .replace("\u2018", "'")  # left single quote
                .replace("\u2019", "'")  # right single quote
                .replace("\u201c", '"')  # left double quote
                .replace("\u201d", '"')  # right double quote
                .replace("\u2026", "...")  # ellipsis
                .replace("\u2022", "-")  # bullet
                .replace("\u200b", "")  # zero-width space
            )
            # Prevent fpdf2 from raising when encountering an unbreakable "word" longer than the line width
            # (common with long URLs or tokens). Insert spaces periodically in long non-whitespace runs.
            out: list[str] = []
            run = 0
            for ch in t:
                out.append(ch)
                if ch.isspace():
                    run = 0
                    continue
                run += 1
                if run >= 60:
                    out.append(" ")
                    run = 0
            t = "".join(out)
            return t.encode("latin-1", "replace").decode("latin-1")

        def _mc(text: str) -> None:
            # Always start multi_cell lines at the left margin to avoid zero-width edge cases.
            pdf.set_x(self.left_margin)
            pdf.multi_cell(0, 5, _pdf_safe(text))

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Evidence (Auto-Collected)", ln=True)
        pdf.set_font("Helvetica", "", 9)

        # Utilities (water/sewer)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Utilities (proximity evidence):", ln=True)
        pdf.set_font("Helvetica", "", 9)
        for label, ue in [("Water", evidence.utilities.water), ("Sewer", evidence.utilities.sewer)]:
            if ue.status == "ok" and ue.nearest_distance_m is not None:
                src = _wrap_url(ue.source.url) if ue.source else ""
                _mc(f"- {label}: nearest line ~{ue.nearest_distance_m}m. Source: {src}")
            else:
                _mc(f"- {label}: {ue.status}. {_trunc(ue.note or '')}")

        pdf.ln(2)

        # Encumbrances proxy (easements)
        enc = evidence.encumbrances_proxy
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Encumbrances proxy (open-data easements):", ln=True)
        pdf.set_font("Helvetica", "", 9)
        if enc.status == "ok":
            src = _wrap_url(enc.source.url) if enc.source else ""
            _mc(f"- Easements intersecting parcel: {enc.easement_count}. Source: {src}")
            if enc.easements:
                sample = ", ".join(_trunc(e.easement_type, 40) for e in enc.easements[:3])
                _mc(f"- Sample easements: {sample}")
            if enc.note:
                _mc(f"- Note: {_trunc(enc.note)}")
        else:
            _mc(f"- Easements: {enc.status}. {_trunc(enc.note or '')}")

        pdf.ln(2)

        # Policy excerpts
        pol = evidence.ocp_policy_excerpts
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "OCP / policy excerpts (from ingested documents):", ln=True)
        pdf.set_font("Helvetica", "", 9)
        if pol.status == "ok" and pol.excerpts:
            for ex in pol.excerpts[:3]:
                title = ex.title or ex.source_type or "Source"
                header = f" ({ex.section_header})" if ex.section_header else ""
                src = _wrap_url(ex.source_url)
                _mc(f"- {title}{header}: {_trunc(ex.excerpt)} Source: {src}")
        else:
            _mc(f"- Policy excerpts: {pol.status}. {_trunc(pol.note or '')}")

        pdf.ln(3)

    # ── Sprint 6: New Due Diligence Report Sections ─────────────────────

    async def _build_executive_summary(self, pdf: FPDF, parcel_data: ParcelReport):
        """Auto-generated executive summary with optional LLM enhancement (<300 words)."""
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Executive Summary", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 10)
        addr = parcel_data.civic_address or parcel_data.pid
        zoning = parcel_data.current_zoning or "N/A"

        # Build template-based summary
        parts = [
            f"This report analyzes {addr} (PID: {parcel_data.pid}), "
            f"a {parcel_data.lot_area_sqft:.0f} sqft lot "
            f"currently zoned {zoning} in Vancouver, BC."
        ]

        if parcel_data.entitled_storeys and parcel_data.current_storeys:
            uplift = parcel_data.entitled_storeys - parcel_data.current_storeys
            if uplift > 0:
                parts.append(
                    f"Under Bill 47 Transit-Oriented Areas legislation, the property is entitled to "
                    f"{parcel_data.entitled_storeys} storeys (up from {parcel_data.current_storeys}), "
                    f"representing a {uplift}-storey density uplift."
                )
            else:
                parts.append(
                    f"The current zoning at {parcel_data.current_storeys} storeys already meets or "
                    f"exceeds the Bill 47 entitlement of {parcel_data.entitled_storeys} storeys."
                )

        if parcel_data.buildable_sqft:
            parts.append(f"Maximum buildable area is {parcel_data.buildable_sqft:,.0f} sqft.")

        if parcel_data.estimated_land_value:
            parts.append(f"Estimated land value is ${parcel_data.estimated_land_value:,}.")

        if parcel_data.assessed_value:
            parts.append(f"BC Assessment value is ${parcel_data.assessed_value:,}.")

        if parcel_data.value_delta and parcel_data.value_delta > 0:
            parts.append(
                f"The estimated value delta of ${parcel_data.value_delta:,} suggests potential "
                f"upside relative to current assessment."
            )

        # Collect red flags and include in template
        red_flags = self._collect_red_flags(parcel_data)
        risk_count = len(parcel_data.risk_flags) + len(red_flags)
        if risk_count > 0:
            high_risks = sum(1 for r in parcel_data.risk_flags if r.severity in ("high", "critical"))
            high_risks += sum(1 for f in red_flags if f.get("severity") in ("high", "critical"))
            risk_detail = f", including {high_risks} high/critical" if high_risks else ""
            parts.append(
                f"{risk_count} risk factor{'s' if risk_count != 1 else ''} identified{risk_detail}."
            )

        parts.append(
            "This automated report is for preliminary analysis only. "
            "Independent verification of all data points is recommended before making investment decisions."
        )

        template_summary = " ".join(parts)

        # Try LLM enhancement if available
        final_summary = template_summary
        try:
            from .intelligence.llm_backend import generate_chat

            # Build context for LLM
            system_prompt = (
                "You are a real estate analyst creating executive summaries for property reports. "
                "Create clear, professional summaries under 300 words. Focus on key opportunities and risks."
            )

            user_message = (
                f"Create a professional executive summary (max 300 words) for this property analysis:\n\n"
                f"{template_summary}\n\n"
                f"Enhance the clarity and professionalism while keeping all factual content intact. "
                f"Keep it under 300 words."
            )

            llm_text, model, latency = await generate_chat(
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=500,
            )

            # Validate word count (~300 words max)
            word_count = len(llm_text.split())
            if word_count <= 350:  # Allow 50 word buffer
                final_summary = llm_text
                logger.info(
                    "LLM-enhanced executive summary generated (model=%s, %d words, %.1fs)",
                    model, word_count, latency
                )
            else:
                logger.warning(
                    "LLM summary too long (%d words), falling back to template", word_count
                )
        except Exception as e:
            logger.warning("LLM enhancement failed, using template summary: %s", e)

        pdf.multi_cell(0, 5, final_summary)
        pdf.ln(4)

    def _build_title_ownership(self, pdf: FPDF, parcel_data: ParcelReport):
        """Title & Ownership section — BCA data + LTSA placeholder."""
        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Title & Ownership", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 10)

        if parcel_data.assessed_value:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(50, 6, "Assessed Value (BCA):")
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, f"${parcel_data.assessed_value:,}", ln=True)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(50, 6, "PID:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, parcel_data.pid, ln=True)

        if parcel_data.current_zoning:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(50, 6, "Zoning:")
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, parcel_data.current_zoning, ln=True)

        pdf.ln(2)

        # LTSA placeholder
        pdf.set_fill_color(240, 240, 255)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(
            0, 8,
            "  Full LTSA title search (ownership, encumbrances, charges) available in Pro tier",
            fill=True, ln=True,
        )
        pdf.ln(4)

    async def _build_environmental_section(
        self, pdf: FPDF, parcel_data: ParcelReport, db_pool: asyncpg.Pool
    ):
        """Environmental section — nearby contaminated sites within 500m."""
        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Environmental Assessment", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        sites = []
        try:
            async with db_pool.acquire() as conn:
                sites = await conn.fetch("""
                    SELECT cs.site_name, cs.address, cs.classification, cs.status,
                           cs.contamination_type, cs.date_reported,
                           ST_Distance(
                               cs.geom::geography,
                               p.geom::geography
                           ) AS distance_m
                    FROM contaminated_sites cs, parcels p
                    WHERE p.pid = $1
                      AND cs.geom IS NOT NULL
                      AND p.geom IS NOT NULL
                      AND ST_DWithin(cs.geom::geography, p.geom::geography, 500)
                    ORDER BY distance_m ASC
                    LIMIT 10
                """, parcel_data.pid)
        except Exception as e:
            logger.debug("Environmental section query failed (table may not exist): %s", e)

        pdf.set_font("Helvetica", "", 10)

        if not sites:
            pdf.set_fill_color(200, 255, 200)
            pdf.cell(0, 6, "  No contaminated sites found within 500m radius", fill=True, ln=True)
        else:
            pdf.set_fill_color(255, 230, 200)
            pdf.cell(
                0, 6,
                f"  {len(sites)} contaminated site{'s' if len(sites) != 1 else ''} found within 500m",
                fill=True, ln=True,
            )
            pdf.ln(2)

            pdf.set_font("Helvetica", "", 9)
            for site in sites[:5]:
                dist = int(site["distance_m"]) if site["distance_m"] else 0
                name = (site["site_name"] or site["address"] or "Unknown site")[:50]
                status = site["status"] or "Unknown"
                contam = site["contamination_type"] or ""
                line = f"- {name} ({dist}m) - {status}"
                if contam:
                    line += f", {contam}"
                pdf.cell(0, 5, line, ln=True)

        pdf.ln(4)

    def _build_heritage_section(self, pdf: FPDF, parcel_data: ParcelReport):
        """Heritage designation section — standalone heritage analysis."""
        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Heritage Designation", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        heritage = getattr(parcel_data, "heritage_designation", None)

        pdf.set_font("Helvetica", "", 10)

        if not heritage:
            pdf.set_fill_color(200, 255, 200)
            pdf.cell(0, 6, "  No heritage designation on record", fill=True, ln=True)
        else:
            # Severity coloring
            severity_map = {"A": "high", "B": "medium", "C": "low"}
            severity = severity_map.get(heritage, "medium")

            if severity == "high":
                pdf.set_fill_color(255, 200, 200)
            elif severity == "medium":
                pdf.set_fill_color(255, 230, 100)
            else:
                pdf.set_fill_color(255, 255, 200)

            pdf.cell(0, 6, f"  Heritage Designation Category: {heritage}", fill=True, ln=True)
            pdf.ln(2)

            pdf.set_font("Helvetica", "", 9)

            # Category significance
            significance = {
                "A": "Primary significance - highest level of heritage protection",
                "B": "Significant heritage value - moderate protection requirements",
                "C": "Contextual or character value - limited protection"
            }
            pdf.cell(0, 5, f"Significance: {significance.get(heritage, 'See city heritage registry')}", ln=True)
            pdf.ln(2)

            # Development implications
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, "Development Implications:", ln=True)
            pdf.set_font("Helvetica", "", 9)

            implications = {
                "A": [
                    "- Heritage alteration permit required for all exterior changes",
                    "- Demolition generally prohibited; facade retention likely mandatory",
                    "- Development timelines extended 6-12 months for heritage review",
                    "- Material and design specifications must match historical character"
                ],
                "B": [
                    "- Heritage alteration permit required for significant changes",
                    "- Partial facade retention may be required",
                    "- Heritage review adds 3-6 months to approval timeline",
                    "- Some flexibility in materials and design approach"
                ],
                "C": [
                    "- Heritage considerations apply but more flexible",
                    "- Focus on contextual fit rather than preservation",
                    "- Minor timeline impact (1-3 months)",
                    "- Opportunities for density bonusing with heritage features"
                ]
            }

            for line in implications.get(heritage, []):
                pdf.cell(0, 4, line, ln=True)

        pdf.ln(4)

    async def _build_market_context(self, pdf: FPDF, db_pool: asyncpg.Pool):
        """Market context — CMHC housing data for Vancouver CMA."""
        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Market Context (Vancouver CMA)", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        metrics = {}
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT metric, dwelling_type, value, ref_date
                    FROM cmhc_housing
                    WHERE cma_code = '933'
                      AND dwelling_type = 'total'
                    ORDER BY ref_date DESC
                    LIMIT 20
                """)
                for row in rows:
                    key = row["metric"]
                    if key not in metrics:
                        metrics[key] = {"value": row["value"], "ref_date": row["ref_date"]}
        except Exception as e:
            logger.debug("Market context query failed (table may not exist): %s", e)

        pdf.set_font("Helvetica", "", 10)

        if not metrics:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 6, "Market data source unavailable", ln=True)
        else:
            metric_labels = {
                "starts": "Housing Starts",
                "completions": "Completions",
                "under_construction": "Under Construction",
                "absorptions": "Absorptions",
            }
            for key, label in metric_labels.items():
                data = metrics.get(key)
                if data:
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.cell(50, 6, f"{label}:")
                    pdf.set_font("Helvetica", "", 10)
                    pdf.cell(0, 6, f"{data['value']:,} ({data['ref_date']})", ln=True)

        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 4, "Note: CSD-level data; may not reflect micro-market conditions.", ln=True)
        pdf.ln(4)

    async def _build_demographic_profile(
        self, pdf: FPDF, parcel_data: ParcelReport, db_pool: asyncpg.Pool
    ):
        """Demographic profile — StatsCan data at census tract level."""
        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Demographic Profile", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        demo = None
        boundary_note = None
        try:
            async with db_pool.acquire() as conn:
                lookup = await conn.fetchrow("""
                    SELECT census_tract, distance_to_tract_boundary_m
                    FROM parcel_census_lookup
                    WHERE pid = $1
                """, parcel_data.pid)

                if lookup and lookup["census_tract"]:
                    census_tract = lookup["census_tract"]
                    if (
                        lookup["distance_to_tract_boundary_m"]
                        and float(lookup["distance_to_tract_boundary_m"]) < 100
                    ):
                        boundary_note = (
                            f"Note: Parcel is within "
                            f"{int(lookup['distance_to_tract_boundary_m'])}m "
                            f"of census tract boundary. Adjacent tract data may also be relevant."
                        )

                    demo = await conn.fetchrow("""
                        SELECT population, population_5yr_growth, median_household_income,
                               avg_household_size, owner_pct, renter_pct,
                               dominant_dwelling_type, total_dwellings, median_age,
                               census_year
                        FROM statscan_demographics
                        WHERE census_tract = $1
                        ORDER BY census_year DESC
                        LIMIT 1
                    """, census_tract)
        except Exception as e:
            logger.debug("Demographic profile query failed (table may not exist): %s", e)

        pdf.set_font("Helvetica", "", 10)

        if not demo:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 6, "Demographic data source unavailable", ln=True)
        else:
            fields = [
                ("Census Year", str(demo["census_year"]) if demo["census_year"] else "N/A"),
                ("Population", f"{demo['population']:,}" if demo["population"] else "N/A"),
                ("5-Year Growth", f"{demo['population_5yr_growth']:.1f}%" if demo["population_5yr_growth"] is not None else "N/A"),
                ("Median Income", f"${demo['median_household_income']:,}" if demo["median_household_income"] else "N/A"),
                ("Avg Household Size", f"{demo['avg_household_size']:.1f}" if demo["avg_household_size"] is not None else "N/A"),
                ("Owner-Occupied", f"{demo['owner_pct']:.1f}%" if demo["owner_pct"] is not None else "N/A"),
                ("Renter-Occupied", f"{demo['renter_pct']:.1f}%" if demo["renter_pct"] is not None else "N/A"),
                ("Dominant Dwelling", demo["dominant_dwelling_type"] or "N/A"),
            ]

            for label, value in fields:
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(50, 6, f"{label}:")
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 6, value, ln=True)

        if boundary_note:
            pdf.ln(2)
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(0, 4, boundary_note, ln=True)

        pdf.ln(4)

    async def _build_nearby_development(
        self, pdf: FPDF, parcel_data: ParcelReport, db_pool: asyncpg.Pool
    ):
        """Nearby development activity within 500m radius."""
        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Nearby Development Activity (500m)", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        projects = []
        try:
            async with db_pool.acquire() as conn:
                projects = await conn.fetch("""
                    SELECT sp.address, sp.developer, sp.pipeline_stage,
                           sp.proposed_units, sp.proposed_storeys,
                           ST_Distance(
                               sp_parcel.geom::geography,
                               subject.geom::geography
                           ) AS distance_m
                    FROM supply_pipeline sp
                    JOIN parcels sp_parcel ON sp_parcel.pid = sp.parcel_pid
                    JOIN parcels subject ON subject.pid = $1
                    WHERE sp_parcel.geom IS NOT NULL
                      AND subject.geom IS NOT NULL
                      AND ST_DWithin(sp_parcel.geom::geography, subject.geom::geography, 500)
                    ORDER BY distance_m ASC
                    LIMIT 10
                """, parcel_data.pid)
        except Exception as e:
            logger.debug("Nearby development query failed (table may not exist): %s", e)

        pdf.set_font("Helvetica", "", 10)

        if not projects:
            pdf.cell(0, 6, "No active development applications found within 500m", ln=True)
        else:
            pdf.cell(
                0, 6,
                f"{len(projects)} development project{'s' if len(projects) != 1 else ''} within 500m:",
                ln=True,
            )
            pdf.ln(2)

            # Table header
            col_widths = [55, 30, 25, 20, 30]
            avail = self.page_width - self.left_margin - self.right_margin
            scale = avail / sum(col_widths)
            col_widths = [int(w * scale) for w in col_widths]

            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(240, 240, 240)
            for w, h in zip(col_widths, ["Address", "Stage", "Units", "Storeys", "Distance"]):
                pdf.cell(w, 5, h, border=1, fill=True)
            pdf.ln()

            pdf.set_font("Helvetica", "", 8)
            for proj in projects[:8]:
                addr = (proj["address"] or "N/A")[:28]
                stage = (proj["pipeline_stage"] or "N/A")[:16]
                units = str(proj["proposed_units"] or "?")
                storeys = str(proj["proposed_storeys"] or "?")
                dist = f"{int(proj['distance_m'])}m" if proj["distance_m"] else "?"

                pdf.cell(col_widths[0], 5, addr, border=1)
                pdf.cell(col_widths[1], 5, stage, border=1)
                pdf.cell(col_widths[2], 5, units, border=1)
                pdf.cell(col_widths[3], 5, storeys, border=1)
                pdf.cell(col_widths[4], 5, dist, border=1)
                pdf.ln()

        pdf.ln(4)

    def _build_red_flags_summary(self, pdf: FPDF, parcel_data: ParcelReport):
        """Red flags summary section — auto-aggregated risk flags with severity coloring."""
        flags = self._collect_red_flags(parcel_data)

        if not flags:
            return  # Skip section if no red flags

        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Red Flags Summary", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 9)

        severity_colors = {
            "high": (255, 100, 100),
            "medium": (255, 200, 100),
            "low": (255, 255, 150),
        }

        # Table header
        col_widths = [35, 55, 100]
        avail = self.page_width - self.left_margin - self.right_margin
        scale = avail / sum(col_widths)
        col_widths = [int(w * scale) for w in col_widths]

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(col_widths[0], 6, "Severity", border=1, fill=True)
        pdf.cell(col_widths[1], 6, "Category", border=1, fill=True)
        pdf.cell(col_widths[2], 6, "Details", border=1, fill=True)
        pdf.ln()

        # Flag rows
        pdf.set_font("Helvetica", "", 8)
        for flag in flags[:10]:  # Limit to 10 flags to avoid page overflow
            severity = flag.get("severity", "low")
            flag_name = flag.get("flag_name", "Unknown")
            detail = flag.get("detail", "")

            # Severity cell with color
            color = severity_colors.get(severity, (200, 200, 200))
            pdf.set_fill_color(*color)
            pdf.cell(col_widths[0], 6, severity.upper(), border=1, fill=True)

            # Category and details
            pdf.set_fill_color(255, 255, 255)
            pdf.cell(col_widths[1], 6, flag_name[:30], border=1)
            pdf.cell(col_widths[2], 6, detail[:80], border=1)
            pdf.ln()

        pdf.ln(3)

    async def _build_data_currency(self, pdf: FPDF, db_pool: asyncpg.Pool):
        """Data currency section — retrieval dates per source."""
        if pdf.get_y() > 250:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Data Currency", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        source_dates = {}
        queries = [
            ("BC Assessment (Parcels)", "SELECT MAX(updated_at) AS latest FROM parcels"),
            ("StatsCan Demographics", "SELECT MAX(retrieved_at) AS latest FROM statscan_demographics"),
            ("CMHC Housing Market", "SELECT MAX(retrieved_at) AS latest FROM cmhc_housing"),
            ("Contaminated Sites", "SELECT MAX(updated_at) AS latest FROM contaminated_sites"),
            ("Development Pipeline", "SELECT MAX(updated_at) AS latest FROM supply_pipeline"),
            ("Intelligence Signals", "SELECT MAX(extracted_at) AS latest FROM intelligence_signals"),
        ]

        try:
            async with db_pool.acquire() as conn:
                for label, query in queries:
                    try:
                        row = await conn.fetchrow(query)
                        if row and row["latest"]:
                            source_dates[label] = row["latest"].strftime("%Y-%m-%d")
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Data currency query failed: %s", e)

        pdf.set_font("Helvetica", "", 9)

        if source_dates:
            for label, date_str in source_dates.items():
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(55, 5, f"{label}:")
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(0, 5, f"Last updated {date_str}", ln=True)
        else:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 5, "Data currency information unavailable", ln=True)

        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 4, "All data subject to source availability. Verify critical data points independently.", ln=True)
        pdf.ln(4)

    def _build_sources(self, pdf: FPDF, parcel_data: ParcelReport):
        """Sprint 10.4: Sources & methodology section with citations and methodology."""
        # Add page break if needed
        if pdf.get_y() > 230:
            pdf.add_page()

        # Section header
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Sources & Methodology", ln=True)
        pdf.set_draw_color(100, 100, 100)
        pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
        pdf.ln(4)

        # Methodology subsection
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Methodology", ln=True)
        pdf.set_font("Helvetica", "", 8)
        methodology_lines = [
            "This report is generated by VanCity Lens using a multi-source data integration approach:",
            "",
            "1. Entitlement Analysis: Bill 47 TOA tiers computed via PostGIS spatial intersection of parcel "
            "centroids with transit station buffers (200m/400m/800m). Distance measured in BC Albers (EPSG:3005).",
            "2. Value Estimation: Buildable square footage (lot area x entitled FSR) multiplied by market "
            "price per buildable SF assumption. Three-scenario analysis (bull/base/bear) with +/-20% variance.",
            "3. Risk Assessment: Composite score from heritage proximity, view cone restrictions, environmental "
            "contamination, and political opposition signals.",
            "4. Data Precedence: When multiple sources conflict, BC Assessment Authority data takes precedence "
            "over City of Vancouver Open Data, which takes precedence over commercial listings (REW.ca).",
        ]
        for line in methodology_lines:
            if line == "":
                pdf.ln(2)
            else:
                pdf.multi_cell(0, 3.5, line)
                pdf.ln(1)

        pdf.ln(2)

        # Data sources table
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Data Sources", ln=True)
        pdf.ln(2)

        # Table header
        col_widths = [55, 50, 35, 30]
        headers = ["Source", "Origin", "Confidence", "Type"]
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_fill_color(240, 240, 240)
        for w, h in zip(col_widths, headers):
            pdf.cell(w, 4, h, border=1, fill=True)
        pdf.ln()

        # Standard sources always included
        standard_sources = [
            ("Parcel Boundaries", "Vancouver Open Data", "Verified", "Spatial"),
            ("Zoning Districts", "Vancouver Open Data", "Verified", "Regulatory"),
            ("Bill 47 TOA Tiers", "BC Legislation", "Calculated", "Regulatory"),
            ("Transit Stations", "TransLink GTFS", "Verified", "Spatial"),
            ("Assessed Values", "BC Assessment Authority", "Verified", "Financial"),
            ("Heritage Sites", "City of Vancouver", "Verified", "Constraint"),
            ("View Cones", "City of Vancouver", "Verified", "Constraint"),
            ("Contaminated Sites", "BC Min. of Environment", "Verified", "Constraint"),
            ("Market Listings", "REW.ca", "Estimated", "Financial"),
        ]

        pdf.set_font("Helvetica", "", 7)
        for row in standard_sources:
            for w, val in zip(col_widths, row):
                pdf.cell(w, 3.5, val, border=1)
            pdf.ln()

        pdf.ln(3)

        # URL citations if available
        if parcel_data.sources:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, "Verification Links", ln=True)
            pdf.set_font("Helvetica", "", 7)
            pdf.ln(1)

            for i, source in enumerate(parcel_data.sources[:8], 1):
                display_url = source[:80] + "..." if len(source) > 80 else source
                pdf.cell(8, 3.5, f"{i}.")
                pdf.cell(0, 3.5, display_url, ln=True)

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

    def _generate_investor_memo(self, parcel_data: ParcelReport) -> FPDF:
        """Generate an investor memo PDF with executive summary + investment thesis."""
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        pdf.set_margins(self.left_margin, self.top_margin, self.right_margin)

        # Title
        pdf.set_font("Helvetica", "B", 22)
        pdf.cell(0, 12, "Investment Memo", ln=True, align="C")
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 7, "VanCity Lens - Confidential", ln=True, align="C")
        pdf.set_draw_color(59, 130, 246)
        pdf.set_line_width(0.5)
        pdf.line(self.left_margin, pdf.get_y() + 2, self.page_width - self.right_margin, pdf.get_y() + 2)
        pdf.ln(8)

        # Executive Summary
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "1. Executive Summary", ln=True)
        pdf.set_font("Helvetica", "", 10)
        addr = parcel_data.civic_address or parcel_data.pid
        pdf.multi_cell(0, 5,
            f"Subject property at {addr} (PID: {parcel_data.pid}) is located in Vancouver, BC. "
            f"The property is zoned {parcel_data.current_zoning or 'N/A'} with a lot area of "
            f"{parcel_data.lot_area_sqm:.0f} sqm ({parcel_data.lot_area_sqft:.0f} sqft). "
            f"Buildable area under current entitlements is {parcel_data.buildable_sqft:,.0f} sqft."
        )
        pdf.ln(4)

        # Investment Thesis
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "2. Investment Thesis", ln=True)
        pdf.set_font("Helvetica", "", 10)
        if parcel_data.entitled_storeys and parcel_data.current_storeys:
            uplift = parcel_data.entitled_storeys - parcel_data.current_storeys
            pdf.multi_cell(0, 5,
                f"Bill 47 Transit-Oriented Areas legislation enables density uplift of "
                f"+{max(0, uplift)} storeys (from {parcel_data.current_storeys} to {parcel_data.entitled_storeys}). "
                f"This creates significant development potential in a supply-constrained market."
            )
        else:
            pdf.multi_cell(0, 5,
                "This property is positioned within a Transit-Oriented Area under Bill 47, "
                "creating potential for density uplift subject to entitlement confirmation."
            )
        pdf.ln(4)

        # Site Analysis
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "3. Site Analysis", ln=True)
        pdf.set_font("Helvetica", "", 10)
        self._build_parcel_overview(pdf, parcel_data)

        # Entitlement
        self._build_entitlement_analysis(pdf, parcel_data)

        # Financials
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "4. Financial Analysis", ln=True)
        self._build_pro_forma(pdf, parcel_data)

        # Value metrics
        pdf.set_font("Helvetica", "", 10)
        if parcel_data.estimated_land_value:
            pdf.cell(50, 6, "Estimated Land Value:")
            pdf.cell(0, 6, f"${parcel_data.estimated_land_value:,}", ln=True)
        if parcel_data.assessed_value:
            pdf.cell(50, 6, "Assessed Value:")
            pdf.cell(0, 6, f"${parcel_data.assessed_value:,}", ln=True)
        if parcel_data.asking_price:
            pdf.cell(50, 6, "Asking Price:")
            pdf.cell(0, 6, f"${parcel_data.asking_price:,}", ln=True)
        if parcel_data.value_delta:
            pdf.cell(50, 6, "Value Delta:")
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, f"${parcel_data.value_delta:,}", ln=True)
            pdf.set_font("Helvetica", "", 10)
        pdf.ln(4)

        # Risk Assessment
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "5. Risk Assessment", ln=True)
        self._build_risk_assessment(pdf, parcel_data)

        # Due Diligence
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "6. Due Diligence Checklist", ln=True)
        self._build_due_diligence(pdf, parcel_data)

        # Comparable Sales
        if parcel_data.comparables:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 8, "7. Comparable Sales", ln=True)
            self._build_comparable_sales(pdf, parcel_data)

        # Sources
        if parcel_data.sources:
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 8, "8. Sources & Citations", ln=True)
            self._build_sources(pdf, parcel_data)

        # Footer
        self._build_footer(pdf, parcel_data)

        return pdf


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
