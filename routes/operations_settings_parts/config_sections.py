from __future__ import annotations

from .settings_store import _currency, _default_labels_text


def _configuration_sections() -> list[dict]:
    return [
        {
            "key": "rent_rules",
            "title": "Rent Rules",
            "summary": "Late logic and rent scoring values.",
        },
        {
            "key": "inspection_defaults",
            "title": "Inspection Defaults",
            "summary": "Checklist defaults and standard item setup.",
        },
        {
            "key": "inspection_stability_scoring",
            "title": "Inspection Stability Scoring",
            "summary": "Scoring behavior and lookback rules.",
        },
        {
            "key": "inspection_color_bands",
            "title": "Inspection Color Bands",
            "summary": "Green, yellow, orange, and red thresholds.",
        },
        {
            "key": "employment_income_graduation_settings",
            "title": "Employment Income Graduation Settings",
            "summary": "Module status and graduation minimum.",
        },
        {
            "key": "employment_income_color_bands",
            "title": "Employment Income Color Bands",
            "summary": "Income thresholds by color band.",
        },
        {
            "key": "income_stability_weighting",
            "title": "Income Stability Weighting",
            "summary": "Reliability weighting for income sources.",
        },
        {
            "key": "kiosk_activity_categories",
            "title": "Kiosk Activity Categories",
            "summary": "Checkout categories and hour counting rules.",
        },
        {
            "key": "employment_income_guidance",
            "title": "Employment Income Guidance",
            "summary": "Read only graduation guidance for this shelter.",
        },
    ]


def _configuration_section_map() -> dict[str, dict]:
    return {section["key"]: section for section in _configuration_sections()}


def _base_section_context(shelter: str, current_section: str) -> dict:
    sections = _configuration_sections()
    section_map = _configuration_section_map()
    current_section_meta = section_map.get(current_section)

    return {
        "shelter": shelter,
        "default_inspection_items": _default_labels_text(),
        "currency": _currency,
        "sections": sections,
        "current_section": current_section,
        "current_section_meta": current_section_meta,
    }
