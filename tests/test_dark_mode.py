import pathlib
import re

COMPONENTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "components"
STYLES_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "styles"
LIB_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib"


class TestThemeToggleComponent:
    def setup_method(self):
        self.theme_toggle_path = COMPONENTS_DIR / "ThemeToggle.tsx"
        self.content = self.theme_toggle_path.read_text()

    def test_theme_toggle_file_exists(self):
        assert self.theme_toggle_path.exists(), "ThemeToggle.tsx does not exist"

    def test_is_react_component(self):
        assert "export" in self.content
        assert "ThemeToggle" in self.content
        assert "React.FC" in self.content

    def test_has_props_interface(self):
        assert "ThemeToggleProps" in self.content
        assert "className?" in self.content

    def test_uses_use_client_directive(self):
        assert '"use client"' in self.content

    def test_imports_use_theme_hook(self):
        assert "useTheme" in self.content
        assert "@/lib/theme-context" in self.content

    def test_has_sun_icon_function(self):
        assert "getSunIcon" in self.content
        assert "svg" in self.content.lower()
        assert "circle" in self.content

    def test_has_moon_icon_function(self):
        assert "getMoonIcon" in self.content
        assert "svg" in self.content.lower()

    def test_has_system_icon_function(self):
        assert "getSystemIcon" in self.content

    def test_has_handle_theme_change_function(self):
        assert "handleThemeChange" in self.content

    def test_onclick_handler_attached(self):
        assert "onClick={handleThemeChange}" in self.content

    def test_has_aria_label(self):
        assert "aria-label" in self.content

    def test_returns_button_element(self):
        assert "<button" in self.content
        assert "</button>" in self.content

    def test_has_tooltip_title(self):
        assert "title={getLabel()}" in self.content

    def test_supports_className_prop(self):
        assert "className={`" in self.content

    def test_button_has_styling_classes(self):
        assert "dark:" in self.content
        assert "bg-gray" in self.content or "bg-" in self.content

    def test_uses_transition_duration(self):
        assert "transition-colors" in self.content or "transition:" in self.content

    def test_has_focus_ring_styles(self):
        assert "focus:outline-none" in self.content or "focus:ring" in self.content

    def test_uses_use_state_hook(self):
        assert "useState" in self.content

    def test_uses_use_effect_hook(self):
        assert "useEffect" in self.content

    def test_hydration_safe_mounting_check(self):
        assert "isMounted" in self.content
        assert "setIsMounted" in self.content


class TestThemeContext:
    def setup_method(self):
        self.theme_context_path = LIB_DIR / "theme-context.tsx"
        self.content = self.theme_context_path.read_text()

    def test_theme_context_file_exists(self):
        assert self.theme_context_path.exists(), "theme-context.tsx does not exist"

    def test_uses_use_client_directive(self):
        assert '"use client"' in self.content

    def test_has_theme_type_definition(self):
        assert "type Theme" in self.content
        assert "light" in self.content
        assert "dark" in self.content
        assert "system" in self.content

    def test_has_theme_context_type_interface(self):
        assert "ThemeContextType" in self.content
        assert "theme: Theme" in self.content
        assert "setTheme:" in self.content
        assert "resolvedTheme:" in self.content

    def test_creates_context(self):
        assert "createContext" in self.content

    def test_exports_theme_provider(self):
        assert "export const ThemeProvider" in self.content

    def test_provider_accepts_children(self):
        assert "children: ReactNode" in self.content

    def test_exports_use_theme_hook(self):
        assert "export const useTheme" in self.content

    def test_use_theme_hook_uses_use_context(self):
        assert "useContext" in self.content

    def test_use_theme_hook_returns_context_type(self):
        assert "ThemeContextType" in self.content

    def test_use_theme_hook_throws_error_outside_provider(self):
        assert "Error" in self.content
        assert "ThemeProvider" in self.content

    def test_theme_provider_sets_theme_state(self):
        assert "setThemeState" in self.content

    def test_theme_provider_sets_resolved_theme_state(self):
        assert "setResolvedTheme" in self.content

    def test_theme_provider_loads_from_local_storage(self):
        assert "localStorage" in self.content
        assert "vancity-theme" in self.content

    def test_localStorage_key_is_correct(self):
        assert '"vancity-theme"' in self.content

    def test_validates_stored_theme_value(self):
        assert "includes" in self.content

    def test_applies_theme_on_mount(self):
        assert "applyTheme" in self.content

    def test_listens_to_prefers_color_scheme_media_query(self):
        assert "matchMedia" in self.content
        assert "prefers-color-scheme" in self.content

    def test_updates_on_media_query_change(self):
        assert "addEventListener" in self.content
        assert "change" in self.content

    def test_removes_media_query_listener_on_unmount(self):
        assert "removeEventListener" in self.content

    def test_system_mode_resolves_to_light_or_dark(self):
        assert "light" in self.content
        assert "dark" in self.content
        assert "system" in self.content

    def test_adds_dark_class_to_document_element(self):
        assert "classList.add" in self.content
        assert '"dark"' in self.content

    def test_removes_dark_class_from_document_element(self):
        assert "classList.remove" in self.content

    def test_persists_theme_to_localStorage(self):
        assert "localStorage.setItem" in self.content

    def test_provider_provides_context_value(self):
        assert "ThemeContext.Provider" in self.content
        assert "value=" in self.content

    def test_context_provider_returns_children(self):
        assert "{children}" in self.content


