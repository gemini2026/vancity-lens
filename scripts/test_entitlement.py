"""
VanCity Lens — Quick smoke test for the Bill 47 engine.
Run after `docker compose up -d`:

    python -m scripts.test_entitlement

Or standalone:

    python scripts/test_entitlement.py
"""

import asyncio
import json
import sys

import asyncpg

DATABASE_URL = "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens"

# Test cases: (pid, expected_in_toa, expected_min_tier)
TEST_CASES = [
    ("009-123-456", True,  1),   # ~150m from Broadway-City Hall -> Tier 1 (20 storeys)
    ("010-456-789", True,  2),   # ~350m from Broadway-City Hall -> Tier 2 (12 storeys)
    ("011-789-012", False, None), # ~2km from any station -> no entitlement
]


async def run_tests():
    conn = await asyncpg.connect(DATABASE_URL)

    print("=" * 70)
    print("VanCity Lens - Bill 47 Engine Smoke Test")
    print("=" * 70)

    # Verify stations loaded
    count = await conn.fetchval("SELECT count(*) FROM transit_stations")
    print(f"\nTransit stations loaded: {count}")

    # Verify buffers materialized
    buf_count = await conn.fetchval("SELECT count(*) FROM toa_buffers")
    print(f"TOA buffer zones generated: {buf_count}")

    # Verify parcels loaded
    parcel_count = await conn.fetchval("SELECT count(*) FROM parcels")
    print(f"Parcels loaded: {parcel_count}")

    print("\n" + "-" * 70)

    all_passed = True
    for pid, expected_toa, expected_tier in TEST_CASES:
        print(f"\nTesting parcel {pid}...")

        # Run the entitlement function
        rows = await conn.fetch("SELECT * FROM get_parcel_entitlement($1)", pid)

        in_toa = len(rows) > 0
        best_tier = min(r["tier"] for r in rows) if rows else None

        # Check expectations
        toa_ok = in_toa == expected_toa
        tier_ok = best_tier == expected_tier

        if in_toa:
            best = rows[0]  # already sorted by storeys DESC
            print(f"  In TOA: Yes")
            print(f"  Station: {best['station_name']}")
            print(f"  Distance: {best['distance_m']}m")
            print(f"  Tier: {best['tier']} -> {best['entitled_storeys']} storeys, FSR {best['entitled_fsr']}")
            print(f"  Uplift: +{best['storey_uplift']} storeys, +{best['fsr_uplift']} FSR")

            # Also run value estimate
            val_rows = await conn.fetch(
                "SELECT * FROM estimate_entitled_value($1, $2)", pid, 800
            )
            if val_rows:
                v = val_rows[0]
                est_val = v["estimated_value"]
                delta = v["value_delta"]
                print(f"  Est. Value: ${est_val:,.0f}")
                print(f"  Value Delta: ${delta:,.0f}")
                if delta > 0:
                    print(f"  ALPHA DETECTED: +${delta:,.0f}")
        else:
            print(f"  In TOA: No (outside all zones)")

        if not toa_ok:
            print(f"  FAIL: Expected in_toa={expected_toa}, got {in_toa}")
            all_passed = False
        if not tier_ok:
            print(f"  FAIL: Expected tier={expected_tier}, got {best_tier}")
            all_passed = False
        if toa_ok and tier_ok:
            print(f"  PASS")

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)

    # Bonus: print the "headline" for the Red Dot demo parcel
    print("\n" + "-" * 70)
    print("DEMO: The Red Dot (what Colin sees)")
    print("-" * 70)
    rows = await conn.fetch("SELECT * FROM get_parcel_entitlement($1)", "009-123-456")
    val = await conn.fetch("SELECT * FROM estimate_entitled_value($1, $2)", "009-123-456", 800)
    if rows and val:
        r, v = rows[0], val[0]
        millions = v["estimated_value"] / 1_000_000
        print(
            f'ZONING ALERT: Approved for {r["entitled_storeys"]} Stories '
            f'(Tier {r["tier"]}, {r["distance_m"]}m from {r["station_name"]}). '
            f'Est. Land Value: ${millions:,.1f}M.'
        )

    await conn.close()


if __name__ == "__main__":
    asyncio.run(run_tests())
