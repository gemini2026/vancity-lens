#!/usr/bin/env python3
"""
Load seed data from data/seed/ JSON files into the VanCity Lens database.

Usage:
    python data/load_seed.py                  # Load all seed data
    python data/load_seed.py --clean          # Clear existing data first, then load
    python data/load_seed.py --dry-run        # Show what would be loaded without executing

Requires: asyncpg (already in project dependencies)
"""
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

import asyncpg


def parse_date(s: str | None) -> date | None:
    """Convert a 'YYYY-MM-DD' string to a date object, or None."""
    if not s:
        return None
    return date.fromisoformat(s)

SEED_DIR = Path(__file__).parent / "seed"
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
)


def load_json(filename: str) -> list[dict]:
    path = SEED_DIR / filename
    with open(path) as f:
        return json.load(f)


async def upsert_neighborhoods(conn: asyncpg.Connection):
    """Update existing neighborhoods with centroid coordinates and population."""
    data = load_json("neighborhoods.json")
    count = 0
    for n in data:
        result = await conn.execute(
            """
            UPDATE neighborhoods
            SET centroid = ST_SetSRID(ST_MakePoint($1, $2), 4326),
                population = $3,
                area_km2 = $4
            WHERE name = $5
            """,
            n["lng"], n["lat"], n["population"], n["area_km2"], n["name"],
        )
        if "UPDATE 1" in result:
            count += 1
        else:
            # Insert if not exists
            await conn.execute(
                """
                INSERT INTO neighborhoods (name, slug, centroid, population, area_km2)
                VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326), $5, $6)
                ON CONFLICT (name) DO UPDATE SET
                    centroid = EXCLUDED.centroid,
                    population = EXCLUDED.population,
                    area_km2 = EXCLUDED.area_km2
                """,
                n["name"], n["slug"], n["lng"], n["lat"], n["population"], n["area_km2"],
            )
            count += 1
    print(f"  Neighborhoods: {count} updated")


async def upsert_transit_stations(conn: asyncpg.Connection):
    """Insert or update transit stations (no unique constraint on name, so check first)."""
    data = load_json("transit_stations.json")
    inserted = 0
    updated = 0
    for s in data:
        existing = await conn.fetchval(
            "SELECT id FROM transit_stations WHERE name = $1", s["name"]
        )
        if existing:
            await conn.execute(
                """
                UPDATE transit_stations
                SET line = $1, type = $2::station_type,
                    geom = ST_SetSRID(ST_MakePoint($3, $4), 4326),
                    opened_date = $5                WHERE id = $6
                """,
                s["line"], s["type"], s["lng"], s["lat"],
                parse_date(s.get("opened_date")), existing,
            )
            updated += 1
        else:
            await conn.execute(
                """
                INSERT INTO transit_stations (name, line, type, geom, opened_date)
                VALUES ($1, $2, $3::station_type, ST_SetSRID(ST_MakePoint($4, $5), 4326), $6)
                """,
                s["name"], s["line"], s["type"], s["lng"], s["lat"],
                parse_date(s.get("opened_date")),
            )
            inserted += 1
    print(f"  Transit stations: {inserted} inserted, {updated} updated")


async def upsert_bill47_tiers(conn: asyncpg.Connection):
    """Insert or update Bill 47 tiers."""
    data = load_json("bill47_tiers.json")
    for t in data:
        await conn.execute(
            """
            INSERT INTO bill47_tiers (tier, station_type, min_distance_m, max_distance_m, max_storeys, max_fsr)
            VALUES ($1, $2::station_type, $3, $4, $5, $6)
            ON CONFLICT (tier, station_type) DO UPDATE SET
                min_distance_m = EXCLUDED.min_distance_m,
                max_distance_m = EXCLUDED.max_distance_m,
                max_storeys = EXCLUDED.max_storeys,
                max_fsr = EXCLUDED.max_fsr
            """,
            t["tier"], t["station_type"], t["min_distance_m"],
            t["max_distance_m"], t["max_storeys"], t["max_fsr"],
        )
    print(f"  Bill 47 tiers: {len(data)} upserted")


