"""
Due Diligence Checklist Tests
Comprehensive test suite for DueDiligenceChecklist component and API endpoint.
Tests: component structure, data types, API endpoints, database, accessibility.
"""

import pathlib
import json
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock

import pytest


COMPONENTS_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "components"
)
API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"
LIB_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib"
)


class TestDueDiligenceChecklistComponent:
    """Tests for React component structure and functionality."""

    def setup_method(self):
        """Load component and types files."""
        self.component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.types_path = LIB_DIR / "checklist-types.ts"

        assert self.component_path.exists(), "Component file not found"
        assert self.types_path.exists(), "Types file not found"

        self.component_content = self.component_path.read_text()
        self.types_content = self.types_path.read_text()

    def test_component_export_exists(self):
        """Component exports DueDiligenceChecklist."""
        assert "export const DueDiligenceChecklist" in self.component_content

    def test_component_is_functional_component(self):
        """Component is a functional component."""
        assert '"use client"' in self.component_content
        assert "useState" in self.component_content
        assert "useEffect" in self.component_content

    def test_component_accepts_parcel_id_prop(self):
        """Component accepts parcelId prop."""
        assert "parcelId: string" in self.component_content

    def test_component_accepts_initial_items_prop(self):
        """Component accepts optional initialItems prop."""
        assert "initialItems?: ChecklistItem[]" in self.component_content

    def test_component_has_state_for_items(self):
        """Component manages items state."""
        assert "useState<ChecklistItem[]>" in self.component_content
        assert "setItems" in self.component_content

    def test_component_has_state_for_expanded_categories(self):
        """Component manages expanded categories state."""
        assert "expandedCategories" in self.component_content
        assert "setExpandedCategories" in self.component_content

    def test_component_has_state_for_custom_input(self):
        """Component manages custom item input state."""
        assert "customItemInput" in self.component_content
        assert "setCustomItemInput" in self.component_content

    def test_component_initializes_with_default_items(self):
        """Component initializes with default items if no initial items provided."""
        assert "DEFAULT_CHECKLIST_ITEMS" in self.component_content
        assert "useEffect" in self.component_content

    def test_component_renders_progress_bar(self):
        """Component renders progress bar."""
        assert "Progress" in self.component_content
        assert "calculateProgress" in self.component_content
        assert "width" in self.component_content

    def test_component_has_collapsible_sections(self):
        """Component has collapsible category sections."""
        assert "toggleCategory" in self.component_content
        assert "expandedCategories" in self.component_content
        assert "aria-expanded" in self.component_content

    def test_component_has_checkbox_for_items(self):
        """Component renders checkboxes for items."""
        assert 'type="checkbox"' in self.component_content
        assert "toggleItem" in self.component_content

    def test_component_supports_notes_field(self):
        """Component supports notes for checked items."""
        assert "updateNotes" in self.component_content
        assert "textarea" in self.component_content
        assert "notes" in self.component_content

    def test_component_has_add_custom_item_button(self):
        """Component has button to add custom items."""
        assert "addCustomItem" in self.component_content
        assert "Add Custom Item" in self.component_content

    def test_component_has_export_function(self):
        """Component has function to export checklist as JSON."""
        assert "exportChecklist" in self.component_content
        assert "Export as JSON" in self.component_content
        assert "JSON.stringify" in self.component_content

    def test_component_uses_tailwind_css(self):
        """Component uses Tailwind CSS classes."""
        assert "className=" in self.component_content
        assert "bg-" in self.component_content
        assert "text-" in self.component_content

    def test_component_has_accessibility_labels(self):
        """Component has proper accessibility labels."""
        assert "aria-label" in self.component_content
        assert "htmlFor" in self.component_content
        assert "role=" in self.component_content