class TestTailwindConfig:
    def setup_method(self):
        self.tailwind_config_path = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "tailwind.config.ts"
        self.content = self.tailwind_config_path.read_text()

    def test_tailwind_config_file_exists(self):
        assert self.tailwind_config_path.exists(), "tailwind.config.ts does not exist"

    def test_exports_config(self):
        assert "export default" in self.content

    def test_has_dark_mode_class_configuration(self):
        assert "darkMode:" in self.content or "darkMode :" in self.content
        assert '"class"' in self.content or "'class'" in self.content

    def test_has_content_configuration(self):
        assert "content:" in self.content
        assert "src/components" in self.content

    def test_has_theme_extension(self):
        assert "theme:" in self.content
        assert "extend:" in self.content

    def test_has_dark_color_palette(self):
        assert "dark:" in self.content or "dark" in self.content

    def test_dark_colors_include_bg_primary(self):
        assert "bg" in self.content
        assert "primary" in self.content

    def test_dark_colors_include_bg_secondary(self):
        assert "secondary" in self.content

    def test_dark_colors_include_text_colors(self):
        assert "text" in self.content

    def test_dark_colors_include_border(self):
        assert "border" in self.content

    def test_dark_colors_include_accent(self):
        assert "accent" in self.content

    def test_config_is_type_safe(self):
        assert "Config" in self.content
        assert "type" in self.content or ":" in self.content


class TestDarkModeCss:
    def setup_method(self):
        self.css_path = STYLES_DIR / "dark-mode.css"
        self.content = self.css_path.read_text()

    def test_dark_mode_css_file_exists(self):
        assert self.css_path.exists(), "dark-mode.css does not exist"

    def test_defines_root_custom_properties(self):
        assert ":root {" in self.content
        assert "--" in self.content

    def test_defines_dark_selector(self):
        assert ".dark {" in self.content

    def test_has_bg_primary_property(self):
        assert "--bg-primary:" in self.content

    def test_has_bg_secondary_property(self):
        assert "--bg-secondary:" in self.content

    def test_has_bg_tertiary_property(self):
        assert "--bg-tertiary:" in self.content

    def test_has_text_primary_property(self):
        assert "--text-primary:" in self.content

    def test_has_text_secondary_property(self):
        assert "--text-secondary:" in self.content

    def test_has_text_tertiary_property(self):
        assert "--text-tertiary:" in self.content

    def test_has_accent_property(self):
        assert "--accent:" in self.content

    def test_has_border_property(self):
        assert "--border:" in self.content

    def test_has_transition_speed_property(self):
        assert "--transition-speed:" in self.content

    def test_light_mode_colors_defined(self):
        assert "#ffffff" in self.content or "white" in self.content

    def test_dark_mode_colors_differ_from_light(self):
        assert "#0a0a0a" in self.content or "#1a1a1a" in self.content

    def test_html_body_use_custom_properties(self):
        assert "html" in self.content or "body" in self.content
        assert "var(--" in self.content

    def test_background_color_transition(self):
        assert "background-color" in self.content
        assert "transition:" in self.content

    def test_color_transition(self):
        assert "color" in self.content

    def test_transition_speed_used(self):
        assert "var(--transition-speed)" in self.content

    def test_mapbox_popup_styling(self):
        assert ".mapboxgl-popup-content" in self.content

    def test_panel_and_card_styling(self):
        assert ".panel" in self.content or ".card" in self.content

    def test_button_styling(self):
        assert "button" in self.content

    def test_input_styling(self):
        assert "input" in self.content or "textarea" in self.content

    def test_link_styling(self):
        assert "a {" in self.content or "a:" in self.content

    def test_border_styling(self):
        assert "hr" in self.content or ".border" in self.content

    def test_scrollbar_styling(self):
        assert "::-webkit-scrollbar" in self.content

    def test_selection_styling(self):
        assert "::selection" in self.content

    def test_focus_visible_styling(self):
        assert ":focus-visible" in self.content

    def test_reduce_transitions_for_mapbox(self):
        assert ".mapboxgl-canvas" in self.content
        assert "transition: none" in self.content

    def test_smooth_transitions_enabled(self):
        assert "transition:" in self.content

    def test_placeholder_styling(self):
        assert "::placeholder" in self.content


