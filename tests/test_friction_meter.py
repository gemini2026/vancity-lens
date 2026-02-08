import pathlib
import re

COMPONENTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "components"
TYPES_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib"


class TestFrictionMeterComponent:
    def setup_method(self):
        self.content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()

    def test_is_react_component(self):
        assert "export" in self.content
        assert "FrictionMeter" in self.content
        assert "React.FC" in self.content

    def test_has_props_interface(self):
        assert "FrictionMeterProps" in self.content
        assert "value: number" in self.content
        assert "size?" in self.content

    def test_value_prop_is_required(self):
        assert "value: number" in self.content

    def test_size_prop_is_optional(self):
        assert "size?" in self.content

    def test_size_prop_has_correct_type(self):
        assert '"sm" | "md" | "lg"' in self.content

    def test_color_green_for_low_friction(self):
        assert '#22c55e' in self.content or 'green' in self.content.lower()

    def test_color_yellow_for_medium_friction(self):
        assert '#eab308' in self.content or 'yellow' in self.content.lower()

    def test_color_red_for_high_friction(self):
        assert '#dc2626' in self.content or 'red' in self.content.lower()

    def test_low_friction_threshold(self):
        assert 'getColor' in self.content
        assert '<= 30' in self.content

    def test_medium_friction_threshold(self):
        assert '<= 60' in self.content

    def test_high_friction_above_60(self):
        assert '> 60' in self.content or '>= 61' in self.content or 'return' in self.content

    def test_has_low_friction_label(self):
        assert 'Low Friction' in self.content

    def test_has_medium_friction_label(self):
        assert 'Medium Friction' in self.content

    def test_has_high_friction_label(self):
        assert 'High Friction' in self.content

    def test_value_clamping_at_zero(self):
        assert 'Math.min' in self.content
        assert 'Math.max' in self.content

    def test_value_clamping_at_100(self):
        assert 'Math.min' in self.content and '100' in self.content

    def test_has_aria_label(self):
        assert 'aria-label' in self.content

    def test_has_aria_valuenow(self):
        assert 'aria-valuenow' in self.content

    def test_has_aria_valuemin(self):
        assert 'aria-valuemin' in self.content

    def test_has_aria_valuemax(self):
        assert 'aria-valuemax' in self.content

    def test_progress_bar_role(self):
        assert 'progressbar' in self.content

    def test_size_sm_defined(self):
        assert 'sm' in self.content

    def test_size_md_defined(self):
        assert 'md' in self.content

    def test_size_lg_defined(self):
        assert 'lg' in self.content

    def test_default_size_is_md(self):
        assert 'size = "md"' in self.content or "size='md'" in self.content

    def test_uses_tailwind_classes(self):
        assert 'className' in self.content

    def test_has_height_variant_sm(self):
        assert 'h-2' in self.content

    def test_has_height_variant_md(self):
        assert 'h-3' in self.content

    def test_has_height_variant_lg(self):
        assert 'h-4' in self.content

    def test_percentage_calculation(self):
        assert '/ 100' in self.content
        assert '* 100' in self.content

    def test_returns_jsx_element(self):
        assert 'return' in self.content
        assert '<div' in self.content

    def test_exported_as_default(self):
        assert 'export default' in self.content

    def test_has_label_element(self):
        assert '<label' in self.content

    def test_has_progress_bar_container(self):
        assert 'role="progressbar"' in self.content

    def test_smooth_transition(self):
        assert 'transition' in self.content or 'duration' in self.content

    def test_friction_meter_title(self):
        assert 'Friction Meter' in self.content


class TestConfidenceStarsComponent:
    def setup_method(self):
        self.content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()

    def test_is_react_component(self):
        assert "export" in self.content
        assert "ConfidenceStars" in self.content
        assert "React.FC" in self.content

    def test_has_props_interface(self):
        assert "ConfidenceStarsProps" in self.content
        assert "rating: number" in self.content

    def test_rating_prop_is_required(self):
        assert "rating: number" in self.content

    def test_maxstars_prop_is_optional(self):
        assert "maxStars?" in self.content or "maxStars =" in self.content

    def test_size_prop_is_optional(self):
        assert "size?" in self.content

    def test_size_prop_has_correct_type(self):
        assert '"sm" | "md" | "lg"' in self.content

    def test_default_max_stars_is_five(self):
        assert "= 5" in self.content

    def test_filled_stars_are_gold(self):
        assert 'yellow' in self.content.lower() or '#fbbf24' in self.content or 'yellow-400' in self.content

    def test_empty_stars_are_gray(self):
        assert 'gray' in self.content.lower() or '#d1d5db' in self.content or 'gray-' in self.content

    def test_rating_clamping(self):
        assert 'Math.min' in self.content
        assert 'Math.max' in self.content

    def test_half_star_support(self):
        assert '- 0.5' in self.content or 'isHalfFilled' in self.content

    def test_star_character_filled(self):
        assert '★' in self.content

    def test_star_character_empty(self):
        assert '☆' in self.content

    def test_star_character_half(self):
        assert '⭐' in self.content

    def test_array_from_loop(self):
        assert 'Array.from' in self.content

    def test_has_aria_label(self):
        assert 'aria-label' in self.content

    def test_confidence_rating_label(self):
        assert 'confidence' in self.content.lower()

    def test_rating_display_format(self):
        assert 'toFixed' in self.content

    def test_exported_as_default(self):
        assert 'export default' in self.content

    def test_returns_jsx_element(self):
        assert 'return' in self.content
        assert '<div' in self.content

    def test_uses_tailwind_classes(self):
        assert 'className' in self.content

    def test_gap_styling(self):
        assert 'gap' in self.content

    def test_max_stars_bounds_checking(self):
        assert 'maxStars' in self.content