async def insert_documents(conn: asyncpg.Connection):
    """Insert documents, skipping duplicates by source_url."""
    data = load_json("documents.json")
    count = 0
    for d in data:
        result = await conn.execute(
            """
            INSERT INTO documents (source_type, source_url, title, published_date, raw_text)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (source_url) DO NOTHING
            """,
            d["source_type"], d["source_url"], d["title"],
            parse_date(d.get("published_date")), d.get("raw_text"),
        )
        if "INSERT" in result:
            count += 1
    print(f"  Documents: {count} inserted ({len(data) - count} already existed)")


async def insert_signals(conn: asyncpg.Connection):
    """Insert intelligence signals, linking to documents by source_url."""
    data = load_json("intelligence_signals.json")
    docs = load_json("documents.json")
    count = 0
    for s in data:
        # Look up the actual document_id by the document's position in our seed data
        doc_idx = s["document_id"] - 1
        if doc_idx < 0 or doc_idx >= len(docs):
            print(f"    WARNING: Document index {s['document_id']} out of range, skipping signal")
            continue
        doc_id = await conn.fetchval(
            "SELECT id FROM documents WHERE source_url = $1",
            docs[doc_idx]["source_url"],
        )
        if not doc_id:
            print(f"    WARNING: Document {s['document_id']} not found, skipping signal")
            continue

        lat = s.get("lat")
        lng = s.get("lng")
        geom_expr = "ST_SetSRID(ST_MakePoint($18, $19), 4326)" if lat and lng else "NULL"

        await conn.execute(
            f"""
            INSERT INTO intelligence_signals (
                document_id, signal_type, summary, headline,
                addresses, neighborhood, geom,
                zoning_from, zoning_to, fsr_after, unit_count,
                project_value_dollars, decision,
                vote_for, vote_against,
                severity, confidence, sentiment, event_date
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, {geom_expr},
                $7, $8, $9, $10,
                $11, $12,
                $13, $14,
                $15, $16, $17, $20            )
            """,
            doc_id, s["signal_type"], s["summary"], s.get("headline"),
            s.get("addresses", []), s.get("neighborhood"),
            s.get("zoning_from"), s.get("zoning_to"),
            s.get("fsr_after"), s.get("unit_count"),
            s.get("project_value_dollars"), s.get("decision"),
            s.get("vote_for"), s.get("vote_against"),
            s.get("severity", "info"), s.get("confidence", 0.5),
            s.get("sentiment", "neutral"),
            lng, lat,
            parse_date(s.get("event_date")),
        )
        count += 1
    print(f"  Intelligence signals: {count} inserted")


async def insert_parcels(conn: asyncpg.Connection):
    """Insert parcels, skipping duplicates by pid."""
    data = load_json("parcels.json")
    count = 0
    for p in data:
        result = await conn.execute(
            """
            INSERT INTO parcels (pid, civic_address, current_zoning, current_fsr, current_height,
                                 lot_area_sqm, assessed_value, geo_local_area,
                                 geom)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                    ST_SetSRID(ST_MakePoint($9, $10), 4326))
            ON CONFLICT (pid) DO UPDATE SET
                civic_address = EXCLUDED.civic_address,
                current_zoning = EXCLUDED.current_zoning,
                current_fsr = EXCLUDED.current_fsr,
                current_height = EXCLUDED.current_height,
                lot_area_sqm = EXCLUDED.lot_area_sqm,
                assessed_value = EXCLUDED.assessed_value,
                geo_local_area = EXCLUDED.geo_local_area,
                geom = EXCLUDED.geom
            """,
            p["pid"], p["civic_address"], p["current_zoning"],
            p["current_fsr"], p["current_height"],
            p["lot_area_sqm"], p["assessed_value"], p["geo_local_area"],
            p["lng"], p["lat"],
        )
        count += 1
    print(f"  Parcels: {count} upserted")


