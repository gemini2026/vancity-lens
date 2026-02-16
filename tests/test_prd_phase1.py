"""Tests for PRD Phase 1 gap-closure features."""

import json
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHeritageIntegration:
    """F01-A: Heritage designation in entitlement response."""

    def test_model_has_heritage_fields(self):
        from api.models import ParcelEntitlementResponse
        fields = ParcelEntitlementResponse.model_fields
        assert "heritage_site" in fields
        assert "heritage_category" in fields

    @pytest.mark.asyncio
    async def test_heritage_site_detected(self):
        """Parcel near a heritage site gets heritage_designation set."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-001",
            "civic_address": "123 Heritage St",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("600"),
            "assessed_value": 1500000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Smith House", "category": "A"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-001")
        assert result.heritage_site is True
        assert result.heritage_category == "A"

    @pytest.mark.asyncio
    async def test_no_heritage_site(self):
        """Parcel not near any heritage site gets heritage_site=False."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-002",
            "civic_address": "456 Normal Ave",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = None

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-002")
        assert result.heritage_site is False
        assert result.heritage_category is None

    @pytest.mark.asyncio
    async def test_heritage_category_a_adds_constraint(self):
        """Heritage Category A adds constraint to data_warnings."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-003",
            "civic_address": "789 Heritage Blvd",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("550"),
            "assessed_value": 2000000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Strathcona",
            "lat": Decimal("49.275"),
            "lng": Decimal("-123.090"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Old Mill", "category": "A"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-003")
        warning_msgs = [w.message for w in result.data_warnings]
        assert any("Heritage Category A" in m for m in warning_msgs)

    @pytest.mark.asyncio
    async def test_heritage_category_b_adds_warning(self):
        """Heritage Category B adds a medium-priority warning."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-004",
            "civic_address": "321 Heritage Ct",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1200000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Historic Building", "category": "B"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-004")
        assert result.heritage_site is True
        assert result.heritage_category == "B"
        warning_msgs = [w.message for w in result.data_warnings]
        assert any("Heritage Category B" in m and "Additional review" in m for m in warning_msgs)