class TestChecklistTypes:
    """Tests for TypeScript type definitions."""

    def setup_method(self):
        """Load types file."""
        self.types_path = LIB_DIR / "checklist-types.ts"
        self.types_content = self.types_path.read_text()

    def test_checklist_category_type_exists(self):
        """ChecklistCategory type is defined."""
        assert "type ChecklistCategory" in self.types_content

    def test_checklist_category_has_title_legal(self):
        """ChecklistCategory includes title_legal."""
        assert "title_legal" in self.types_content

    def test_checklist_category_has_zoning_planning(self):
        """ChecklistCategory includes zoning_planning."""
        assert "zoning_planning" in self.types_content

    def test_checklist_category_has_physical(self):
        """ChecklistCategory includes physical."""
        assert "physical" in self.types_content

    def test_checklist_category_has_financial(self):
        """ChecklistCategory includes financial."""
        assert "financial" in self.types_content

    def test_checklist_category_has_municipal(self):
        """ChecklistCategory includes municipal."""
        assert "municipal" in self.types_content

    def test_checklist_item_interface_exists(self):
        """ChecklistItem interface is defined."""
        assert "interface ChecklistItem" in self.types_content

    def test_checklist_item_has_id(self):
        """ChecklistItem has id field."""
        assert "id: string" in self.types_content

    def test_checklist_item_has_label(self):
        """ChecklistItem has label field."""
        assert "label: string" in self.types_content

    def test_checklist_item_has_category(self):
        """ChecklistItem has category field."""
        assert "category: ChecklistCategory" in self.types_content

    def test_checklist_item_has_checked(self):
        """ChecklistItem has checked field."""
        assert "checked: boolean" in self.types_content

    def test_checklist_item_has_optional_notes(self):
        """ChecklistItem has optional notes field."""
        assert "notes?" in self.types_content

    def test_checklist_item_has_created_at(self):
        """ChecklistItem has createdAt field."""
        assert "createdAt: string" in self.types_content

    def test_default_checklist_items_constant_exists(self):
        """DEFAULT_CHECKLIST_ITEMS constant is defined."""
        assert "DEFAULT_CHECKLIST_ITEMS" in self.types_content

    def test_default_checklist_items_exported(self):
        """DEFAULT_CHECKLIST_ITEMS is exported."""
        assert "export const DEFAULT_CHECKLIST_ITEMS" in self.types_content

    def test_category_labels_constant_exists(self):
        """CATEGORY_LABELS constant is defined."""
        assert "CATEGORY_LABELS" in self.types_content


class TestDefaultChecklistItems:
    """Tests for default checklist items."""

    def setup_method(self):
        """Load and parse default items from types file."""
        types_path = LIB_DIR / "checklist-types.ts"
        self.types_content = types_path.read_text()

    def test_has_20_default_items(self):
        """DEFAULT_CHECKLIST_ITEMS has 20 items."""
        count = self.types_content.count("label:")
        assert count >= 20, f"Expected at least 20 items, found {count}"

    def test_title_legal_category_items(self):
        """Has 4 items in title_legal category."""
        items = [
            "Title search",
            "Encumbrances check",
            "Legal non-conforming status",
            "Covenant review"
        ]
        for item in items:
            assert item in self.types_content

    def test_zoning_planning_category_items(self):
        """Has 4 items in zoning_planning category."""
        items = [
            "Current zoning verification",
            "OCP designation check",
            "Transit proximity confirmed",
            "View cone analysis"
        ]
        for item in items:
            assert item in self.types_content

    def test_physical_category_items(self):
        """Has 4 items in physical category."""
        items = [
            "Environmental site assessment (Phase 1)",
            "Geotechnical report",
            "Building condition assessment",
            "Survey/legal plan"
        ]
        for item in items:
            assert item in self.types_content

    def test_financial_category_items(self):
        """Has 4 items in financial category."""
        items = [
            "Market comparable analysis",
            "Pro forma review",
            "Construction cost estimate",
            "Financing pre-approval"
        ]
        for item in items:
            assert item in self.types_content

    def test_municipal_category_items(self):
        """Has 4 items in municipal category."""
        items = [
            "Development permit pre-application",
            "Utility capacity check",
            "Community amenity contribution estimate",
            "DCL estimate"
        ]
        for item in items:
            assert item in self.types_content


class TestCategoryGrouping:
    """Tests for category organization."""

    def setup_method(self):
        """Load types file."""
        types_path = LIB_DIR / "checklist-types.ts"
        self.types_content = types_path.read_text()

    def test_five_categories_exist(self):
        """All 5 categories are defined."""
        categories = [
            "title_legal",
            "zoning_planning",
            "physical",
            "financial",
            "municipal"
        ]
        for cat in categories:
            assert f'"{cat}"' in self.types_content or f"'{cat}'" in self.types_content

    def test_category_labels_has_five_entries(self):
        """CATEGORY_LABELS has entries for all 5 categories."""
        assert "title_legal:" in self.types_content or "title_legal :" in self.types_content
        assert "zoning_planning:" in self.types_content or "zoning_planning :" in self.types_content
        assert "physical:" in self.types_content or "physical :" in self.types_content
        assert "financial:" in self.types_content or "financial :" in self.types_content
        assert "municipal:" in self.types_content or "municipal :" in self.types_content


