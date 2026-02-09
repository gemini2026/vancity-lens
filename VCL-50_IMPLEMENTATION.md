# VCL-50 [INTEL-009] - Proactive Opportunity Alerts Implementation

## Overview

VCL-50 implements a proactive opportunity alert system that allows users to define custom search profiles for real estate development opportunities in Vancouver. The system intelligently scans the parcel database for properties matching user criteria and ranks them by development potential.

## Features

### User-Defined Opportunity Profiles
- Create, read, update, and delete customizable search profiles
- Define criteria:
  - Minimum lot area (sqm)
  - Maximum purchase price ($)
  - Target neighborhoods (text array)
  - Target zoning codes (text array)
  - Minimum storey uplift (above current height)
  - Minimum FSR uplift (above current FSR)
  - Maximum distance from transit stations (meters)
- Activate/deactivate profiles without deletion

### Intelligent Opportunity Scanning
- Automatic detection of parcels within TOA buffers matching profile criteria
- Multi-factor match scoring:
  - **Storey uplift potential** (35% weight): Vertical development capacity
  - **FSR uplift potential** (35% weight): Density/intensity development capacity
  - **Transit proximity** (20% weight): Distance to nearest transit station
  - **Lot size** (10% bonus): Larger lots (3000+ sqm) get bonus points
- Scores normalized to 0-100 range for easy interpretation
- On-demand and scheduled scanning capability

### Match Management
- View all matches for a profile with pagination
- Filter by dismissed status
- Sort by match score (highest potential first)
- Dismiss individual matches to hide them from future views
- Access top matches across all active profiles
- Retrieve detailed match reasons showing development potential

### Admin Functions
- Scan all active profiles in bulk (for scheduled background jobs)
- Monitor scan results and error handling
- Full audit trail via created_at timestamps

## Database Schema

### Tables

#### `opportunity_profiles`
Stores user-defined search criteria and preferences.

