"""
VanCity Lens — Admin Data Loading Endpoints
Scrapes REW.ca listings + Vancouver Open Data (BCA assessed values)
and loads them into the parcels table.

Uses only stdlib (urllib) so no Docker rebuild is needed.
"""

import asyncio
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from .auth import require_admin
from .db import db

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}


# ── Helpers ───────────────────────────────────────────────────


def _fetch_json(url: str, headers: dict | None = None, *, timeout_s: int = 15) -> dict:
    """Blocking JSON fetch (run via asyncio.to_thread)."""
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode())


def _normalize_address(addr: str) -> str:
    """Normalize a street address for DB matching."""
    addr = addr.upper().strip()
    addr = re.sub(r",?\s*(VANCOUVER|BC|V\d\w\s*\d\w\d).*$", "", addr)
    for old, new in [
        ("STREET", "ST"),
        ("AVENUE", "AV"),
        ("BOULEVARD", "BLVD"),
        ("DRIVE", "DR"),
        ("ROAD", "RD"),
        ("CRESCENT", "CRES"),
        ("WEST ", "W "),
        ("EAST ", "E "),
        ("NORTH ", "N "),
        ("SOUTH ", "S "),
    ]:
        addr = addr.replace(old, new)
    return re.sub(r"\s+", " ", addr).strip()


def _parse_listings_html(html: str) -> list[dict]:
    """Extract address + price from REW.ca listing HTML fragments.

    REW.ca returns <article> blocks with:
      - <a ... title="ADDR, Vancouver, BC, POSTAL" href="https://www.rew.ca/properties/SLUG">
      - <div class='marqueepanel-title'>$X,XXX,XXX</div>  (or displaypanel-title)
    """
    results = []
    # Split into article blocks
    articles = re.split(r"<article[^>]*>", html)
    for chunk in articles[1:]:  # skip text before first article
        # Extract title from <a> tag (title comes before or after href)
        title_m = re.search(r'title="([^"]*Vancouver[^"]*)"', chunk)
        if not title_m:
            continue
        full_title = title_m.group(1)
        address = full_title.split(",")[0].strip()

        # Extract href
        href_m = re.search(r'href="([^"]*rew\.ca/properties/[^"]+)"', chunk)
        if not href_m:
            href_m = re.search(r'href="(/properties/[^"]+)"', chunk)
        href = href_m.group(1) if href_m else ""

        # Extract price from panel-title div
        price_m = re.search(
            r"(?:marqueepanel|displaypanel)-title[^>]*>\s*\$([\d,]+)", chunk
        )
        if not price_m:
            # Fallback: find first big dollar amount in chunk
            price_m = re.search(r"\$([\d,]{7,})", chunk)
        if not price_m:
            continue

        price = int(price_m.group(1).replace(",", ""))
        if price < 100_000:
            continue

        results.append(
            {
                "address": address,
                "href": href,
                "full_title": full_title,
                "price": price,
            }
        )

    return results


# ── REW.ca Scraper ────────────────────────────────────────────


@router.post("/scrape-rew")
async def scrape_rew(
    pages: int = Query(default=15, le=50, description="Number of pages to scrape"),
    property_types: str = Query(
        default="house,townhouse,duplex",
        description="Comma-separated property types",
    ),
):
    """
    Scrape REW.ca JSON API for Vancouver listings.
    Matches addresses to parcels and updates asking_price.
    """
    types = [t.strip() for t in property_types.split(",")]
    all_listings: list[dict] = []
    seen_addresses: set[str] = set()
    errors: list[str] = []

    for ptype in types:
        for page in range(1, pages + 1):
            url = (
                f"https://www.rew.ca/properties/areas/vancouver-bc"
                f"/type/{ptype}/page/{page}.json"
            )
            try:
                data = await asyncio.to_thread(_fetch_json, url, HEADERS)
                html = data.get("listings", "")
                if isinstance(html, list):
                    html = "".join(str(h) for h in html)
                if not html:
                    break
                page_listings = _parse_listings_html(html)
                if not page_listings:
                    break
                for listing in page_listings:
                    key = _normalize_address(listing["address"])
                    if key not in seen_addresses:
                        seen_addresses.add(key)
                        listing["norm_address"] = key
                        all_listings.append(listing)
                # Polite delay (3s to avoid 429 rate limiting)
                await asyncio.sleep(3)
            except Exception as e:
                errors.append(f"{ptype} p{page}: {e}")
                break

    # Match to parcels
    matched = 0
    match_details: list[dict] = []
    async with db.acquire() as conn:
        for listing in all_listings:
            norm = listing["norm_address"]
            if len(norm) < 5:
                continue
            # Strategy 1: exact prefix match
            row = await conn.fetchrow(
                "SELECT pid, civic_address FROM parcels "
                "WHERE UPPER(civic_address) LIKE $1 || '%' LIMIT 1",
                norm,
            )
            # Strategy 2: number + partial street
            if not row:
                parts = norm.split()
                if len(parts) >= 3:
                    row = await conn.fetchrow(
                        "SELECT pid, civic_address FROM parcels "
                        "WHERE UPPER(civic_address) LIKE '%' || $1 || ' ' || $2 || '%' LIMIT 1",
                        parts[0],
                        parts[-1],
                    )
            if row:
                href = listing["href"]
                if href.startswith("https://"):
                    rew_url = href
                else:
                    rew_url = f"https://www.rew.ca{href}"
                await conn.execute(
                    "UPDATE parcels SET asking_price = $1, rew_url = $3, updated_at = now() WHERE pid = $2",
                    listing["price"],
                    row["pid"],
                    rew_url,
                )
                matched += 1
                match_details.append(
                    {
                        "pid": row["pid"],
                        "civic_address": row["civic_address"],
                        "rew_address": listing["address"],
                        "price": listing["price"],
                        "rew_url": rew_url,
                    }
                )

        total_priced = await conn.fetchval(
            "SELECT count(*) FROM parcels WHERE asking_price IS NOT NULL"
        )

    return {
        "scraped": len(all_listings),
        "matched": matched,
        "total_with_price": total_priced,
        "matches": match_details[:50],
        "errors": errors,
    }


# ── BCA Assessed Values Loader ────────────────────────────────


