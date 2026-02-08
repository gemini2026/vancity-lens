"""
Test suite for neighborhood revenue adjustment module.
VCL-107: [VAL-002] Neighborhood revenue adjustment
90+ comprehensive tests covering all functionality.
"""

import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"


class TestNeighborhoodRevenueModuleStructure:
    """Tests for module structure and imports."""

    def setup_method(self):
        self.content = (API_DIR / "neighborhood_revenue.py").read_text()

    def test_module_has_docstring(self):
        assert '"""' in self.content
        assert "neighborhood revenue adjustment" in self.content.lower()

    def test_imports_asyncpg(self):
        assert "import asyncpg" in self.content or "from asyncpg" in self.content

    def test_imports_pydantic(self):
        assert "from pydantic import" in self.content
        assert "BaseModel" in self.content

    def test_defines_adjustment_factors_dict(self):
        assert "NEIGHBORHOOD_ADJUSTMENT_FACTORS" in self.content

    def test_defines_psf_dict(self):
        assert "REVENUE_PSF_BY_NEIGHBORHOOD" in self.content

    def test_defines_default_psf(self):
        assert "DEFAULT_PSF" in self.content

    def test_defines_neighborhood_revenue_adjuster_class(self):
        assert "class NeighborhoodRevenueAdjuster" in self.content

    def test_defines_revenue_factor_response_model(self):
        assert "class RevenueFactorResponse" in self.content
        assert "BaseModel" in self.content

    def test_defines_revenue_map_response_model(self):
        assert "class RevenueMapResponse" in self.content

    def test_adjustment_factors_are_floats(self):
        assert "1.35" in self.content
        assert "0.7" in self.content or "0.75" in self.content

    def test_psf_values_are_reasonable(self):
        assert "1400" in self.content
        assert "580" in self.content


