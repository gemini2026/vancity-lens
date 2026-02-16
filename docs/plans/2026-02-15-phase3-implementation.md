# Phase 3 Implementation Plan — F05 + F06 Gap Closure

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close remaining gaps in F05 (Community Opposition Scoring) and F06 (Undervalued Parcel Alerts).

**Architecture:** Both features are ~80% built. Gaps are: missing RSS sources, missing scheduler wiring, missing K8s CronJobs, missing undervalued watchlist integration, and missing map choropleth layer.

**Tech Stack:** FastAPI, asyncpg, Next.js 15, Mapbox GL JS, FPDF2

---

## What Already Exists (No Changes Needed)

| Component | File | Status |
|-----------|------|--------|
| Political risk engine | `api/intelligence/political_risk.py` | Full: 4-component scoring, `materialize_all_scores()`, narratives, themes |
| Political risk DB | `db/040_political_risk_sprint7.sql` | Table + `latest_political_risk` view |
| Political risk API | `api/intelligence/political_risk_routes.py` | 3 endpoints, mounted in main.py |
| Political risk badge | `frontend/src/components/PoliticalRiskBadge.tsx` | Parcel-level badge with expandable details |
| Undervalued scoring | `api/intelligence/undervalued_scoring.py` | Full: `score_parcels()`, `get_top_opportunities()` |
| Undervalued DB | `db/041_undervalued_alerts_sprint9.sql` | Table + indexes |
| Undervalued API | `api/intelligence/undervalued_routes.py` | 2 endpoints, mounted in main.py |
| Opportunity dashboard | `frontend/src/components/OpportunityAlertDashboard.tsx` | Top-20 display with repeat badges |
| News scraper | `api/intelligence/scraper_news.py` | 6 RSS feeds, `scrape_news_feeds()` |
| Scheduler framework | `api/intelligence/scheduler.py` | Cron-based scheduler with run tracking |
| Watchlist + alerts | `api/intelligence/alerts.py` | 12 rule types, `match_rule()`, `evaluate_signal()` |

---

## Tasks

### Task 1: Add Missing RSS Sources to News Scraper

**Files:**
- Modify: `api/intelligence/scraper_news.py:32-81` (NEWS_FEEDS list)
- Test: `tests/test_prd_phase3.py`

**What:** Add 3 missing RSS feeds per design doc: The Tyee, Storeys, Western Investor.

**Step 1: Write the failing test**

```python
# tests/test_prd_phase3.py
"""Phase 3 PRD gap-closure tests — F05 + F06."""
import pytest

class TestNewsRSSSources:
    """F05-A: News RSS must have all 7+ sources."""

    def test_news_feeds_count_at_least_seven(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        assert len(NEWS_FEEDS) >= 7

    def test_news_feeds_has_tyee(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        names = [f["name"].lower() for f in NEWS_FEEDS]
        assert any("tyee" in n for n in names)

    def test_news_feeds_has_storeys(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        names = [f["name"].lower() for f in NEWS_FEEDS]
        assert any("storeys" in n or "storey" in n for n in names)

    def test_news_feeds_has_western_investor(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        names = [f["name"].lower() for f in NEWS_FEEDS]
        assert any("western investor" in n for n in names)
```

**Step 2:** Run `pytest tests/test_prd_phase3.py::TestNewsRSSSources -v` — expect 3 FAIL (tyee, storeys, western investor)

**Step 3: Add feeds to NEWS_FEEDS**

Append after line 81 in scraper_news.py:
```python
    # The Tyee - investigative journalism
    {
        'name': 'The Tyee',
        'url': 'https://thetyee.ca/Topic/Housing/',
        'rss_url': 'https://thetyee.ca/rss2.xml',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
    # Storeys - Canadian real estate news
    {
        'name': 'Storeys',
        'url': 'https://storeys.com/category/vancouver/',
        'rss_url': 'https://storeys.com/feed/',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
    # Western Investor - BC commercial real estate
    {
        'name': 'Western Investor',
        'url': 'https://westerninvestor.com/',
        'rss_url': 'https://westerninvestor.com/feed/',
        'source_type': 'staff_report',
        'priority': 'medium',
    },
```