@router.post("/load-bca")
async def load_bca(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=50000, le=300000),
):
    """
    Load real BC Assessment values from Vancouver Open Data property-tax-report.
    Fetches via the ODSQL API and updates parcels.assessed_value.
    """
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/property-tax-report/records"
    )

    updated = 0
    processed = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        while processed < max_records:
            url = (
                f"{base_url}?select=pid,current_land_value,current_improvement_value,"
                f"tax_assessment_year&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                pid_raw = record.get("pid")
                land_val = record.get("current_land_value")
                impr_val = record.get("current_improvement_value")

                if not pid_raw or land_val is None:
                    continue

                # Normalize PID to XXX-XXX-XXX format
                pid_digits = re.sub(r"[^0-9]", "", str(pid_raw))
                if len(pid_digits) == 9:
                    pid = f"{pid_digits[:3]}-{pid_digits[3:6]}-{pid_digits[6:9]}"
                else:
                    continue

                total_value = int(land_val or 0) + int(impr_val or 0)
                if total_value <= 0:
                    continue

                result = await conn.execute(
                    "UPDATE parcels SET assessed_value = $1, land_value = $3, improvement_value = $4, updated_at = now() "
                    "WHERE pid = $2",
                    total_value,
                    pid,
                    int(land_val or 0),
                    int(impr_val or 0),
                )
                if "UPDATE 1" in result:
                    updated += 1

            processed += len(results)
            offset += batch_size

            # Polite delay
            await asyncio.sleep(0.5)

            # Progress log every 1000 records
            if processed % 1000 == 0:
                pass  # API is async, no stdout needed

        total_assessed = await conn.fetchval(
            "SELECT count(*) FROM parcels WHERE assessed_value IS NOT NULL"
        )

    return {
        "processed": processed,
        "updated": updated,
        "total_with_assessed_value": total_assessed,
        "errors": errors[:20],
    }


# ── Heritage Sites Loader ─────────────────────────────────────


@router.post("/load-heritage")
async def load_heritage(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=50000, le=300000),
):
    """
    Load heritage sites from Vancouver Open Data heritage-sites dataset.
    Fetches via the ODSQL API and stores in heritage_sites table.
    """
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/heritage-sites/records"
    )

    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        # Clean reload: truncate existing data
        await conn.execute("TRUNCATE heritage_sites CASCADE")

        while loaded < max_records:
            url = (
                f"{base_url}?select=buildingnamespecifics,streetnumber,streetname,"
                f"evaluationgroup,municipaldesignationm,status,geo_point_2d"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                name = record.get("buildingnamespecifics", "")
                street_num = record.get("streetnumber", "")
                street_name = record.get("streetname", "")
                address = f"{street_num} {street_name}".strip()
                category = record.get("evaluationgroup", "")
                geo_point = record.get("geo_point_2d", {})

                if not geo_point:
                    continue

                lat = geo_point.get("lat")
                lon = geo_point.get("lon")

                if lat is None or lon is None:
                    continue

                try:
                    await conn.execute(
                        "INSERT INTO heritage_sites (name, address, category, geom) "
                        "VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326))",
                        name or address,
                        address,
                        category,
                        lon,
                        lat,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert error: {e}")

            offset += batch_size

            # Polite delay
            await asyncio.sleep(0.5)

        total_heritage = await conn.fetchval("SELECT count(*) FROM heritage_sites")

    return {
        "loaded": loaded,
        "total_heritage_sites": total_heritage,
        "errors": errors[:20],
    }


# ── Floodplain Zones Loader ───────────────────────────────────


@router.post("/load-floodplain")
async def load_floodplain(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=50000, le=300000),
):
    """
    Load designated floodplain zones from Vancouver Open Data.
    Fetches via the ODSQL API and stores in floodplain_zones table.
    """
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/designated-floodplain/records"
    )

    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        # Clean reload: truncate existing data
        await conn.execute("TRUNCATE floodplain_zones CASCADE")

        while loaded < max_records:
            url = (
                f"{base_url}?select=name,description,geom"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                zone_type = record.get("name", "") or record.get("description", "")
                geom_feature = record.get("geom")

                if not geom_feature:
                    continue

                try:
                    # geom is a GeoJSON Feature — extract .geometry for PostGIS
                    if isinstance(geom_feature, dict) and "geometry" in geom_feature:
                        geo_json = json.dumps(geom_feature["geometry"])
                    else:
                        geo_json = json.dumps(geom_feature)
                    await conn.execute(
                        "INSERT INTO floodplain_zones (zone_type, geom) "
                        "VALUES ($1, ST_SetSRID(ST_GeomFromGeoJSON($2), 4326))",
                        zone_type,
                        geo_json,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert error: {e}")

            offset += batch_size

            # Polite delay
            await asyncio.sleep(0.5)

        total_floodplain = await conn.fetchval("SELECT count(*) FROM floodplain_zones")

    return {
        "loaded": loaded,
        "total_floodplain_zones": total_floodplain,
        "errors": errors[:20],
    }


# ── Property Easements Loader ──────────────────────────────────


@router.post("/load-easements")
async def load_easements(
    batch_size: int = Query(
        default=1000, le=5000, description="Insert batch size (rows per DB flush)"
    ),
    max_records: int = Query(default=50000, le=300000),
):
    """
    Load property easements from Vancouver Open Data.
    Uses the dataset GeoJSON export so we can ingest >10k records (offset+limit is capped).
    """
    export_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/property-easements/exports/geojson?select=label"
    )

    loaded = 0
    errors: list[str] = []

    async with db.acquire() as conn:
        # Clean reload: truncate existing data
        await conn.execute("TRUNCATE property_easements CASCADE")

        try:
            data = await asyncio.to_thread(
                _fetch_json,
                export_url,
                {
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept": "application/json",
                },
                timeout_s=120,
            )
        except Exception as e:
            errors.append(f"fetch error: {e}")
            return {"loaded": 0, "total_easements": 0, "errors": errors[:20]}

        features = data.get("features", []) if isinstance(data, dict) else []

        insert_sql = (
            "INSERT INTO property_easements (easement_type, plan_number, geom) "
            "VALUES ($1, $2, ST_SetSRID(ST_GeomFromGeoJSON($3), 4326))"
        )
        pending: list[tuple[str, str, str]] = []

        for feature in features:
            if loaded >= max_records:
                break

            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            geom = feature.get("geometry")
            if not isinstance(geom, dict):
                continue

            label = (props.get("label") or "").strip()
            geom_json = json.dumps(geom)
            pending.append((label, "", geom_json))

            if len(pending) >= batch_size:
                try:
                    await conn.executemany(insert_sql, pending)
                    loaded += len(pending)
                except Exception as e:
                    errors.append(f"batch insert error: {e}")
                pending = []

        if pending:
            try:
                await conn.executemany(insert_sql, pending)
                loaded += len(pending)
            except Exception as e:
                errors.append(f"batch insert error: {e}")

        total_easements = await conn.fetchval("SELECT count(*) FROM property_easements")

    return {
        "loaded": loaded,
        "total_easements": total_easements,
        "errors": errors[:20],
    }


# ── Utility Infrastructure Loader (Water/Sewer Mains) ────────────


def _extract_geojson_geometry(record: dict) -> str | None:
    """
    Extract GeoJSON geometry from common Opendatasoft fields.

    Opendatasoft often returns geometry as:
      - {"type": "...", "coordinates": ...} or
      - {"type":"Feature","geometry":{...},"properties":{...}}
    """
    for key in ("geom", "geo_shape", "geometry", "the_geom"):
        val = record.get(key)
        if not val:
            continue
        if isinstance(val, dict):
            if isinstance(val.get("geometry"), dict):
                return json.dumps(val["geometry"])
            if "type" in val and "coordinates" in val:
                return json.dumps(val)
        if isinstance(val, str):
            # Some datasets may return a raw GeoJSON string.
            return val
    return None


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _pick_first(record: dict, keys: list[str]) -> str | None:
    for k in keys:
        v = record.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


async def _load_utility_lines_from_opendata(
    *,
    dataset_id: str,
    utility_type: str,
    source_url: str,
    batch_size: int,
    max_records: int,
) -> dict:
    # Use GeoJSON export so we can ingest datasets with >10k records (offset+limit is capped).
    export_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        f"/{dataset_id}/exports/geojson?select=recordid,*"
    )

    loaded = 0
    errors: list[str] = []

    async with db.acquire() as conn:
        # Delete only rows from this dataset so multiple datasets can coexist.
        await conn.execute(
            "DELETE FROM utility_lines WHERE source_dataset = $1", dataset_id
        )

        try:
            data = await asyncio.to_thread(
                _fetch_json,
                export_url,
                {
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept": "application/json",
                },
                timeout_s=240,
            )
        except Exception as e:
            errors.append(f"fetch error: {e}")
            total = await conn.fetchval(
                "SELECT count(*) FROM utility_lines WHERE source_dataset = $1",
                dataset_id,
            )
            return {
                "dataset_id": dataset_id,
                "utility_type": utility_type,
                "loaded": loaded,
                "total_rows_for_dataset": total,
                "errors": errors[:20],
                "source_url": source_url,
            }

        features = data.get("features", []) if isinstance(data, dict) else []

        insert_sql = """
            INSERT INTO utility_lines (
                utility_type, asset_id, line_type, diameter_mm, material,
                source_dataset, source_url, geom, metadata
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, ST_SetSRID(ST_GeomFromGeoJSON($8), 4326), $9::jsonb
            )
            """

        pending: list[tuple] = []
        for feature in features:
            if loaded >= max_records:
                break
            if not isinstance(feature, dict):
                continue

            props = feature.get("properties") or {}
            geom = feature.get("geometry")
            if not isinstance(props, dict) or not isinstance(geom, dict):
                continue

            # Build a record dict compatible with _extract_geojson_geometry().
            record = {**props, "geometry": geom}
            geom_json = _extract_geojson_geometry(record)
            if not geom_json:
                continue

            asset_id = _pick_first(
                props, ["asset_id", "assetid", "id", "objectid", "fid", "recordid"]
            )
            diameter_mm = (
                _as_float(props.get("diameter_mm"))
                or _as_float(props.get("diameter"))
                or _as_float(props.get("pipe_diameter"))
            )
            material = _pick_first(
                props, ["material", "pipe_material", "construction_material"]
            )
            line_type = _pick_first(
                props, ["line_type", "sewer_type", "effluent_type", "system", "type"]
            )

            pending.append(
                (
                    utility_type,
                    asset_id,
                    line_type,
                    diameter_mm,
                    material,
                    dataset_id,
                    source_url,
                    geom_json,
                    json.dumps(props),
                )
            )

            if len(pending) >= batch_size:
                try:
                    await conn.executemany(insert_sql, pending)
                    loaded += len(pending)
                except Exception as e:
                    errors.append(f"batch insert error: {e}")
                pending = []

        if pending:
            try:
                await conn.executemany(insert_sql, pending)
                loaded += len(pending)
            except Exception as e:
                errors.append(f"batch insert error: {e}")

        total = await conn.fetchval(
            "SELECT count(*) FROM utility_lines WHERE source_dataset = $1",
            dataset_id,
        )

    return {
        "dataset_id": dataset_id,
        "utility_type": utility_type,
        "loaded": loaded,
        "total_rows_for_dataset": total,
        "errors": errors[:20],
        "source_url": source_url,
    }