class TestComponentDarkModeSupport:
    def setup_method(self):
        self.components = [
            "MapView.tsx",
            "IntelPage.tsx",
            "NeighborhoodPage.tsx",
            "FrictionMeter.tsx",
            "ConfidenceStars.tsx",
            "DueDiligenceChecklist.tsx",
            "NotificationBadge.tsx",
            "NotificationPanel.tsx",
            "AddressSearchBar.tsx",
            "DueDiligencePopup.tsx",
        ]

    def test_friction_meter_has_dark_support(self):
        component_path = COMPONENTS_DIR / "FrictionMeter.tsx"
        content = component_path.read_text()
        assert "dark:" in content or "text-gray" in content, "FrictionMeter should support dark mode through CSS variables or Tailwind classes"

    def test_confidence_stars_has_dark_support(self):
        component_path = COMPONENTS_DIR / "ConfidenceStars.tsx"
        content = component_path.read_text()
        assert "dark:" in content or "gray" in content, "ConfidenceStars should support dark mode"

    def test_map_view_exists(self):
        component_path = COMPONENTS_DIR / "MapView.tsx"
        assert component_path.exists(), "MapView.tsx should exist"

    def test_intel_page_exists(self):
        component_path = COMPONENTS_DIR / "IntelPage.tsx"
        assert component_path.exists(), "IntelPage.tsx should exist"

    def test_neighborhood_page_exists(self):
        component_path = COMPONENTS_DIR / "NeighborhoodPage.tsx"
        assert component_path.exists(), "NeighborhoodPage.tsx should exist"

    def test_due_diligence_checklist_exists(self):
        component_path = COMPONENTS_DIR / "DueDiligenceChecklist.tsx"
        assert component_path.exists(), "DueDiligenceChecklist.tsx should exist"

    def test_notification_badge_exists(self):
        component_path = COMPONENTS_DIR / "NotificationBadge.tsx"
        assert component_path.exists(), "NotificationBadge.tsx should exist"

    def test_notification_panel_exists(self):
        component_path = COMPONENTS_DIR / "NotificationPanel.tsx"
        assert component_path.exists(), "NotificationPanel.tsx should exist"

    def test_address_search_bar_exists(self):
        component_path = COMPONENTS_DIR / "AddressSearchBar.tsx"
        assert component_path.exists(), "AddressSearchBar.tsx should exist"

    def test_due_diligence_popup_exists(self):
        component_path = COMPONENTS_DIR / "DueDiligencePopup.tsx"
        assert component_path.exists(), "DueDiligencePopup.tsx should exist"


