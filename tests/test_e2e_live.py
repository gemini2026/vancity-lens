"""
E2E Live Integration Tests — VanCity Lens API
Runs against the actual running service (docker compose up).

Usage:
    pytest tests/test_e2e_live.py -m e2e -v

Skip if service is not running:
    Automatically skips all tests if localhost:8000 is unreachable.
"""

import time

import pytest
import httpx

BASE = "http://localhost:8000"
ADMIN_KEY = "vcl-admin-dev-key-2026"
_REQUEST_DELAY = 0.3  # seconds between requests to avoid rate limiting


def _service_available() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not _service_available(), reason="API not running on localhost:8000"),
]


@pytest.fixture(scope="module")
def client():
    def _throttle(request):
        time.sleep(_REQUEST_DELAY)
    with httpx.Client(base_url=BASE, timeout=15, event_hooks={"request": [_throttle]}) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers():
    return {"X-Admin-Key": ADMIN_KEY}


@pytest.fixture(scope="module")
def auth_token(client):
    """Register + login to get a JWT token."""
    email = "e2e-live-test@example.com"
    password = "E2ETest123!"
    # Register (ignore if already exists)
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    # Login
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json()["access_token"]
    pytest.skip("Could not obtain auth token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ──────────────────────────────────────────────────────────────────────
# Health & Infrastructure
# ──────────────────────────────────────────────────────────────────────

class TestHealthInfrastructure:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["db"] == "connected"
        assert data["tables"] >= 40

    def test_ready(self, client):
        r = client.get("/ready")
        assert r.status_code == 200
        data = r.json()
        assert data["ready"] is True
        assert data["checks"]["database"] is True
        assert data["checks"]["cache"] == "healthy"

    def test_versions(self, client):
        r = client.get("/api/versions")
        assert r.status_code == 200
        data = r.json()
        assert data["default_version"] == "1"
        assert len(data["versions"]) >= 1

    def test_metrics_endpoint(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "python_gc" in r.text


# ──────────────────────────────────────────────────────────────────────
# Admin Auth Security
# ──────────────────────────────────────────────────────────────────────

class TestAdminSecurity:
    def test_admin_rejects_no_key(self, client):
        r = client.get("/api/v1/admin/data-status")
        assert r.status_code in (401, 503)

    def test_admin_rejects_wrong_key(self, client):
        r = client.get("/api/v1/admin/data-status", headers={"X-Admin-Key": "wrong"})
        assert r.status_code == 403

    def test_admin_accepts_correct_key(self, client, admin_headers):
        r = client.get("/api/v1/admin/data-status", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_parcels" in data

    def test_intel_admin_rejects_no_key(self, client):
        r = client.get("/api/v1/intel/admin/status")
        assert r.status_code in (401, 503)

    def test_intel_admin_accepts_correct_key(self, client, admin_headers):
        r = client.get("/api/v1/intel/admin/status", headers=admin_headers)
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Auth Flow
# ──────────────────────────────────────────────────────────────────────

class TestAuthFlow:
    def test_register_login_me(self, client):
        email = "e2e-flow-test@example.com"
        pw = "FlowTest123!"
        # Register
        r = client.post("/api/v1/auth/register", json={"email": email, "password": pw})
        assert r.status_code in (201, 400, 409)  # 400/409 if already exists

        # Login
        r = client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200
        token = r.json()["access_token"]
        assert len(token) > 20

        # Me
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == email

    def test_bad_token_rejected(self, client):
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer GARBAGE"})
        assert r.status_code == 401

    def test_register_missing_fields(self, client):
        r = client.post("/api/v1/auth/register", json={})
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Parcels & Entitlement
# ──────────────────────────────────────────────────────────────────────

class TestParcels:
    def test_parcel_by_pid(self, client):
        r = client.get("/api/v1/parcels/by-pid/009-123-456")
        assert r.status_code == 200
        data = r.json()
        assert data["pid"] == "009-123-456"
        assert data["civic_address"] == "163 W 8th Ave, Vancouver"
        assert data["zoning"] == "RS-1"

    def test_parcel_not_found(self, client):
        r = client.get("/api/v1/parcels/by-pid/999-999-999")
        assert r.status_code == 404

    def test_entitlement(self, client):
        r = client.get("/api/v1/parcels/009-123-456/entitlement")
        assert r.status_code == 200
        data = r.json()
        assert data["in_toa"] is True
        assert len(data["entitlements"]) >= 1
        best = data["best_entitlement"]
        assert best["tier"] == 1
        assert best["bill47_storeys"] == 20
        assert float(best["bill47_fsr"]) == 5.5

    def test_nearby_stations(self, client):
        r = client.get("/api/v1/parcels/009-123-456/nearby-stations")
        assert r.status_code == 200
        stations = r.json()
        assert len(stations) >= 1
        assert stations[0]["name"] == "Broadway-City Hall"

    def test_nearest_parcel(self, client):
        r = client.get("/api/v1/parcels/nearest", params={"lng": -123.1165, "lat": 49.2636, "radius_m": 500})
        assert r.status_code == 200
        data = r.json()
        assert data["pid"] == "009-123-456"

    def test_parcel_search(self, client):
        r = client.get("/api/v1/parcels/search", params={"q": "8th Ave", "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data

    def test_opportunities(self, client):
        r = client.get("/api/v1/opportunities", params={"limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["total"] >= 1


# ──────────────────────────────────────────────────────────────────────
# Intelligence Signals
# ──────────────────────────────────────────────────────────────────────

class TestIntelligence:
    def test_signals_list(self, client):
        r = client.get("/api/v1/intel/signals", params={"limit": 10})
        assert r.status_code == 200
        data = r.json()
        assert "signals" in data
        assert len(data["signals"]) >= 1

    def test_signal_by_id(self, client):
        r = client.get("/api/v1/intel/signals/10001")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == 10001
        assert data["signal_type"] == "rezoning_decision"

    def test_signal_not_found(self, client):
        r = client.get("/api/v1/intel/signals/999999")
        assert r.status_code == 404

    def test_stats(self, client):
        r = client.get("/api/v1/intel/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_signals"] >= 5
        assert "by_type" in data
        assert "by_neighborhood" in data
        assert data["recent_count_7d"] >= 0

    def test_geojson(self, client):
        r = client.get("/api/v1/intel/signals/geojson", params={"limit": 10, "days": 365})
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 1
        feat = data["features"][0]
        assert feat["geometry"]["type"] == "Point"
        coords = feat["geometry"]["coordinates"]
        assert -124 < coords[0] < -122  # Vancouver lng
        assert 49 < coords[1] < 50  # Vancouver lat


# ──────────────────────────────────────────────────────────────────────
# Neighborhoods
# ──────────────────────────────────────────────────────────────────────

class TestNeighborhoods:
    def test_list_neighborhoods(self, client):
        r = client.get("/api/v1/intel/neighborhoods")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1

    def test_scorecards(self, client):
        r = client.get("/api/v1/intel/neighborhoods/scorecards")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert "name" in data[0]
        assert "slug" in data[0]

    def test_single_scorecard(self, client):
        r = client.get("/api/v1/intel/neighborhoods/mount-pleasant/scorecard")
        assert r.status_code == 200
        data = r.json()
        assert data["neighborhood"]["name"] == "Mount Pleasant"

    def test_invalid_neighborhood(self, client):
        r = client.get("/api/v1/intel/neighborhoods/nonexistent-place/scorecard")
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# TOA & Geocoding
# ──────────────────────────────────────────────────────────────────────

class TestTOAAndGeocoding:
    def test_toa_geojson(self, client):
        r = client.get("/api/v1/toa/geojson", params={"limit": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 1
        props = data["features"][0]["properties"]
        assert "station" in props
        assert "tier" in props

    def test_reverse_geocode(self, client):
        r = client.get("/api/v1/reverse-geocode", params={"lat": 49.2636, "lng": -123.1165})
        assert r.status_code == 200
        data = r.json()
        assert "lat" in data
        assert "lng" in data

    def test_geocode(self, client):
        r = client.get("/api/v1/geocode", params={"q": "Vancouver"})
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Financing Calculator
# ──────────────────────────────────────────────────────────────────────

class TestFinancing:
    def test_financing_calculate(self, client):
        r = client.post("/api/v1/financing/calculate", json={
            "acquisition_cost": 2500000,
            "equity_pct": 0.25,
            "interest_rate": 0.055,
            "hold_period_months": 36,
            "construction_cost": 1500000,
            "gross_revenue": 6000000,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_viable"] is True
        assert data["roi"] > 0
        assert "scenarios" in data
        assert "bull" in data["scenarios"]

    def test_financing_quick_calc(self, client):
        r = client.get("/api/v1/financing/quick-calc", params={
            "acquisition_cost": 2500000,
            "equity_pct": 0.25,
            "interest_rate": 0.055,
            "hold_period_months": 36,
            "construction_cost": 1500000,
            "gross_revenue": 6000000,
        })
        assert r.status_code == 200

    def test_financing_validation_rejects_bad_rate(self, client):
        r = client.post("/api/v1/financing/calculate", json={
            "acquisition_cost": 2500000,
            "equity_pct": 0.25,
            "interest_rate": 5.5,  # >1, should be rejected
            "hold_period_months": 36,
            "construction_cost": 1500000,
            "gross_revenue": 6000000,
        })
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Subscription Tiers
# ──────────────────────────────────────────────────────────────────────

class TestSubscriptions:
    def test_list_tiers(self, client):
        r = client.get("/api/v1/subscriptions/tiers")
        assert r.status_code == 200
        tiers = r.json()
        assert len(tiers) >= 3
        names = [t["name"] for t in tiers]
        assert "free" in names
        assert "starter" in names

    def test_current_no_auth(self, client):
        r = client.get("/api/v1/subscriptions/current")
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# Data Validation (attack vectors)
# ──────────────────────────────────────────────────────────────────────

class TestDataValidation:
    def test_sql_injection_search(self, client):
        r = client.get("/api/v1/parcels/search", params={"q": "' OR 1=1--"})
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_sql_injection_pid(self, client):
        r = client.get("/api/v1/parcels/by-pid/' OR 1=1--")
        assert r.status_code == 404

    def test_xss_search(self, client):
        r = client.get("/api/v1/parcels/search", params={"q": "<script>alert(1)</script>"})
        assert r.status_code == 200
        # Response should be JSON, not HTML
        assert r.headers["content-type"].startswith("application/json")

    def test_invalid_coordinates(self, client):
        r = client.get("/api/v1/parcels/nearby", params={"lat": 999, "lng": 999, "radius": -1})
        assert r.status_code == 422

    def test_non_numeric_coordinates(self, client):
        r = client.get("/api/v1/parcels/nearby", params={"lat": "abc", "lng": "def"})
        assert r.status_code == 422

    def test_oversized_limit(self, client):
        r = client.get("/api/v1/parcels/search", params={"limit": 999999})
        assert r.status_code == 422

    def test_path_traversal(self, client):
        r = client.get("/api/v1/parcels/by-pid/..%2F..%2Fetc%2Fpasswd")
        assert r.status_code in (404, 422)

    def test_security_headers(self, client):
        r = client.get("/api/v1/parcels/search", params={"q": "test"})
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"


# ──────────────────────────────────────────────────────────────────────
# Comparables
# ──────────────────────────────────────────────────────────────────────

class TestComparables:
    def test_search_comparables(self, client):
        r = client.get("/api/v1/comparables/search", params={
            "lat": 49.2636, "lng": -123.1165, "radius_m": 1000,
        })
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)


# ──────────────────────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────────────────────

class TestPipeline:
    def test_pipeline_stats(self, client):
        r = client.get("/api/v1/intel/pipeline/stats")
        assert r.status_code == 200

    def test_pipeline_summary(self, client):
        r = client.get("/api/v1/intel/pipeline/summary")
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Export (auth required)
# ──────────────────────────────────────────────────────────────────────

class TestExport:
    def test_export_requires_auth(self, client):
        r = client.get("/api/v1/export/parcels")
        assert r.status_code == 401

    def test_export_parcels(self, client, auth_headers):
        r = client.get("/api/v1/export/parcels", headers=auth_headers)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "csv" in ct or "json" in ct or "text" in ct

    def test_export_signals(self, client, auth_headers):
        r = client.get("/api/v1/export/signals", headers=auth_headers)
        assert r.status_code == 200