@router.post("/load-utility-lines")
async def load_utility_lines(
    dataset_id: str = Query(
        ..., description="Open Data dataset id, e.g. 'water-distribution-mains'"
    ),
    utility_type: str = Query(
        ..., description="Logical type stored in DB, e.g. 'water' or 'sewer'"
    ),
    source_url: str = Query(..., description="Human-friendly dataset page URL"),
    batch_size: int = Query(
        default=1000, le=5000, description="Insert batch size (rows per DB flush)"
    ),
    max_records: int = Query(default=200000, le=500000),
):
    """Load a utility line dataset from City of Vancouver Open Data into `utility_lines`."""
    return await _load_utility_lines_from_opendata(
        dataset_id=dataset_id,
        utility_type=utility_type,
        source_url=source_url,
        batch_size=batch_size,
        max_records=max_records,
    )


@router.post("/load-utilities-water")
async def load_utilities_water(
    batch_size: int = Query(
        default=1000, le=5000, description="Insert batch size (rows per DB flush)"
    ),
    max_records: int = Query(default=200000, le=500000),
):
    """Convenience loader for water mains (dataset id may be updated if CoV changes naming)."""
    return await _load_utility_lines_from_opendata(
        dataset_id="water-distribution-mains",
        utility_type="water",
        source_url="https://opendata.vancouver.ca/explore/dataset/water-distribution-mains/",
        batch_size=batch_size,
        max_records=max_records,
    )


@router.post("/load-utilities-sewer")
async def load_utilities_sewer(
    batch_size: int = Query(
        default=1000, le=5000, description="Insert batch size (rows per DB flush)"
    ),
    max_records: int = Query(default=200000, le=500000),
):
    """Convenience loader for sewer mains (dataset id may be updated if CoV changes naming)."""
    return await _load_utility_lines_from_opendata(
        dataset_id="sewer-mains",
        utility_type="sewer",
        source_url="https://opendata.vancouver.ca/explore/dataset/sewer-mains/",
        batch_size=batch_size,
        max_records=max_records,
    )


# ── Manual Listing Loader ─────────────────────────────────────


@router.post("/load-listing")
async def load_listing(
    pid: str = Query(..., description="Parcel PID (XXX-XXX-XXX)"),
    asking_price: int = Query(..., description="Asking price in dollars"),
):
    """Manually set the asking price for a specific parcel."""
    async with db.acquire() as conn:
        result = await conn.execute(
            "UPDATE parcels SET asking_price = $1, updated_at = now() WHERE pid = $2",
            asking_price,
            pid,
        )
        if "UPDATE 0" in result:
            return {"error": f"PID {pid} not found", "updated": False}
        row = await conn.fetchrow(
            "SELECT pid, civic_address, asking_price, assessed_value FROM parcels WHERE pid = $1",
            pid,
        )
        return {"updated": True, "parcel": dict(row) if row else None}


# ── Realtor.ca Scraper (RapidAPI) ─────────────────────────────

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.environ.get("RAPIDAPI_HOST", "realtor-ca-scraper-api.p.rapidapi.com")

# Vancouver bounding box (covers city proper)
VAN_BBOX = {
    "LatitudeMin": 49.20,
    "LatitudeMax": 49.32,
    "LongitudeMin": -123.27,
    "LongitudeMax": -123.02,
}


def _rapidapi_post(endpoint: str, payload: dict) -> dict:
    """Generic POST to Realtor.ca RapidAPI scraper. Returns parsed JSON."""
    if not RAPIDAPI_KEY:
        raise RuntimeError(
            "RAPIDAPI_KEY environment variable is required for RapidAPI calls. "
            "Set it in your .env file."
        )
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://{RAPIDAPI_HOST}{endpoint}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {err_body[:500]}") from e


# ── Realtor.ca Internal CREA API ─────────────────────────────

CREA_API_URL = "https://api2.realtor.ca/Listing.svc/PropertySearch_Post"
CREA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.realtor.ca",
    "Referer": "https://www.realtor.ca/",
    "Content-Type": "application/x-www-form-urlencoded",
}


def _crea_search(
    page: int = 1,
    records_per_page: int = 50,
    price_min: int = 0,
    price_max: int = 0,
    property_type: int = 1,
) -> dict:
    """Call Realtor.ca's internal CREA PropertySearch API. Returns parsed JSON.
    property_type: 1=Residential, 3=Commercial
    """
    form_data = urllib.parse.urlencode(
        {
            "CultureId": "1",
            "ApplicationId": "1",
            "PropertySearchTypeId": "0",
            "TransactionTypeId": "2",  # For sale
            "LatitudeMin": str(VAN_BBOX["LatitudeMin"]),
            "LatitudeMax": str(VAN_BBOX["LatitudeMax"]),
            "LongitudeMin": str(VAN_BBOX["LongitudeMin"]),
            "LongitudeMax": str(VAN_BBOX["LongitudeMax"]),
            "PriceMin": str(price_min) if price_min else "",
            "PriceMax": str(price_max) if price_max else "",
            "PropertyTypeGroupID": str(property_type),
            "CurrentPage": str(page),
            "RecordsPerPage": str(records_per_page),
            "Sort": "6-D",
            "Currency": "CAD",
        }
    ).encode()
    req = urllib.request.Request(CREA_API_URL, data=form_data, headers=CREA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"CREA HTTP {e.code}: {err_body[:500]}") from e


@router.post("/scrape-realtor")
async def scrape_realtor(
    pages: int = Query(
        default=5, le=20, description="Number of result pages to scrape"
    ),
    price_min: int = Query(default=500000, description="Minimum price"),
    price_max: int = Query(default=10000000, description="Maximum price"),
):
    """
    Scrape Realtor.ca via RapidAPI for Vancouver listings.
    Two-step approach: 1) get pagination index, 2) fetch each page of listings.
    Note: RapidAPI free tier has ~50-100 daily requests. Plan usage accordingly.
    """
    all_listings: list[dict] = []
    seen_addresses: set[str] = set()
    errors: list[str] = []

    # Step 1: Get the pagination index (list of page URLs)
    search_url = (
        f"https://www.realtor.ca/map#ZoomLevel=12"
        f"&Center={VAN_BBOX['LatitudeMin'] + 0.06}%2C{VAN_BBOX['LongitudeMin'] + 0.125}"
        f"&LatitudeMax={VAN_BBOX['LatitudeMax']}&LongitudeMax={VAN_BBOX['LongitudeMax']}"
        f"&LatitudeMin={VAN_BBOX['LatitudeMin']}&LongitudeMin={VAN_BBOX['LongitudeMin']}"
        f"&Sort=6-D&PGeoIds=g30_c2b2nq20&GeoName=Vancouver%2C+BC"
        f"&PropertyTypeGroupID=1&PriceMin={price_min}&PriceMax={price_max}"
        f"&TransactionTypeId=2&PropertySearchTypeId=0&Currency=CAD"
    )
    page_urls = []
    total_records = 0
    try:
        index = await asyncio.to_thread(
            _rapidapi_post, "/agents/properties", {"url": search_url}
        )
        total_records = index.get("totalRecords", 0)
        page_urls = index.get("pageUrls", [])
        if not page_urls:
            errors.append(
                f"RapidAPI returned totalRecords={total_records} but no pageUrls. "
                "Likely daily quota exceeded — try again tomorrow."
            )
    except Exception as e:
        errors.append(f"Step 1 index: {e}")

    # Step 2: Fetch actual listings from each page URL
    pages_to_fetch = min(pages, len(page_urls))
    for i in range(pages_to_fetch):
        try:
            page_data = await asyncio.to_thread(
                _rapidapi_post, "/agents/properties", {"url": page_urls[i]}
            )
            # Find the listings array in the response
            listings = []
            if isinstance(page_data, list):
                listings = page_data
            elif isinstance(page_data, dict):
                for k in ["Results", "results", "Listings", "listings", "properties"]:
                    if k in page_data and isinstance(page_data[k], list):
                        listings = page_data[k]
                        break

            for item in listings:
                listing = _parse_realtor_listing(item)
                if listing:
                    key = _normalize_address(listing.get("address", ""))
                    if key and key not in seen_addresses:
                        seen_addresses.add(key)
                        listing["norm_address"] = key
                        all_listings.append(listing)

            await asyncio.sleep(2)  # polite delay between pages
        except Exception as e:
            errors.append(f"Page {i + 1}: {e}")
            break

    # Match to parcels
    matched = 0
    match_details: list[dict] = []
    if all_listings:
        async with db.acquire() as conn:
            for listing in all_listings:
                norm = listing.get("norm_address", "")
                if len(norm) < 5:
                    continue
                price = listing.get("price", 0)
                if not price or price < 100_000:
                    continue

                # Strategy 1: exact prefix match
                row = await conn.fetchrow(
                    "SELECT pid, civic_address FROM parcels "
                    "WHERE UPPER(civic_address) LIKE $1 || '%' LIMIT 1",
                    norm,
                )
                # Strategy 2: number + partial street
                if not row:
                    parts = norm.split()
                    if len(parts) >= 3:
                        row = await conn.fetchrow(
                            "SELECT pid, civic_address FROM parcels "
                            "WHERE UPPER(civic_address) LIKE '%' || $1 || ' ' || $2 || '%' LIMIT 1",
                            parts[0],
                            parts[-1],
                        )
                # Strategy 3: lat/lng proximity if available
                if not row and listing.get("lat") and listing.get("lng"):
                    row = await conn.fetchrow(
                        "SELECT pid, civic_address FROM parcels "
                        "WHERE ST_DWithin("
                        "  ST_Centroid(geom)::geography,"
                        "  ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,"
                        "  30"
                        ") ORDER BY ST_Distance("
                        "  ST_Centroid(geom)::geography,"
                        "  ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography"
                        ") LIMIT 1",
                        listing["lng"],
                        listing["lat"],
                    )

                if row:
                    await conn.execute(
                        "UPDATE parcels SET asking_price = $1, updated_at = now() "
                        "WHERE pid = $2 AND (asking_price IS NULL OR asking_price != $1)",
                        price,
                        row["pid"],
                    )
                    matched += 1
                    match_details.append(
                        {
                            "pid": row["pid"],
                            "civic_address": row["civic_address"],
                            "realtor_address": listing.get("address", ""),
                            "price": price,
                            "mls": listing.get("mls", ""),
                        }
                    )

            total_priced = await conn.fetchval(
                "SELECT count(*) FROM parcels WHERE asking_price IS NOT NULL"
            )
    else:
        total_priced = 0

    return {
        "api_approach": "RapidAPI",
        "scraped": len(all_listings),
        "matched": matched,
        "total_with_price": total_priced,
        "matches": match_details[:50],
        "errors": errors,
        "sample_listings": [
            {
                "address": listing.get("address"),
                "price": listing.get("price"),
                "mls": listing.get("mls"),
            }
            for listing in all_listings[:5]
        ],
    }


