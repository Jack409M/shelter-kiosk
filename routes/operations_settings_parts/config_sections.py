from __future__ import annotations

from core.kiosk_activity_categories import LOCKED_PARENT_ACTIVITY_DEFINITIONS

from .settings_store import _currency, _default_labels_text


def _kiosk_child_option_sections() -> list[dict]:
    sections: list[dict] = []
    for activity_key, activity_label in LOCKED_PARENT_ACTIVITY_DEFINITIONS.items():
        sections.append(
            {
                "key": f"kiosk_child_options__{activity_key}",
                "title": f"{activity_label} Options",
                "summary": f"Child dropdown choices shown when {activity_label} is selected.",
                "type": "form",
                "parent_key": "kiosk_settings",
                "activity_key": activity_key,
                "activity_label": activity_label,
            }
        )
    return sections


def _configuration_sections() -> list[dict]:
    return [
        {
            "key": "rent_rules",
            "title": "Rent Rules",
            "summary": "Late logic and rent scoring values.",
            "type": "form",
        },
        {
            "key": "inspection_settings",
            "title": "Inspection Settings",
            "summary": "Defaults, scoring behavior, and color bands.",
            "type": "group",
            "children": [
                "inspection_defaults",
                "inspection_stability_scoring",
                "inspection_color_bands",
            ],
        },
        {
            "key": "employment_income_settings",
            "title": "Employment and Income Settings",
            "summary": "Graduation settings, color bands, weighting, and guidance.",
            "type": "group",
            "children": [
                "employment_income_graduation_settings",
                "employment_income_color_bands",
                "income_stability_weighting",
                "employment_income_guidance",
            ],
        },
        {
            "key": "pass_settings",
            "title": "Pass Settings",
            "summary": "Deadlines, required hours, and resident pass rule text.",
            "type": "group",
            "children": [
                "pass_general_rules",
                "pass_shared_house_rules",
                "pass_gratitude_house_rules",
            ],
        },
        {
            "key": "kiosk_settings",
            "title": "Kiosk Settings",
            "summary": "Checkout categories and kiosk child options.",
            "type": "group",
            "children": [
                "kiosk_activity_categories",
                *[section["key"] for section in _kiosk_child_option_sections()],
            ],
        },
    ]


def _configuration_leaf_sections() -> list[dict]:
    return [
        {
            "key": "rent_rules",
            "title": "Rent Rules",
            "summary": "Late logic and rent scoring values.",
            "type": "form",
        },
        {
            "key": "inspection_defaults",
            "title": "Inspection Defaults",
            "summary": "Checklist defaults and standard item setup.",
            "type": "form",
            "parent_key": "inspection_settings",
        },
        {
            "key": "inspection_stability_scoring",
            "title": "Inspection Stability Scoring",
            "summary": "Scoring behavior and lookback rules.",
            "type": "form",
            "parent_key": "inspection_settings",
        },
        {
            "key": "inspection_color_bands",
            "title": "Inspection Color Bands",
            "summary": "Green, yellow, orange, and red thresholds.",
            "type": "form",
            "parent_key": "inspection_settings",
        },
        {
            "key": "employment_income_graduation_settings",
            "title": "Employment Income Graduation Settings",
            "summary": "Module status and graduation minimum.",
            "type": "form",
            "parent_key": "employment_income_settings",
        },
        {
            "key": "employment_income_color_bands",
            "title": "Employment Income Color Bands",
            "summary": "Income thresholds by color band.",
            "type": "form",
            "parent_key": "employment_income_settings",
        },
        {
            "key": "income_stability_weighting",
            "title": "Income Stability Weighting",
            "summary": "Reliability weighting for income sources.",
            "type": "form",
            "parent_key": "employment_income_settings",
        },
        {
            "key": "employment_income_guidance",
            "title": "Employment Income Guidance",
            "summary": "Read only graduation guidance for this shelter.",
            "type": "read_only",
            "parent_key": "employment_income_settings",
        },
        {
            "key": "pass_general_rules",
            "title": "Pass General Rules",
            "summary": "Deadline timing, required hours, and special pass handling.",
            "type": "form",
            "parent_key": "pass_settings",
        },
        {
            "key": "pass_shared_house_rules",
            "title": "Abba and Haven Pass Rules",
            "summary": "Shared pass rule text for Abba House and Haven House.",
            "type": "form",
            "parent_key": "pass_settings",
        },
        {
            "key": "pass_gratitude_house_rules",
            "title": "Gratitude House Pass Rules",
            "summary": "Gratitude House rule text by level.",
            "type": "form",
            "parent_key": "pass_settings",
        },
        {
            "key": "kiosk_activity_categories",
            "title": "Kiosk Activity Categories",
            "summary": "Top level checkout categories and hour counting rules.",
            "type": "form",
            "parent_key": "kiosk_settings",
        },
        *_kiosk_child_option_sections(),
    ]


def _configuration_section_map() -> dict[str, dict]:
    section_map: dict[str, dict] = {}

    for section in _configuration_sections():
        section_map[section["key"]] = section

    for section in _configuration_leaf_sections():
        section_map[section["key"]] = section

    return section_map


def _child_sections_for_parent(parent_key: str) -> list[dict]:
    return [
        section
        for section in _configuration_leaf_sections()
        if section.get("parent_key") == parent_key
    ]


def _base_section_context(shelter: str, current_section: str) -> dict:
    sections = _configuration_sections()
    section_map = _configuration_section_map()
    current_section_meta = section_map.get(current_section)
    current_section_children = _child_sections_for_parent(current_section)

    return {
        "shelter": shelter,
        "default_inspection_items": _default_labels_text(),
        "currency": _currency,
        "sections": sections,
        "section_map": section_map,
        "current_section": current_section,
        "current_section_meta": current_section_meta,
        "current_section_children": current_section_children,
    }
