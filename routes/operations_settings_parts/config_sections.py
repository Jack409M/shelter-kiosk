from __future__ import annotations

from .employment_guidance import _employment_income_guidance
from .kiosk_categories import _load_kiosk_activity_categories_for_shelter
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


def _build_settings_section_context(shelter: str, row, current_section: str) -> dict:
    sections = _configuration_sections()
    section_map = _configuration_section_map()
    current_section_meta = section_map.get(current_section)

    guidance = _employment_income_guidance(shelter) if current_section == "employment_income_guidance" else None
    kiosk_activity_categories = (
        _load_kiosk_activity_categories_for_shelter(shelter)
        if current_section == "kiosk_activity_categories"
        else None
    )

    return {
        "shelter": shelter,
        "settings": row,
        "default_inspection_items": _default_labels_text(),
        "employment_guidance": guidance,
        "currency": _currency,
        "kiosk_activity_categories": kiosk_activity_categories,
        "sections": sections,
        "current_section": current_section,
        "current_section_meta": current_section_meta,
    }