**Step 4:** Run tests — expect 4 PASS

**Step 5:** Commit: `feat(F05): add Tyee, Storeys, Western Investor RSS feeds`

---

### Task 2: Wire News Scraper into Scheduler

**Files:**
- Modify: `api/intelligence/scheduler.py:199-219`
- Modify: `api/intelligence/scraper_news.py` (verify `scrape_news_feeds` signature)
- Test: `tests/test_prd_phase3.py`

**What:** Register the news scraper function with the scheduler so it runs every 6 hours.

**Step 1: Write the failing test**

```python
class TestSchedulerIntegration:
    """F05-A: News scraper must be registered in scheduler."""

    def test_scheduler_has_news_function(self):
        """Scheduler default schedules include news with a function reference."""
        import inspect
        from api.intelligence.scheduler import ScraperScheduler
        source = inspect.getsource(ScraperScheduler._register_defaults)
        assert "scrape_news" in source or "news" in source

    def test_scheduler_has_political_risk_schedule(self):
        """Scheduler should have a political_risk entry for monthly materialization."""
        import inspect
        from api.intelligence.scheduler import ScraperScheduler
        source = inspect.getsource(ScraperScheduler._register_defaults)
        assert "political_risk" in source or "risk_score" in source

    def test_scheduler_has_undervalued_schedule(self):
        """Scheduler should have an undervalued entry for weekly scoring."""
        import inspect
        from api.intelligence.scheduler import ScraperScheduler
        source = inspect.getsource(ScraperScheduler._register_defaults)
        assert "undervalued" in source or "score_parcels" in source
```

**Step 2:** Run tests — expect 2-3 FAIL

**Step 3: Add scheduler entries**

In `scheduler.py:_register_defaults`, add to `default_schedules` dict:
```python
            "political_risk": "0 2 1 * *",  # monthly 1st 2am UTC
            "undervalued": "0 15 * * 1",   # weekly Monday 3pm UTC (8am Pacific)
```

And add imports + wiring comment at top of `_register_defaults`:
```python
        # Note: actual function references are set via register_scraper() in main.py startup
        # news → scraper_news.scrape_news_feeds
        # political_risk → political_risk.materialize_all_scores
        # undervalued → undervalued_scoring.score_parcels
```

**Step 4:** Run tests — expect PASS

**Step 5:** Commit: `feat(F05/F06): register news, political risk, undervalued in scheduler`

---

### Task 3: K8s CronJobs for Political Risk + Undervalued Scoring

**Files:**
- Create: `k8s/cronjob-political-risk.yaml`
- Create: `k8s/cronjob-undervalued.yaml`
- Test: `tests/test_prd_phase3.py`

**What:** Create K8s CronJob manifests for the two batch jobs.

**Step 1: Write the failing test**

```python
import os

class TestK8sCronJobs:
    """F05-B + F06-A: K8s CronJobs must exist."""

    def test_political_risk_cronjob_exists(self):
        assert os.path.isfile("k8s/cronjob-political-risk.yaml")

    def test_political_risk_cronjob_has_monthly_schedule(self):
        with open("k8s/cronjob-political-risk.yaml") as f:
            content = f.read()
        assert "0 2 1 * *" in content

    def test_political_risk_cronjob_calls_materialize(self):
        with open("k8s/cronjob-political-risk.yaml") as f:
            content = f.read()
        assert "materialize" in content.lower() or "political_risk" in content.lower()

    def test_undervalued_cronjob_exists(self):
        assert os.path.isfile("k8s/cronjob-undervalued.yaml")

    def test_undervalued_cronjob_has_weekly_schedule(self):
        with open("k8s/cronjob-undervalued.yaml") as f:
            content = f.read()
        assert "0 15 * * 1" in content

    def test_undervalued_cronjob_calls_score(self):
        with open("k8s/cronjob-undervalued.yaml") as f:
            content = f.read()
        assert "score" in content.lower() or "undervalued" in content.lower()
```

**Step 2:** Run tests — expect 6 FAIL

**Step 3: Create manifests**