```sql
CREATE TABLE opportunity_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    profile_name TEXT NOT NULL,
    min_lot_area_sqm NUMERIC(12,2),
    max_price BIGINT,
    target_neighborhoods TEXT[],
    target_zoning_codes TEXT[],
    min_storey_uplift INTEGER,
    min_fsr_uplift NUMERIC(4,2),
    max_distance_m INTEGER DEFAULT 800,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Key Indexes:**
- `idx_opportunity_profiles_user_id`: For user's profile queries
- `idx_opportunity_profiles_user_active`: Compound for common filtered queries

#### `opportunity_matches`
Stores detected matches between profiles and parcels.

```sql
CREATE TABLE opportunity_matches (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES opportunity_profiles(id),
    parcel_pid TEXT NOT NULL REFERENCES parcels(pid),
    match_score NUMERIC(5,2) NOT NULL,
    match_reasons JSONB,
    is_dismissed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    dismissed_at TIMESTAMP
);
```

**Key Indexes:**
- `idx_opportunity_matches_profile_active`: For retrieving active matches
- `idx_opportunity_matches_score`: For ranking by potential
- `idx_opportunity_matches_unique_profile_parcel`: Prevents duplicate active matches

**Match Reasons JSON Structure:**
```json
{
  "storey_uplift": 10,
  "fsr_uplift": 2.8,
  "distance_m": 250.5,
  "lot_area_sqm": 2500,
  "entitled_storeys": 20,
  "entitled_fsr": 5.5,
  "current_zoning": "RM-5"
}
```

## API Endpoints

All endpoints require JWT authentication via `Authorization: Bearer {token}` header (except admin endpoints which use `X-Admin-Key` header).

### Profile Management

#### POST `/api/v1/intel/opportunities/profiles`
Create a new opportunity profile.

**Request:**
```json
{
  "profile_name": "Downtown High-Rise Opportunities",
  "min_lot_area_sqm": 2000,
  "max_price": 50000000,
  "target_neighborhoods": ["Downtown", "False Creek"],
  "target_zoning_codes": ["RM-5", "CD-1"],
  "min_storey_uplift": 8,
  "min_fsr_uplift": 2.5,
  "max_distance_m": 500
}
```

**Response:** `OpportunityProfileResponse` (201 Created)

#### GET `/api/v1/intel/opportunities/profiles`
List all profiles for the current user.

**Query Parameters:**
- `include_inactive` (boolean, default: false): Include deactivated profiles

**Response:** `list[OpportunityProfileResponse]`

#### GET `/api/v1/intel/opportunities/profiles/{profile_id}`
Get a specific profile (authorization check: user must own profile).

**Response:** `OpportunityProfileResponse`

#### PUT `/api/v1/intel/opportunities/profiles/{profile_id}`
Update a profile (all fields optional, only provided fields updated).

**Request:**
```json
{
  "profile_name": "Updated Name",
  "max_price": 60000000,
  "is_active": true
}
```

**Response:** `OpportunityProfileResponse`

#### DELETE `/api/v1/intel/opportunities/profiles/{profile_id}`
Delete a profile and all associated matches.

**Response:**
```json
{
  "deleted": true,
  "profile_id": 1
}
```

### Opportunity Scanning

#### POST `/api/v1/intel/opportunities/profiles/{profile_id}/scan`
Trigger an opportunity scan for a specific profile.

Queries parcels within TOA buffers, calculates match scores, and stores matches in the database. Can be called on-demand or by scheduled jobs.

**Response:** `list[OpportunityMatchResponse]` - Ranked by match score (descending)

### Match Management

#### GET `/api/v1/intel/opportunities/matches?profile_id={id}`
Get matches for a profile with filtering and pagination.

**Query Parameters:**
- `profile_id` (required, integer): Profile to filter by
- `include_dismissed` (boolean, default: false): Include dismissed matches
- `limit` (integer, default: 50, max: 200): Result limit
- `offset` (integer, default: 0): Result offset

**Response:** `list[OpportunityMatchResponse]`

#### GET `/api/v1/intel/opportunities/top`
Get top matches across all user's active profiles.

**Query Parameters:**
- `limit` (integer, default: 10, max: 100): Number of top matches

**Response:** `list[OpportunityMatchResponse]`

#### POST `/api/v1/intel/opportunities/matches/{match_id}/dismiss`
Hide a match from future views (can be shown again with `include_dismissed=true`).

**Response:**
```json
{
  "dismissed": true,
  "match_id": 1
}
```

### Admin Operations

#### POST `/api/v1/intel/opportunities/admin/scan-all`
Scan opportunities for all active profiles (admin-only, requires `X-Admin-Key` header).

Typically called by a scheduled background job (e.g., nightly scan via cron or scheduler).

**Response:**
```json
{
  "total_profiles": 42,
  "scanned": 42,
  "errors": []
}
```

## Data Models

### OpportunityProfileCreate
Request model for creating a profile.

```python
profile_name: str  # Max 255 chars
min_lot_area_sqm: Optional[float]
max_price: Optional[int]
target_neighborhoods: Optional[List[str]]
target_zoning_codes: Optional[List[str]]
min_storey_uplift: Optional[int]
min_fsr_uplift: Optional[float]
max_distance_m: int = 800  # Range: 100-2000
```

### OpportunityProfileResponse
Returned when reading profiles.

```python
id: int
user_id: int
profile_name: str
min_lot_area_sqm: Optional[float]
max_price: Optional[int]
target_neighborhoods: Optional[List[str]]
target_zoning_codes: Optional[List[str]]
min_storey_uplift: Optional[int]
min_fsr_uplift: Optional[float]
max_distance_m: int
is_active: bool
created_at: datetime
updated_at: datetime
```

### OpportunityMatchResponse
Returned when querying matches.

```python
id: int
profile_id: int
parcel_pid: str
civic_address: Optional[str]
match_score: float  # 0-100
match_reasons: dict  # See JSON structure above
is_dismissed: bool
created_at: datetime
dismissed_at: Optional[datetime]
```

## Implementation Details

### Match Scoring Algorithm

The scoring system combines multiple factors into a 0-100 score:

```
base_score = (
    (storey_uplift / min_storey_uplift) * 0.35 +
    (fsr_uplift / min_fsr_uplift) * 0.35 +
    (1.0 - distance_to_station / max_distance) * 0.20 +
    lot_size_bonus * 0.10
)

match_score = CLAMP(base_score * 100, 0, 100)
```

**Weights:**
- Storey uplift: 35% - Highest impact (vertical development)
- FSR uplift: 35% - Highest impact (density)
- Transit proximity: 20% - Proximity matters but secondary
- Lot size: 10% - Bonus for larger developable sites

**Lot Size Bonus:**
- 3000+ sqm: +10 points (0.10 weight)
- 1500-3000 sqm: +5 points (0.05 weight)
- <1500 sqm: +0 points

### Scanning Logic

1. **Query TOA buffers** containing the user's target neighborhoods and zoning codes
2. **Filter parcels** by:
   - Lot area >= min_lot_area_sqm
   - Assessed value or asking price <= max_price
   - Current zoning in target_zoning_codes (if specified)
   - Within max_distance_m of transit
3. **Calculate entitlements** for each parcel using Bill 47 tier rules
4. **Compute uplifts** by comparing entitled vs current:
   - Storey uplift = entitled_storeys - current_height
   - FSR uplift = entitled_fsr - current_fsr
5. **Score matches** using multi-factor algorithm (see above)
6. **Store results** in opportunity_matches with ON CONFLICT upsert
7. **Return ranked list** ordered by match_score DESC

### Authorization

All user endpoints enforce ownership checks:
- Users can only view/modify their own profiles
- Users can only access matches from their own profiles
- Profile ownership verified via `user_id` FK

Admin endpoints require `X-Admin-Key` header (set via `ADMIN_API_KEY` env var).

### Database Performance

**Key optimizations:**
- Compound indexes for common query patterns
- Unique constraint on (profile_id, parcel_pid) preventing duplicate matches
- ON CONFLICT upsert for idempotent scans
- Proper foreign key constraints with cascading deletes
- Materialized views (toa_buffers) pre-computed at schema migration time

## File Structure

```
/db/
  017_opportunity_alerts.sql           # Database migration