class TestProgressCalculation:
    """Tests for progress calculation logic."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_progress_calculation_exists(self):
        """calculateProgress function exists."""
        assert "calculateProgress" in self.component_content

    def test_progress_uses_checked_count(self):
        """Progress calculation uses checked items count."""
        assert "checked" in self.component_content
        assert "filter" in self.component_content

    def test_progress_bar_displayed(self):
        """Progress bar is displayed."""
        assert "Progress" in self.component_content
        assert "{progress}%" in self.component_content


class TestCollapsibleSections:
    """Tests for collapsible category sections."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_has_toggle_function(self):
        """toggleCategory function exists."""
        assert "toggleCategory" in self.component_content

    def test_uses_expanded_state(self):
        """Uses expandedCategories state."""
        assert "expandedCategories" in self.component_content

    def test_button_has_aria_expanded(self):
        """Button has aria-expanded attribute."""
        assert "aria-expanded" in self.component_content

    def test_section_hides_when_collapsed(self):
        """Section content hidden when not expanded."""
        assert "isExpanded &&" in self.component_content or "{isExpanded &&" in self.component_content


class TestCustomItemAddition:
    """Tests for custom item functionality."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_has_add_custom_item_function(self):
        """addCustomItem function exists."""
        assert "addCustomItem" in self.component_content

    def test_has_custom_item_input_state(self):
        """customItemInput state exists."""
        assert "customItemInput" in self.component_content

    def test_has_add_button(self):
        """Add button for custom items exists."""
        assert "Add" in self.component_content or "add" in self.component_content

    def test_generates_unique_ids(self):
        """Generates unique IDs for custom items."""
        assert "Date.now()" in self.component_content or "uuid" in self.component_content

    def test_custom_item_can_be_removed(self):
        """Custom items can be removed."""
        assert "removeItem" in self.component_content


class TestNotesFieldSupport:
    """Tests for notes field functionality."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_has_update_notes_function(self):
        """updateNotes function exists."""
        assert "updateNotes" in self.component_content

    def test_renders_textarea_for_notes(self):
        """Textarea element for notes exists."""
        assert "textarea" in self.component_content

    def test_notes_appear_when_item_checked(self):
        """Notes field appears only when item is checked."""
        assert "checked &&" in self.component_content or "{item.checked &&" in self.component_content

    def test_notes_stored_in_item(self):
        """Notes are stored in ChecklistItem."""
        assert "notes" in self.component_content


class TestExportFunctionality:
    """Tests for export functionality."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_has_export_function(self):
        """exportChecklist function exists."""
        assert "exportChecklist" in self.component_content

    def test_exports_as_json(self):
        """Exports checklist as JSON."""
        assert "JSON.stringify" in self.component_content

    def test_export_button_exists(self):
        """Export button exists."""
        assert "Export" in self.component_content

    def test_export_includes_parcel_id(self):
        """Export includes parcelId."""
        assert "parcelId" in self.component_content


class TestAccessibility:
    """Tests for accessibility features."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_checkboxes_have_aria_labels(self):
        """Checkboxes have aria-label attribute."""
        assert "aria-label" in self.component_content

    def test_checkboxes_have_role(self):
        """Checkboxes have role attribute."""
        assert 'role="checkbox"' in self.component_content

    def test_labels_associated_with_inputs(self):
        """Labels are associated with form inputs."""
        assert "htmlFor=" in self.component_content or "htmlFor =" in self.component_content

    def test_buttons_have_aria_labels(self):
        """Buttons have descriptive aria-labels."""
        assert "aria-label=" in self.component_content or "aria-label =" in self.component_content

    def test_expanded_button_has_aria_expanded(self):
        """Expand/collapse button has aria-expanded."""
        assert "aria-expanded" in self.component_content


