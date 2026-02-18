"""
VCL-96 [DATA-008] VSB School Data Scraper for VanCity Lens

Scrapes Vancouver School Board (VSB) open data API for school information
(enrolment, capacity, student-teacher ratios) and computes neighborhood-level
school quality metrics.

Key components:
- VSBSchoolScraper: Main scraper class
- SchoolData: Pydantic model for individual school records
- SchoolMetrics: Model for aggregated neighborhood school metrics
- Neighborhood mapping via school coordinates to Vancouver neighborhoods
"""

import logging
from datetime import datetime, date
from typing import List, Dict, Optional

from pydantic import BaseModel, Field
import aiohttp
import asyncpg

logger = logging.getLogger(__name__)

# VSB Open Data API URL for schools data
VSB_SCHOOLS_API_URL = (
    "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/schools/records"
)

# Vancouver neighborhood bounding boxes (approximate lat/lon ranges)
# Used to map school coordinates to neighborhoods
NEIGHBORHOOD_BOUNDS = {
    "Kitsilano": {
        "lat_min": 49.26,
        "lat_max": 49.28,
        "lon_min": -123.18,
        "lon_max": -123.14,
    },
    "Mount Pleasant": {
        "lat_min": 49.25,
        "lat_max": 49.27,
        "lon_min": -123.11,
        "lon_max": -123.08,
    },
    "Fairview": {
        "lat_min": 49.26,
        "lat_max": 49.27,
        "lon_min": -123.13,
        "lon_max": -123.11,
    },
    "Downtown": {
        "lat_min": 49.27,
        "lat_max": 49.30,
        "lon_min": -123.13,
        "lon_max": -123.10,
    },
    "West End": {
        "lat_min": 49.28,
        "lat_max": 49.30,
        "lon_min": -123.15,
        "lon_max": -123.13,
    },
    "Strathcona": {
        "lat_min": 49.27,
        "lat_max": 49.29,
        "lon_min": -123.09,
        "lon_max": -123.08,
    },
    "Grandview-Woodland": {
        "lat_min": 49.27,
        "lat_max": 49.29,
        "lon_min": -123.08,
        "lon_max": -123.05,
    },
    "Hastings-Sunrise": {
        "lat_min": 49.27,
        "lat_max": 49.29,
        "lon_min": -123.04,
        "lon_max": -123.00,
    },
    "Renfrew-Collingwood": {
        "lat_min": 49.23,
        "lat_max": 49.25,
        "lon_min": -123.05,
        "lon_max": -123.02,
    },
    "Dunbar-Southlands": {
        "lat_min": 49.23,
        "lat_max": 49.25,
        "lon_min": -123.20,
        "lon_max": -123.17,
    },
    "Arbutus Ridge": {
        "lat_min": 49.24,
        "lat_max": 49.26,
        "lon_min": -123.17,
        "lon_max": -123.14,
    },
    "Kerrisdale": {
        "lat_min": 49.22,
        "lat_max": 49.24,
        "lon_min": -123.17,
        "lon_max": -123.14,
    },
    "Marpole": {
        "lat_min": 49.20,
        "lat_max": 49.22,
        "lon_min": -123.13,
        "lon_max": -123.10,
    },
    "Oakridge": {
        "lat_min": 49.22,
        "lat_max": 49.24,
        "lon_min": -123.13,
        "lon_max": -123.10,
    },
    "South Cambie": {
        "lat_min": 49.24,
        "lat_max": 49.26,
        "lon_min": -123.12,
        "lon_max": -123.10,
    },
    "Riley Park": {
        "lat_min": 49.23,
        "lat_max": 49.25,
        "lon_min": -123.10,
        "lon_max": -123.08,
    },
    "Killarney": {
        "lat_min": 49.22,
        "lat_max": 49.24,
        "lon_min": -123.04,
        "lon_max": -123.01,
    },
    "Victoria-Fraserview": {
        "lat_min": 49.21,
        "lat_max": 49.23,
        "lon_min": -123.06,
        "lon_max": -123.03,
    },
    "Sunset": {
        "lat_min": 49.21,
        "lat_max": 49.23,
        "lon_min": -123.09,
        "lon_max": -123.06,
    },
    "Kensington-Cedar Cottage": {
        "lat_min": 49.24,
        "lat_max": 49.26,
        "lon_min": -123.08,
        "lon_max": -123.05,
    },
    "Shaughnessy": {
        "lat_min": 49.24,
        "lat_max": 49.26,
        "lon_min": -123.15,
        "lon_max": -123.12,
    },
    "West Point Grey": {
        "lat_min": 49.26,
        "lat_max": 49.27,
        "lon_min": -123.21,
        "lon_max": -123.18,
    },
}


