"""
VCL-100: Comparable Sales Data Pipeline
Service for managing comparable sales data and spatial queries
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from pydantic import BaseModel, Field
import asyncpg
from logging import getLogger

logger = getLogger(__name__)


class ComparableSale(BaseModel):
    """Model for a single comparable sale"""
    id: int
    address: str
    pid: Optional[str] = None
    sale_price: Decimal
    sale_date: str
    lot_area_sqft: Optional[Decimal] = None
    lot_area_sqm: Optional[Decimal] = None
    zoning: Optional[str] = None
    building_type: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    year_built: Optional[int] = None
    floor_area_sqft: Optional[Decimal] = None
    price_per_lot_sqft: Optional[Decimal] = None
    price_per_floor_sqft: Optional[Decimal] = None
    neighborhood: Optional[str] = None
    distance_m: Optional[Decimal] = Field(None, description="Distance in meters from query point")
    data_source: str = "bc_assessment"

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "address": "123 Main St, Vancouver, BC",
                "pid": "0123456789",
                "sale_price": "850000.00",
                "sale_date": "2023-06-15",
                "lot_area_sqft": "4500.00",
                "zoning": "RS1",
                "building_type": "Single Family",
                "bedrooms": 3,
                "bathrooms": 2,
                "year_built": 1995,
                "floor_area_sqft": "2100.00",
                "price_per_lot_sqft": "188.89",
                "neighborhood": "Kitsilano",
                "distance_m": "250.50"
            }
        }


class ComparableResult(BaseModel):
    """Model for comparable sales query result"""
    parcel_pid: str
    comparables: List[ComparableSale]
    market_stats: Optional[Dict[str, Any]] = None
    query_radius_m: int
    count: int


class MarketStats(BaseModel):
    """Model for neighborhood market statistics"""
    neighborhood: str
    zoning: Optional[str] = None
    count: int
    avg_price: Optional[Decimal] = None
    median_price: Optional[Decimal] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    avg_price_per_lot_sqft: Optional[Decimal] = None
    median_price_per_lot_sqft: Optional[Decimal] = None
    avg_sale_days_on_market: Optional[int] = None
    period_months: int = 12
    last_updated: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    class Config:
        from_attributes = True


class PriceTrend(BaseModel):
    """Model for monthly price trend data"""
    year_month: str
    avg_price: Optional[Decimal] = None
    median_price: Optional[Decimal] = None
    sale_count: int = 0
    avg_price_per_lot_sqft: Optional[Decimal] = None


class ComparableSalesService:
    """Service for managing and querying comparable sales data"""

    @staticmethod
    async def find_comparables(
        pool: asyncpg.Pool,
        pid: str,
        radius_m: int = 500,
        limit: int = 5,
        same_zoning: bool = True,
        months: int = 12
    ) -> Optional[ComparableResult]:
        """
        Find comparable sales near a parcel using spatial query.

        Args:
            pool: asyncpg connection pool
            pid: parcel ID to find comparables for
            radius_m: search radius in meters (default 500)
            limit: maximum number of results to return (default 5)
            same_zoning: filter to same zoning category if True (default True)
            months: only include sales from last N months (default 12)

        Returns:
            ComparableResult with list of comparable sales or None if parcel not found
        """
        async with pool.acquire() as conn:
            # Get the parcel's geometry and zoning
            parcel = await conn.fetchrow(
                """
                SELECT ST_AsText(geom) as geom_text, zoning
                FROM parcels
                WHERE pid = $1
                LIMIT 1
                """,
                pid
            )

            if not parcel:
                return None

            # Parse geometry
            geom_text = parcel['geom_text']
            zoning = parcel['zoning'] if same_zoning else None

            # Build the comparable sales query
            cutoff_date = datetime.utcnow() - timedelta(days=months * 30)

            if same_zoning and zoning:
                # Query with zoning filter
                query = """
                    SELECT
                        id, address, pid, sale_price, sale_date,
                        lot_area_sqft, lot_area_sqm, zoning, building_type,
                        bedrooms, bathrooms, year_built, floor_area_sqft,
                        price_per_lot_sqft, price_per_floor_sqft,
                        neighborhood, data_source,
                        ROUND(ST_Distance(geom, ST_SetSRID(ST_GeomFromText($1), 4326))::numeric, 2) as distance_m
                    FROM comparable_sales
                    WHERE
                        ST_DWithin(geom, ST_SetSRID(ST_GeomFromText($1), 4326), $2)
                        AND zoning = $3
                        AND sale_date >= $4
                    ORDER BY ST_Distance(geom, ST_SetSRID(ST_GeomFromText($1), 4326)) ASC
                    LIMIT $5
                """
                rows = await conn.fetch(query, geom_text, radius_m, zoning, cutoff_date, limit)
            else:
                # Query without zoning filter
                query = """
                    SELECT
                        id, address, pid, sale_price, sale_date,
                        lot_area_sqft, lot_area_sqm, zoning, building_type,
                        bedrooms, bathrooms, year_built, floor_area_sqft,
                        price_per_lot_sqft, price_per_floor_sqft,
                        neighborhood, data_source,
                        ROUND(ST_Distance(geom, ST_SetSRID(ST_GeomFromText($1), 4326))::numeric, 2) as distance_m
                    FROM comparable_sales
                    WHERE
                        ST_DWithin(geom, ST_SetSRID(ST_GeomFromText($1), 4326), $2)
                        AND sale_date >= $3
                    ORDER BY ST_Distance(geom, ST_SetSRID(ST_GeomFromText($1), 4326)) ASC
                    LIMIT $4
                """
                rows = await conn.fetch(query, geom_text, radius_m, cutoff_date, limit)

            # Convert rows to ComparableSale models
            comparables = [
                ComparableSale(
                    id=row['id'],
                    address=row['address'],
                    pid=row['pid'],
                    sale_price=row['sale_price'],
                    sale_date=row['sale_date'].isoformat() if isinstance(row['sale_date'], datetime) else str(row['sale_date']),
                    lot_area_sqft=row['lot_area_sqft'],
                    lot_area_sqm=row['lot_area_sqm'],
                    zoning=row['zoning'],
                    building_type=row['building_type'],
                    bedrooms=row['bedrooms'],
                    bathrooms=row['bathrooms'],
                    year_built=row['year_built'],
                    floor_area_sqft=row['floor_area_sqft'],
                    price_per_lot_sqft=row['price_per_lot_sqft'],
                    price_per_floor_sqft=row['price_per_floor_sqft'],
                    neighborhood=row['neighborhood'],
                    distance_m=row['distance_m'],
                    data_source=row['data_source']
                )
                for row in rows
            ]

            # Get market stats if we have comparables
            market_stats = None
            if comparables and parcel.get('zoning'):
                market_stats = await ComparableSalesService.get_market_stats(
                    pool, parcel['zoning'], months=months
                )

            return ComparableResult(
                parcel_pid=pid,
                comparables=comparables,
                market_stats=market_stats.model_dump() if market_stats else None,
                query_radius_m=radius_m,
                count=len(comparables)
            )

    @staticmethod
    async def get_market_stats(
        pool: asyncpg.Pool,
        zoning: str,
        months: int = 12,
        neighborhood: Optional[str] = None
    ) -> Optional[MarketStats]:
        """
        Get aggregate market statistics for a zoning category or neighborhood.

        Args:
            pool: asyncpg connection pool
            zoning: zoning category to get stats for
            months: look back period in months (default 12)
            neighborhood: optional neighborhood filter

        Returns:
            MarketStats with aggregated data or None if no data found
        """
        async with pool.acquire() as conn:
            cutoff_date = datetime.utcnow() - timedelta(days=months * 30)

            if neighborhood:
                stats = await conn.fetchrow(
                    """
                    SELECT
                        $1::text as neighborhood,
                        $2::text as zoning,
                        COUNT(*) as count,
                        AVG(sale_price)::numeric as avg_price,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sale_price)::numeric as median_price,
                        MIN(sale_price)::numeric as min_price,
                        MAX(sale_price)::numeric as max_price,
                        AVG(price_per_lot_sqft)::numeric as avg_price_per_lot_sqft,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_per_lot_sqft)::numeric as median_price_per_lot_sqft
                    FROM comparable_sales
                    WHERE zoning = $2
                        AND neighborhood = $1
                        AND sale_date >= $3
                    """,
                    neighborhood, zoning, cutoff_date
                )
            else:
                stats = await conn.fetchrow(
                    """
                    SELECT
                        $1::text as zoning,
                        COUNT(*) as count,
                        AVG(sale_price)::numeric as avg_price,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sale_price)::numeric as median_price,
                        MIN(sale_price)::numeric as min_price,
                        MAX(sale_price)::numeric as max_price,
                        AVG(price_per_lot_sqft)::numeric as avg_price_per_lot_sqft,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_per_lot_sqft)::numeric as median_price_per_lot_sqft
                    FROM comparable_sales
                    WHERE zoning = $1 AND sale_date >= $2
                    """,
                    zoning, cutoff_date
                )

            if stats is None or stats['count'] == 0:
                return None

            return MarketStats(
                neighborhood=neighborhood or "All",
                zoning=zoning,
                count=stats['count'],
                avg_price=stats['avg_price'],
                median_price=stats['median_price'],
                min_price=stats['min_price'],
                max_price=stats['max_price'],
                avg_price_per_lot_sqft=stats['avg_price_per_lot_sqft'],
                median_price_per_lot_sqft=stats['median_price_per_lot_sqft'],
                period_months=months
            )

    @staticmethod
    async def get_price_trends(
        pool: asyncpg.Pool,
        zoning: str,
        months: int = 24,
        neighborhood: Optional[str] = None
    ) -> List[PriceTrend]:
        """
        Get monthly price trend data for a zoning category.

        Args:
            pool: asyncpg connection pool
            zoning: zoning category to get trends for
            months: look back period in months (default 24)
            neighborhood: optional neighborhood filter

        Returns:
            List of PriceTrend objects with monthly aggregated data
        """
        async with pool.acquire() as conn:
            cutoff_date = datetime.utcnow() - timedelta(days=months * 30)

            if neighborhood:
                rows = await conn.fetch(
                    """
                    SELECT
                        TO_CHAR(DATE_TRUNC('month', sale_date), 'YYYY-MM') as year_month,
                        AVG(sale_price)::numeric as avg_price,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sale_price)::numeric as median_price,
                        COUNT(*) as sale_count,
                        AVG(price_per_lot_sqft)::numeric as avg_price_per_lot_sqft
                    FROM comparable_sales
                    WHERE zoning = $1
                        AND neighborhood = $2
                        AND sale_date >= $3
                    GROUP BY DATE_TRUNC('month', sale_date)
                    ORDER BY DATE_TRUNC('month', sale_date) DESC
                    """,
                    zoning, neighborhood, cutoff_date
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        TO_CHAR(DATE_TRUNC('month', sale_date), 'YYYY-MM') as year_month,
                        AVG(sale_price)::numeric as avg_price,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sale_price)::numeric as median_price,
                        COUNT(*) as sale_count,
                        AVG(price_per_lot_sqft)::numeric as avg_price_per_lot_sqft
                    FROM comparable_sales
                    WHERE zoning = $1 AND sale_date >= $2
                    GROUP BY DATE_TRUNC('month', sale_date)
                    ORDER BY DATE_TRUNC('month', sale_date) DESC
                    """,
                    zoning, cutoff_date
                )

            return [
                PriceTrend(
                    year_month=row['year_month'],
                    avg_price=row['avg_price'],
                    median_price=row['median_price'],
                    sale_count=row['sale_count'],
                    avg_price_per_lot_sqft=row['avg_price_per_lot_sqft']
                )
                for row in rows
            ]

    @staticmethod
    async def ingest_sales_data(
        pool: asyncpg.Pool,
        records: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Bulk insert comparable sales records into the database.

        Args:
            pool: asyncpg connection pool
            records: list of sale records to insert

        Returns:
            Dictionary with ingestion statistics (inserted, failed, etc.)
        """
        if not records:
            return {"inserted": 0, "failed": 0, "total": 0}

        async with pool.acquire() as conn:
            inserted = 0
            failed = 0

            async with conn.transaction():
                for record in records:
                    try:
                        # Extract geometry coordinates if provided
                        geom = None
                        if 'latitude' in record and 'longitude' in record:
                            geom = f"POINT({record['longitude']} {record['latitude']})"

                        # Prepare the insert statement
                        await conn.execute(
                            """
                            INSERT INTO comparable_sales (
                                address, pid, sale_price, sale_date,
                                lot_area_sqft, lot_area_sqm, zoning, building_type,
                                bedrooms, bathrooms, year_built, floor_area_sqft,
                                neighborhood, data_source, geom
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                                CASE WHEN $15 IS NOT NULL THEN ST_SetSRID(ST_GeomFromText($15), 4326) ELSE NULL END
                            )
                            ON CONFLICT DO NOTHING
                            """,
                            record.get('address'),
                            record.get('pid'),
                            record.get('sale_price'),
                            record.get('sale_date'),
                            record.get('lot_area_sqft'),
                            record.get('lot_area_sqm'),
                            record.get('zoning'),
                            record.get('building_type'),
                            record.get('bedrooms'),
                            record.get('bathrooms'),
                            record.get('year_built'),
                            record.get('floor_area_sqft'),
                            record.get('neighborhood'),
                            record.get('data_source', 'bc_assessment'),
                            geom
                        )
                        inserted += 1
                    except Exception as e:
                        logger.error(f"Failed to insert record {record}: {str(e)}")
                        failed += 1

        return {
            "inserted": inserted,
            "failed": failed,
            "total": len(records)
        }