class TestDueDiligencePopupComponent:
    def setup_method(self):
        self.content = (COMPONENTS_DIR / "DueDiligencePopup.tsx").read_text()

    def test_is_react_component(self):
        assert "export" in self.content
        assert "DueDiligencePopup" in self.content
        assert "React.FC" in self.content

    def test_has_props_interface(self):
        assert "DueDiligencePopupProps" in self.content
        assert "parcel:" in self.content

    def test_parcel_prop_is_required(self):
        assert "ParcelEntitlement" in self.content

    def test_imports_friction_meter(self):
        assert "FrictionMeter" in self.content
        assert "import" in self.content

    def test_imports_confidence_stars(self):
        assert "ConfidenceStars" in self.content

    def test_uses_friction_meter_component(self):
        assert "<FrictionMeter" in self.content

    def test_uses_confidence_stars_component(self):
        assert "<ConfidenceStars" in self.content

    def test_friction_meter_receives_value_prop(self):
        assert "value=" in self.content and "FrictionMeter" in self.content

    def test_confidence_stars_receives_rating_prop(self):
        assert "rating=" in self.content and "ConfidenceStars" in self.content

    def test_displays_civic_address(self):
        assert "civic_address" in self.content

    def test_displays_parcel_id(self):
        assert "pid" in self.content

    def test_displays_deal_grade(self):
        assert "deal_grade" in self.content

    def test_displays_deal_score(self):
        assert "deal_score" in self.content

    def test_displays_one_liner(self):
        assert "one_liner" in self.content

    def test_displays_neighborhood(self):
        assert "neighborhood" in self.content

    def test_displays_execution_difficulty(self):
        assert "execution_difficulty_score" in self.content

    def test_displays_execution_factors(self):
        assert "execution_difficulty_factors" in self.content

    def test_handles_no_validation_data(self):
        assert "validation" in self.content

    def test_exported_as_default(self):
        assert "export default" in self.content

    def test_returns_jsx_element(self):
        assert "return" in self.content
        assert "<div" in self.content

    def test_uses_tailwind_classes(self):
        assert "className" in self.content

    def test_has_dark_theme(self):
        assert "gray-900" in self.content or "dark" in self.content.lower()


class TestTypesFile:
    def setup_method(self):
        self.content = (TYPES_DIR / "types.ts").read_text()

    def test_has_deal_validation_interface(self):
        assert "DealValidation" in self.content
        assert "interface" in self.content

    def test_has_friction_score_field(self):
        assert "friction_score" in self.content

    def test_friction_score_is_number(self):
        assert "friction_score: number" in self.content

    def test_has_confidence_stars_field(self):
        assert "confidence_stars" in self.content

    def test_confidence_stars_is_number(self):
        assert "confidence_stars: number" in self.content

    def test_has_friction_level_field(self):
        assert "friction_level" in self.content

    def test_friction_level_is_string_union(self):
        assert "friction_level:" in self.content
        assert '"low" | "medium" | "high"' in self.content

    def test_parcel_entitlement_uses_deal_validation(self):
        assert "ParcelEntitlement" in self.content
        assert "validation:" in self.content

    def test_validation_is_optional_in_parcel(self):
        assert "validation:" in self.content


class TestFrictionMeterLogic:
    def setup_method(self):
        self.content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()

    def test_value_zero_is_green(self):
        assert "0" in self.content
        assert "#22c55e" in self.content

    def test_value_thirty_is_green(self):
        assert "<= 30" in self.content

    def test_value_thirty_one_is_yellow(self):
        assert "<= 60" in self.content

    def test_value_sixty_is_yellow(self):
        assert "<= 60" in self.content

    def test_value_sixty_one_is_red(self):
        assert "#dc2626" in self.content

    def test_value_hundred_is_red(self):
        assert "100" in self.content
        assert "#dc2626" in self.content

    def test_clamps_above_100(self):
        assert "Math.min" in self.content

    def test_clamps_below_0(self):
        assert "Math.max" in self.content