async def insert_comparable_sales(conn: asyncpg.Connection):
    """Insert comparable sales data."""
    data = load_json("comparable_sales.json")
    count = 0
    for s in data:
        await conn.execute(
            """
            INSERT INTO comparable_sales (
                address, pid, sale_price, sale_date, lot_area_sqft,
                zoning, building_type, bedrooms, bathrooms, year_built,
                floor_area_sqft, neighborhood, geom
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, ST_SetSRID(ST_MakePoint($13, $14), 4326)
            )
            """,
            s["address"], s.get("pid"), s["sale_price"], parse_date(s["sale_date"]),
            s.get("lot_area_sqft"),
            s.get("zoning"), s.get("building_type"),
            s.get("bedrooms"), s.get("bathrooms"), s.get("year_built"),
            s.get("floor_area_sqft"), s.get("neighborhood"),
            s["lng"], s["lat"],
        )
        count += 1
    print(f"  Comparable sales: {count} inserted")


async def insert_supply_pipeline(conn: asyncpg.Connection):
    """Insert supply pipeline entries."""
    data = load_json("supply_pipeline.json")
    count = 0
    for p in data:
        result = await conn.execute(
            """
            INSERT INTO supply_pipeline (
                parcel_pid, address, neighborhood, pipeline_stage,
                current_zoning, proposed_zoning, proposed_storeys,
                proposed_units, developer, estimated_completion
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (parcel_pid) DO UPDATE SET
                address = EXCLUDED.address,
                neighborhood = EXCLUDED.neighborhood,
                pipeline_stage = EXCLUDED.pipeline_stage,
                current_zoning = EXCLUDED.current_zoning,
                proposed_zoning = EXCLUDED.proposed_zoning,
                proposed_storeys = EXCLUDED.proposed_storeys,
                proposed_units = EXCLUDED.proposed_units,
                developer = EXCLUDED.developer,
                estimated_completion = EXCLUDED.estimated_completion
            """,
            p["parcel_pid"], p["address"], p["neighborhood"],
            p["pipeline_stage"], p.get("current_zoning"),
            p.get("proposed_zoning"), p.get("proposed_storeys"),
            p.get("proposed_units"), p.get("developer"),
            parse_date(p.get("estimated_completion")),
        )
        count += 1
    print(f"  Supply pipeline: {count} upserted")


async def insert_schools(conn: asyncpg.Connection):
    """Insert school data."""
    data = load_json("schools.json")
    count = 0
    for s in data:
        result = await conn.execute(
            """
            INSERT INTO school_data (name, address, school_type, enrollment, capacity, neighborhood, latitude, longitude)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (name, address) DO UPDATE SET
                enrollment = EXCLUDED.enrollment,
                capacity = EXCLUDED.capacity,
                neighborhood = EXCLUDED.neighborhood
            """,
            s["name"], s["address"], s["school_type"],
            s.get("enrollment"), s.get("capacity"),
            s["neighborhood"], s["lat"], s["lng"],
        )
        count += 1
    print(f"  Schools: {count} upserted")


async def insert_heritage_sites(conn: asyncpg.Connection):
    """Insert heritage sites."""
    data = load_json("heritage_sites.json")
    count = 0
    for h in data:
        await conn.execute(
            """
            INSERT INTO heritage_sites (name, address, category, geom)
            VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326))
            """,
            h["name"], h["address"], h["category"],
            h["lng"], h["lat"],
        )
        count += 1
    print(f"  Heritage sites: {count} inserted")


async def insert_community_gardens(conn: asyncpg.Connection):
    """Insert community gardens."""
    data = load_json("community_gardens.json")
    count = 0
    for g in data:
        await conn.execute(
            """
            INSERT INTO community_gardens (name, address, number_of_plots, geom)
            VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326))
            """,
            g["name"], g["address"], g["number_of_plots"],
            g["lng"], g["lat"],
        )
        count += 1
    print(f"  Community gardens: {count} inserted")


