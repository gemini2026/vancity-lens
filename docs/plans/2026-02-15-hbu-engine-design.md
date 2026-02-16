# HBU Engine Design — Automated Highest & Best Use Analysis

**Date:** 2026-02-15
**Status:** Approved
**Priority:** High (Phase 1 of AI Pipeline Opportunities)

---

## Problem

When a developer evaluates a lot, the first question is: "What is the most profitable thing I can legally build here?" Answering this today requires 15-40 hours of manual research per parcel — reading zoning bylaws (50-200 pages), cross-referencing Bill 47 TOD entitlements, checking community plans, heritage overlays, view cones, and running pro forma math.

VanCity Lens already computes Bill 47 entitlements and basic pro forma. The gap is: **no LLM-powered synthesis** that reads the full regulatory context (zoning bylaw text, community plan policies, heritage constraints) and produces a confident "highest and best use" recommendation with narrative reasoning.

## Approach

Compose on the existing stack:

- **Entitlement engine** (`api/entitlement.py`) — Bill 47/44, community plans, setbacks
- **K2 RAG backend** (`api/intelligence/k2_client.py`, `retrieval_backend.py`) — document retrieval
- **LLM backend** (`api/intelligence/llm_backend.py`) — Gemini primary, Anthropic fallback
- **Report generator** (`api/report_generator.py`) — PDF output

No new infrastructure. A new **HBU orchestration module** calls existing services, retrieves regulatory document chunks from K2, sends everything to the LLM with an HBU-specific prompt, and returns structured + narrative output.

---

## 1. New Document Sources for K2

Add to `pipeline/sources.yaml` and ingest into existing K2 corpus:

| Document | Source | Cadence |
|---|---|---|
| Vancouver Zoning & Development Bylaw | vancouver.ca (PDF upload if Cloudflare blocks) | Monthly |
| Marpole Community Plan | shapeyourcity.ca/marpole-community-plan/documents | Weekly |
| West End Community Plan | shapeyourcity.ca/west-end-community-plan/documents | Weekly |
| Mount Pleasant Community Plan | shapeyourcity.ca | Weekly |
| Norquay Village Plan | shapeyourcity.ca | Weekly |
| Cambie Corridor Plan | shapeyourcity.ca | Weekly |
| Grandview-Woodland Plan | shapeyourcity.ca | Weekly |
| Heritage Register | vancouver.ca/heritage | Monthly |
| View Cone Maps | vancouver.ca/view-cones | Monthly |

These supplement the existing Broadway Plan, Vancouver Plan, and Rupert/Renfrew plan documents already in K2.

---

## 2. HBU Engine Architecture

### Flow

```
POST /api/v1/parcels/{pid}/hbu
  │
  ├─ 1. Fetch parcel data (existing DB query)
  ├─ 2. Run entitlement calc (existing entitlement.py)
  ├─ 3. Run pro forma (existing financing.py)
  ├─ 4. K2 retrieval: zoning bylaw chunks for this zoning district
  ├─ 5. K2 retrieval: community plan chunks for this neighborhood
  ├─ 6. K2 retrieval: heritage/view cone constraints for this location
  ├─ 7. LLM synthesis with HBU system prompt
  ├─ 8. Parse structured response
  └─ 9. Cache result in DB (7-day TTL)
```

### API Response Shape

```json
{
  "pid": "100-001-006",
  "address": "3838 Cambie Street",
  "current_zoning": "RS-1",
  "highest_best_use": {
    "recommended_use": "12-storey mixed-use residential",
    "zoning_basis": "Bill 47 Tier 1 TOD + C-2 base zoning",
    "max_height_storeys": 20,
    "max_fsr": 5.50,
    "estimated_units": 85,
    "unit_mix": {"studio": 15, "1br": 35, "2br": 25, "3br": 10},
    "buildable_sqft": 35521,
    "setbacks": {"front": "3.0m", "rear": "7.5m", "side": "1.2m"},
    "site_coverage": 0.60,
    "key_constraints": [
      "View cone caps effective height at 18 storeys on west side",
      "Heritage-adjacent lot — design panel review required"
    ],
    "pro_forma_summary": {
      "land_value_estimate": 28416696,
      "construction_cost_estimate": 21300000,
      "revenue_estimate": 42000000,
      "feasibility_verdict": "pencils"
    },
    "narrative": "This RS-1 lot at 3838 Cambie St is 165m from King Edward station...",
    "sources": [
      {"title": "Zoning Bylaw §4.7.1", "url": "...", "relevance": 0.92},
      {"title": "Cambie Corridor Plan p.42", "url": "...", "relevance": 0.88}
    ]
  },
  "confidence_score": 0.85,
  "cached_at": "2026-02-15T10:30:00Z",
  "expires_at": "2026-02-22T10:30:00Z"
}
```

### Caching Strategy

- Results cached in `hbu_analyses` table with 7-day TTL
- `GET /parcels/{pid}/hbu` returns cached result if fresh
- `POST /parcels/{pid}/hbu` forces re-analysis (or analyzes if no cache)
- Cache invalidated when parcel data or entitlement rules change

### Fallback

If K2 or LLM is unavailable:
- Return rule-engine-only results (entitlement + pro forma)
- `narrative` field set to null
- `confidence_score` reduced (no regulatory context verification)
- Frontend shows "Limited analysis — AI insights unavailable" banner

### Cost

- K2 retrieval: free (included in subscription)
- LLM: ~$0.05-0.15 per analysis (Gemini Flash for speed, Sonnet for quality)
- Cached results: zero incremental cost
- Expected usage: 50-200 analyses/day at scale = $2.50-30/day

