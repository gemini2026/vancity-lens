# Tavily Search Query Expansion for Real Estate Intelligence

## Current State

**Existing Queries (3):**
1. "Vancouver rezoning application 2026"
2. "Bill 47 TOD development Vancouver"
3. "Vancouver density development news"

**Current Coverage:**
- Government/official sources (covered by 12 existing scrapers)
- Rezoning and TOD regulatory content
- Generic development news

**Duplication Rate:** 96.5% (28 of 29 URLs already in database)

---

## What Realtors Need (Gap Analysis)

### ✅ Already Covered by Existing Scrapers

| Category | Existing Scraper | What it Gets |
|----------|------------------|--------------|
| Official rezoning | `scraper_rezoning` | City rezoning applications |
| Council decisions | `scraper_council` | Council meeting minutes, votes |
| Development permits | `scraper_dpb` | Development Permit Board applications |
| News (RSS) | `scraper_news` | RSS feeds from major outlets |
| Open data | `scraper_opendata` | City open data portal |
| Political risk | `scraper_political_risk` | Political climate analysis |
| Schools | `scraper_schools` | School quality, rankings |
| Contaminated sites | `scraper_contaminated` | Environmental risk registry |
| Stats/CMHC | `scraper_statscan`, `scraper_cmhc` | Official housing data |

### ❌ NOT Covered (Tavily Opportunity)

| Category | Gap | Realtor Value |
|----------|-----|---------------|
| **Developer announcements** | Pre-permit project reveals, groundbreaking ceremonies, architect selections | Lead time on supply pipeline |
| **Neighborhood blogs/BIAs** | Community blogs, Business Improvement Area news, local events | Neighborhood momentum signals |
| **Commercial real estate** | Office leasing, retail openings/closings, coworking expansion | Employment density, foot traffic |
| **Private market analysis** | Real estate blogs, broker market reports, appraisal trends | Competitive intelligence |
| **Transit beyond TOD** | SkyTrain extensions, bus rapid transit, bike lane projects | Accessibility changes |
| **Economic development** | Tech companies relocating, startup funding, office expansions | Job growth indicators |
| **University research** | UBC/SFU urban planning studies, housing research, demographic forecasts | Academic insights |
| **Advocacy/YIMBY** | Abundant Housing Vancouver, community planning groups, pro-density campaigns | Political momentum for upzoning |
| **Architecture/design** | Local firm project showcases, design competition wins, heritage restoration | Quality of upcoming developments |
| **Infrastructure** | Parks, community centers, library expansions, cultural facilities | Amenity improvements |

---

## Proposed Expanded Query Set

### Strategy

**Approach:** Organize queries by **realtor decision categories**, not data sources.

**Categories:**
1. **Deal Pipeline** (upcoming supply)
2. **Neighborhood Momentum** (gentrification signals)
3. **Market Intelligence** (pricing, trends)
4. **Infrastructure & Amenities** (livability improvements)
5. **Economic Drivers** (job growth, business activity)

**Credit Budget:**
- Current: 3 queries × 10 results × 2 (search + extract) = ~30 credits/run
- Proposed: 15 queries × 10 results × 2 = ~150 credits/run
- At 3 runs/day (every 8h): **450 credits/day** = **13,500 credits/month**
- Tavily Pricing: Free tier = 1,000/month, Pro tier ($30/mo) = 100,000/month
- **Recommendation:** Upgrade to Pro tier ($30/month) for comprehensive coverage

---

## Recommended Queries (15 Total)

### Category 1: Deal Pipeline (4 queries)
**Goal:** Find projects before they hit official permit systems

```python
# Pre-permit announcements
"Vancouver developer announces new project 2026"

# Groundbreaking and construction starts
"Vancouver construction groundbreaking ceremony 2026"

# Architect selections (precedes permits by 6-12 months)
"Vancouver architecture firm selected residential tower 2026"

# Condo pre-sales and marketing launches
"Vancouver condo pre-sale launch 2026"
```

**Realtor Value:** Lead time on inventory, early insights into supply pipeline, developer sentiment

---

### Category 2: Neighborhood Momentum (3 queries)
**Goal:** Early signals of gentrification, business growth, community investment

```python
# Business openings (restaurants, retail, cafes signal foot traffic)
"Vancouver new restaurant opening 2026"

# Community improvements and activism
"Vancouver neighborhood improvement BIA community 2026"

# Cultural/arts scene (galleries, studios, events)
"Vancouver arts district gallery opening 2026"
```

**Realtor Value:** Identify "up and coming" neighborhoods before price spikes, spot gentrification early

---

### Category 3: Market Intelligence (2 queries)
**Goal:** Competitive intelligence, pricing trends, broker insights

```python
# Real estate broker market reports and analysis
"Vancouver real estate market report 2026"

# Appraisal and valuation trends
"Vancouver property valuation trends 2026"
```

**Realtor Value:** Competitive intelligence, pricing strategy, market positioning

---

### Category 4: Infrastructure & Amenities (3 queries)
**Goal:** Livability improvements that drive property values