class SchoolData(BaseModel):
    """Pydantic model for individual school record."""

    name: str = Field(..., description="School name")
    address: str = Field(..., description="School address")
    school_type: str = Field(
        ..., description="School type: elementary, middle, secondary"
    )
    enrollment: Optional[int] = Field(None, description="Current enrollment")
    capacity: Optional[int] = Field(None, description="Maximum capacity")
    student_teacher_ratio: Optional[float] = Field(
        None, description="Student-to-teacher ratio"
    )
    latitude: Optional[float] = Field(None, description="School latitude")
    longitude: Optional[float] = Field(None, description="School longitude")
    neighborhood: Optional[str] = Field(
        None, description="Mapped Vancouver neighborhood"
    )

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class SchoolMetrics(BaseModel):
    """Pydantic model for aggregated neighborhood school metrics."""

    neighborhood: str = Field(..., description="Neighborhood name")
    school_count: int = Field(default=0, description="Number of schools")
    elementary_count: int = Field(default=0, description="Elementary schools count")
    secondary_count: int = Field(default=0, description="Secondary schools count")
    total_enrollment: int = Field(default=0, description="Total enrollment")
    total_capacity: int = Field(default=0, description="Total capacity")
    avg_capacity_utilization: Optional[float] = Field(
        None, description="Average capacity utilization (0-100%)"
    )
    avg_student_teacher_ratio: Optional[float] = Field(
        None, description="Average student-to-teacher ratio"
    )
    quality_score: Optional[float] = Field(None, description="Quality score 0-10")

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class VSBSchoolScraper:
    """Main VSB school data scraper."""

    def __init__(self, timeout: int = 30):
        """
        Initialize scraper.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            "User-Agent": "VanCity-Lens/1.0 (School Data Scraper)",
            "Accept": "application/json",
        }

    async def scrape(self) -> List[SchoolData]:
        """
        Main entry point: scrape VSB Open Data API and return school records.

        Returns:
            List of SchoolData objects
        """
        try:
            logger.info("Starting VSB school data scrape")
            raw_data = await self._fetch_school_list()
            schools = self._parse_school_data(raw_data)
            logger.info(f"Scraped {len(schools)} schools from VSB API")
            return schools
        except Exception as e:
            logger.error(f"Error in scrape(): {e}", exc_info=True)
            return []

    async def _fetch_school_list(self) -> Dict:
        """
        Fetch raw school list from VSB Open Data API.

        Returns:
            Dictionary with API response data
        """
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()

            async with self.session.get(
                VSB_SCHOOLS_API_URL,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                params={"limit": 1000},
            ) as response:
                if response.status != 200:
                    logger.warning(f"VSB API returned status {response.status}")
                    return {"results": []}

                data = await response.json()
                return data
        except Exception as e:
            logger.error(f"Error fetching from VSB API: {e}")
            return {"results": []}

    def _parse_school_data(self, raw_data: Dict) -> List[SchoolData]:
        """
        Parse raw API response into SchoolData objects.

        Args:
            raw_data: Raw API response dictionary

        Returns:
            List of parsed SchoolData objects
        """
        schools = []

        try:
            records = raw_data.get("results", [])

            for record in records:
                try:
                    # Map API fields to SchoolData fields
                    school_type = self._normalize_school_type(
                        record.get("school_type") or record.get("type") or "elementary"
                    )

                    enrollment = record.get("enrollment")
                    if isinstance(enrollment, str):
                        enrollment = int(enrollment) if enrollment.isdigit() else None

                    capacity = record.get("capacity")
                    if isinstance(capacity, str):
                        capacity = int(capacity) if capacity.isdigit() else None

                    str_ratio = record.get("student_teacher_ratio") or record.get("str")
                    student_teacher_ratio = None
                    if str_ratio:
                        try:
                            student_teacher_ratio = float(str_ratio)
                        except (ValueError, TypeError):
                            pass

                    # Extract coordinates
                    latitude = None
                    longitude = None
                    geo = record.get("geo_point_2d") or record.get("location") or {}
                    if isinstance(geo, dict):
                        latitude = geo.get("lat")
                        longitude = geo.get("lon")
                    elif isinstance(geo, str):
                        parts = geo.split(",")
                        if len(parts) == 2:
                            try:
                                latitude = float(parts[0].strip())
                                longitude = float(parts[1].strip())
                            except ValueError:
                                pass

                    address = (
                        record.get("address") or record.get("street_address") or ""
                    )
                    name = record.get("name") or record.get("school_name") or ""

                    if not name or not address:
                        logger.warning("Skipping school with missing name or address")
                        continue

                    # Map to neighborhood
                    neighborhood = self._map_to_neighborhood(
                        latitude, longitude, record.get("neighborhood")
                    )

                    school = SchoolData(
                        name=name,
                        address=address,
                        school_type=school_type,
                        enrollment=enrollment,
                        capacity=capacity,
                        student_teacher_ratio=student_teacher_ratio,
                        latitude=latitude,
                        longitude=longitude,
                        neighborhood=neighborhood,
                    )

                    schools.append(school)

                except Exception as e:
                    logger.warning(f"Error parsing school record: {e}")
                    continue

            logger.info(
                f"Successfully parsed {len(schools)} schools from {len(records)} records"
            )
            return schools

        except Exception as e:
            logger.error(f"Error in _parse_school_data: {e}", exc_info=True)
            return []

    @staticmethod
    def _normalize_school_type(school_type: str) -> str:
        """Normalize school type to standard values."""
        school_type = school_type.lower().strip()

        if "secondary" in school_type or "high" in school_type:
            return "secondary"
        elif "middle" in school_type:
            return "middle"
        else:
            return "elementary"

    @staticmethod
    def _map_to_neighborhood(
        latitude: Optional[float],
        longitude: Optional[float],
        provided_neighborhood: Optional[str] = None,
    ) -> str:
        """
        Map school coordinates to Vancouver neighborhood.

        Args:
            latitude: School latitude
            longitude: School longitude
            provided_neighborhood: Pre-mapped neighborhood from data source

        Returns:
            Neighborhood name or "Unknown"
        """
        # If neighborhood is already provided in data, use it
        if provided_neighborhood:
            for neighborhood in NEIGHBORHOOD_BOUNDS.keys():
                if neighborhood.lower() == provided_neighborhood.lower():
                    return neighborhood

        # Try to map by coordinates
        if latitude is not None and longitude is not None:
            for neighborhood, bounds in NEIGHBORHOOD_BOUNDS.items():
                if (
                    bounds["lat_min"] <= latitude <= bounds["lat_max"]
                    and bounds["lon_min"] <= longitude <= bounds["lon_max"]
                ):
                    return neighborhood

        return "Unknown"

    @staticmethod
    def _compute_quality_metrics(
        schools_by_neighborhood: Dict[str, List[SchoolData]],
    ) -> Dict[str, SchoolMetrics]:
        """
        Compute school quality metrics per neighborhood.

        Args:
            schools_by_neighborhood: Dict mapping neighborhood name to list of schools

        Returns:
            Dict mapping neighborhood name to SchoolMetrics
        """
        metrics = {}

        for neighborhood, schools in schools_by_neighborhood.items():
            if not schools:
                continue

            elementary = [s for s in schools if s.school_type == "elementary"]
            secondary = [s for s in schools if s.school_type in ("secondary", "middle")]

            total_enrollment = sum(s.enrollment or 0 for s in schools)
            total_capacity = sum(s.capacity or 0 for s in schools)

            # Calculate average capacity utilization
            avg_capacity_util = None
            if total_capacity > 0:
                avg_capacity_util = round((total_enrollment / total_capacity) * 100, 2)

            # Calculate average student-teacher ratio
            avg_str = None
            str_values = [
                s.student_teacher_ratio for s in schools if s.student_teacher_ratio
            ]
            if str_values:
                avg_str = round(sum(str_values) / len(str_values), 2)

            # Compute quality score (0-10)
            # Higher enrollment/capacity = more demand (positive)
            # Lower student-teacher ratio = better quality (positive, needs inversion)
            quality_score = VSBSchoolScraper._compute_quality_score(
                avg_capacity_util, avg_str, len(schools)
            )

            metrics[neighborhood] = SchoolMetrics(
                neighborhood=neighborhood,
                school_count=len(schools),
                elementary_count=len(elementary),
                secondary_count=len(secondary),
                total_enrollment=total_enrollment,
                total_capacity=total_capacity,
                avg_capacity_utilization=avg_capacity_util,
                avg_student_teacher_ratio=avg_str,
                quality_score=quality_score,
            )

        return metrics

    @staticmethod
    def _compute_quality_score(
        capacity_util: Optional[float],
        student_teacher_ratio: Optional[float],
        school_count: int,
    ) -> Optional[float]:
        """
        Compute school quality score (0-10).

        Args:
            capacity_util: Average capacity utilization (0-100%)
            student_teacher_ratio: Average student-to-teacher ratio
            school_count: Number of schools in neighborhood

        Returns:
            Quality score 0-10, or None if insufficient data
        """
        if capacity_util is None and student_teacher_ratio is None:
            return None

        score_components = []

        # Capacity utilization: 50-100% utilization is ideal (scores 8-10)
        if capacity_util is not None:
            if capacity_util < 50:
                util_score = (capacity_util / 50) * 5  # 0-50% maps to 0-5
            elif capacity_util <= 100:
                util_score = 5 + ((capacity_util - 50) / 50) * 5  # 50-100% maps to 5-10
            else:
                util_score = 10  # Over capacity still gets high score (demand)
            score_components.append(util_score)

        # Student-teacher ratio: lower is better
        # Ideal: 15-18, poor: 25+
        if student_teacher_ratio is not None:
            if student_teacher_ratio <= 15:
                str_score = 10
            elif student_teacher_ratio <= 25:
                str_score = (
                    10 - ((student_teacher_ratio - 15) / 10) * 5
                )  # 15-25 maps to 10-5
            else:
                str_score = max(
                    0, 5 - ((student_teacher_ratio - 25) / 10)
                )  # 25+ maps to 5-0
            score_components.append(str_score)

        # School diversity bonus: neighborhoods with multiple school types
        diversity_bonus = min(1.0, school_count / 5)  # Max 1 point for 5+ schools
        score_components.append(5 + (diversity_bonus * 5))  # Scales 5-10

        if not score_components:
            return None

        # Average all components
        quality_score = sum(score_components) / len(score_components)
        return round(max(0.0, min(10.0, quality_score)), 1)

    async def save_to_db(
        self, db_pool: asyncpg.Pool, schools: List[SchoolData]
    ) -> Dict:
        """
        Save school data to database and compute neighborhood metrics.

        Args:
            db_pool: asyncpg connection pool
            schools: List of SchoolData objects to save

        Returns:
            Dict with save statistics
        """
        try:
            async with db_pool.acquire() as conn:
                # Save individual school records
                saved_count = 0
                for school in schools:
                    try:
                        await conn.execute(
                            """
                            INSERT INTO school_data
                            (name, address, school_type, enrollment, capacity,
                             student_teacher_ratio, latitude, longitude, neighborhood, scraped_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                            ON CONFLICT (name, address) DO UPDATE SET
                                enrollment = EXCLUDED.enrollment,
                                capacity = EXCLUDED.capacity,
                                student_teacher_ratio = EXCLUDED.student_teacher_ratio,
                                scraped_at = EXCLUDED.scraped_at
                            """,
                            school.name,
                            school.address,
                            school.school_type,
                            school.enrollment,
                            school.capacity,
                            school.student_teacher_ratio,
                            school.latitude,
                            school.longitude,
                            school.neighborhood,
                            datetime.now(),
                        )
                        saved_count += 1
                    except Exception as e:
                        logger.warning(f"Error saving school {school.name}: {e}")
                        continue

                # Group schools by neighborhood and compute metrics
                schools_by_neighborhood: Dict[str, List[SchoolData]] = {}
                for school in schools:
                    if school.neighborhood:
                        if school.neighborhood not in schools_by_neighborhood:
                            schools_by_neighborhood[school.neighborhood] = []
                        schools_by_neighborhood[school.neighborhood].append(school)

                metrics = self._compute_quality_metrics(schools_by_neighborhood)

                # Save neighborhood metrics
                period_start = date.today()
                period_end = date.today()
                neighborhoods_updated = 0

                for neighborhood, metric in metrics.items():
                    try:
                        await conn.execute(
                            """
                            INSERT INTO school_metrics
                            (neighborhood, school_count, elementary_count, secondary_count,
                             total_enrollment, total_capacity, avg_capacity_utilization,
                             avg_student_teacher_ratio, quality_score, period_start, period_end)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                            ON CONFLICT (neighborhood, period_start) DO UPDATE SET
                                school_count = EXCLUDED.school_count,
                                elementary_count = EXCLUDED.elementary_count,
                                secondary_count = EXCLUDED.secondary_count,
                                total_enrollment = EXCLUDED.total_enrollment,
                                total_capacity = EXCLUDED.total_capacity,
                                avg_capacity_utilization = EXCLUDED.avg_capacity_utilization,
                                avg_student_teacher_ratio = EXCLUDED.avg_student_teacher_ratio,
                                quality_score = EXCLUDED.quality_score
                            """,
                            neighborhood,
                            metric.school_count,
                            metric.elementary_count,
                            metric.secondary_count,
                            metric.total_enrollment,
                            metric.total_capacity,
                            metric.avg_capacity_utilization,
                            metric.avg_student_teacher_ratio,
                            metric.quality_score,
                            period_start,
                            period_end,
                        )
                        neighborhoods_updated += 1
                    except Exception as e:
                        logger.warning(f"Error saving metrics for {neighborhood}: {e}")
                        continue

                logger.info(
                    f"Saved {saved_count} schools and updated {neighborhoods_updated} neighborhoods"
                )

                return {
                    "schools_found": len(schools),
                    "schools_saved": saved_count,
                    "neighborhoods_updated": neighborhoods_updated,
                }

        except Exception as e:
            logger.error(f"Error in save_to_db: {e}", exc_info=True)
            return {
                "schools_found": len(schools),
                "schools_saved": 0,
                "neighborhoods_updated": 0,
            }

    async def close(self):
        """Close aiohttp session."""
        if self.session:
            await self.session.close()