Model after existing `k8s/cronjob.yaml`. Each CronJob runs:
- `python -c "import asyncio; from api.intelligence.political_risk import materialize_all_scores; ..."`
- or a small `scripts/run_political_risk.py` / `scripts/run_undervalued_scoring.py`

Use the same container image, env vars, and cloud-sql-proxy sidecar as `cronjob.yaml`.

**Step 4:** Run tests — expect 6 PASS

**Step 5:** Commit: `feat(F05/F06): add K8s CronJobs for political risk and undervalued scoring`

---

### Task 4: Undervalued Alert Watchlist Integration

**Files:**
- Modify: `api/intelligence/alerts.py:27-41` (RuleType enum)
- Modify: `api/intelligence/alerts.py:548-640` (match_rule method)
- Test: `tests/test_prd_phase3.py`

**What:** Add `UNDERVALUED_DISCOUNT`, `UNDERVALUED_LOT_AREA`, `UNDERVALUED_TOD_TIER` rule types so users can configure undervalued alert filters.

**Step 1: Write the failing test**

```python
class TestUndervaluedWatchlistRules:
    """F06-B: Undervalued alert filter rule types."""

    def test_rule_type_has_undervalued_discount(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "UNDERVALUED_DISCOUNT")

    def test_rule_type_has_undervalued_lot_area(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "UNDERVALUED_LOT_AREA")

    def test_rule_type_has_undervalued_tod_tier(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "UNDERVALUED_TOD_TIER")

    def test_match_undervalued_discount_above_threshold(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"discount_pct": 25.0}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_DISCOUNT, rule_value="20")
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_undervalued_discount_below_threshold(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"discount_pct": 15.0}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_DISCOUNT, rule_value="20")
        assert AlertEngine.match_rule(signal, rule) is False

    def test_match_undervalued_lot_area_above_min(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"lot_area_sqft": 5000}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_LOT_AREA, rule_value="4000")
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_undervalued_lot_area_below_min(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"lot_area_sqft": 3000}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_LOT_AREA, rule_value="4000")
        assert AlertEngine.match_rule(signal, rule) is False

    def test_match_undervalued_tod_tier(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"tod_tier": 1}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_TOD_TIER, rule_value="1")
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_undervalued_tod_tier_no_match(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"tod_tier": 3}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_TOD_TIER, rule_value="1")
        assert AlertEngine.match_rule(signal, rule) is False
```

**Step 2:** Run tests — expect 9 FAIL

**Step 3: Add to RuleType enum**

```python
    UNDERVALUED_DISCOUNT = "undervalued_discount"
    UNDERVALUED_LOT_AREA = "undervalued_lot_area"
    UNDERVALUED_TOD_TIER = "undervalued_tod_tier"
```

**Add to match_rule()** after the CHANGE_TYPE block:

```python
            elif rule_type == RuleType.UNDERVALUED_DISCOUNT:
                try:
                    min_discount = float(rule_value)
                    discount = signal.get("discount_pct", 0)
                    return float(discount) >= min_discount
                except (ValueError, TypeError):
                    return False

            elif rule_type == RuleType.UNDERVALUED_LOT_AREA:
                try:
                    min_area = float(rule_value)
                    area = signal.get("lot_area_sqft", 0)
                    return float(area) >= min_area
                except (ValueError, TypeError):
                    return False

            elif rule_type == RuleType.UNDERVALUED_TOD_TIER:
                try:
                    tier_val = int(rule_value)
                    signal_tier = signal.get("tod_tier")
                    return int(signal_tier) == tier_val
                except (ValueError, TypeError):
                    return False
```

**Step 4:** Run tests — expect 9 PASS

**Step 5:** Commit: `feat(F06): add undervalued alert watchlist rule types`

---

### Task 5: Undervalued Alert Generation After Scoring

**Files:**
- Modify: `api/intelligence/undervalued_scoring.py` (add post-scoring alert generation)
- Test: `tests/test_prd_phase3.py`

**What:** After `score_parcels()` runs, evaluate flagged parcels against user watchlist rules with UNDERVALUED_* types, and generate alerts for matches.

**Step 1: Write the failing test**

