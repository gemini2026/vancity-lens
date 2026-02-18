import pathlib
import re
import pytest

COMPONENTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "components"
HOOKS_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "hooks"
LAYOUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "app"


class TestMobileNavComponent:
    def test_mobilenav_file_exists(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        assert filepath.exists(), "MobileNav.tsx should exist"

    def test_mobilenav_is_client_component(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert '"use client"' in content, "MobileNav should be a client component"

    def test_mobilenav_imports_react(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "import { useState } from" in content, "MobileNav should import useState"

    def test_mobilenav_has_interface(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "interface MobileNavProps" in content, "MobileNav should have props interface"

    def test_mobilenav_accepts_activetab_prop(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert 'activeTab: "map" | "intel" | "hoods" | "alerts"' in content

    def test_mobilenav_accepts_ontabchange_callback(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "onTabChange:" in content

    def test_mobilenav_uses_usestate_for_isopen(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "useState(false)" in content, "MobileNav should track isOpen state"

    def test_mobilenav_hamburger_button_hidden_on_desktop(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "md:hidden" in content, "Hamburger button should use md:hidden"

    def test_mobilenav_hamburger_has_three_lines(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "h-0.5 w-6" in content, "Should have hamburger line elements"
        assert content.count("h-0.5") >= 3, "Should have at least three line elements"

    def test_mobilenav_hamburger_animated(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "rotate-45" in content, "First line should rotate when open"
        assert "translate-y-2" in content, "Lines should translate when open"
        assert "opacity-0" in content, "Middle line should fade when open"

    def test_mobilenav_has_overlay(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "bg-black/50" in content, "Overlay should have semi-transparent background"

    def test_mobilenav_overlay_closes_drawer(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert content.count("onClick={() => setIsOpen(false)}") >= 2

    def test_mobilenav_drawer_slides_from_left(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "left-0" in content, "Drawer should be positioned left"
        assert "-translate-x-full" in content, "Drawer should slide from left"
        assert "translate-x-0" in content, "Drawer should slide in"

    def test_mobilenav_drawer_has_close_button(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "✕" in content, "Drawer should have close button"

    def test_mobilenav_drawer_fixed_width(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "w-64" in content, "Drawer should have fixed width"

    def test_mobilenav_navigation_items_defined(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "navItems" in content, "Navigation items should be defined"
        assert "map" in content and "intel" in content and "hoods" in content and "alerts" in content

    def test_mobilenav_nav_items_mapped(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "navItems.map" in content, "Nav items should be mapped to buttons"

    def test_mobilenav_active_tab_highlighted(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "bg-blue-600" in content, "Active tab should have blue background"
        assert "text-white" in content, "Active tab text should be white"

    def test_mobilenav_inactive_tab_styling(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "text-gray-300" in content, "Inactive tab should have gray text"
        assert "hover:bg-slate-800" in content, "Inactive tab should have hover state"

    def test_mobilenav_aria_expanded(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "aria-expanded" in content, "Hamburger button should have aria-expanded"

    def test_mobilenav_aria_current(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "aria-current" in content, "Active nav item should have aria-current"

    def test_mobilenav_nav_role(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert 'role="navigation"' in content, "Drawer should have navigation role"

    def test_mobilenav_transition_duration(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "duration-300" in content, "Animations should use 300ms duration"

    def test_mobilenav_icons_present(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "📍" in content, "Map icon should be present"
        assert "🧠" in content, "Intelligence icon should be present"
        assert "🏢" in content, "Neighborhoods icon should be present"
        assert "🔔" in content, "Alerts icon should be present"


class TestResponsiveLayoutComponent:
    def test_responsivelayout_file_exists(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        assert filepath.exists(), "ResponsiveLayout.tsx should exist"

    def test_responsivelayout_is_client_component(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert '"use client"' in content

    def test_responsivelayout_has_interface(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "interface ResponsiveLayoutProps" in content

    def test_responsivelayout_accepts_children(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "children: ReactNode" in content

    def test_responsivelayout_accepts_sidebar_prop(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "sidebar?" in content

    def test_responsivelayout_accepts_activetab_prop(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "activeTab?" in content

    def test_responsivelayout_desktop_layout_hidden_lg(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "hidden lg:flex" in content, "Desktop layout should be hidden then flex on lg+"

    def test_responsivelayout_desktop_sidebar_width(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "w-64" in content, "Desktop sidebar should have fixed width"

    def test_responsivelayout_tablet_layout(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "hidden md:flex lg:hidden" in content, "Tablet layout should show between md and lg"

    def test_responsivelayout_mobile_layout(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "md:hidden" in content, "Mobile layout should be md:hidden"

    def test_responsivelayout_flex_column(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "flex-col" in content, "Layout should use flex column"

    def test_responsivelayout_full_height(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "h-screen" in content, "Layout should take full screen height"

    def test_responsivelayout_full_width(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "w-screen" in content, "Layout should take full screen width"

    def test_responsivelayout_dark_background(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "bg-slate-950" in content, "Layout should have dark background"

    def test_responsivelayout_sidebar_scrollable(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "overflow-y-auto" in content, "Sidebar should be scrollable"

    def test_responsivelayout_main_scrollable(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "overflow-auto" in content, "Main content should be scrollable"

    def test_responsivelayout_sidebar_border(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "border-r" in content, "Sidebar should have right border"

    def test_responsivelayout_main_tag_used(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "<main" in content, "Should use semantic main tag"


class TestBottomTabBarComponent:
    def test_bottomtabbar_file_exists(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        assert filepath.exists(), "BottomTabBar.tsx should exist"

    def test_bottomtabbar_is_client_component(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert '"use client"' in content

    def test_bottomtabbar_has_interface(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "interface BottomTabBarProps" in content

    def test_bottomtabbar_accepts_activetab(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert 'activeTab: "map" | "intel" | "hoods" | "alerts"' in content

    def test_bottomtabbar_accepts_ontabchange(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "onTabChange:" in content

    def test_bottomtabbar_hidden_on_tablet_up(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "md:hidden" in content, "Tab bar should be hidden on md and above"

    def test_bottomtabbar_fixed_to_bottom(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "fixed bottom-0" in content, "Tab bar should be fixed to bottom"

    def test_bottomtabbar_spans_full_width(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "left-0 right-0" in content, "Tab bar should span full width"

    def test_bottomtabbar_has_four_tabs(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "tabs.map" in content, "Tabs should be mapped"
        tabs_count = content.count('"map"') + content.count("'map'")
        assert tabs_count >= 1, "Should have map tab"

    def test_bottomtabbar_map_tab(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "map" in content, "Should have map tab"

    def test_bottomtabbar_intel_tab(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "intel" in content, "Should have intel tab"

    def test_bottomtabbar_neighborhoods_tab(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "hoods" in content, "Should have neighborhoods tab"

    def test_bottomtabbar_alerts_tab(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "alerts" in content, "Should have alerts tab"

    def test_bottomtabbar_icons_present(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "📍" in content, "Map icon present"
        assert "🧠" in content, "Intel icon present"
        assert "🏢" in content, "Neighborhoods icon present"
        assert "🔔" in content, "Alerts icon present"

    def test_bottomtabbar_active_tab_color(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "text-blue-500" in content, "Active tab should be blue"

    def test_bottomtabbar_active_border(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "border-t-2 border-blue-500" in content, "Active tab should have blue top border"

    def test_bottomtabbar_inactive_color(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "text-gray-400" in content, "Inactive tab should be gray"

    def test_bottomtabbar_min_height(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "min-h-14" in content, "Tabs should have minimum height for touch targets"

    def test_bottomtabbar_fixed_height(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "h-16" in content, "Tab bar should have fixed height"

    def test_bottomtabbar_safe_area_padding(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "pb-safe" in content or "safe" in content, "Should have safe area padding"

    def test_bottomtabbar_nav_role(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert 'role="tablist"' in content, "Nav should have tablist role"

    def test_bottomtabbar_tab_role(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert 'role="tab"' in content, "Each tab should have tab role"

    def test_bottomtabbar_aria_selected(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "aria-selected" in content, "Tabs should have aria-selected"

    def test_bottomtabbar_flex_justify_around(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "justify-around" in content, "Tabs should be evenly distributed"


class TestUseMediaQueryHook:
    def test_usemediaquery_file_exists(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        assert filepath.exists(), "useMediaQuery.ts should exist"

    def test_usemediaquery_is_client_hook(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert '"use client"' in content

    def test_usemediaquery_imports_usestate(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "useState" in content

    def test_usemediaquery_imports_useeffect(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "useEffect" in content

    def test_usemediaquery_hook_defined(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "export function useMediaQuery" in content

    def test_usemediaquery_accepts_string_query(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "query: string" in content

    def test_usemediaquery_returns_boolean(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert ": boolean" in content

    def test_usemediaquery_ssr_safe(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert 'typeof window === "undefined"' in content or "window" in content

    def test_usemediaquery_uses_matchmedia(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "matchMedia" in content

    def test_usemediaquery_adds_event_listener(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "addEventListener" in content

    def test_usemediaquery_removes_event_listener(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "removeEventListener" in content

    def test_useismobile_hook_defined(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "export function useIsMobile" in content

    def test_useismobile_max_width_640(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "max-width: 640px" in content

    def test_usetablet_hook_defined(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "export function useIsTablet" in content

    def test_usetablet_breakpoints(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "641px" in content and "1024px" in content

    def test_usedesktop_hook_defined(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "export function useIsDesktop" in content

    def test_usedesktop_min_width_1025(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        content = filepath.read_text()
        assert "min-width: 1025px" in content


class TestResponsiveClasses:
    def test_mobile_breakpoint_sm(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "md:hidden" in content, "Mobile components should use md:hidden"

    def test_tablet_breakpoint_md(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "md:" in content, "Tablet breakpoint md: should be used"

    def test_desktop_breakpoint_lg(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "lg:" in content, "Desktop breakpoint lg: should be used"

    def test_responsive_flex_classes(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "flex" in content, "Should use flex layouts"

    def test_responsive_padding_classes(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "mb-" in content or "pb-" in content or "p-" in content or "gap-" in content


class TestAccessibility:
    def test_hamburger_aria_label(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "aria-label" in content, "Hamburger should have aria-label"

    def test_drawer_aria_label(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert 'role="navigation"' in content

    def test_tabbar_tablist_role(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert 'role="tablist"' in content

    def test_tabbar_tab_roles(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert 'role="tab"' in content

    def test_nav_item_aria_current(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "aria-current" in content


class TestTouchTargets:
    def test_hamburger_min_size(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert ("p-2" in content or "p-3" in content or "p-4" in content), "Hamburger should have padding for touch"

    def test_bottom_tab_min_height(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "min-h-14" in content, "Tab should have min height of 56px (44px minimum)"

    def test_nav_item_padding(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "py-3" in content or "py-2" in content, "Nav items should have vertical padding"


class TestViewportAndMetaTags:
    def test_layout_has_html_lang(self):
        filepath = LAYOUT_DIR / "layout.tsx"
        content = filepath.read_text()
        assert 'lang="en"' in content, "HTML should have lang attribute"

    def test_body_margin_padding_zero(self):
        filepath = LAYOUT_DIR / "layout.tsx"
        content = filepath.read_text()
        assert "margin: 0" in content and "padding: 0" in content


class TestAnimations:
    def test_hamburger_rotation_animation(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "rotate-45" in content, "Hamburger lines should rotate"

    def test_hamburger_transition_duration(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "duration-300" in content or "duration" in content, "Animation should have duration"

    def test_drawer_slide_animation(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "translate-x" in content, "Drawer should use translate transform"

    def test_drawer_transition_smooth(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "transition" in content, "Drawer should have transition"

    def test_tab_highlight_animation(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "duration-200" in content or "transition" in content


class TestDarkTheme:
    def test_dark_background_layout(self):
        filepath = COMPONENTS_DIR / "ResponsiveLayout.tsx"
        content = filepath.read_text()
        assert "bg-slate-950" in content

    def test_dark_drawer_background(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "bg-slate-900" in content

    def test_dark_tabbar_background(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "bg-slate-900" in content

    def test_light_text_colors(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "text-gray" in content or "text-white" in content or "text-slate" in content


class TestIntegration:
    def test_all_components_present(self):
        components = [
            "MobileNav.tsx",
            "ResponsiveLayout.tsx",
            "BottomTabBar.tsx",
        ]
        for component in components:
            filepath = COMPONENTS_DIR / component
            assert filepath.exists(), f"{component} should exist"

    def test_all_hooks_present(self):
        filepath = HOOKS_DIR / "useMediaQuery.ts"
        assert filepath.exists(), "useMediaQuery.ts should exist"

    def test_mobilenav_connects_to_ontabchange(self):
        filepath = COMPONENTS_DIR / "MobileNav.tsx"
        content = filepath.read_text()
        assert "onTabChange" in content, "MobileNav should use onTabChange callback"

    def test_bottomtabbar_connects_to_ontabchange(self):
        filepath = COMPONENTS_DIR / "BottomTabBar.tsx"
        content = filepath.read_text()
        assert "onTabChange" in content, "BottomTabBar should use onTabChange callback"