```python
# Transit expansion beyond Bill 47 TOD
"Vancouver SkyTrain extension bus rapid transit 2026"

# Parks, community centers, recreation facilities
"Vancouver new park community center opening 2026"

# Bike lanes, seawalls, pedestrian improvements
"Vancouver bike lane seawall pedestrian infrastructure 2026"
```

**Realtor Value:** Accessibility improvements increase property values, amenities attract buyers

---

### Category 5: Economic Drivers (3 queries)
**Goal:** Employment growth, business relocations, job density

```python
# Tech companies and startups (office demand, high-income renters)
"Vancouver tech company office expansion relocation 2026"

# Major employers and job announcements
"Vancouver jobs hiring employment growth 2026"

# Commercial real estate and office leasing
"Vancouver office lease coworking commercial real estate 2026"
```

**Realtor Value:** Job growth = rental demand, office concentration = residential premium

---

## Implementation Plan

### Phase 1: Validate with 6 Queries (2 weeks)

Start with the **highest-value, lowest-duplication** queries:

```python
DEFAULT_QUERIES = [
    # Existing (keep for consistency)
    "Vancouver rezoning application 2026",
    "Bill 47 TOD development Vancouver",

    # New: Pre-permit pipeline
    "Vancouver developer announces new project 2026",
    "Vancouver condo pre-sale launch 2026",

    # New: Neighborhood momentum
    "Vancouver new restaurant opening 2026",

    # New: Economic drivers
    "Vancouver tech company office expansion relocation 2026",
]
```

**Expected Outcome:**
- Lower duplication rate (targeting sources NOT covered by scrapers)
- 6 queries × 10 results = ~60 URLs/run
- Tavily cost: ~60 searches + ~10 extracts = **80 credits/run** × 3/day = **240 credits/day** (under free tier 1,000/month)

**Success Metrics:**
- Duplication rate < 70% (vs current 96.5%)
- At least 10 new documents/run (vs current 1)
- Documents score >0.7 relevance in RAG search

---

### Phase 2: Full Rollout (if Phase 1 succeeds)

Expand to all 15 queries, upgrade to Tavily Pro tier ($30/month).

**Config changes:**

```python
# api/intelligence/tavily_search.py

DEFAULT_QUERIES = [
    # Category 1: Deal Pipeline
    "Vancouver developer announces new project 2026",
    "Vancouver construction groundbreaking ceremony 2026",
    "Vancouver architecture firm selected residential tower 2026",
    "Vancouver condo pre-sale launch 2026",

    # Category 2: Neighborhood Momentum
    "Vancouver new restaurant opening 2026",
    "Vancouver neighborhood improvement BIA community 2026",
    "Vancouver arts district gallery opening 2026",

    # Category 3: Market Intelligence
    "Vancouver real estate market report 2026",
    "Vancouver property valuation trends 2026",

    # Category 4: Infrastructure & Amenities
    "Vancouver SkyTrain extension bus rapid transit 2026",
    "Vancouver new park community center opening 2026",
    "Vancouver bike lane seawall pedestrian infrastructure 2026",

    # Category 5: Economic Drivers
    "Vancouver tech company office expansion relocation 2026",
    "Vancouver jobs hiring employment growth 2026",
    "Vancouver office lease coworking commercial real estate 2026",
]

# Increase extraction budget (more unique content = more to extract)
MAX_EXTRACT_URLS = 10  # Up from 5
```

**Expected Outcome:**
- 15 queries × 10 results = ~150 URLs/run
- Duplication rate: 50-70% (vs current 96.5%)
- **45-75 new documents/run** (vs current 1)
- Cost: ~450 credits/day (well within Pro tier 100k/month)

---

## Alternative: Targeted Daily Queries

Instead of running all 15 queries every 8 hours, **rotate query categories by day**:

**Monday:** Deal Pipeline (4 queries)
**Tuesday:** Neighborhood Momentum (3 queries)
**Wednesday:** Market Intelligence (2 queries)
**Thursday:** Infrastructure (3 queries)
**Friday:** Economic Drivers (3 queries)
**Weekend:** Rest (or run full set once on Saturday)

**Benefits:**
- Stays within free tier (1,000 credits/month)
- Spreads API load across week
- Still covers all categories monthly

**Trade-off:** Less fresh data (each category updated weekly vs every 8h)

---

## Recommendation

**Start with Phase 1** (6 queries, free tier):
1. Validate that expanded queries reduce duplication
2. Measure realtor value (user feedback, RAG citation frequency)
3. Monitor Tavily credit usage
4. If successful after 2 weeks → proceed to Phase 2 (upgrade to Pro)

**Expected ROI:**
- **Cost:** $30/month (Tavily Pro)
- **Value:** 45-75 new documents/run × 3 runs/day × 30 days = **4,000-6,750 new documents/month**
- **Duplication reduction:** 96.5% → 50-70% = **10-15x more unique content**
- **Realtor value:** Early signals on deals, neighborhoods, market trends not available in official sources

---

## Next Steps

1. ✅ Review and approve Phase 1 query set
2. 📝 Update `api/intelligence/tavily_search.py` with new queries
3. 🚀 Deploy to staging, trigger manual run
4. 📊 Monitor duplication rate and document quality for 2 weeks
5. 💰 If successful: Upgrade to Tavily Pro ($30/month)
6. 📈 Roll out full 15-query set