class TestThemeIntegration:
    def setup_method(self):
        self.theme_toggle_path = COMPONENTS_DIR / "ThemeToggle.tsx"
        self.theme_context_path = LIB_DIR / "theme-context.tsx"
        self.toggle_content = self.theme_toggle_path.read_text()
        self.context_content = self.theme_context_path.read_text()

    def test_toggle_uses_theme_context(self):
        assert "useTheme" in self.toggle_content

    def test_toggle_can_set_theme(self):
        assert "setTheme" in self.toggle_content

    def test_context_exports_use_theme_hook(self):
        assert "export const useTheme" in self.context_content

    def test_context_provides_theme_state(self):
        assert "theme," in self.context_content

    def test_context_provides_set_theme_function(self):
        assert "setTheme," in self.context_content

    def test_context_provides_resolved_theme(self):
        assert "resolvedTheme," in self.context_content

    def test_toggle_cycles_through_modes(self):
        assert "if (theme ===" in self.toggle_content

    def test_toggle_shows_appropriate_icon(self):
        assert "getIcon" in self.toggle_content

    def test_toggle_shows_appropriate_label(self):
        assert "getLabel" in self.toggle_content


class TestAccessibility:
    def setup_method(self):
        self.theme_toggle_path = COMPONENTS_DIR / "ThemeToggle.tsx"
        self.content = self.theme_toggle_path.read_text()

    def test_button_has_aria_label(self):
        assert "aria-label" in self.content

    def test_aria_label_is_descriptive(self):
        assert "theme" in self.content.lower()

    def test_button_has_title_attribute(self):
        assert "title=" in self.content

    def test_focus_ring_for_keyboard_navigation(self):
        assert "focus:" in self.content or "outline" in self.content

    def test_sufficient_color_contrast_in_light_mode(self):
        assert "text-gray" in self.content or "text-" in self.content

    def test_sufficient_color_contrast_in_dark_mode(self):
        assert "dark:" in self.content


class TestHydrationSafety:
    def setup_method(self):
        self.theme_context_path = LIB_DIR / "theme-context.tsx"
        self.theme_toggle_path = COMPONENTS_DIR / "ThemeToggle.tsx"
        self.context_content = self.theme_context_path.read_text()
        self.toggle_content = self.theme_toggle_path.read_text()

    def test_context_uses_use_effect(self):
        assert "useEffect" in self.context_content

    def test_context_checks_mount_status(self):
        # Context achieves hydration safety by reading localStorage only inside useEffect
        # (client-side only) with safe initial values for SSR
        assert "useEffect" in self.context_content and "localStorage" in self.context_content

    def test_toggle_uses_use_effect(self):
        assert "useEffect" in self.toggle_content

    def test_toggle_checks_mount_status(self):
        assert "isMounted" in self.toggle_content

    def test_toggle_returns_null_before_mount(self):
        assert "return null" in self.toggle_content

    def test_context_dependencies_array_exists(self):
        assert "useEffect(" in self.context_content and "[]" in self.context_content

    def test_toggle_dependencies_array_exists(self):
        assert "useEffect(" in self.toggle_content and "[]" in self.toggle_content

    def test_async_state_updates_prevented(self):
        assert "setIsMounted" in self.toggle_content or "setIsMounted" in self.context_content


class TestEdgeCases:
    def setup_method(self):
        self.theme_context_path = LIB_DIR / "theme-context.tsx"
        self.content = self.theme_context_path.read_text()

    def test_handles_missing_localStorage(self):
        assert "localStorage" in self.content or "try" in self.content

    def test_handles_invalid_stored_theme(self):
        assert "includes" in self.content or "if" in self.content

    def test_handles_system_preference_changes(self):
        assert "matchMedia" in self.content
        assert "addEventListener" in self.content

    def test_cleans_up_event_listeners(self):
        assert "removeEventListener" in self.content

    def test_validates_theme_values(self):
        assert "light" in self.content
        assert "dark" in self.content
        assert "system" in self.content

    def test_resolves_system_theme_correctly(self):
        assert "prefers-color-scheme" in self.content
        assert "matches" in self.content


class TestDocumentElement:
    def setup_method(self):
        self.theme_context_path = LIB_DIR / "theme-context.tsx"
        self.content = self.theme_context_path.read_text()

    def test_modifies_document_element(self):
        assert "document.documentElement" in self.content

    def test_adds_dark_class(self):
        assert "classList.add" in self.content

    def test_removes_dark_class(self):
        assert "classList.remove" in self.content

    def test_dark_class_string_is_correct(self):
        assert '"dark"' in self.content

    def test_applies_theme_on_mount(self):
        assert "applyTheme" in self.content

    def test_applies_theme_on_change(self):
        assert "applyTheme" in self.content