def _parse_realtor_listing(item: dict) -> dict | None:
    """Parse a single Realtor.ca listing from various API response formats."""
    if not isinstance(item, dict):
        return None

    listing = {}

    # Price — try multiple field names
    for pf in ["Price", "price", "ListPrice", "listPrice"]:
        val = item.get(pf)
        if val:
            if isinstance(val, str):
                val = re.sub(r"[^0-9]", "", val)
                if val:
                    listing["price"] = int(val)
            elif isinstance(val, (int, float)):
                listing["price"] = int(val)
            break

    # Nested Property.Price format (common in Realtor.ca API)
    if "price" not in listing:
        prop = item.get("Property", {})
        price_str = prop.get("Price", prop.get("price", ""))
        if price_str:
            digits = re.sub(r"[^0-9]", "", str(price_str))
            if digits:
                listing["price"] = int(digits)

    # Address — try multiple structures
    addr = item.get("Address", item.get("address", {}))
    if isinstance(addr, str):
        listing["address"] = addr
    elif isinstance(addr, dict):
        parts = []
        for f in ["AddressText", "addressText", "StreetAddress", "streetAddress"]:
            if addr.get(f):
                parts.append(addr[f])
                break
        if not parts:
            num = addr.get("StreetNumber", addr.get("streetNumber", ""))
            name = addr.get("StreetName", addr.get("streetName", ""))
            sfx = addr.get("StreetSuffix", addr.get("streetSuffix", ""))
            if num and name:
                parts = [f"{num} {name} {sfx}".strip()]
        if parts:
            raw_addr = parts[0].split("|")[0].strip()  # Realtor.ca uses | to separate
            listing["address"] = raw_addr

    # Nested Property.Address format
    if "address" not in listing:
        prop = item.get("Property", {})
        adr = prop.get("Address", {})
        if isinstance(adr, dict):
            txt = adr.get("AddressText", "")
            if txt:
                listing["address"] = txt.split("|")[0].strip()

    # Coordinates
    for lat_f, lng_f in [
        ("Latitude", "Longitude"),
        ("latitude", "longitude"),
        ("lat", "lng"),
    ]:
        if item.get(lat_f) and item.get(lng_f):
            listing["lat"] = float(item[lat_f])
            listing["lng"] = float(item[lng_f])
            break

    # MLS number
    for mls_f in ["MlsNumber", "mlsNumber", "MLS", "mls", "ListingID"]:
        if item.get(mls_f):
            listing["mls"] = str(item[mls_f])
            break
    if "mls" not in listing:
        prop = item.get("Property", {})
        listing["mls"] = prop.get("MlsNumber", "")

    if not listing.get("price") and not listing.get("address"):
        return None

    return listing


@router.get("/debug-realtor")
async def debug_realtor():
    """Debug: test both RapidAPI and CREA direct API for Realtor.ca data."""
    results = {}

    # Test 1: RapidAPI /agents/properties (two-step: get index, then page 1)
    van_search_url = (
        "https://www.realtor.ca/map#ZoomLevel=12&Center=49.26%2C-123.145"
        "&LatitudeMax=49.32&LongitudeMax=-123.02"
        "&LatitudeMin=49.20&LongitudeMin=-123.27"
        "&Sort=6-D&PGeoIds=g30_c2b2nq20&GeoName=Vancouver%2C+BC"
        "&PropertyTypeGroupID=1&TransactionTypeId=2"
        "&PropertySearchTypeId=0&Currency=CAD"
    )
    try:
        index_data = await asyncio.to_thread(
            _rapidapi_post, "/agents/properties", {"url": van_search_url}
        )
        total = index_data.get("totalRecords", 0)
        page_urls = index_data.get("pageUrls", [])
        results["rapidapi_index"] = {
            "success": True,
            "totalRecords": total,
            "totalPages": index_data.get("totalPages", 0),
            "num_page_urls": len(page_urls),
        }

        # If we got page URLs, fetch page 1 to see actual listings
        if page_urls:
            try:
                page1 = await asyncio.to_thread(
                    _rapidapi_post, "/agents/properties", {"url": page_urls[0]}
                )
                results["rapidapi_page1"] = {
                    "success": True,
                    "type": type(page1).__name__,
                    "keys": list(page1.keys())[:15]
                    if isinstance(page1, dict)
                    else None,
                    "sample": str(page1)[:2000],
                }
            except Exception as e:
                results["rapidapi_page1"] = {"success": False, "error": str(e)[:300]}
        else:
            results["rapidapi_note"] = (
                "No page URLs returned — likely RapidAPI daily quota exceeded. "
                "The free tier usually allows ~50-100 requests/day. Try again tomorrow."
            )

    except Exception as e:
        results["rapidapi_index"] = {"success": False, "error": str(e)[:300]}

    # Test 2: CREA direct API (usually blocked by Imperva WAF from servers)
    try:
        crea_data = await asyncio.to_thread(
            _crea_search,
            page=1,
            records_per_page=3,
            price_min=500000,
            price_max=5000000,
        )
        paging = crea_data.get("Paging", {})
        results["crea_direct"] = {
            "success": True,
            "total_records": paging.get("TotalRecords"),
            "result_count": len(crea_data.get("Results", [])),
        }
    except Exception as e:
        results["crea_direct"] = {
            "success": False,
            "error": str(e)[:300],
            "note": "Expected: Imperva WAF blocks direct server→CREA calls",
        }

    return results


# ── Debug ─────────────────────────────────────────────────────


@router.get("/debug-rew")
async def debug_rew():
    """Debug: show what REW.ca JSON API returns from inside Docker."""
    url = "https://www.rew.ca/properties/areas/vancouver-bc/type/house/page/1.json"
    try:
        data = await asyncio.to_thread(_fetch_json, url, HEADERS)
        listings_raw = data.get("listings", "")
        listings_type = type(listings_raw).__name__
        if isinstance(listings_raw, str):
            sample = listings_raw[:3000]
            length = len(listings_raw)
        elif isinstance(listings_raw, list):
            sample = str(listings_raw[:2])[:3000]
            length = len(listings_raw)
        else:
            sample = str(listings_raw)[:3000]
            length = -1

        # Try parsing with current parser
        html = (
            listings_raw
            if isinstance(listings_raw, str)
            else "".join(str(h) for h in listings_raw)
            if isinstance(listings_raw, list)
            else ""
        )
        parsed = _parse_listings_html(html)

        # Also try the v2 scraper approach (article-based parsing)
        articles = re.findall(r"<article[^>]*>(.*?)</article>", html, re.DOTALL)
        article_sample = articles[0][:500] if articles else "NO ARTICLES FOUND"

        # Find ALL <a> tags with title
        a_tags = re.findall(r'<a[^>]+title="([^"]+)"', html)

        # Find ALL prices
        prices = re.findall(r"\$([\d,]+)", html)

        return {
            "keys": list(data.keys()),
            "listings_type": listings_type,
            "listings_length": length,
            "sample": sample,
            "parsed_count": len(parsed),
            "parsed_sample": parsed[:3],
            "article_count": len(articles),
            "article_sample": article_sample,
            "a_tag_titles": a_tags[:20],
            "prices_found": prices[:20],
        }
    except Exception as e:
        return {"error": str(e)}