async def insert_view_cones(conn: asyncpg.Connection):
    """Insert view cones with geometry."""
    data = load_json("view_cones.json")
    count = 0
    for v in data:
        geom_json = json.dumps(v["geometry"])
        await conn.execute(
            """
            INSERT INTO view_cones (
                name, view_number, description, max_height_m,
                source_location, target_location, bylaw_reference,
                cone_type, geom
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, ST_SetSRID(ST_GeomFromGeoJSON($9), 4326))
            """,
            v["name"], v.get("view_number"), v.get("description"),
            v.get("max_height_m"),
            v.get("source_location"), v.get("target_location"),
            v.get("bylaw_reference"), v.get("cone_type", "protected_view"),
            geom_json,
        )
        count += 1
    print(f"  View cones: {count} inserted")


async def insert_building_permits(conn: asyncpg.Connection):
    """Insert building permits data."""
    path = SEED_DIR / "building_permits.json"
    if not path.exists():
        print("  Building permits: skipped (no file)")
        return
    data = load_json("building_permits.json")
    count = 0
    for p in data:
        await conn.execute(
            """
            INSERT INTO issued_building_permits (
                permit_number, type_of_work, specific_use,
                project_value, issue_year, geom
            ) VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326))
            """,
            p["permit_number"], p["type_of_work"], p["specific_use"],
            p["project_value"], p["issue_year"],
            p["lng"], p["lat"],
        )
        count += 1
    print(f"  Building permits: {count} inserted")


async def insert_court_rulings(conn: asyncpg.Connection):
    """Insert court ruling documents from separate file (supplements documents.json)."""
    path = SEED_DIR / "court_rulings.json"
    if not path.exists():
        print("  Court rulings: skipped (no file)")
        return
    data = load_json("court_rulings.json")
    count = 0
    for d in data:
        result = await conn.execute(
            """
            INSERT INTO documents (source_type, source_url, title, published_date, raw_text)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (source_url) DO NOTHING
            """,
            d["source_type"], d["source_url"], d["title"],
            parse_date(d.get("published_date")), d.get("raw_text"),
        )
        if "INSERT" in result:
            count += 1
    print(f"  Court rulings: {count} inserted ({len(data) - count} already existed)")


async def insert_neighborhood_scores(conn: asyncpg.Connection):
    """Insert neighborhood scores and compute composite scores."""
    data = load_json("neighborhood_scores.json")
    period_start = date(2025, 1, 1)
    period_end = date(2025, 12, 31)

    # Default scoring weights
    weights = {
        "safety": 0.15, "schools": 0.15, "transit": 0.15,
        "parks": 0.10, "development": 0.15, "air_quality": 0.05,
        "affordability": 0.15, "walkability": 0.10,
    }

    score_count = 0
    composite_count = 0

    for entry in data:
        neighborhood_name = entry["neighborhood"]
        scores = entry["scores"]

        # Get neighborhood_id
        nid = await conn.fetchval(
            "SELECT id FROM neighborhoods WHERE name = $1", neighborhood_name
        )
        if not nid:
            print(f"    WARNING: Neighborhood '{neighborhood_name}' not found, skipping")
            continue

        # Insert individual category scores
        for category, score in scores.items():
            await conn.execute(
                """
                INSERT INTO neighborhood_scores (neighborhood_id, category, score, period_start, period_end)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (neighborhood_id, category, period_start) DO UPDATE SET
                    score = EXCLUDED.score
                """,
                nid, category, score, period_start, period_end,
            )
            score_count += 1

        # Compute and insert composite score
        overall = sum(scores[cat] * weights[cat] for cat in weights)
        await conn.execute(
            """
            INSERT INTO neighborhood_composite_scores (
                neighborhood_id, overall_score, category_scores, weights_used,
                period_start, period_end
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (neighborhood_id, period_start) DO UPDATE SET
                overall_score = EXCLUDED.overall_score,
                category_scores = EXCLUDED.category_scores,
                weights_used = EXCLUDED.weights_used
            """,
            nid, round(overall, 1),
            json.dumps(scores), json.dumps(weights),
            period_start, period_end,
        )
        composite_count += 1

    print(f"  Neighborhood scores: {score_count} inserted")
    print(f"  Composite scores: {composite_count} computed")