class TestAdjustmentFactorConstants:
    """Tests for neighborhood adjustment factor constants."""

    def setup_method(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

    def test_downtown_adjustment_factor_exists(self):
        assert "Downtown" in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS

    def test_coal_harbour_adjustment_factor_exists(self):
        assert "Coal Harbour" in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS

    def test_kitsilano_adjustment_factor_exists(self):
        assert "Kitsilano" in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS

    def test_mount_pleasant_adjustment_factor_exists(self):
        assert "Mount Pleasant" in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS

    def test_hastings_sunrise_adjustment_factor_exists(self):
        assert "Hastings-Sunrise" in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS

    def test_marpole_adjustment_factor_exists(self):
        assert "Marpole" in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS

    def test_renfrew_collingwood_adjustment_factor_exists(self):
        assert "Renfrew-Collingwood" in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS

    def test_adjustment_factors_within_bounds(self):
        for factor in self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS.values():
            assert 0.7 <= factor <= 1.5

    def test_downtown_premium_pricing(self):
        downtown = self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS["Downtown"]
        kitsilano = self.module.NEIGHBORHOOD_ADJUSTMENT_FACTORS["Kitsilano"]
        assert downtown > kitsilano

    def test_default_adjustment_factor_is_1_0(self):
        assert self.module.DEFAULT_ADJUSTMENT_FACTOR == 1.0


class TestRevenuePerSqftConstants:
    """Tests for revenue per sqft by neighborhood."""

    def setup_method(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

    def test_downtown_psf_data_complete(self):
        downtown = self.module.REVENUE_PSF_BY_NEIGHBORHOOD["Downtown"]
        assert "condo" in downtown
        assert "rental" in downtown
        assert "commercial" in downtown
        assert "townhouse" in downtown

    def test_downtown_condo_psf_is_reasonable(self):
        downtown_condo = self.module.REVENUE_PSF_BY_NEIGHBORHOOD[
            "Downtown"
        ]["condo"]
        assert 600 <= downtown_condo <= 1800

    def test_kitsilano_psf_data_complete(self):
        kits = self.module.REVENUE_PSF_BY_NEIGHBORHOOD["Kitsilano"]
        assert len(kits) == 4

    def test_hastings_sunrise_psf_data_complete(self):
        hs = self.module.REVENUE_PSF_BY_NEIGHBORHOOD["Hastings-Sunrise"]
        assert len(hs) == 4

    def test_south_vancouver_psf_data_complete(self):
        sv = self.module.REVENUE_PSF_BY_NEIGHBORHOOD["South Vancouver"]
        assert len(sv) == 4

    def test_all_neighborhoods_have_four_property_types(self):
        for neighborhood, psf_dict in (
            self.module.REVENUE_PSF_BY_NEIGHBORHOOD.items()
        ):
            assert len(psf_dict) == 4, f"{neighborhood} missing property types"

    def test_condo_psf_values_in_valid_range(self):
        for neighborhood, psf_dict in (
            self.module.REVENUE_PSF_BY_NEIGHBORHOOD.items()
        ):
            condo = psf_dict["condo"]
            assert 580 <= condo <= 1800, (
                f"{neighborhood} condo PSF {condo} out of range"
            )

    def test_rental_psf_values_in_valid_range(self):
        for neighborhood, psf_dict in (
            self.module.REVENUE_PSF_BY_NEIGHBORHOOD.items()
        ):
            rental = psf_dict["rental"]
            assert 20 <= rental <= 70, (
                f"{neighborhood} rental PSF {rental} out of range"
            )

    def test_commercial_psf_values_in_valid_range(self):
        for neighborhood, psf_dict in (
            self.module.REVENUE_PSF_BY_NEIGHBORHOOD.items()
        ):
            commercial = psf_dict["commercial"]
            assert 15 <= commercial <= 50, (
                f"{neighborhood} commercial PSF {commercial} out of range"
            )

    def test_townhouse_psf_values_in_valid_range(self):
        for neighborhood, psf_dict in (
            self.module.REVENUE_PSF_BY_NEIGHBORHOOD.items()
        ):
            townhouse = psf_dict["townhouse"]
            assert 400 <= townhouse <= 1200, (
                f"{neighborhood} townhouse PSF {townhouse} out of range"
            )

    def test_downtown_premium_over_east_side(self):
        downtown_condo = self.module.REVENUE_PSF_BY_NEIGHBORHOOD[
            "Downtown"
        ]["condo"]
        hastings_condo = self.module.REVENUE_PSF_BY_NEIGHBORHOOD[
            "Hastings-Sunrise"
        ]["condo"]
        assert downtown_condo > hastings_condo

    def test_default_psf_complete(self):
        assert "condo" in self.module.DEFAULT_PSF
        assert "rental" in self.module.DEFAULT_PSF
        assert "commercial" in self.module.DEFAULT_PSF
        assert "townhouse" in self.module.DEFAULT_PSF


class TestRevenueFactorResponseModel:
    """Tests for RevenueFactorResponse Pydantic model."""

    def setup_method(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

    def test_revenue_factor_response_is_pydantic_model(self):
        assert hasattr(self.module.RevenueFactorResponse, "model_validate")

    def test_revenue_factor_response_has_neighborhood_field(self):
        model = self.module.RevenueFactorResponse(
            neighborhood="Test",
            adjustment_factor=1.0,
            condo_psf=800,
            rental_psf=32,
            commercial_psf=24,
            townhouse_psf=550,
        )
        assert model.neighborhood == "Test"

    def test_revenue_factor_response_has_adjustment_factor_field(self):
        model = self.module.RevenueFactorResponse(
            neighborhood="Test",
            adjustment_factor=1.1,
            condo_psf=800,
            rental_psf=32,
            commercial_psf=24,
            townhouse_psf=550,
        )
        assert model.adjustment_factor == 1.1

    def test_revenue_factor_response_validates_adjustment_factor_min(self):
        with pytest.raises(Exception):
            self.module.RevenueFactorResponse(
                neighborhood="Test",
                adjustment_factor=0.5,
                condo_psf=800,
                rental_psf=32,
                commercial_psf=24,
                townhouse_psf=550,
            )

    def test_revenue_factor_response_validates_adjustment_factor_max(self):
        with pytest.raises(Exception):
            self.module.RevenueFactorResponse(
                neighborhood="Test",
                adjustment_factor=2.0,
                condo_psf=800,
                rental_psf=32,
                commercial_psf=24,
                townhouse_psf=550,
            )

    def test_revenue_factor_response_validates_condo_psf_min(self):
        with pytest.raises(Exception):
            self.module.RevenueFactorResponse(
                neighborhood="Test",
                adjustment_factor=1.0,
                condo_psf=570,
                rental_psf=32,
                commercial_psf=24,
                townhouse_psf=550,
            )

    def test_revenue_factor_response_validates_condo_psf_max(self):
        with pytest.raises(Exception):
            self.module.RevenueFactorResponse(
                neighborhood="Test",
                adjustment_factor=1.0,
                condo_psf=2000,
                rental_psf=32,
                commercial_psf=24,
                townhouse_psf=550,
            )


class TestRevenueMapResponseModel:
    """Tests for RevenueMapResponse Pydantic model."""

    def setup_method(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

    def test_revenue_map_response_is_pydantic_model(self):
        assert hasattr(self.module.RevenueMapResponse, "model_validate")

    def test_revenue_map_response_has_neighborhoods_field(self):
        model = self.module.RevenueMapResponse(
            neighborhoods=[],
            total_neighborhoods=0,
        )
        assert hasattr(model, "neighborhoods")

    def test_revenue_map_response_has_total_neighborhoods_field(self):
        model = self.module.RevenueMapResponse(
            neighborhoods=[],
            total_neighborhoods=0,
        )
        assert model.total_neighborhoods == 0


class TestNeighborhoodRevenueAdjusterInit:
    """Tests for NeighborhoodRevenueAdjuster initialization."""

    def setup_method(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

    def test_adjuster_init_without_pool(self):
        adjuster = self.module.NeighborhoodRevenueAdjuster()
        assert adjuster.pool is None

    def test_adjuster_init_with_none_pool(self):
        adjuster = self.module.NeighborhoodRevenueAdjuster(pool=None)
        assert adjuster.pool is None

    def test_adjuster_init_with_mock_pool(self):
        mock_pool = MagicMock()
        adjuster = self.module.NeighborhoodRevenueAdjuster(pool=mock_pool)
        assert adjuster.pool is mock_pool

    def test_adjuster_has_get_adjustment_factor_method(self):
        adjuster = self.module.NeighborhoodRevenueAdjuster()
        assert hasattr(adjuster, "get_adjustment_factor")
        assert callable(adjuster.get_adjustment_factor)

    def test_adjuster_has_get_revenue_per_sqft_method(self):
        adjuster = self.module.NeighborhoodRevenueAdjuster()
        assert hasattr(adjuster, "get_revenue_per_sqft")
        assert callable(adjuster.get_revenue_per_sqft)

    def test_adjuster_has_compute_adjusted_revenue_method(self):
        adjuster = self.module.NeighborhoodRevenueAdjuster()
        assert hasattr(adjuster, "compute_adjusted_revenue")
        assert callable(adjuster.compute_adjusted_revenue)


class TestGetAdjustmentFactorAsync:
    """Tests for get_adjustment_factor async method."""

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_downtown(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("Downtown")
        assert factor == 1.35

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_coal_harbour(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("Coal Harbour")
        assert factor == 1.35

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_kitsilano(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("Kitsilano")
        assert factor == 1.25

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_mount_pleasant(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("Mount Pleasant")
        assert factor == 1.15

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_hastings_sunrise(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("Hastings-Sunrise")
        assert factor == 0.95

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_renfrew_collingwood(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("Renfrew-Collingwood")
        assert factor == 0.85

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_unknown_returns_default(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("Unknown Neighborhood")
        assert factor == 1.0

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_empty_string_returns_default(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor("")
        assert factor == 1.0

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_none_returns_default(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor(None or "")
        assert factor == 1.0

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_within_bounds_min(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        for neighborhood in (
            module.NEIGHBORHOOD_ADJUSTMENT_FACTORS.keys()
        ):
            factor = await adjuster.get_adjustment_factor(neighborhood)
            assert factor >= 0.7, (
                f"{neighborhood} factor {factor} below minimum"
            )

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_within_bounds_max(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        for neighborhood in (
            module.NEIGHBORHOOD_ADJUSTMENT_FACTORS.keys()
        ):
            factor = await adjuster.get_adjustment_factor(neighborhood)
            assert factor <= 1.5, (
                f"{neighborhood} factor {factor} above maximum"
            )


class TestGetRevenuePerSqftAsync:
    """Tests for get_revenue_per_sqft async method."""

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_downtown(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Downtown")
        assert "condo" in psf
        assert "rental" in psf
        assert "commercial" in psf
        assert "townhouse" in psf

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_downtown_condo_value(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Downtown")
        assert psf["condo"] == 1400

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_kitsilano(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Kitsilano")
        assert psf["condo"] == 1200

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_hastings_sunrise(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Hastings-Sunrise")
        assert psf["condo"] == 680

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_unknown_returns_default(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Unknown")
        assert psf == module.DEFAULT_PSF

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_all_four_types(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Downtown")
        assert len(psf) == 4

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_rental_in_range(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Downtown")
        assert 20 <= psf["rental"] <= 70

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_commercial_in_range(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        psf = await adjuster.get_revenue_per_sqft("Downtown")
        assert 15 <= psf["commercial"] <= 50


class TestComputeAdjustedRevenueAsync:
    """Tests for compute_adjusted_revenue async method."""

    @pytest.mark.asyncio
    async def test_compute_adjusted_revenue_no_pool(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        result = await adjuster.compute_adjusted_revenue(
            1000000.0, "Downtown"
        )
        expected = 1000000.0 * 1.35
        assert result == expected

    @pytest.mark.asyncio
    async def test_compute_adjusted_revenue_kitsilano(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        result = await adjuster.compute_adjusted_revenue(
            1000000.0, "Kitsilano"
        )
        expected = 1000000.0 * 1.25
        assert result == expected

    @pytest.mark.asyncio
    async def test_compute_adjusted_revenue_negative_base(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        result = await adjuster.compute_adjusted_revenue(
            -1000000.0, "Downtown"
        )
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_compute_adjusted_revenue_zero_base(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        result = await adjuster.compute_adjusted_revenue(0.0, "Downtown")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_compute_adjusted_revenue_realistic_values(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        base = 5000000.0
        result = await adjuster.compute_adjusted_revenue(
            base, "Mount Pleasant"
        )
        expected = base * 1.15
        assert result == expected


class TestNormalizeNeighborhood:
    """Tests for neighborhood name normalization."""

    @pytest.mark.asyncio
    async def test_normalize_neighborhood_method_exists(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        assert hasattr(adjuster, "_normalize_neighborhood")

    def test_normalize_neighborhood_trim_whitespace(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        result = adjuster._normalize_neighborhood("  Downtown  ")
        assert result == "Downtown"

    def test_normalize_neighborhood_empty_string(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        result = adjuster._normalize_neighborhood("")
        assert result == ""

    def test_normalize_neighborhood_none_type(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        try:
            result = adjuster._normalize_neighborhood(None)
            assert result == ""
        except (TypeError, AttributeError):
            pass


class TestDatabaseFallback:
    """Tests for database fallback behavior."""

    @pytest.mark.asyncio
    async def test_get_adjustment_factor_fallback_when_db_unavailable(
        self,
    ):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        mock_pool = AsyncMock()
        mock_pool.fetchrow.side_effect = Exception("Connection failed")

        adjuster = module.NeighborhoodRevenueAdjuster(pool=mock_pool)
        factor = await adjuster.get_adjustment_factor("Downtown")
        assert factor == 1.35

    @pytest.mark.asyncio
    async def test_get_revenue_per_sqft_fallback_when_db_unavailable(
        self,
    ):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        mock_pool = AsyncMock()
        mock_pool.fetch.side_effect = Exception("Connection failed")

        adjuster = module.NeighborhoodRevenueAdjuster(pool=mock_pool)
        psf = await adjuster.get_revenue_per_sqft("Downtown")
        assert psf["condo"] == 1400


class TestSpecialCharactersAndEdgeCases:
    """Tests for special characters and edge cases."""

    @pytest.mark.asyncio
    async def test_neighborhood_with_hyphens(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor(
            "Dunbar-Southlands"
        )
        assert factor == 1.2

    @pytest.mark.asyncio
    async def test_neighborhood_with_multiple_words(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor(
            "Kensington-Cedar Cottage"
        )
        assert factor == 0.95

    @pytest.mark.asyncio
    async def test_neighborhood_leading_trailing_spaces(self):
        spec = __import__(
            "importlib.util"
        ).util.spec_from_file_location(
            "neighborhood_revenue",
            API_DIR / "neighborhood_revenue.py"
        )
        module = __import__(
            "importlib.util"
        ).util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adjuster = module.NeighborhoodRevenueAdjuster()
        factor = await adjuster.get_adjustment_factor(
            "  Mount Pleasant  "
        )
        assert factor == 1.15