# ── Run Migrations ────────────────────────────────────────────


@router.post("/run-migrations")
async def run_migrations():
    """Run pending database migrations for local/dev DBs with existing volumes."""
    results = []
    async with db.acquire() as conn:
        # Migration 003: Add rew_url column
        try:
            await conn.execute(
                "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS rew_url TEXT"
            )
            results.append({"migration": "003_add_rew_url", "status": "ok"})
        except Exception as e:
            results.append(
                {"migration": "003_add_rew_url", "status": "error", "detail": str(e)}
            )

        # Migration 004: Risk layers tables + land/improvement split
        migration_004_stmts = [
            """CREATE TABLE IF NOT EXISTS heritage_sites (
                id SERIAL PRIMARY KEY, name TEXT, address TEXT, category TEXT,
                geom GEOMETRY(Point, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_heritage_geom ON heritage_sites USING GIST (geom)",
            """CREATE TABLE IF NOT EXISTS floodplain_zones (
                id SERIAL PRIMARY KEY, zone_type TEXT,
                geom GEOMETRY(Geometry, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_floodplain_geom ON floodplain_zones USING GIST (geom)",
            """CREATE TABLE IF NOT EXISTS property_easements (
                id SERIAL PRIMARY KEY, easement_type TEXT, plan_number TEXT,
                geom GEOMETRY(Geometry, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_easements_geom ON property_easements USING GIST (geom)",
            "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS land_value BIGINT",
            "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS improvement_value BIGINT",
        ]
        for stmt in migration_004_stmts:
            try:
                await conn.execute(stmt)
            except Exception as e:
                results.append(
                    {
                        "migration": "004_risk_layers",
                        "status": "error",
                        "detail": str(e),
                        "stmt": stmt[:80],
                    }
                )
                break
        else:
            results.append({"migration": "004_risk_layers", "status": "ok"})

        # Migration 005: V2 validation layers
        migration_005_stmts = [
            """CREATE TABLE IF NOT EXISTS view_cones (
                id SERIAL PRIMARY KEY, view_number TEXT, view_cone_name TEXT, description TEXT,
                geom GEOMETRY(Geometry, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_view_cones_geom ON view_cones USING GIST (geom)",
            """CREATE TABLE IF NOT EXISTS protected_trees (
                id SERIAL PRIMARY KEY, asset_id TEXT, common_name TEXT,
                diameter_cm NUMERIC, height_m NUMERIC,
                geom GEOMETRY(Point, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_protected_trees_geom ON protected_trees USING GIST (geom)",
            """CREATE TABLE IF NOT EXISTS non_market_housing (
                id SERIAL PRIMARY KEY, name TEXT, address TEXT,
                project_status TEXT, total_units INT,
                geom GEOMETRY(Geometry, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_nmh_geom ON non_market_housing USING GIST (geom)",
            """CREATE TABLE IF NOT EXISTS community_gardens (
                id SERIAL PRIMARY KEY, name TEXT, address TEXT, number_of_plots INT,
                geom GEOMETRY(Point, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_community_gardens_geom ON community_gardens USING GIST (geom)",
            """CREATE TABLE IF NOT EXISTS issued_building_permits (
                id SERIAL PRIMARY KEY, permit_number TEXT, type_of_work TEXT,
                specific_use TEXT, project_value BIGINT, issue_year INT,
                geom GEOMETRY(Point, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_permits_geom ON issued_building_permits USING GIST (geom)",
            "CREATE INDEX IF NOT EXISTS idx_permits_year_value ON issued_building_permits (issue_year, project_value)",
            """CREATE TABLE IF NOT EXISTS zoning_districts (
                id SERIAL PRIMARY KEY, zoning_classification TEXT, zoning_category TEXT,
                cd_1_number TEXT, geom GEOMETRY(Geometry, 4326), created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_zoning_geom ON zoning_districts USING GIST (geom)",
            "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS year_built INT",
            "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS geo_local_area TEXT",
        ]
        for stmt in migration_005_stmts:
            try:
                await conn.execute(stmt)
            except Exception as e:
                results.append(
                    {
                        "migration": "005_v2_risk_layers",
                        "status": "error",
                        "detail": str(e),
                        "stmt": stmt[:80],
                    }
                )
                break
        else:
            results.append({"migration": "005_v2_risk_layers", "status": "ok"})

        # Migration 006: V3 business licences + permit elapsed days
        migration_006_stmts = [
            """CREATE TABLE IF NOT EXISTS business_licences (
                id SERIAL PRIMARY KEY, licence_number TEXT, business_name TEXT,
                business_type TEXT, status TEXT, issue_date DATE, expiry_date DATE,
                address TEXT, local_area TEXT, number_of_employees INT,
                geom GEOMETRY(Point, 4326)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_business_licences_geom ON business_licences USING GIST (geom)",
            "CREATE INDEX IF NOT EXISTS idx_business_licences_status ON business_licences (status)",
            "CREATE INDEX IF NOT EXISTS idx_business_licences_type ON business_licences (business_type)",
        ]
        for stmt in migration_006_stmts:
            try:
                await conn.execute(stmt)
            except Exception as e:
                results.append(
                    {
                        "migration": "006_v3_execution_risk",
                        "status": "error",
                        "detail": str(e),
                        "stmt": stmt[:80],
                    }
                )
                break
        else:
            results.append({"migration": "006_v3_execution_risk", "status": "ok"})

        # Migration 030: Utility infrastructure lines (for due diligence evidence)
        migration_030_stmts = [
            """CREATE TABLE IF NOT EXISTS utility_lines (
                id SERIAL PRIMARY KEY,
                utility_type TEXT NOT NULL,
                asset_id TEXT,
                line_type TEXT,
                diameter_mm NUMERIC,
                material TEXT,
                source_dataset TEXT NOT NULL,
                source_url TEXT,
                geom GEOMETRY(Geometry, 4326) NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_utility_lines_geom ON utility_lines USING GIST (geom)",
            "CREATE INDEX IF NOT EXISTS idx_utility_lines_type ON utility_lines (utility_type)",
            "CREATE INDEX IF NOT EXISTS idx_utility_lines_dataset ON utility_lines (source_dataset)",
        ]
        for stmt in migration_030_stmts:
            try:
                await conn.execute(stmt)
            except Exception as e:
                results.append(
                    {
                        "migration": "030_utility_lines",
                        "status": "error",
                        "detail": str(e),
                        "stmt": stmt[:80],
                    }
                )
                break
        else:
            results.append({"migration": "030_utility_lines", "status": "ok"})

    return {"migrations": results}


# ── V2 Data Loaders ──────────────────────────────────────────


@router.post("/load-view-cones")
async def load_view_cones():
    """Load view cone polygons from Vancouver Open Data view-cones dataset."""
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/view-cones/records"
    )
    loaded = 0
    errors: list[str] = []

    async with db.acquire() as conn:
        await conn.execute("TRUNCATE view_cones CASCADE")
        url = f"{base_url}?select=view_number,view_cone_name,description,geom&limit=100&offset=0"
        try:
            data = await asyncio.to_thread(
                _fetch_json,
                url,
                {
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept": "application/json",
                },
            )
        except Exception as e:
            return {"error": str(e)}

        for record in data.get("results", []):
            geom_feature = record.get("geom")
            if not geom_feature:
                continue
            try:
                if isinstance(geom_feature, dict) and "geometry" in geom_feature:
                    geo_json = json.dumps(geom_feature["geometry"])
                else:
                    geo_json = json.dumps(geom_feature)
                await conn.execute(
                    "INSERT INTO view_cones (view_number, view_cone_name, description, geom) "
                    "VALUES ($1, $2, $3, ST_SetSRID(ST_GeomFromGeoJSON($4), 4326))",
                    record.get("view_number", ""),
                    record.get("view_cone_name", ""),
                    record.get("description", ""),
                    geo_json,
                )
                loaded += 1
            except Exception as e:
                errors.append(f"insert: {e}")

        total = await conn.fetchval("SELECT count(*) FROM view_cones")

    return {"loaded": loaded, "total_view_cones": total, "errors": errors[:10]}


@router.post("/load-trees")
async def load_trees(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=200000, le=300000),
    min_diameter: int = Query(default=30, description="Minimum diameter in cm"),
):
    """Load large trees from Vancouver Open Data public-trees dataset."""
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/public-trees/records"
    )
    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        await conn.execute("TRUNCATE protected_trees CASCADE")

        while loaded < max_records:
            url = (
                f"{base_url}?select=asset_id,common_name,diameter_cm,height_m,geo_point_2d"
                f"&where=diameter_cm>={min_diameter}"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                geo_point = record.get("geo_point_2d", {})
                if not geo_point:
                    continue
                lat = geo_point.get("lat")
                lon = geo_point.get("lon")
                if lat is None or lon is None:
                    continue

                diameter = record.get("diameter_cm")
                height = record.get("height_m")
                try:
                    await conn.execute(
                        "INSERT INTO protected_trees (asset_id, common_name, diameter_cm, height_m, geom) "
                        "VALUES ($1, $2, $3, $4, ST_SetSRID(ST_MakePoint($5, $6), 4326))",
                        str(record.get("asset_id", "")),
                        record.get("common_name", ""),
                        float(diameter) if diameter else None,
                        float(height) if height else None,
                        lon,
                        lat,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert: {e}")

            offset += batch_size
            await asyncio.sleep(0.5)

        total = await conn.fetchval("SELECT count(*) FROM protected_trees")

    return {"loaded": loaded, "total_protected_trees": total, "errors": errors[:10]}


@router.post("/load-non-market-housing")
async def load_non_market_housing(
    batch_size: int = Query(default=100, le=100),
):
    """Load non-market housing from Vancouver Open Data."""
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/non-market-housing/records"
    )
    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        await conn.execute("TRUNCATE non_market_housing CASCADE")

        while True:
            url = (
                f"{base_url}?select=name,address,project_status,geom"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                geom_feature = record.get("geom")
                if not geom_feature:
                    continue

                try:
                    if isinstance(geom_feature, dict) and "geometry" in geom_feature:
                        geo_json = json.dumps(geom_feature["geometry"])
                    else:
                        geo_json = json.dumps(geom_feature)
                    await conn.execute(
                        "INSERT INTO non_market_housing (name, address, project_status, total_units, geom) "
                        "VALUES ($1, $2, $3, $4, ST_SetSRID(ST_GeomFromGeoJSON($5), 4326))",
                        record.get("name", ""),
                        record.get("address", ""),
                        record.get("project_status", ""),
                        None,
                        geo_json,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert: {e}")

            offset += batch_size
            await asyncio.sleep(0.5)

        total = await conn.fetchval("SELECT count(*) FROM non_market_housing")

    return {"loaded": loaded, "total_non_market_housing": total, "errors": errors[:10]}


@router.post("/load-community-gardens")
async def load_community_gardens(
    batch_size: int = Query(default=100, le=100),
):
    """Load community gardens from Vancouver Open Data."""
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/community-gardens-and-food-trees/records"
    )
    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        await conn.execute("TRUNCATE community_gardens CASCADE")

        while True:
            url = (
                f"{base_url}?select=name,number_of_plots,merged_address,geo_point_2d"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                geo_point = record.get("geo_point_2d", {})
                if not geo_point:
                    continue
                lat = geo_point.get("lat")
                lon = geo_point.get("lon")
                if lat is None or lon is None:
                    continue

                plots_raw = record.get("number_of_plots")
                plots = int(plots_raw) if plots_raw else None

                try:
                    await conn.execute(
                        "INSERT INTO community_gardens (name, address, number_of_plots, geom) "
                        "VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326))",
                        record.get("name", ""),
                        record.get("merged_address", ""),
                        plots,
                        lon,
                        lat,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert: {e}")

            offset += batch_size
            await asyncio.sleep(0.5)

        total = await conn.fetchval("SELECT count(*) FROM community_gardens")

    return {"loaded": loaded, "total_community_gardens": total, "errors": errors[:10]}


@router.post("/load-building-permits")
async def load_building_permits(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=50000, le=100000),
    min_value: int = Query(default=1000000, description="Minimum project value"),
):
    """Load issued building permits from Vancouver Open Data."""
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/issued-building-permits/records"
    )
    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        await conn.execute("TRUNCATE issued_building_permits CASCADE")

        while loaded < max_records:
            url = (
                f"{base_url}?select=permitnumber,typeofwork,specificusecategory,"
                f"projectvalue,issueyear,geo_point_2d"
                f"&where=projectvalue>={min_value}"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                geo_point = record.get("geo_point_2d", {})
                if not geo_point:
                    continue
                lat = geo_point.get("lat")
                lon = geo_point.get("lon")
                if lat is None or lon is None:
                    continue

                pv = record.get("projectvalue")
                iy = record.get("issueyear")
                specific_use = record.get("specificusecategory", "")
                if isinstance(specific_use, list):
                    specific_use = ", ".join(str(s) for s in specific_use)
                try:
                    await conn.execute(
                        "INSERT INTO issued_building_permits "
                        "(permit_number, type_of_work, specific_use, project_value, issue_year, geom) "
                        "VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326))",
                        record.get("permitnumber", ""),
                        record.get("typeofwork", "") or "",
                        specific_use or "",
                        int(pv) if pv else None,
                        int(iy) if iy else None,
                        lon,
                        lat,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert: {e}")

            offset += batch_size
            await asyncio.sleep(0.5)

        total = await conn.fetchval("SELECT count(*) FROM issued_building_permits")

    return {"loaded": loaded, "total_permits": total, "errors": errors[:10]}


@router.post("/load-zoning-districts")
async def load_zoning_districts(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=5000, le=10000),
):
    """Load zoning districts from Vancouver Open Data (for CD-1 detection)."""
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/zoning-districts-and-labels/records"
    )
    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        await conn.execute("TRUNCATE zoning_districts CASCADE")

        while loaded < max_records:
            url = (
                f"{base_url}?select=zoning_classification,zoning_category,cd_1_number,geom"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                geom_feature = record.get("geom")
                if not geom_feature:
                    continue
                try:
                    if isinstance(geom_feature, dict) and "geometry" in geom_feature:
                        geo_json = json.dumps(geom_feature["geometry"])
                    else:
                        geo_json = json.dumps(geom_feature)
                    await conn.execute(
                        "INSERT INTO zoning_districts "
                        "(zoning_classification, zoning_category, cd_1_number, geom) "
                        "VALUES ($1, $2, $3, ST_SetSRID(ST_GeomFromGeoJSON($4), 4326))",
                        record.get("zoning_classification", ""),
                        record.get("zoning_category", ""),
                        record.get("cd_1_number", ""),
                        geo_json,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert: {e}")

            offset += batch_size
            await asyncio.sleep(0.5)

        total = await conn.fetchval("SELECT count(*) FROM zoning_districts")

    return {"loaded": loaded, "total_zoning_districts": total, "errors": errors[:10]}


@router.post("/load-year-built")
async def load_year_built(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=100000, le=300000),
):
    """Enrich parcels with year_built and geo_local_area from property-tax-report."""
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/property-tax-report/records"
    )
    updated = 0
    processed = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        while processed < max_records:
            where_clause = urllib.parse.quote("year_built IS NOT NULL")
            url = (
                f"{base_url}?select=pid,year_built,neighbourhood_code"
                f"&where={where_clause}"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                pid_raw = record.get("pid")
                yb = record.get("year_built")
                neighborhood = record.get("neighbourhood_code", "")

                if not pid_raw or not yb:
                    continue

                pid_digits = re.sub(r"[^0-9]", "", str(pid_raw))
                if len(pid_digits) == 9:
                    pid = f"{pid_digits[:3]}-{pid_digits[3:6]}-{pid_digits[6:9]}"
                else:
                    continue

                try:
                    result = await conn.execute(
                        "UPDATE parcels SET year_built = $1, geo_local_area = $2, updated_at = now() "
                        "WHERE pid = $3 AND (year_built IS NULL OR geo_local_area IS NULL)",
                        int(yb),
                        neighborhood,
                        pid,
                    )
                    if "UPDATE 1" in result:
                        updated += 1
                except Exception as e:
                    errors.append(f"update: {e}")

            processed += len(results)
            offset += batch_size
            await asyncio.sleep(0.5)

        total_enriched = await conn.fetchval(
            "SELECT count(*) FROM parcels WHERE year_built IS NOT NULL"
        )

    return {
        "processed": processed,
        "updated": updated,
        "total_with_year_built": total_enriched,
        "errors": errors[:10],
    }


# ── V3 Business Licences Loader ────────────────────────────────


@router.post("/load-business-licences")
async def load_business_licences(
    batch_size: int = Query(default=100, le=100),
    max_records: int = Query(default=50000, le=300000),
):
    """
    Load business licences from Vancouver Open Data business-licences dataset.
    Used for V3 tenant displacement + environmental risk estimation.
    Only loads licences with status=Issued and valid geo_point_2d.
    """
    base_url = (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
        "/business-licences/records"
    )
    loaded = 0
    errors: list[str] = []
    offset = 0

    async with db.acquire() as conn:
        await conn.execute("TRUNCATE business_licences CASCADE")

        while loaded < max_records:
            where_clause = urllib.parse.quote("status='Issued'")
            url = (
                f"{base_url}?select=licencenumber,businessname,businesstype,"
                f"status,issueddate,expireddate,house,street,localarea,"
                f"numberofemployees,geo_point_2d"
                f"&where={where_clause}"
                f"&limit={batch_size}&offset={offset}"
            )
            try:
                data = await asyncio.to_thread(
                    _fetch_json,
                    url,
                    {
                        "User-Agent": HEADERS["User-Agent"],
                        "Accept": "application/json",
                    },
                )
            except Exception as e:
                errors.append(f"offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for record in results:
                geo_point = record.get("geo_point_2d", {})
                if not geo_point:
                    continue
                lat = geo_point.get("lat")
                lon = geo_point.get("lon")
                if lat is None or lon is None:
                    continue

                house = record.get("house", "")
                street = record.get("street", "")
                address = f"{house} {street}".strip()

                try:
                    await conn.execute(
                        "INSERT INTO business_licences "
                        "(licence_number, business_name, business_type, status, "
                        " address, local_area, number_of_employees, geom) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, "
                        "ST_SetSRID(ST_MakePoint($8, $9), 4326))",
                        record.get("licencenumber", ""),
                        record.get("businessname", ""),
                        record.get("businesstype", ""),
                        record.get("status", ""),
                        address,
                        record.get("localarea", ""),
                        int(record["numberofemployees"])
                        if record.get("numberofemployees")
                        else None,
                        lon,
                        lat,
                    )
                    loaded += 1
                except Exception as e:
                    errors.append(f"insert: {e}")

            offset += batch_size
            await asyncio.sleep(0.5)

        total = await conn.fetchval("SELECT count(*) FROM business_licences")

    return {"loaded": loaded, "total_business_licences": total, "errors": errors[:20]}


# ── Status ────────────────────────────────────────────────────


@router.get("/data-status")
async def data_status():
    """Check the current state of data in the database."""
    async with db.acquire() as conn:
        stats = {}
        stats["total_parcels"] = await conn.fetchval("SELECT count(*) FROM parcels")
        stats["with_asking_price"] = await conn.fetchval(
            "SELECT count(*) FROM parcels WHERE asking_price IS NOT NULL"
        )
        stats["with_assessed_value"] = await conn.fetchval(
            "SELECT count(*) FROM parcels WHERE assessed_value IS NOT NULL"
        )
        stats["in_toa"] = await conn.fetchval(
            "SELECT count(DISTINCT p.pid) FROM parcels p "
            "JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom)"
        )
        stats["priced_in_toa"] = await conn.fetchval(
            "SELECT count(DISTINCT p.pid) FROM parcels p "
            "JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom) "
            "WHERE p.asking_price IS NOT NULL"
        )
        stats["priced_and_assessed_in_toa"] = await conn.fetchval(
            "SELECT count(DISTINCT p.pid) FROM parcels p "
            "JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom) "
            "WHERE p.asking_price IS NOT NULL AND p.assessed_value IS NOT NULL"
        )

        # Risk and validation data layer stats
        try:
            stats["heritage_sites"] = await conn.fetchval(
                "SELECT count(*) FROM heritage_sites"
            )
        except Exception:
            stats["heritage_sites"] = 0

        try:
            stats["floodplain_zones"] = await conn.fetchval(
                "SELECT count(*) FROM floodplain_zones"
            )
        except Exception:
            stats["floodplain_zones"] = 0

        try:
            stats["easements"] = await conn.fetchval(
                "SELECT count(*) FROM property_easements"
            )
        except Exception:
            stats["easements"] = 0

        try:
            stats["parcels_with_land_split"] = await conn.fetchval(
                "SELECT count(*) FROM parcels WHERE land_value IS NOT NULL"
            )
        except Exception:
            stats["parcels_with_land_split"] = 0

        # V2 + V3 data layers
        for table_name in [
            "view_cones",
            "protected_trees",
            "non_market_housing",
            "community_gardens",
            "issued_building_permits",
            "zoning_districts",
            "business_licences",
        ]:
            try:
                stats[table_name] = await conn.fetchval(
                    f"SELECT count(*) FROM {table_name}"
                )
            except Exception:
                stats[table_name] = 0

        try:
            stats["parcels_with_year_built"] = await conn.fetchval(
                "SELECT count(*) FROM parcels WHERE year_built IS NOT NULL"
            )
        except Exception:
            stats["parcels_with_year_built"] = 0

        try:
            stats["parcels_with_neighborhood"] = await conn.fetchval(
                "SELECT count(*) FROM parcels WHERE geo_local_area IS NOT NULL"
            )
        except Exception:
            stats["parcels_with_neighborhood"] = 0

        # Sample of priced parcels IN TOA
        priced = await conn.fetch(
            "SELECT DISTINCT ON (p.pid) p.pid, p.civic_address, p.asking_price, "
            "p.assessed_value, p.current_zoning, b.station_name, b.tier "
            "FROM parcels p "
            "JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom) "
            "JOIN transit_stations s ON s.id = b.station_id "
            "WHERE p.asking_price IS NOT NULL "
            "ORDER BY p.pid, b.tier LIMIT 10"
        )
        stats["sample_priced"] = [dict(r) for r in priced]
        return stats


# ── Pool Monitoring Routes ────────────────────────────────────────


@router.get(
    "/pool/metrics",
    summary="Get connection pool metrics",
    description="Returns real-time connection pool statistics including utilization, "
    "timing, and error counts. Admin-only endpoint.",
)
async def get_pool_metrics():
    """Get current connection pool metrics (VCL-87 / PERF-013)."""
    if db.monitor is None:
        return {"error": "Pool monitor not initialized"}

    metrics = db.monitor.get_metrics()
    return {
        "pool": {
            "size": metrics.size,
            "min_size": metrics.min_size,
            "max_size": metrics.max_size,
            "free_size": metrics.free_size,
            "used_size": metrics.used_size,
            "utilization_pct": round(metrics.utilization_pct, 2),
        },
        "queries": {
            "total": metrics.queries_total,
            "active": metrics.queries_active,
        },
        "timing": {
            "avg_acquire_ms": round(metrics.avg_acquire_time_ms, 2),
            "max_acquire_ms": round(metrics.max_acquire_time_ms, 2),
        },
        "errors": {
            "connection_errors": metrics.connection_errors,
            "pool_full_events": metrics.pool_full_events,
        },
        "uptime_seconds": round(metrics.uptime_seconds, 1),
    }


@router.get(
    "/pool/health",
    summary="Get connection pool health status",
    description="Returns pool health assessment (healthy/degraded/unhealthy) "
    "based on utilization and error thresholds.",
)
async def get_pool_health():
    """Get connection pool health status (VCL-87 / PERF-013)."""
    if db.monitor is None:
        return {"error": "Pool monitor not initialized"}

    health = db.monitor.get_health_status()
    metrics = db.monitor.get_metrics()

    return {
        "status": health["status"],
        "reason": health["reason"],
        "utilization_pct": round(health["utilization_pct"], 2),
        "connection_errors": health["connection_errors"],
        "pool_full_events": health["pool_full_events"],
        "pool": {
            "size": metrics.size,
            "used": metrics.used_size,
            "free": metrics.free_size,
        },
    }


# ────────────────────────────────────────────────────────────────────────────
# Scraper Scheduling Routes (VCL-80 / DATA-004)
# ────────────────────────────────────────────────────────────────────────────


@router.get(
    "/scrapers/status",
    summary="Get scraper schedule status",
    description="Returns status of all registered scrapers including schedules, "
    "last run time, and next scheduled run.",
)
async def get_scrapers_status(request: Request):
    """Get status of all registered scrapers."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"error": "Scheduler not initialized"}

    return scheduler.get_status()


@router.post(
    "/scrapers/{scraper_name}/run",
    summary="Manually trigger a scraper run",
    description="Execute a specific scraper immediately, bypassing schedule.",
)
async def run_scraper_manual(scraper_name: str, request: Request):
    """Manually trigger a scraper run."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"error": "Scheduler not initialized"}

    try:
        result = await scheduler.run_scraper(scraper_name)
        return result.to_dict()
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Failed to run scraper: {str(e)}"}


@router.get(
    "/scrapers/history",
    summary="Get scraper run history",
    description="Returns paginated history of all scraper runs with metrics.",
)
async def get_scrapers_history(
    request: Request,
    scraper_name: str = Query(None, description="Filter by scraper name"),
    limit: int = Query(50, ge=1, le=500, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status: str = Query(None, description="Filter by status (success/partial/failed)"),
):
    """Get paginated scraper run history."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None or scheduler.db_pool is None:
        return {"error": "Scheduler not initialized"}

    try:
        query = "SELECT * FROM scraper_runs WHERE 1=1"
        params = []

        if scraper_name:
            query += " AND scraper_name = $" + str(len(params) + 1)
            params.append(scraper_name)

        if status:
            query += " AND status = $" + str(len(params) + 1)
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        query += " OFFSET $" + str(len(params) + 1)
        params.append(offset)

        async with scheduler.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        # Get total count for pagination
        count_query = "SELECT COUNT(*) as total FROM scraper_runs WHERE 1=1"
        count_params = []

        if scraper_name:
            count_query += " AND scraper_name = $" + str(len(count_params) + 1)
            count_params.append(scraper_name)

        if status:
            count_query += " AND status = $" + str(len(count_params) + 1)
            count_params.append(status)

        async with scheduler.db_pool.acquire() as conn:
            count_result = await conn.fetchval(count_query, *count_params)

        return {
            "history": [
                {
                    "id": row["id"],
                    "scraper_name": row["scraper_name"],
                    "started_at": row["started_at"].isoformat(),
                    "completed_at": row["completed_at"].isoformat(),
                    "duration_seconds": (
                        row["completed_at"] - row["started_at"]
                    ).total_seconds(),
                    "status": row["status"],
                    "documents_found": row["documents_found"],
                    "documents_new": row["documents_new"],
                    "documents_skipped": row["documents_skipped"],
                    "errors": row["errors"],
                }
                for row in rows
            ],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": count_result or 0,
            },
        }
    except Exception as e:
        return {"error": f"Failed to retrieve history: {str(e)}"}


# ── Data Freshness Dashboard ──────────────────────────────────────


@router.get(
    "/data-freshness",
    summary="Data freshness dashboard",
    description="Returns freshness metrics for all data sources — last updated timestamp, "
    "record count, and staleness assessment.",
)
async def data_freshness():
    """Sprint 10.1: Data freshness admin dashboard.

    Returns per-source freshness metrics:
    - last_updated: most recent timestamp in the table
    - record_count: total rows
    - staleness: "fresh" (<7d), "aging" (7-30d), "stale" (>30d), "unknown"
    """
    from datetime import datetime, timezone, timedelta

    sources = [
        {
            "name": "BC Assessment (Parcels)",
            "table": "parcels",
            "ts_col": "updated_at",
            "count_filter": None,
            "origin": "BC Assessment via Vancouver Open Data",
        },
        {
            "name": "Transit Stations",
            "table": "transit_stations",
            "ts_col": "created_at",
            "count_filter": None,
            "origin": "TransLink GTFS",
        },
        {
            "name": "TOA Buffers",
            "table": "toa_buffers",
            "ts_col": "created_at",
            "count_filter": None,
            "origin": "Calculated from transit stations + Bill 47 tiers",
        },
        {
            "name": "Heritage Sites",
            "table": "heritage_sites",
            "ts_col": "updated_at",
            "count_filter": None,
            "origin": "City of Vancouver Open Data",
        },
        {
            "name": "Contaminated Sites",
            "table": "contaminated_sites",
            "ts_col": "updated_at",
            "count_filter": None,
            "origin": "BC Ministry of Environment",
        },
        {
            "name": "Development Pipeline",
            "table": "supply_pipeline",
            "ts_col": "updated_at",
            "count_filter": None,
            "origin": "City of Vancouver Permits",
        },
        {
            "name": "Comparable Sales",
            "table": "comparable_sales",
            "ts_col": "created_at",
            "count_filter": None,
            "origin": "BC Assessment / MLS",
        },
        {
            "name": "Intelligence Signals",
            "table": "intelligence_signals",
            "ts_col": "extracted_at",
            "count_filter": None,
            "origin": "K2 Pipeline (multi-source)",
        },
        {
            "name": "StatsCan Demographics",
            "table": "statscan_demographics",
            "ts_col": "retrieved_at",
            "count_filter": None,
            "origin": "Statistics Canada Census API",
        },
        {
            "name": "CMHC Housing Market",
            "table": "cmhc_housing",
            "ts_col": "retrieved_at",
            "count_filter": None,
            "origin": "CMHC Housing Market Indicators",
        },
        {
            "name": "View Cones",
            "table": "view_cones",
            "ts_col": "created_at",
            "count_filter": None,
            "origin": "City of Vancouver Open Data",
        },
        {
            "name": "Building Permits",
            "table": "issued_building_permits",
            "ts_col": "created_at",
            "count_filter": None,
            "origin": "City of Vancouver Permit Portal",
        },
    ]

    now = datetime.now(timezone.utc)
    results = []

    async with db.acquire() as conn:
        for src in sources:
            entry = {
                "name": src["name"],
                "origin": src["origin"],
                "table": src["table"],
                "last_updated": None,
                "record_count": 0,
                "staleness": "unknown",
                "days_old": None,
            }
            try:
                ts_val = await conn.fetchval(
                    f"SELECT MAX({src['ts_col']}) FROM {src['table']}"
                )
                count_val = await conn.fetchval(f"SELECT COUNT(*) FROM {src['table']}")
                entry["record_count"] = count_val or 0
                if ts_val:
                    # Ensure timezone-aware
                    if ts_val.tzinfo is None:
                        ts_val = ts_val.replace(tzinfo=timezone.utc)
                    entry["last_updated"] = ts_val.isoformat()
                    age = now - ts_val
                    entry["days_old"] = age.days
                    if age < timedelta(days=7):
                        entry["staleness"] = "fresh"
                    elif age < timedelta(days=30):
                        entry["staleness"] = "aging"
                    else:
                        entry["staleness"] = "stale"
            except Exception:
                entry["staleness"] = "unavailable"

            results.append(entry)

    # Summary stats
    fresh = sum(1 for r in results if r["staleness"] == "fresh")
    aging = sum(1 for r in results if r["staleness"] == "aging")
    stale = sum(1 for r in results if r["staleness"] == "stale")
    unavail = sum(1 for r in results if r["staleness"] in ("unknown", "unavailable"))

    return {
        "sources": results,
        "summary": {
            "total_sources": len(results),
            "fresh": fresh,
            "aging": aging,
            "stale": stale,
            "unavailable": unavail,
        },
        "generated_at": now.isoformat(),
    }


# ── Pipeline Health Dashboard Endpoints ──────────────────────


@router.get("/scraper-health")
async def scraper_health(request: Request):
    """
    Per-scraper health overview: last run time, status, doc counts,
    cron schedule, next run time.  Plus aggregate totals for documents
    and intelligence signals.
    """
    from datetime import datetime

    pool = request.app.state.pool
    scheduler = getattr(request.app.state, "scheduler", None)

    # ------------------------------------------------------------------
    # 1.  Build per-scraper info from the scheduler's registered scrapers
    # ------------------------------------------------------------------
    scrapers_info = []
    if scheduler is not None:
        for name, (func, schedule) in scheduler.scrapers.items():
            entry: dict = {
                "name": name,
                "enabled": schedule.enabled,
                "cron": schedule.cron_expression,
                "has_function": func is not None,
                "last_run": None,
                "status": "never_run",
                "documents_found": 0,
                "documents_new": 0,
                "next_run": None,
            }

            # Pull the latest run from DB (more reliable than in-memory)
            try:
                row = await pool.fetchrow(
                    """
                    SELECT status, started_at, completed_at,
                           documents_found, documents_new
                    FROM scraper_runs
                    WHERE scraper_name = $1
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    name,
                )
                if row:
                    entry["status"] = row["status"]
                    entry["last_run"] = (
                        row["started_at"].isoformat() if row["started_at"] else None
                    )
                    entry["documents_found"] = row["documents_found"] or 0
                    entry["documents_new"] = row["documents_new"] or 0
            except Exception:
                pass  # DB table may not exist yet

            # Next run from scheduler cache
            if schedule.next_run:
                entry["next_run"] = schedule.next_run.isoformat()
            else:
                # Calculate next run from now
                try:
                    entry["next_run"] = scheduler._calculate_next_run(
                        name, datetime.now()
                    ).isoformat()
                except Exception:
                    pass

            scrapers_info.append(entry)

    # ------------------------------------------------------------------
    # 2.  Aggregate totals: documents + intelligence_signals
    # ------------------------------------------------------------------
    total_documents = 0
    total_signals = 0
    try:
        total_documents = await pool.fetchval("SELECT COUNT(*) FROM documents") or 0
    except Exception:
        pass
    try:
        total_signals = (
            await pool.fetchval("SELECT COUNT(*) FROM intelligence_signals") or 0
        )
    except Exception:
        pass

    return {
        "scrapers": scrapers_info,
        "totals": {
            "documents": total_documents,
            "signals": total_signals,
        },
    }


@router.post("/scraper/{name}/run")
async def scraper_run(
    name: str = Path(..., pattern=r"^[a-z_]{1,50}$"), request: Request = None
):
    """
    Manually trigger a scraper by name via the scheduler's run_scraper()
    method.  Returns the ScraperResult dict on success.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    if name not in scheduler.scrapers:
        raise HTTPException(status_code=404, detail=f"Unknown scraper: {name}")

    func, _schedule = scheduler.scrapers[name]
    if func is None:
        raise HTTPException(
            status_code=400,
            detail=f"Scraper '{name}' has no function registered",
        )

    try:
        result = await scheduler.run_scraper(name)
        return {"ok": True, "result": result.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