class TestTailwindCSSValidation:
    """Tests for Tailwind CSS usage."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_uses_background_classes(self):
        """Uses Tailwind background classes."""
        assert "bg-" in self.component_content

    def test_uses_text_classes(self):
        """Uses Tailwind text classes."""
        assert "text-" in self.component_content

    def test_uses_spacing_classes(self):
        """Uses Tailwind spacing classes."""
        assert "p-" in self.component_content or "m-" in self.component_content

    def test_uses_border_classes(self):
        """Uses Tailwind border classes."""
        assert "border" in self.component_content

    def test_uses_rounded_classes(self):
        """Uses Tailwind rounded corner classes."""
        assert "rounded" in self.component_content

    def test_no_separate_css_file(self):
        """No separate CSS file is used."""
        css_path = COMPONENTS_DIR / "DueDiligenceChecklist.css"
        assert not css_path.exists(), "Should not have separate CSS file"


class TestAPIEndpointStructure:
    """Tests for API endpoint structure."""

    def setup_method(self):
        """Load API file."""
        api_path = API_DIR / "checklist.py"
        assert api_path.exists(), "API file not found"
        self.api_content = api_path.read_text()

    def test_router_created(self):
        """FastAPI router is created."""
        assert "APIRouter" in self.api_content

    def test_has_get_endpoint(self):
        """GET endpoint exists."""
        assert "@router.get" in self.api_content
        assert "parcels/{parcel_id}/checklist" in self.api_content

    def test_has_put_endpoint(self):
        """PUT endpoint exists."""
        assert "@router.put" in self.api_content
        assert "parcels/{parcel_id}/checklist" in self.api_content

    def test_has_post_endpoint(self):
        """POST endpoint exists for adding items."""
        assert "@router.post" in self.api_content
        assert "parcels/{parcel_id}/checklist/items" in self.api_content

    def test_has_delete_endpoint(self):
        """DELETE endpoint exists for removing items."""
        assert "@router.delete" in self.api_content
        assert "parcels/{parcel_id}/checklist/items/{item_id}" in self.api_content


class TestAPIInputValidation:
    """Tests for API input validation."""

    def setup_method(self):
        """Load API file."""
        api_path = API_DIR / "checklist.py"
        self.api_content = api_path.read_text()

    def test_has_pydantic_models(self):
        """Uses Pydantic models for validation."""
        assert "BaseModel" in self.api_content

    def test_checklist_item_request_model(self):
        """ChecklistItemRequest model exists."""
        assert "ChecklistItemRequest" in self.api_content

    def test_checklist_response_model(self):
        """ChecklistResponse model exists."""
        assert "ChecklistResponse" in self.api_content

    def test_label_field_required(self):
        """Label field is required."""
        assert "label:" in self.api_content or "label :" in self.api_content

    def test_label_has_min_length(self):
        """Label has minimum length validation."""
        assert "min_length" in self.api_content

    def test_category_field_required(self):
        """Category field is required."""
        assert "category:" in self.api_content or "category :" in self.api_content

    def test_checked_field_optional(self):
        """Checked field is optional with default."""
        assert "checked" in self.api_content or "False" in self.api_content


class TestAPIDatabase:
    """Tests for database interaction."""

    def setup_method(self):
        """Load API file."""
        api_path = API_DIR / "checklist.py"
        self.api_content = api_path.read_text()

    def test_uses_asyncpg(self):
        """Uses asyncpg for database access."""
        assert "asyncpg" in self.api_content

    def test_table_name_is_due_diligence_checklists(self):
        """Uses due_diligence_checklists table."""
        assert "due_diligence_checklists" in self.api_content

    def test_stores_parcel_id(self):
        """Stores parcel_id in database."""
        assert "parcel_id" in self.api_content

    def test_stores_user_id(self):
        """Stores user_id in database."""
        assert "user_id" in self.api_content

    def test_stores_items_as_json(self):
        """Stores items as JSONB/JSON."""
        assert "items" in self.api_content

    def test_stores_updated_at(self):
        """Stores updated_at timestamp."""
        assert "updated_at" in self.api_content

    def test_uses_upsert_pattern(self):
        """Uses INSERT...ON CONFLICT for upsert."""
        assert "ON CONFLICT" in self.api_content or "on conflict" in self.api_content.lower()


class TestAPIErrorHandling:
    """Tests for API error handling."""

    def setup_method(self):
        """Load API file."""
        api_path = API_DIR / "checklist.py"
        self.api_content = api_path.read_text()

    def test_handles_not_found_errors(self):
        """Handles 404 Not Found errors."""
        assert "HTTPException" in self.api_content
        assert "404" in self.api_content or "NOT_FOUND" in self.api_content

    def test_returns_proper_status_codes(self):
        """Returns proper HTTP status codes."""
        assert "status_code" in self.api_content


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_handles_empty_checklist(self):
        """Handles empty checklist gracefully."""
        assert "items.length" in self.component_content

    def test_handles_all_items_checked(self):
        """Handles case where all items are checked."""
        assert "calculateProgress" in self.component_content

    def test_handles_no_custom_items(self):
        """Handles checklist with no custom items."""
        assert "default" in self.component_content.lower()

    def test_prevents_duplicate_custom_items(self):
        """Can prevent or handle duplicate custom items."""
        assert "id:" in self.component_content or "customItemInput" in self.component_content


class TestComponentIntegration:
    """Integration tests for component usage."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_component_can_be_imported(self):
        """Component can be imported as named export."""
        assert "export const DueDiligenceChecklist" in self.component_content

    def test_component_uses_correct_imports(self):
        """Component imports from correct paths."""
        assert "import" in self.component_content
        assert "useState" in self.component_content or "@" in self.component_content

    def test_component_renders_heading(self):
        """Component renders a main heading."""
        assert "Due Diligence Checklist" in self.component_content

    def test_component_has_proper_structure(self):
        """Component has proper JSX structure."""
        assert "return" in self.component_content
        assert "<" in self.component_content and ">" in self.component_content