/api/intelligence/
  opportunity_alerts.py                 # Core engine (~500 lines)
  opportunity_routes.py                 # FastAPI routes (~400 lines)
  routes.py                             # (modified: added router import)

/tests/
  test_opportunity_alerts.py            # Tests (~600+ lines, 40+ tests)
```

## Testing

Run tests with:
```bash
pytest tests/test_opportunity_alerts.py -v
```

**Test Coverage:**
- Profile CRUD operations (7 tests)
- Opportunity scanning with match scoring (4 tests)
- Match retrieval and filtering (7 tests)
- Match dismissal functionality (2 tests)
- Top matches aggregation (3 tests)
- Admin scan-all function (2 tests)
- Authorization checks (2 tests)
- Edge cases (6+ tests)

All tests use mocked asyncpg pools and do not require a real database.

## Usage Example

### Python Client Example

```python
import httpx

# Create client with auth
headers = {"Authorization": "Bearer {jwt_token}"}
async with httpx.AsyncClient(base_url="http://localhost:8000", headers=headers) as client:
    # Create profile
    profile = await client.post(
        "/api/v1/intel/opportunities/profiles",
        json={
            "profile_name": "My Search",
            "min_lot_area_sqm": 2000,
            "max_price": 50000000,
            "target_zoning_codes": ["RM-5"],
            "min_storey_uplift": 8,
            "min_fsr_uplift": 2.5,
        }
    )
    profile_id = profile.json()["id"]

    # Scan for opportunities
    matches = await client.post(f"/api/v1/intel/opportunities/profiles/{profile_id}/scan")
    print(f"Found {len(matches.json())} opportunities")

    # Get top 5 matches
    top = await client.get(
        "/api/v1/intel/opportunities/top",
        params={"limit": 5}
    )
    for match in top.json():
        print(f"  {match['civic_address']}: Score {match['match_score']}")
```

### Scheduled Scanning

Set up a scheduled job (e.g., with APScheduler or cron) to run:

```bash
curl -X POST http://localhost:8000/api/v1/intel/opportunities/admin/scan-all \
  -H "X-Admin-Key: {admin_api_key}"
```

This will scan all active profiles and update the matches database nightly.

## Security Considerations

1. **JWT Authentication**: All user endpoints require valid JWT tokens
2. **Ownership Verification**: Every user endpoint verifies profile/match ownership
3. **Admin Key Protection**: Admin endpoint requires separate X-Admin-Key header
4. **Database Constraints**: FK constraints prevent orphaned records
5. **SQL Injection Prevention**: All queries use parameterized statements via asyncpg
6. **Input Validation**: Pydantic v2 models validate all inputs
7. **Rate Limiting**: Can be applied at API gateway level (not in this implementation)

## Future Enhancements

1. **Notification System**: Email/SMS alerts when new matches found
2. **Saved Comparisons**: Compare multiple matching parcels side-by-side
3. **Historical Tracking**: Track score changes over time for opportunity maturation
4. **Advanced Filters**: Neighborhood sentiment, nearby developments, traffic studies
5. **Export**: Download matches to CSV/Excel for analysis
6. **Webhooks**: Send match updates to external systems in real-time
7. **Machine Learning**: Learn user preferences from dismissed matches
8. **Collaboration**: Share profiles with team members

## Known Limitations

1. Score calculation uses simple weighted average (could incorporate ML models)
2. Bill 47 entitlements only (doesn't account for other zoning)
3. Price data limited to assessed value and REW.ca listings
4. No notification system (scan results must be polled)
5. Dismissed matches are permanent (cannot un-dismiss)
6. No bulk operations (delete multiple profiles, etc.)

## Migration Instructions

1. Apply database migration:
   ```sql
   psql -U $USER -d vancity_lens < db/017_opportunity_alerts.sql
   ```

2. Verify tables created:
   ```sql
   \dt opportunity_*
   ```

3. Restart API server to load new routes

4. Test endpoints with API client (Postman, curl, etc.)

## References

- **Ticket**: VCL-50 [INTEL-009]
- **Project**: VanCity Lens (Bill 47 Transit-Oriented Development Analysis)
- **Database**: PostgreSQL 16 + PostGIS + pgvector
- **Framework**: FastAPI with asyncpg
- **Python Version**: 3.10+
