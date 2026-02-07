# VanCity Lens — Validation Engine V2
## "From Napkin Math to Institutional-Grade Due Diligence"

### The Problem
V1 catches the basics (overpriced, lot too small, negative residual), but a Grade A parcel today might still have a heritage covenant, sit in a view cone with a 12-storey height cap, have 6 protected 100-year-old trees, or be on a contaminated gas station site. A top Vancouver realtor would catch all of these before presenting a deal. VanCity Lens should too.

---

## What We Have (V1) — 10 Checks

| # | Check | Data Source | Status |
|---|-------|-----------|--------|
| 1 | Price per buildable sqft | Calculated | ✅ Live |
| 2 | Ask/Assessed ratio | BCA Open Data | ✅ Live |
| 3 | Land-to-improvement ratio | BCA Open Data | ✅ 4,094 parcels |
| 4 | Heritage site proximity | Van Open Data | ✅ 2,359 sites |
| 5 | Floodplain intersection | Van Open Data | ✅ 8 zones |
| 6 | Easement count | Van Open Data | ✅ 16,293 easements |
| 7 | Lot adequacy / assembly risk | Calculated | ✅ Live |
| 8 | Supply saturation | PostGIS query | ✅ Live |
| 9 | Developer residual land value | Pro forma model | ✅ Live |
| 10 | Data completeness | Meta-check | ✅ Live |

---

## What We're Adding (V2) — 11 New Checks

### Phase 1: Spatial Risk Layers (Free Vancouver Open Data API)
All available via `opendata.vancouver.ca` API — no cost, no registration.

#### 11. View Cone Intersection 🔴
- **Dataset:** `view-cones` (23 protected view corridors)
- **Risk:** If a parcel falls inside a view cone, the entitled height from Bill 47 may be CAPPED by the view corridor. A Tier 1 parcel "approved for 20 storeys" might actually be limited to 8 by a view cone — destroying the entire pro forma.
- **Severity:** RED — this is a deal killer that most amateur investors miss
- **Implementation:** `ST_Intersects(parcel.geom, view_cone.geom)` → flag + cap entitled height
- **Impact on pro forma:** Recalculate buildable sqft using capped height

#### 12. Protected Tree Count 🟡
- **Dataset:** `public-trees` (185,526 trees with diameter, species, location)
- **Risk:** Vancouver's tree protection bylaw requires permits to remove trees >20cm diameter. Large trees (>50cm) near a parcel boundary can delay permitting by 3-6 months and cost $5K-25K per tree in arborist reports + replacement requirements.
- **Severity:** YELLOW (1-3 trees) / RED (4+ large trees on the lot)
- **Implementation:** Count trees within 15m of parcel centroid with diameter >30cm
- **Cost impact:** $5K-25K per tree removal + replacement planting

#### 13. Building Permit Activity (Competing Supply) 🟡
- **Dataset:** `issued-building-permits` (50,263 permits with geo, project value, type of work)
- **Risk:** If multiple large development permits ($5M+) have been issued within 500m in the last 2 years, the area faces supply saturation. Pre-sale absorption becomes harder.
- **Severity:** YELLOW (3-5 competing projects) / RED (6+ competing projects)
- **Implementation:** Count permits within 500m where `projectvalue > 5000000` and `issueyear >= 2024`
- **Fields:** `typeofwork`, `projectvalue`, `specificusecategory`, `geo_point_2d`

#### 14. Non-Market Housing Proximity 🟡
- **Dataset:** `non-market-housing` (641 social/co-op housing locations)
- **Risk:** If a non-market housing project exists on or adjacent to the parcel, the City's Rental Replacement Policy may require 1:1 replacement of existing rental units in any new development — a massive cost adder.
- **Severity:** YELLOW (within 100m) / RED (on the parcel itself)
- **Implementation:** `ST_DWithin(parcel.geom, nmh.geom, 0.001)` (~100m)
- **Cost impact:** $50K-150K per unit of rental replacement

#### 15. CD-1 Zoning Detection 🟡
- **Dataset:** `zoning-districts-and-labels` (1,592 zones)
- **Risk:** CD-1 (Comprehensive Development) zones have site-specific bylaws — the standard Bill 47 entitlement calculations may not apply. Each CD-1 has its own height/FSR/use rules defined in its individual bylaw. The parcel needs manual review.
- **Severity:** YELLOW — requires manual verification of the CD-1 bylaw
- **Implementation:** Check if parcel falls within a `zoning_category = 'CD-1'` zone
- **Note:** Can link to the specific CD-1 bylaw number for manual review