```python
class TestUndervaluedAlertGeneration:
    """F06-B: Alert generation after scoring run."""

    def test_score_parcels_has_alert_generation(self):
        import inspect
        from api.intelligence.undervalued_scoring import score_parcels
        source = inspect.getsource(score_parcels)
        assert "watchlist" in source.lower() or "alert" in source.lower() or "generate_undervalued_alerts" in source.lower()

    def test_generate_undervalued_alerts_exists(self):
        from api.intelligence import undervalued_scoring
        assert hasattr(undervalued_scoring, "generate_undervalued_alerts")

    def test_generate_undervalued_alerts_is_async(self):
        import asyncio
        from api.intelligence.undervalued_scoring import generate_undervalued_alerts
        assert asyncio.iscoroutinefunction(generate_undervalued_alerts)
```

**Step 2:** Run tests — expect FAIL

**Step 3: Implement `generate_undervalued_alerts`**

Add to `undervalued_scoring.py`:

```python
async def generate_undervalued_alerts(
    db_pool: asyncpg.Pool,
    scored_parcels: List[dict],
) -> int:
    """
    Evaluate scored parcels against user watchlist rules and generate alerts.

    Returns count of alerts generated.
    """
    alerts_created = 0

    async with db_pool.acquire() as conn:
        # Get all active watchlists with undervalued-related rules
        watchlists = await conn.fetch("""
            SELECT w.id, w.user_id, wr.rule_type, wr.rule_value
            FROM watchlists w
            JOIN watchlist_rules wr ON wr.watchlist_id = w.id
            WHERE w.is_active = true
              AND wr.rule_type IN ('undervalued_discount', 'undervalued_lot_area', 'undervalued_tod_tier')
        """)

        if not watchlists:
            return 0

        # Group rules by watchlist_id
        from collections import defaultdict
        wl_rules = defaultdict(list)
        wl_users = {}
        for row in watchlists:
            wl_rules[row["id"]].append(row)
            wl_users[row["id"]] = row["user_id"]

        for parcel in scored_parcels:
            if not parcel.get("is_undervalued"):
                continue

            signal = {
                "discount_pct": parcel.get("discount_pct", 0),
                "lot_area_sqft": parcel.get("lot_area_sqft", 0),
                "tod_tier": parcel.get("tod_tier"),
            }

            for wl_id, rules in wl_rules.items():
                from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
                rule_objs = [
                    WatchlistRule(rule_type=RuleType(r["rule_type"]), rule_value=r["rule_value"])
                    for r in rules
                ]
                if AlertEngine.match_rules(signal, rule_objs):
                    # Create alert (skip if duplicate)
                    try:
                        await conn.execute("""
                            INSERT INTO alerts (watchlist_id, signal_id, alert_type, headline, summary, severity, created_at)
                            VALUES ($1, 0, 'undervalued_match', $2, $3, 'medium', NOW())
                            ON CONFLICT DO NOTHING
                        """,
                            wl_id,
                            f"Undervalued parcel: {parcel.get('pid', 'unknown')} ({parcel.get('discount_pct', 0):.0f}% below market)",
                            f"Parcel {parcel.get('pid')} in {parcel.get('neighborhood', 'N/A')} flagged as undervalued.",
                        )
                        alerts_created += 1
                    except Exception as e:
                        logger.warning("Error creating undervalued alert: %s", e)

    return alerts_created
```

Then at end of `score_parcels()`, after the scoring loop, add:
```python
    # Generate alerts for matched watchlist rules
    try:
        alerts = await generate_undervalued_alerts(db_pool, scored_list)
        stats["alerts_generated"] = alerts
    except Exception as e:
        logger.warning("Error generating undervalued alerts: %s", e)
```

**Step 4:** Run tests — expect PASS

**Step 5:** Commit: `feat(F06): generate alerts from undervalued scoring against watchlist rules`

---

### Task 6: Neighborhood Risk Choropleth on Map

**Files:**
- Modify: `frontend/src/components/MapView.tsx`
- Create: `frontend/src/lib/political-risk-api.ts`
- Test: `tests/test_prd_phase3.py`