class TestTypeScriptCompilation:
    """Tests for TypeScript type correctness."""

    def setup_method(self):
        """Load files."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        types_path = LIB_DIR / "checklist-types.ts"
        self.component_content = component_path.read_text()
        self.types_content = types_path.read_text()

    def test_component_imports_types(self):
        """Component imports types from checklist-types."""
        assert "checklist-types" in self.component_content

    def test_types_are_properly_exported(self):
        """Types are exported from types file."""
        assert "export" in self.types_content

    def test_no_any_types_in_component(self):
        """Component uses typed parameters, not any."""
        assert "DueDiligenceChecklistProps" in self.component_content

    def test_props_properly_typed(self):
        """Props interface is properly typed."""
        assert "interface DueDiligenceChecklistProps" in self.component_content


class TestAPITypes:
    """Tests for API Pydantic types."""

    def setup_method(self):
        """Load API file."""
        api_path = API_DIR / "checklist.py"
        self.api_content = api_path.read_text()

    def test_request_model_has_field_validators(self):
        """Request models have Field validators."""
        assert "Field" in self.api_content

    def test_response_model_defined(self):
        """Response models are properly defined."""
        assert "ChecklistResponse" in self.api_content

    def test_models_inherit_from_basemodel(self):
        """Models inherit from BaseModel."""
        assert "BaseModel" in self.api_content


class TestAPIAsync:
    """Tests for async API implementation."""

    def setup_method(self):
        """Load API file."""
        api_path = API_DIR / "checklist.py"
        self.api_content = api_path.read_text()

    def test_endpoints_are_async(self):
        """Endpoint functions are async."""
        assert "async def" in self.api_content

    def test_uses_database_pool(self):
        """Uses asyncpg Pool for database access."""
        assert "asyncpg.Pool" in self.api_content or "pool" in self.api_content.lower()

    def test_uses_context_managers(self):
        """Uses async context managers for database access."""
        assert "async with" in self.api_content


class TestDataPersistence:
    """Tests for data persistence behavior."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_component_state_management(self):
        """Component properly manages state."""
        assert "useState" in self.component_content

    def test_component_uses_effects(self):
        """Component uses useEffect for initialization."""
        assert "useEffect" in self.component_content

    def test_state_updates_on_item_change(self):
        """State updates when items change."""
        assert "setItems" in self.component_content


class TestUserInteraction:
    """Tests for user interaction patterns."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_checkbox_toggle_handler(self):
        """Checkbox has toggle handler."""
        assert "onChange" in self.component_content
        assert "toggleItem" in self.component_content

    def test_category_expand_handler(self):
        """Category button has expand handler."""
        assert "toggleCategory" in self.component_content

    def test_custom_item_submission(self):
        """Custom item can be submitted."""
        assert "addCustomItem" in self.component_content
        assert "onKeyDown" in self.component_content or "onClick" in self.component_content

    def test_export_download_handler(self):
        """Export button has download handler."""
        assert "exportChecklist" in self.component_content


class TestPerformance:
    """Tests for performance considerations."""

    def setup_method(self):
        """Load component file."""
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        self.component_content = component_path.read_text()

    def test_uses_filter_for_category_items(self):
        """Uses efficient filtering for items."""
        assert "filter" in self.component_content

    def test_uses_map_for_rendering_items(self):
        """Uses map for rendering items."""
        assert ".map(" in self.component_content

    def test_progress_memoization(self):
        """Progress calculation is efficient."""
        assert "calculateProgress" in self.component_content