### Phase 2: Enhanced Economics

#### 16. Building Age Assessment 🟢/🟡
- **Dataset:** `property-tax-report` (has `year_built` field)
- **Risk:** A building <15 years old is unlikely to be demolished (owner has significant improvement value). A building >50 years old is a natural teardown candidate.
- **Severity:** GREEN (<15 yr: teardown candidate, low demo friction) / YELLOW (15-40 yr: moderate improvement value)
- **Implementation:** Fetch `year_built` from property tax report, add to parcel data
- **Already have:** land_value/improvement_value ratio (this adds context)

#### 17. Neighborhood Revenue Adjustment 📊
- **Current problem:** We use flat revenue per sqft ($1,100 highrise, $950 midrise, $850 lowrise) across all of Vancouver. But Kitsilano sells for $1,300/sqft while Renfrew-Collingwood sells for $850/sqft.
- **Implementation:** Use `geo_local_area` from building permits or property tax data to create a neighborhood price multiplier table:

| Neighborhood | Multiplier | Rationale |
|-------------|-----------|-----------|
| West End / Coal Harbour | 1.25 | Premium waterfront |
| Kitsilano / Point Grey | 1.20 | Established west side |
| Mount Pleasant / Cambie | 1.10 | Trendy, transit-rich |
| Marpole / Oakridge | 1.05 | Emerging, new transit |
| Renfrew / Killarney | 0.90 | East side discount |
| Southeast Van | 0.85 | Value market |

- **Impact:** This alone can flip a Grade A to Grade C or vice versa

#### 18. Holding Cost / Time Value of Money 📊
- **Current problem:** Our pro forma ignores the 18-36 month rezoning timeline. A developer holding $3M in land for 2 years at 6% interest burns $360K before breaking ground.
- **Implementation:** Add holding period estimate based on tier + construction type:
  - Tier 1 concrete: 30 months (rezoning + permit + preconstruction)
  - Tier 2 midrise: 24 months
  - Tier 3 lowrise: 18 months
- **Cost:** `asking_price × interest_rate × holding_months / 12`
- **Interest rate:** 6.5% (current Canadian prime + spread)

### Phase 3: Title & Legal Friction (Manual Verification Prompts)
These can't be automated via free API, but we can TELL the user what to check.

#### 19. Title Search Checklist 📋
- **What:** Generate a "Title Due Diligence Checklist" for each parcel showing what to verify at LTSA
- **Items to check:**
  - Certificates of Pending Litigation (CPL)
  - Restrictive covenants (may limit use/height)
  - Statutory rights of way (separate from easements)
  - Existing mortgages/liens (financial encumbrances)
  - Strata title status (requires 80% vote to dissolve)
- **Implementation:** Add a `due_diligence_checklist` field to the validation response with items + LTSA lookup URLs
- **Severity:** INFO — these are "go verify" prompts, not automated flags

#### 20. Contamination Risk Indicator 🔴
- **Data source:** BC Environmental Remediation Sites (available as KML/CSV from BC Data Catalogue)
- **Risk:** Former gas stations, dry cleaners, industrial sites require Phase 1/2/3 Environmental Site Assessments. Remediation can cost $500K-5M+ and delay projects by 1-3 years.
- **Implementation:** Download BC contaminated sites registry, load into PostGIS, spatial intersection check
- **Severity:** RED (confirmed contaminated) / YELLOW (within 200m of known site)
- **Note:** The dataset URL is `catalogue.data.gov.bc.ca/dataset/environmental-remediation-sites`

#### 21. Community Opposition Score 🟡
- **Dataset:** `community-gardens-and-food-trees` (170 locations) + non-market housing + heritage proximity
- **Risk:** Parcels near community gardens, heritage buildings, or social housing tend to face stronger NIMBY opposition during public hearings, adding 3-12 months to rezoning.
- **Implementation:** Composite score based on proximity to: community gardens (<200m), heritage sites (<100m), non-market housing (<100m)
- **Severity:** YELLOW (1 factor) / RED (3+ factors — "hot zone")

---

## Updated Grading System

### Current V1 Grading
Score starts at 100, deductions per risk. Simple A/B/C/D/F.

### Proposed V2 Grading — Multi-Dimensional

Instead of a single grade, produce a **3-axis assessment**:

