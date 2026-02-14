# Due Diligence Evidence: Data Sources + Ingestion Plan

This repo now supports *evidence-backed* due diligence outputs for:

1. Utilities (water/sewer) proximity
2. Encumbrances proxy (easements)
3. OCP / policy excerpts (document-based citations)

The goal is to show the evidence + source links in:
- Parcel UI: `Due Diligence -> Evidence (Auto-Collected)`
- PDFs: Report + Investor Memo due diligence section

## Principles

- Prefer authoritative sources first; use open data as *early-stage evidence* and clearly label proxies.
- Every evidence item should include:
  - `status` (`ok`, `partial`, `not_loaded`, `not_configured`, `error`)
  - a human-readable note explaining limitations or next steps
  - `source.url` (where a human can verify)
- Some checklist items cannot be fully automated for <$200/mo due to paywalls and/or lack of official APIs. For those:
  - We include “manual confirm” instructions + source links in UI/PDF.

## Checklist Coverage (What We Can Source)

The checklist items we want to support end-to-end:

- Confirm parcel dimensions and lot area with **BC Land Titles (LTSA)**
- Verify current zoning with **City of Vancouver zoning map**
- Review OCP / plans for proposed zoning changes
- Check soil/environmental contamination records
- Confirm utility servicing (water, sewer, electrical, gas)
- Verify no tax arrears or encumbrances
- Review neighborhood rezoning patterns and pipeline
- Assess community opposition risk via council minutes
- Validate comparable sales used in valuation
- Confirm Bill 47 transit-oriented development eligibility

Current state in this repo:

- Auto-collected (implemented):
  - Water + sewer proximity (open data)
  - Encumbrances proxy via easements (open data)
  - Policy/plan/legislation excerpts (RAG citations; depends on ingestion)
- Partially automated (planned/iterative):
  - Zoning cross-check via City zoning GIS ingestion + bylaw citations
  - Rezoning / pipeline via signals + development/permit datasets
  - Environmental risk proxies (already exists in report as “hidden costs”; can be upgraded with evidence links)
- Manual confirm (likely remains manual due to access constraints):
  - LTSA title + parcel dimensions (paid)
  - Property tax arrears (municipal; often no public API)
  - Electrical + gas servicing (utility provider confirmation)
  - True comparable sales (MLS / Landcor / paid datasets)

## 1) Utilities Evidence (Water + Sewer)

### Data source (free)
- City of Vancouver Open Data (Opendatasoft)
  - Water distribution mains dataset (expected id: `water-distribution-mains`)
  - Sewer mains dataset (expected id: `sewer-mains`)

### Ingestion
- DB table: `utility_lines` (migration `db/030_utility_lines.sql`)
- Admin endpoints (require admin key):
  - `POST /api/v1/admin/load-utilities-water`
  - `POST /api/v1/admin/load-utilities-sewer`
  - Generic (if dataset naming changes): `POST /api/v1/admin/load-utility-lines`

### Evidence we compute (sufficient for "presence/proximity")
- Nearest line distance (meters) to parcel geometry
- Up to 3 nearest assets with basic attributes (when available): `asset_id`, `diameter_mm`, `material`, `line_type`
- Source link stored on each row (`source_url`)

### Limitations
- This is *not* a capacity/pressure/servicing confirmation. It is "there is infrastructure nearby" evidence.
- Electrical/gas servicing is usually not available as the same level of open data; treat as manual/utility-confirm step.

## 2) Encumbrances Proxy (Property Easements)

### Data source (free)
- City of Vancouver Open Data: property easements dataset (`property-easements`)

### Ingestion
- DB table: `property_easements` (existing migration)
- Admin endpoint:
  - `POST /api/v1/admin/load-easements`

### Evidence we compute
- Count of easement geometries intersecting the parcel
- Up to 10 sample records (easement label + plan number when present)
- Source link to dataset

### Limitations
- This is a *proxy* for encumbrances. The authoritative source is an LTSA title search.
- Use this for early-stage risk surfacing; confirm via title before LOI.

## 3) OCP / Policy Excerpts (Cited Snippets)

### Data sources (free)
- ShapeYourCity Vancouver document libraries (planning documents)
- BC Laws (regulations / legislation pages)
- BC Gov policy pages (e.g., TOD program overview)

### Ingestion (config-driven)
- Config file: `pipeline/sources.yaml`
- Ingestion script: `scripts/ingest_sources.py`
  - `--dry-run` shows discovered URLs
  - Default mode stores documents; `--process` chunks + embeds + extracts signals (requires API keys)

### Storage
- `documents` table stores the URL/title/full text
- `document_chunks` stores searchable chunks + tsvector (and optional embeddings)

### Evidence we compute
- Full-text search over `document_chunks` for parcel-relevant terms:
  - local area (e.g., `geo_local_area`)
  - zoning
  - plan/policy keywords
- Return top excerpts with:
  - title
  - URL
  - optional section header
  - excerpt text (truncated)

### Limitations
- Excerpts are only as good as what has been ingested and chunked.
- Some `vancouver.ca` sources are Cloudflare-protected; ShapeYourCity sources are preferred.

