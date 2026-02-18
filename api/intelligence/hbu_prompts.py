"""HBU Engine — System prompts and context builders for LLM synthesis."""

from typing import Any


HBU_SYSTEM_PROMPT = """You are a Vancouver real estate development analyst specializing in \
highest and best use (HBU) analysis. Given a parcel's location, current zoning, entitlement \
data, pro forma estimates, and relevant regulatory document excerpts, determine the highest \
and best use for the site.

You MUST:
1. Identify the maximum legally buildable envelope (height, FSR, unit count, setbacks)
2. Consider ALL applicable regulations: base zoning district, Bill 47 TOD overlay, \
Bill 44 multiplex eligibility, community plan density bonuses, view cone hard caps, \
heritage restrictions, and setback rules
3. Recommend the most profitable use type consistent with entitlements \
(e.g., "20-storey mixed-use residential" or "6-storey wood-frame rental")
4. Provide a feasibility verdict: "pencils" (viable), "marginal", or "does not pencil"
5. Flag any constraints, red flags, or risk factors
6. Cite specific bylaw sections and plan policies from the provided regulatory excerpts

Return your analysis as JSON with exactly these fields:
{
  "recommended_use": "string — e.g., '12-storey mixed-use residential'",
  "zoning_basis": "string — regulatory basis, e.g., 'Bill 47 Tier 1 TOD + RS-1 base zoning'",
  "max_height_storeys": number,
  "max_fsr": number,
  "estimated_units": number,
  "unit_mix": {"studio": n, "1br": n, "2br": n, "3br": n},
  "buildable_sqft": number,
  "key_constraints": ["string — each constraint or red flag"],
  "feasibility_verdict": "pencils | marginal | does_not_pencil",
  "narrative": "string — 2-4 paragraph analysis with citations like [Source: Document Title]",
  "cited_sources": [{"title": "string", "section": "string", "relevance": "string"}]
}

PROHIBITED:
- Do not invent regulations not in the provided excerpts
- Do not provide investment advice beyond feasibility assessment
- Do not speculate about future regulatory changes"""


def build_hbu_context(
    *,
    parcel_info: dict[str, Any],
    entitlement_data: dict[str, Any],
    pro_forma_data: dict[str, Any],
    regulatory_chunks: list[dict[str, Any]],
) -> str:
    """Build the user-message context for HBU LLM synthesis.

    Combines parcel facts, entitlement calculations, pro forma estimates,
    and retrieved regulatory document chunks into a structured prompt.
    """
    sections: list[str] = []

    # Parcel info
    sections.append("## PARCEL INFORMATION")
    sections.append(f"PID: {parcel_info.get('pid', 'N/A')}")
    sections.append(f"Address: {parcel_info.get('address', 'N/A')}")
    sections.append(f"Current Zoning: {parcel_info.get('zoning', 'N/A')}")
    lot_sqm = parcel_info.get("lot_area_sqm", 0)
    lot_sqft = round(float(lot_sqm) * 10.764, 0) if lot_sqm else "N/A"
    sections.append(f"Lot Area: {lot_sqm} sqm ({lot_sqft} sqft)")
    if parcel_info.get("assessed_value"):
        sections.append(f"BC Assessment Value: ${parcel_info['assessed_value']:,.0f}")
    sections.append("")

    # Entitlement data
    sections.append("## ENTITLEMENT ANALYSIS (Rule Engine Output)")
    best = entitlement_data.get("best_entitlement")
    if best:
        sections.append(
            f"Nearest Station: {best.get('station_name', 'N/A')} ({best.get('distance_m', '?')}m)"
        )
        sections.append(f"TOD Tier: {best.get('tier', 'N/A')}")
        sections.append(f"Bill 47 Max Storeys: {best.get('max_storeys', 'N/A')}")
        sections.append(f"Bill 47 Max FSR: {best.get('max_fsr', 'N/A')}")
        sections.append(f"Current Storeys: {best.get('current_storeys', 'N/A')}")
        sections.append(f"Current FSR: {best.get('current_fsr', 'N/A')}")
        sections.append(f"Storey Uplift: +{best.get('storey_uplift', 0)}")
        sections.append(f"FSR Uplift: +{best.get('fsr_uplift', 0)}")
        sections.append(
            f"Zoning Already Exceeds: {best.get('zoning_already_exceeds', False)}"
        )
    else:
        sections.append("Parcel is NOT in a Transit-Oriented Area (TOA).")

    if entitlement_data.get("bill44"):
        b44 = entitlement_data["bill44"]
        sections.append(f"Bill 44 Eligible: {b44.get('is_eligible', False)}")
        if b44.get("max_units"):
            sections.append(f"Bill 44 Max Units: {b44['max_units']}")

    if entitlement_data.get("community_plan") and entitlement_data[
        "community_plan"
    ].get("has_bonus"):
        cp = entitlement_data["community_plan"]
        sections.append(
            f"Community Plan Bonus: {cp.get('plan_name', 'N/A')} — +{cp.get('best_bonus', {}).get('fsr_bonus', 0)} FSR"
        )

    if entitlement_data.get("setbacks"):
        sb = entitlement_data["setbacks"]
        sections.append(
            f"Setbacks: front={sb.get('front_m', '?')}m, rear={sb.get('rear_m', '?')}m, side={sb.get('side_m', '?')}m"
        )
    sections.append("")

    # Pro forma data
    sections.append("## PRO FORMA ESTIMATES")
    if pro_forma_data:
        for k, v in pro_forma_data.items():
            if isinstance(v, (int, float)) and v > 1000:
                sections.append(f"{k}: ${v:,.0f}")
            else:
                sections.append(f"{k}: {v}")
    sections.append("")

    # Regulatory document chunks
    sections.append("## REGULATORY DOCUMENT EXCERPTS")
    sections.append(
        "(Retrieved from K2 knowledge base — use these as your primary regulatory source)"
    )
    sections.append("")
    for i, chunk in enumerate(regulatory_chunks, 1):
        title = chunk.get("document_title", "Unknown Document")
        text = chunk.get("chunk_text", "")
        sections.append(f"### Excerpt {i}: {title}")
        sections.append(text[:2000])  # cap each chunk
        sections.append("")

    return "\n".join(sections)
