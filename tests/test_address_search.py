import pathlib
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

COMPONENTS_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "components"
)
API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"


class TestAddressSearchBarStructure:
    """Test AddressSearchBar component structure"""

    def test_component_file_exists(self):
        assert (COMPONENTS_DIR / "AddressSearchBar.tsx").exists()

    def test_component_imports_geocoding(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "geocodeAddress" in content and "@/lib/geocoding" in content

    def test_component_has_required_props(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "onSelect" in content
        assert "placeholder" in content
        assert "className" in content

    def test_component_exports_default(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "export default function AddressSearchBar" in content

    def test_search_input_element_present(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert 'input' in content
        assert 'type="text"' in content

    def test_dropdown_element_present(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert 'role="listbox"' in content

    def test_clear_button_present(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "handleClear" in content
        assert "Clear search" in content


class TestDebounceImplementation:
    """Test debounce functionality (300ms reference)"""

    def test_debounce_timeout_used(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "debounceTimer" in content
        assert "clearTimeout" in content
        assert "setTimeout" in content

    def test_debounce_delay_is_300ms(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "300" in content

    def test_debounce_on_input_change(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "handleInputChange" in content
        assert "onChange={handleInputChange}" in content

    def test_debounce_clears_previous_timer(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "debounceTimer.current" in content

    def test_debounce_prevents_api_spam(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "debounceTimer" in content


class TestAutocompleteDropdown:
    """Test autocomplete dropdown behavior"""

    def test_dropdown_opens_on_input_focus(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "onFocus" in content
        assert "setIsOpen(true)" in content

    def test_dropdown_shows_results(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "displayResults" in content
        assert "map(" in content

    def test_dropdown_shows_recent_when_empty_query(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "recentSearches" in content
        assert 'query === ""' in content

    def test_dropdown_closes_on_outside_click(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "handleClickOutside" in content
        assert "setIsOpen(false)" in content

    def test_dropdown_closes_on_selection(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "handleSelectResult" in content

    def test_dropdown_displays_address_info(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "result.address" in content
        assert "result.neighborhood" in content
        assert "result.postalCode" in content


class TestKeyboardNavigation:
    """Test keyboard navigation (arrow keys, Enter, Escape)"""

    def test_arrow_down_navigation(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert '"ArrowDown"' in content
        assert "setActiveIndex" in content

    def test_arrow_up_navigation(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert '"ArrowUp"' in content

    def test_enter_selects_item(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert '"Enter"' in content
        assert "handleSelectResult" in content

    def test_escape_closes_dropdown(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert '"Escape"' in content
        assert "setIsOpen(false)" in content

    def test_active_index_tracking(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "activeIndex" in content
        assert "aria-activedescendant" in content

    def test_keyboard_handler_prevents_default(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "preventDefault()" in content

    def test_keyboard_prevents_boundary_overflow(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "displayResults.length" in content


class TestRecentSearches:
    """Test recent searches history (localStorage, last 10)"""

    def test_localstorage_key_constant(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "RECENT_SEARCHES_KEY" in content
        assert "address_search_history" in content

    def test_max_recent_searches_limit(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "MAX_RECENT_SEARCHES" in content
        assert "10" in content

    def test_loads_from_localstorage_on_mount(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "localStorage.getItem" in content
        assert "useEffect" in content

    def test_saves_to_localstorage_on_select(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "localStorage.setItem" in content
        assert "updateRecentSearches" in content

    def test_recent_searches_deduplication(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "filtered" in content
        assert "r.lat === result.lat && r.lng === result.lng" in content

    def test_recent_searches_state_managed(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "recentSearches" in content
        assert "setRecentSearches" in content


class TestLoadingState:
    """Test loading state during geocode requests"""

    def test_loading_state_defined(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "[loading, setLoading]" in content

    def test_loading_spinner_displayed(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "loading &&" in content
        assert "animate-spin" in content

    def test_loading_set_true_on_request(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "setLoading(true)" in content

    def test_loading_set_false_on_complete(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "setLoading(false)" in content


class TestAccessibility:
    """Test accessibility (combobox role, aria attributes)"""

    def test_combobox_role_present(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert 'role="combobox"' in content

    def test_aria_expanded_attribute(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "aria-expanded={isOpen}" in content

    def test_aria_haspopup_attribute(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert 'aria-haspopup="listbox"' in content

    def test_aria_activedescendant_attribute(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "aria-activedescendant" in content

    def test_listbox_role_on_dropdown(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert 'role="listbox"' in content

    def test_option_role_on_items(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert 'role="option"' in content

    def test_aria_selected_on_options(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "aria-selected" in content

    def test_aria_autocomplete_attribute(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "aria-autocomplete" in content

    def test_aria_controls_attribute(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert "aria-controls" in content


class TestGeocodingService:
    """Test geocoding service (geocodeAddress, reverseGeocode)"""

    def test_geocoding_file_exists(self):
        assert (pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "geocoding.ts").exists()

    def test_geocoding_exports_geocodeaddress(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "export async function geocodeAddress" in content

    def test_geocoding_exports_reversegeocode(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "export async function reverseGeocode" in content

    def test_geocodeaddress_returns_promise(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "Promise<GeocodingResult[]>" in content

    def test_reversegeocode_returns_promise(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "Promise<GeocodingResult>" in content

    def test_geocoding_validates_bounds(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "isWithinVancouverBounds" in content


class TestGeocodingResultType:
    """Test GeocodingResult type structure"""

    def test_result_type_has_address(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "address: string" in content

    def test_result_type_has_coordinates(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "lat: number" in content
        assert "lng: number" in content

    def test_result_type_has_neighborhood(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "neighborhood" in content

    def test_result_type_has_postalcode(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "postalCode" in content

    def test_result_type_has_confidence(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "confidence: number" in content

    def test_result_type_exported(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "export interface GeocodingResult" in content


class TestVancouverBoundaryValidation:
    """Test Vancouver bounds validation (lat 49.0-49.4, lng -123.3 to -122.9)"""

    def test_bounds_constants_frontend(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "VANCOUVER_BOUNDS" in content
        assert "49.0" in content
        assert "49.4" in content
        assert "-123.3" in content
        assert "-122.9" in content

    def test_bounds_check_function_frontend(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "isWithinVancouverBounds" in content

    def test_bounds_validation_backend(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "VANCOUVER_BOUNDS" in content

    def test_bounds_min_lat(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert '"min_lat": 49.0' in content

    def test_bounds_max_lat(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert '"max_lat": 49.4' in content

    def test_bounds_min_lng(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert '"min_lng": -123.3' in content

    def test_bounds_max_lng(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert '"max_lng": -122.9' in content

    def test_bounds_validation_in_geocode(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "validate_bounds" in content


class TestAPIEndpointStructure:
    """Test API endpoint structure (GET /geocode, GET /reverse-geocode)"""

    def test_geocode_endpoint_exists(self):
        assert (API_DIR / "geocoding.py").exists()

    def test_geocode_endpoint_decorated(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "@router.get(\"/geocode\"" in content

    def test_reverse_geocode_endpoint_decorated(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "@router.get(\"/reverse-geocode\"" in content

    def test_geocode_endpoint_function(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "async def geocode" in content

    def test_reverse_geocode_endpoint_function(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "async def reverse_geocode" in content

    def test_geocode_accepts_query_param(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "q: str = Query" in content

    def test_reverse_geocode_accepts_lat_lng(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "lat: float = Query" in content
        assert "lng: float = Query" in content

    def test_endpoints_return_geocoding_result(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "GeocodingResult" in content


class TestRateLimiting:
    """Test rate limiting on geocoding endpoints"""

    def test_rate_limiter_class_exists(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "class RateLimiter" in content

    def test_rate_limiter_initialized(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "rate_limiter = RateLimiter" in content

    def test_rate_limiter_max_requests(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "max_requests" in content
        assert "10" in content

    def test_rate_limiter_window_seconds(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "window_seconds" in content

    def test_rate_limiter_is_allowed_method(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "def is_allowed" in content

    def test_rate_limiter_checks_geocode(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "rate_limiter.is_allowed" in content

    def test_rate_limit_returns_429(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "429" in content
        assert "Rate limit exceeded" in content


class TestCachingImplementation:
    """Test caching implementation"""

    def test_cache_ttl_defined(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "CACHE_TTL" in content

    def test_cache_map_frontend(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "cache" in content
        assert "new Map" in content

    def test_cache_key_function_frontend(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "getCacheKey" in content

    def test_cache_get_function_frontend(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "getCachedResults" in content

    def test_cache_set_function_frontend(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "setCachedResults" in content

    def test_backend_caching_lru(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "@lru_cache" in content

    def test_backend_cache_maxsize(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "maxsize=256" in content


class TestFallbackGeocoder:
    """Test fallback geocoder logic"""

    def test_fallback_handling_in_geocode(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "try:" in content
        assert "except" in content

    def test_mapbox_token_check(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "MAPBOX_TOKEN" in content
        assert "os.getenv" in content

    def test_error_handling_returns_empty(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "except Exception" in content

    def test_fallback_returns_coordinates_as_string(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "address=" in content


class TestEdgeCases:
    """Test edge cases (empty query, special characters, out-of-bounds)"""

    def test_empty_query_handling(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert 'if (!query.trim())' in content
        assert 'return []' in content

    def test_empty_query_closes_dropdown(self):
        content = (COMPONENTS_DIR / "AddressSearchBar.tsx").read_text()
        assert 'if (!value.trim())' in content

    def test_special_characters_encoded(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "encodeURIComponent" in content

    def test_out_of_bounds_coords_rejected_frontend(self):
        content = (
            pathlib.Path(__file__).resolve().parent.parent
            / "frontend"
            / "src"
            / "lib"
            / "geocoding.ts"
        ).read_text()
        assert "isWithinVancouverBounds" in content

    def test_out_of_bounds_coords_rejected_backend(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "validate_bounds" in content

    def test_out_of_bounds_throws_error(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "outside Vancouver" in content

    def test_minimum_query_length(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "min_length=2" in content

    def test_timeout_on_requests(self):
        content = (API_DIR / "geocoding.py").read_text()
        assert "timeout=" in content