| Axis | What It Measures | How It's Computed |
|------|-----------------|-------------------|
| **Economics** (A-F) | Is the money right? | Pro forma alpha, price/buildable sqft, assessed ratio, neighborhood adjustment |
| **Friction** (Low/Med/High) | How hard is the path to permit? | Heritage, view cones, trees, CD-1, easements, contamination, opposition |
| **Confidence** (★☆☆ to ★★★) | How complete is our data? | % of checks that returned data vs "unknown" |

**Example outputs:**
- `Economics: A | Friction: Low | Confidence: ★★★` → "Strong buy — clean path"
- `Economics: A | Friction: High | Confidence: ★★☆` → "High alpha but significant obstacles — experienced developer only"
- `Economics: D | Friction: Low | Confidence: ★★★` → "Overpriced — negotiate or pass"

The single-letter grade stays as a headline, but the detail underneath tells the real story.

---

## Data Pipeline Summary

### New Tables Needed (migration 005)

```sql
-- View cones (23 records)
CREATE TABLE IF NOT EXISTS view_cones (
    id SERIAL PRIMARY KEY,
    view_number TEXT,
    view_cone_name TEXT,
    geom GEOMETRY(Geometry, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Large trees near parcels (185K records, but we'll only index trees >30cm)
CREATE TABLE IF NOT EXISTS protected_trees (
    id SERIAL PRIMARY KEY,
    asset_id TEXT,
    common_name TEXT,
    diameter_cm NUMERIC,
    height_m NUMERIC,
    geom GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Non-market housing locations (641 records)
CREATE TABLE IF NOT EXISTS non_market_housing (
    id SERIAL PRIMARY KEY,
    name TEXT,
    address TEXT,
    project_status TEXT,
    total_units INT,
    geom GEOMETRY(Geometry, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Community gardens (170 records)
CREATE TABLE IF NOT EXISTS community_gardens (
    id SERIAL PRIMARY KEY,
    name TEXT,
    address TEXT,
    geom GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Add year_built + neighborhood to parcels
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS year_built INT;
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS geo_local_area TEXT;
```

### New Admin Endpoints
- `POST /load-view-cones` — from `view-cones` dataset
- `POST /load-trees` — from `public-trees` dataset (filter diameter > 30cm)
- `POST /load-non-market-housing` — from `non-market-housing` dataset
- `POST /load-community-gardens` — from `community-gardens-and-food-trees` dataset
- `POST /load-year-built` — from `property-tax-report` dataset (adds year_built to parcels)

### Updated Validation Engine
- `validation.py` grows from 10 checks to 21
- New `neighborhood_economics.py` module for revenue multipliers
- New `holding_costs.py` module for time-value calculations
- Updated `models.py` with multi-axis grading + due diligence checklist

---

## Implementation Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 🔴 P0 | View cones (deal-killer detection) | 2 hrs | CRITICAL — without this, we're showing fake heights |
| 🔴 P0 | Neighborhood revenue adjustment | 1 hr | CRITICAL — flat pricing is misleading |
| 🔴 P0 | Holding cost model | 1 hr | CRITICAL — ignoring time value is amateur |
| 🟡 P1 | Building permit activity (competing supply) | 2 hrs | HIGH — real market intelligence |
| 🟡 P1 | Protected trees | 2 hrs | HIGH — common surprise cost |
| 🟡 P1 | Building age (year_built) | 1 hr | MEDIUM — adds teardown context |
| 🟡 P1 | Non-market housing proximity | 1 hr | MEDIUM — rental replacement trigger |
| 🟢 P2 | CD-1 zoning detection | 1 hr | MEDIUM — manual review flag |
| 🟢 P2 | Community opposition score | 1 hr | LOW-MED — soft signal |
| 🟢 P2 | Due diligence checklist | 1 hr | HIGH — professional touch |
| 🟢 P2 | Contamination risk (BC registry) | 3 hrs | HIGH — but dataset requires download |

**Total estimated effort: ~16 hours of implementation**

**Recommended approach:** Ship P0 items first (4 hours), they change the most grades. Then P1 (6 hours) for completeness. P2 can follow.

---

## Frontend Changes

The popup already has the right structure. V2 changes:
1. Add **Friction meter** (Low/Med/High bar) next to the grade badge
2. Add **Confidence stars** (★★★)
3. Expand Risk Assessment section with new flag types
4. Add collapsible **"Due Diligence Checklist"** section at bottom
5. Color-code the pro forma numbers differently if neighborhood adjustment applied
6. Show **holding cost** as a line item in the pro forma

---

*This plan was researched against Vancouver Open Data (verified API schemas), BC Data Catalogue, LTSA, BC Courts, and Metro Vancouver data sources. All dataset slugs and field names have been verified against live API responses.*