## 4) Parcel Dimensions + Lot Area (LTSA / Survey Plan)

### Authoritative source (paid)
- Land Title and Survey Authority of BC (LTSA): title + plan search

### What we can do in-app (budget-friendly)
- Treat LTSA as a *manual confirm* step:
  - UI/PDF shows “Manual confirm via LTSA” with link + instructions.
- Cross-check with free/open sources (non-authoritative):
  - Parcel geometry-derived area (already in `parcels.lot_area_sqm`)
  - BC Assessment (sometimes lists lot size; not authoritative)

### Future (if budget allows)
- If an official LTSA API / reseller integration is available within budget:
  - Store a “title search performed at” timestamp + a redacted reference id
  - Never store raw title PDFs unless explicitly required (PII risk)

## 5) Current Zoning (City of Vancouver)

### Data sources (free)
- City of Vancouver zoning map + zoning bylaw (human verification)
- City of Vancouver Open Data: zoning polygons (GIS)

### Ingestion plan
- Add a zoning polygons table (e.g., `zoning_districts`) with:
  - district code, name, bylaw reference URL
  - geometry
- Compute:
  - parcel → zoning district intersection
  - evidence output:
    - zoning code(s)
    - intersection area % (optional)
    - source URL(s)

### Limitations
- CD-1 / site-specific bylaws can be complex; “current_zoning” should be verified against official map + bylaw.

## 6) OCP / Plan / Proposed Zoning Changes (City Plans)

### Data sources (free)
- ShapeYourCity Vancouver plan documents (preferred: usually accessible to non-browser scrapers)
- BC Laws for provincial regs impacting entitlements (Bill 47 / TOA / TOD-related regs)

### Ingestion plan
- Keep `pipeline/sources.yaml` focused on:
  - plan summaries + boards + appendices (often contain the actual height/density tables)
  - stable PDFs hosted on `syc.vancouver.ca` or S3 redirects
- Present evidence as:
  - excerpt(s) + source URL
  - section header (when present)
  - “relevance” label (“Broadway Plan”, “Vancouver Plan”, “TOA regulation”, etc.)

## 7) Environmental / Contamination Records

### Sources (mixed)
- Provincial contaminated sites registries (may not be fully open or easy to automate)
- Proxy indicators (free/open):
  - known risky business types nearby (gas stations, dry cleaners) already used in “hidden costs”
  - floodplain / liquefaction / soft soil layers (if already present in repo datasets)

### Plan
- Short-term: present proxy indicators with clear labels + source links.
- Medium-term: add a “Contamination registry” check as manual confirm:
  - link to registry search instructions
  - fields user can paste back (site id, status, last update)

## 8) Utility Servicing (Electrical + Gas)

### Sources (often not open)
- BC Hydro (electric) and FortisBC (gas) typically require utility confirmation

### Plan
- Keep as manual confirm:
  - UI/PDF shows contacts + “confirm servicing capacity and connection requirements”
- Optional proxies:
  - nearest substation / major infrastructure if a reliable open dataset exists (not assumed)

## 9) Tax Arrears + Encumbrances

### Tax arrears
- Often municipal systems without public API
- Plan: manual confirm step with City of Vancouver property tax lookup workflow

### Encumbrances
- Authoritative: LTSA title search (paid)
- Proxy (implemented): easements intersection count + sample records

## 10) Rezoning Patterns + Pipeline

### Sources (free/open)
- ShapeYourCity development application pages + document libraries (already supported by intel ingestion)
- City open data: development permits / building permits (if available and stable)

### Plan
- Use the intelligence pipeline to populate:
  - rezoning / permit / policy “signals” with citations
- Add neighborhood-level aggregation:
  - counts by local area and last 30/90/365 days
  - “similar nearby approvals” evidence blocks

## 11) Community Opposition Risk (Council / Public Hearing)

### Sources (free, but access can be blocked)
- Council agendas/minutes are authoritative but can be Cloudflare-protected for non-browser clients.
- Alternative sources:
  - ShapeYourCity engagement summaries
  - publicly hosted PDFs on accessible domains

### Plan
- Ingest what is accessible via ShapeYourCity.
- For blocked council sources:
  - present a manual confirm step + link to council meeting page
  - optionally allow users to upload/download a PDF and ingest locally

## 12) Comparable Sales Validation

### Constraints
- True comps are usually gated (MLS/Landcor/etc.).

### Plan (budget-friendly)
- Support “user-provided comps” in UI:
  - address/PID, sale date, price, lot size, notes, source link
  - show in PDF as a comps appendix with citations (user links)
- Use free anchors:
  - BC Assessment values (already in model) as a sanity check, not a comp dataset

## 13) Bill 47 / TOA Eligibility

### Sources (free)
- Provincial TOA tiers dataset / GeoJSON (already used by the entitlement engine)
- BC Laws / regulations citations (ingested into RAG)

### Evidence we should show
- Applicable tier (e.g., 1/2/3)
- Distance bands / station proximity logic (what rule triggered)
- Source URL(s) to the regulation / dataset