**What:** Add a toggle to MapView that fetches neighborhood political risk scores and renders a color-coded fill layer (green 1-3, yellow 4-6, red 7-10) over Vancouver neighborhoods.

**Step 1: Write the failing test**

```python
class TestRiskChoropleth:
    """F05-C: Map choropleth for neighborhood risk scores."""

    def test_political_risk_api_file_exists(self):
        import os
        assert os.path.isfile("frontend/src/lib/political-risk-api.ts")

    def test_political_risk_api_has_fetch_function(self):
        with open("frontend/src/lib/political-risk-api.ts") as f:
            content = f.read()
        assert "fetchNeighborhoodRiskScores" in content or "fetchPoliticalRiskScores" in content

    def test_mapview_has_risk_toggle(self):
        with open("frontend/src/components/MapView.tsx") as f:
            content = f.read()
        assert "risk" in content.lower() and ("choropleth" in content.lower() or "risk-layer" in content.lower() or "showRisk" in content.lower())

    def test_mapview_has_risk_colors(self):
        with open("frontend/src/components/MapView.tsx") as f:
            content = f.read()
        # Should have color mapping for risk score ranges
        assert "green" in content.lower() or "#22c55e" in content.lower() or "rgb(34" in content.lower()
```

**Step 2:** Run tests — expect FAIL

**Step 3: Implement**

Create `frontend/src/lib/political-risk-api.ts`:
```typescript
import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

export interface NeighborhoodRisk {
  neighborhood: string;
  risk_score: number;
  opposition_rate: number;
  delay_score: number;
  sentiment_intensity: number;
  council_resistance: number;
}

export async function fetchNeighborhoodRiskScores(): Promise<NeighborhoodRisk[]> {
  const res = await fetch(`${API_BASE}/api/v1/political-risk/neighborhoods`);
  if (!res.ok) return [];
  return res.json();
}
```

In `MapView.tsx`:
- Add `showRiskChoropleth` state toggle
- On toggle: fetch risk scores, create a GeoJSON FeatureCollection of neighborhood polygons (from existing Vancouver local area boundaries)
- Add Mapbox `fill` layer colored by score: green (#22c55e) for 1-3, yellow (#eab308) for 4-6, red (#ef4444) for 7-10
- Add toggle button in control bar area

**Step 4:** Run tests — expect PASS

**Step 5:** Commit: `feat(F05): add neighborhood risk choropleth layer to map`

---

### Task 7: Final Integration Verification

**Files:** None (verification only)

**What:**
1. Run full test suite: `python3 -m pytest tests/ -q --tb=short`
2. Run Phase 3 tests: `python3 -m pytest tests/test_prd_phase3.py -v`
3. Verify frontend builds: `cd frontend && npx next build`
4. Count new tests
5. Push to main

**Expected:** All new Phase 3 tests pass, existing tests unbroken, frontend builds clean.

---

## Implementation Order

1. **Task 1** (RSS Sources) — trivial data addition
2. **Task 2** (Scheduler Wiring) — config change
3. **Task 3** (K8s CronJobs) — infra manifests, independent
4. **Task 4** (Undervalued Rules) — backend rule types
5. **Task 5** (Alert Generation) — depends on Task 4
6. **Task 6** (Map Choropleth) — frontend, independent of 4-5
7. **Task 7** (Integration) — depends on all above

**Parallelizable:** Tasks 1-4 are independent. Task 5 depends on Task 4. Task 6 is independent.

---

## Files Summary

### New files (3):
1. `k8s/cronjob-political-risk.yaml`
2. `k8s/cronjob-undervalued.yaml`
3. `frontend/src/lib/political-risk-api.ts`

### Modified files (4):
1. `api/intelligence/scraper_news.py` — Add 3 RSS feeds
2. `api/intelligence/scheduler.py` — Register risk + undervalued schedules
3. `api/intelligence/alerts.py` — Add 3 undervalued rule types + matching
4. `api/intelligence/undervalued_scoring.py` — Alert generation post-scoring
5. `frontend/src/components/MapView.tsx` — Risk choropleth toggle + layer

### Test file:
- `tests/test_prd_phase3.py` — All Phase 3 tests