---

## 3. Database Migration

```sql
-- db/034_hbu_analyses.sql
CREATE TABLE IF NOT EXISTS hbu_analyses (
    id SERIAL PRIMARY KEY,
    pid TEXT NOT NULL REFERENCES parcels(pid),
    analysis JSONB NOT NULL,
    narrative TEXT,
    confidence_score NUMERIC(3,2),
    llm_model TEXT,
    llm_cost_cents INTEGER DEFAULT 0,
    sources JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);
CREATE INDEX idx_hbu_analyses_pid ON hbu_analyses(pid);
CREATE INDEX idx_hbu_analyses_expires ON hbu_analyses(expires_at);
```

---

## 4. Frontend Component

`HBUAnalysis.tsx` — positioned in ParcelDetailPanel after BeforeAfterComparison.

### Behavior
- **On-demand**: User clicks "Analyze Highest & Best Use" button (avoids unnecessary LLM costs)
- **Loading**: Skeleton/spinner during K2+LLM processing (~3-5 seconds)
- **Cached indicator**: "Cached 2d ago" badge with refresh button
- **Collapsible sections**: Constraints and AI Analysis
- **Download**: "Download HBU Report" button generates standalone PDF

### Layout
```
┌─────────────────────────────────────────┐
│ ★ Highest & Best Use Analysis    [⟳]   │
│                                         │
│ Recommended: 12-storey mixed-use        │
│ Basis: Bill 47 Tier 1 + C-2 base       │
│                                         │
│ ┌────────┬────────┬──────────┐          │
│ │Height  │ FSR    │ Units    │          │
│ │20 st   │ 5.50   │ ~85      │          │
│ └────────┴────────┴──────────┘          │
│                                         │
│ Buildable: 35,521 SF                    │
│ Est. Land Value: $28.4M                 │
│ Construction: ~$21.3M                   │
│ Feasibility: ✅ Pencils                 │
│                                         │
│ ▼ Constraints (2)                       │
│ ▼ AI Analysis                           │
│                                         │
│ Sources: [Zoning Bylaw] [Cambie Plan]   │
│ [📄 Download HBU Report]               │
└─────────────────────────────────────────┘
```

---

## 5. PDF Report

### In existing parcel report
New section in `report_generator.py` after Before/After table:
- HBU recommendation headline
- Key metrics table (height, FSR, units, buildable SF)
- Pro forma summary
- Constraints list
- Truncated narrative (first 500 chars)

### Standalone HBU PDF
2-3 page focused report:
- **Page 1**: Parcel summary + recommended HBU + metrics table
- **Page 2**: 3-scenario pro forma + constraints + regulatory sources
- **Page 3**: Full AI narrative + citations + methodology disclaimer

---

## 6. LLM System Prompt

Dedicated HBU prompt in `hbu_prompts.py`:

```
You are a Vancouver real estate development analyst. Given a parcel's
location, current zoning, entitlement data, and relevant regulatory
document excerpts, determine the highest and best use.

You MUST:
1. Identify the maximum legally buildable envelope (height, FSR, units)
2. Consider ALL applicable regulations: base zoning, Bill 47 TOD overlay,
   community plan bonuses, view cones, heritage restrictions, setbacks
3. Recommend the most profitable use consistent with entitlements
4. Run a back-of-napkin feasibility check
5. Flag any constraints or red flags
6. Cite specific bylaw sections and plan policies

Return your analysis as structured JSON with a narrative field.
```

---

## 7. Files Summary

### New files (7)
| File | Purpose |
|---|---|
| `api/intelligence/hbu_engine.py` | Orchestrator module |
| `api/intelligence/hbu_routes.py` | API endpoints |
| `api/intelligence/hbu_prompts.py` | LLM system prompts |
| `db/034_hbu_analyses.sql` | Cache table |
| `frontend/src/components/HBUAnalysis.tsx` | Frontend component |
| `frontend/src/lib/hbu-api.ts` | API client |
| `tests/test_hbu_engine.py` | Tests |

### Modified files (4)
| File | Change |
|---|---|
| `pipeline/sources.yaml` | Add 9 new document sources |
| `api/intelligence/routes.py` or `api/main.py` | Mount HBU router |
| `api/report_generator.py` | Add HBU section to PDF |
| `frontend/src/components/ParcelDetailPanel.tsx` | Integrate HBUAnalysis component |

---

## 8. Implementation Order

1. **Document ingestion**: Add sources to `sources.yaml`, run K2 ingest
2. **Database migration**: Create `hbu_analyses` table
3. **HBU engine**: Build orchestrator (`hbu_engine.py` + `hbu_prompts.py`)
4. **API routes**: Wire up endpoints (`hbu_routes.py`)
5. **Tests**: Unit + integration tests
6. **Frontend component**: `HBUAnalysis.tsx` + API client
7. **PDF integration**: Add HBU section to report generator
8. **Standalone PDF**: HBU-specific report endpoint

---

## 9. Success Criteria

1. User clicks parcel → clicks "Analyze HBU" → gets structured recommendation in <5 seconds
2. Recommendation cites specific zoning bylaw sections and community plan policies
3. Pro forma feasibility verdict matches manual analyst judgment for seed parcels
4. PDF report includes HBU section with all key metrics
5. Cached results served instantly on repeat visits
6. Graceful degradation when LLM unavailable (rule-engine-only fallback)
7. All existing 4923 tests still pass + new HBU tests added