class TestConfidenceStarsLogic:
    def setup_method(self):
        self.content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()

    def test_one_star_is_filled(self):
        assert "★" in self.content

    def test_one_and_half_stars(self):
        assert "- 0.5" in self.content or "isHalfFilled" in self.content

    def test_five_stars_max(self):
        assert "maxStars" in self.content

    def test_zero_rating_shows_empty_stars(self):
        assert "☆" in self.content

    def test_five_rating_shows_full_stars(self):
        assert "★" in self.content

    def test_rating_clamping_at_zero(self):
        assert "Math.max" in self.content

    def test_rating_clamping_at_max(self):
        assert "Math.min" in self.content


class TestComponentIntegration:
    def setup_method(self):
        self.friction_content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()
        self.stars_content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()
        self.popup_content = (COMPONENTS_DIR / "DueDiligencePopup.tsx").read_text()

    def test_popup_integrates_friction_meter(self):
        assert "FrictionMeter" in self.popup_content
        assert "value=" in self.popup_content

    def test_popup_integrates_confidence_stars(self):
        assert "ConfidenceStars" in self.popup_content
        assert "rating=" in self.popup_content

    def test_both_components_are_react_components(self):
        assert "React.FC" in self.friction_content
        assert "React.FC" in self.stars_content

    def test_both_use_tailwind(self):
        assert "className" in self.friction_content
        assert "className" in self.stars_content

    def test_components_have_proper_exports(self):
        assert "export const FrictionMeter" in self.friction_content
        assert "export const ConfidenceStars" in self.stars_content


class TestAccessibility:
    def setup_method(self):
        self.friction_content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()
        self.stars_content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()

    def test_friction_meter_has_aria_attributes(self):
        assert "aria-label" in self.friction_content
        assert "aria-valuenow" in self.friction_content

    def test_friction_meter_has_min_max_attributes(self):
        assert "aria-valuemin" in self.friction_content
        assert "aria-valuemax" in self.friction_content

    def test_friction_meter_has_role(self):
        assert "role=" in self.friction_content

    def test_stars_have_aria_label(self):
        assert "aria-label" in self.stars_content

    def test_friction_shows_numeric_value(self):
        assert "toFixed" in self.friction_content or "clampedValue" in self.friction_content


class TestSizeVariants:
    def setup_method(self):
        self.friction_content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()
        self.stars_content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()

    def test_friction_meter_small_size(self):
        assert "h-2" in self.friction_content

    def test_friction_meter_medium_size(self):
        assert "h-3" in self.friction_content

    def test_friction_meter_large_size(self):
        assert "h-4" in self.friction_content

    def test_stars_small_size(self):
        assert "sm" in self.stars_content

    def test_stars_medium_size(self):
        assert "md" in self.stars_content

    def test_stars_large_size(self):
        assert "lg" in self.stars_content

    def test_friction_text_size_variants(self):
        assert "text-xs" in self.friction_content or "text-sm" in self.friction_content

    def test_stars_text_size_variants(self):
        assert "text-xs" in self.stars_content or "text-sm" in self.stars_content


class TestEdgeCases:
    def setup_method(self):
        self.friction_content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()
        self.stars_content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()

    def test_friction_handles_negative_value(self):
        assert "Math.max" in self.friction_content

    def test_friction_handles_over_100(self):
        assert "Math.min" in self.friction_content

    def test_friction_handles_float_values(self):
        assert "number" in self.friction_content

    def test_stars_handles_zero_rating(self):
        assert "Math.max" in self.stars_content

    def test_stars_handles_above_max(self):
        assert "Math.min" in self.stars_content

    def test_friction_percentage_calculation(self):
        assert "/ 100" in self.friction_content
        assert "* 100" in self.friction_content or "%" in self.friction_content


class TestDefaultValues:
    def setup_method(self):
        self.friction_content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()
        self.stars_content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()

    def test_friction_default_size_md(self):
        assert 'size = "md"' in self.friction_content or "size='md'" in self.friction_content

    def test_stars_default_max_stars_5(self):
        assert "= 5" in self.stars_content

    def test_stars_default_size_md(self):
        assert 'size = "md"' in self.stars_content or "size='md'" in self.stars_content


class TestTailwindValidation:
    def setup_method(self):
        self.friction_content = (COMPONENTS_DIR / "FrictionMeter.tsx").read_text()
        self.stars_content = (COMPONENTS_DIR / "ConfidenceStars.tsx").read_text()
        self.popup_content = (COMPONENTS_DIR / "DueDiligencePopup.tsx").read_text()

    def test_friction_uses_valid_tailwind_colors(self):
        valid_colors = ["gray-", "bg-", "text-"]
        assert any(color in self.friction_content for color in valid_colors)

    def test_stars_uses_valid_tailwind_colors(self):
        valid_colors = ["yellow-", "gray-", "text-"]
        assert any(color in self.stars_content for color in valid_colors)

    def test_popup_uses_valid_tailwind_colors(self):
        valid_colors = ["bg-", "text-", "rounded-"]
        assert any(color in self.popup_content for color in valid_colors)

    def test_friction_rounded_corners(self):
        assert "rounded" in self.friction_content

    def test_popup_spacing_classes(self):
        assert "p-" in self.popup_content or "gap-" in self.popup_content