async def compute_school_metrics(conn: asyncpg.Connection):
    """Compute school_metrics from school_data."""
    period_start = date(2025, 1, 1)
    period_end = date(2025, 12, 31)
    neighborhoods = await conn.fetch(
        "SELECT DISTINCT neighborhood FROM school_data"
    )
    count = 0
    for row in neighborhoods:
        n = row["neighborhood"]
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as school_count,
                COUNT(*) FILTER (WHERE school_type = 'elementary') as elementary_count,
                COUNT(*) FILTER (WHERE school_type = 'secondary') as secondary_count,
                COALESCE(SUM(enrollment), 0) as total_enrollment,
                COALESCE(SUM(capacity), 0) as total_capacity,
                CASE WHEN SUM(capacity) > 0
                     THEN ROUND(100.0 * SUM(enrollment) / SUM(capacity), 2)
                     ELSE 0 END as avg_capacity_utilization
            FROM school_data WHERE neighborhood = $1
        """, n)
        quality = min(10.0, max(0.0, 5.0 + (stats["school_count"] - 1) * 0.8))
        await conn.execute("""
            INSERT INTO school_metrics (
                neighborhood, school_count, elementary_count, secondary_count,
                total_enrollment, total_capacity, avg_capacity_utilization,
                quality_score, period_start, period_end
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (neighborhood, period_start) DO UPDATE SET
                school_count = EXCLUDED.school_count,
                elementary_count = EXCLUDED.elementary_count,
                secondary_count = EXCLUDED.secondary_count,
                total_enrollment = EXCLUDED.total_enrollment,
                total_capacity = EXCLUDED.total_capacity,
                avg_capacity_utilization = EXCLUDED.avg_capacity_utilization,
                quality_score = EXCLUDED.quality_score
        """, n, stats["school_count"], stats["elementary_count"],
            stats["secondary_count"], stats["total_enrollment"],
            stats["total_capacity"], float(stats["avg_capacity_utilization"]),
            quality, period_start, period_end,
        )
        count += 1
    print(f"  School metrics: {count} neighborhoods computed")


async def insert_case_studies(conn: asyncpg.Connection):
    """Insert case study showcase parcels."""
    path = SEED_DIR / "case_studies.json"
    if not path.exists():
        print("  Case studies: skipped (no file)")
        return
    data = load_json("case_studies.json")
    count = 0
    for cs in data:
        await conn.execute(
            """
            INSERT INTO case_studies (pid, title, narrative, highlight_metrics, display_order, is_active)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6)
            ON CONFLICT DO NOTHING
            """,
            cs["pid"], cs["title"], cs["narrative"],
            json.dumps(cs["highlight_metrics"]),
            cs.get("display_order", 0), cs.get("is_active", True),
        )
        count += 1
    print(f"  Case studies: {count} inserted")


async def upsert_market_benchmarks(conn: asyncpg.Connection):
    """Insert or update market benchmarks (revenue/cost per sf by neighbourhood)."""
    path = SEED_DIR / "market_benchmarks.json"
    if not path.exists():
        print("  Market benchmarks: skipped (no file)")
        return
    data = load_json("market_benchmarks.json")
    count = 0
    for mb in data:
        await conn.execute(
            """
            INSERT INTO market_benchmarks (
                neighbourhood, product_type, revenue_per_sf,
                hard_cost_per_sf, source, effective_date
            ) VALUES ($1, $2, $3, $4, $5, $6::date)
            ON CONFLICT (neighbourhood, product_type) DO UPDATE SET
                revenue_per_sf = EXCLUDED.revenue_per_sf,
                hard_cost_per_sf = EXCLUDED.hard_cost_per_sf,
                source = EXCLUDED.source,
                effective_date = EXCLUDED.effective_date
            """,
            mb["neighbourhood"], mb["product_type"],
            mb["revenue_per_sf"], mb["hard_cost_per_sf"],
            mb["source"], mb["effective_date"],
        )
        count += 1
    print(f"  Market benchmarks: {count} upserted")


async def refresh_materialized_views(conn: asyncpg.Connection):
    """Refresh materialized views that depend on seed data."""
    try:
        await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY toa_buffers")
        print("  Materialized view toa_buffers refreshed")
    except Exception as e:
        # May fail if no unique index for CONCURRENTLY
        try:
            await conn.execute("REFRESH MATERIALIZED VIEW toa_buffers")
            print("  Materialized view toa_buffers refreshed (non-concurrent)")
        except Exception as e2:
            print(f"  WARNING: Could not refresh toa_buffers: {e2}")


async def clean_seed_data(conn: asyncpg.Connection):
    """Remove existing seed data to allow clean reload."""
    print("\nCleaning existing data...")
    # Order matters due to FK constraints
    tables_to_clean = [
        "alerts",
        "watchlist_rules",
        "watchlists",
        "pipeline_stage_history",
        "supply_pipeline",
        "intelligence_signals",
        "document_chunks",
        "documents",
        "comparable_sales",
        "issued_building_permits",
        "community_gardens",
        "heritage_sites",
        "view_cones",
        "school_metrics",
        "school_data",
        "neighborhood_composite_scores",
        "neighborhood_scores",
        "neighborhood_metrics",
        "market_benchmarks",
        "parcels",
    ]
    for table in tables_to_clean:
        try:
            result = await conn.execute(f"DELETE FROM {table}")
            deleted = int(result.split()[-1]) if result else 0
            if deleted > 0:
                print(f"  Cleaned {table}: {deleted} rows")
        except Exception as e:
            print(f"  WARNING: Could not clean {table}: {e}")


async def show_summary(conn: asyncpg.Connection):
    """Show counts of seeded data."""
    print("\n--- Database Summary ---")
    tables = [
        "neighborhoods", "transit_stations", "bill47_tiers",
        "documents", "intelligence_signals", "parcels",
        "comparable_sales", "issued_building_permits",
        "supply_pipeline", "school_data",
        "heritage_sites", "community_gardens", "view_cones",
        "neighborhood_scores", "neighborhood_composite_scores",
        "market_benchmarks",
    ]
    for table in tables:
        try:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table}: {count} rows")
        except Exception:
            print(f"  {table}: (table not found)")


async def main():
    clean = "--clean" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("DRY RUN — showing what would be loaded:\n")
        files = sorted(SEED_DIR.glob("*.json"))
        for f in files:
            data = json.loads(f.read_text())
            print(f"  {f.name}: {len(data)} records")
        return

    print(f"Connecting to: {DB_URL.split('@')[-1]}")
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)

    async with pool.acquire() as conn:
        if clean:
            await clean_seed_data(conn)

        print("\nLoading seed data...")

        # 1. Neighborhoods (update existing)
        await upsert_neighborhoods(conn)

        # 2. Transit stations
        await upsert_transit_stations(conn)

        # 3. Bill 47 tiers
        await upsert_bill47_tiers(conn)

        # 4. Documents
        await insert_documents(conn)

        # 5. Intelligence signals (depends on documents)
        await insert_signals(conn)

        # 6. Parcels
        await insert_parcels(conn)

        # 7. Comparable sales
        await insert_comparable_sales(conn)

        # 8. Supply pipeline
        await insert_supply_pipeline(conn)

        # 9. Schools
        await insert_schools(conn)

        # 9b. Court rulings (additional documents)
        await insert_court_rulings(conn)

        # 9c. Building permits
        await insert_building_permits(conn)

        # 10. Heritage sites, community gardens, view cones
        await insert_heritage_sites(conn)
        await insert_community_gardens(conn)
        await insert_view_cones(conn)

        # 10b. Case studies (showcase parcels)
        await insert_case_studies(conn)

        # 10c. Market benchmarks (revenue/cost per sf)
        await upsert_market_benchmarks(conn)

        # 11. Neighborhood scores + composites
        await insert_neighborhood_scores(conn)

        # 12. School metrics (derived from school_data)
        await compute_school_metrics(conn)

        # 13. Refresh materialized views
        await refresh_materialized_views(conn)

        # Summary
        await show_summary(conn)

    await pool.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
