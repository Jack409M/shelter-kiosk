from __future__ import annotations

from core.db import db_execute
from core.helpers import utcnow_iso

from .parsing import _merge_bool, _merge_int, _merge_text
from .settings_store import _default_labels_text, _placeholder


def save_inspection_settings(shelter: str, row: dict, form) -> None:
    now = utcnow_iso()
    is_pg = _placeholder() == "%s"
    default_inspection_items = _default_labels_text()

    inspection_default_item_status = _merge_text(
        "inspection_default_item_status",
        form,
        row.get("inspection_default_item_status"),
        "passed",
    ).lower()

    if inspection_default_item_status not in {"passed", "needs_attention", "failed"}:
        inspection_default_item_status = "passed"

    inspection_item_labels = (
        _merge_text(
            "inspection_item_labels",
            form,
            row.get("inspection_item_labels"),
            default_inspection_items,
        )
        or default_inspection_items
    )

    inspection_scoring_enabled = _merge_bool(
        "inspection_scoring_enabled",
        form,
        row.get("inspection_scoring_enabled"),
        True,
    )

    inspection_lookback_months = max(
        _merge_int(
            "inspection_lookback_months",
            form,
            row.get("inspection_lookback_months"),
            9,
        ),
        1,
    )

    inspection_include_current_open_month = _merge_bool(
        "inspection_include_current_open_month",
        form,
        row.get("inspection_include_current_open_month"),
        False,
    )

    inspection_score_passed = _merge_int(
        "inspection_score_passed",
        form,
        row.get("inspection_score_passed"),
        100,
    )

    inspection_needs_attention_enabled = _merge_bool(
        "inspection_needs_attention_enabled",
        form,
        row.get("inspection_needs_attention_enabled"),
        False,
    )

    inspection_score_needs_attention = _merge_int(
        "inspection_score_needs_attention",
        form,
        row.get("inspection_score_needs_attention"),
        70,
    )

    inspection_score_failed = _merge_int(
        "inspection_score_failed",
        form,
        row.get("inspection_score_failed"),
        0,
    )

    inspection_passing_threshold = _merge_int(
        "inspection_passing_threshold",
        form,
        row.get("inspection_passing_threshold"),
        83,
    )

    inspection_band_green_min = _merge_int(
        "inspection_band_green_min",
        form,
        row.get("inspection_band_green_min"),
        83,
    )

    inspection_band_yellow_min = _merge_int(
        "inspection_band_yellow_min",
        form,
        row.get("inspection_band_yellow_min"),
        78,
    )

    inspection_band_orange_min = _merge_int(
        "inspection_band_orange_min",
        form,
        row.get("inspection_band_orange_min"),
        56,
    )

    inspection_band_red_max = _merge_int(
        "inspection_band_red_max",
        form,
        row.get("inspection_band_red_max"),
        55,
    )

    # Normalize ranges
    if inspection_band_green_min < inspection_band_yellow_min:
        inspection_band_green_min = inspection_band_yellow_min + 1
    if inspection_band_yellow_min < inspection_band_orange_min:
        inspection_band_yellow_min = inspection_band_orange_min + 1
    if inspection_band_red_max >= inspection_band_orange_min:
        inspection_band_red_max = inspection_band_orange_min - 1

    db_execute(
        """
        UPDATE shelter_operation_settings
        SET inspection_default_item_status = %s,
            inspection_item_labels = %s,
            inspection_scoring_enabled = %s,
            inspection_lookback_months = %s,
            inspection_include_current_open_month = %s,
            inspection_score_passed = %s,
            inspection_needs_attention_enabled = %s,
            inspection_score_needs_attention = %s,
            inspection_score_failed = %s,
            inspection_passing_threshold = %s,
            inspection_band_green_min = %s,
            inspection_band_yellow_min = %s,
            inspection_band_orange_min = %s,
            inspection_band_red_max = %s,
            updated_at = %s
        WHERE LOWER(COALESCE(shelter, '')) = %s
        """
        if is_pg
        else """
        UPDATE shelter_operation_settings
        SET inspection_default_item_status = ?,
            inspection_item_labels = ?,
            inspection_scoring_enabled = ?,
            inspection_lookback_months = ?,
            inspection_include_current_open_month = ?,
            inspection_score_passed = ?,
            inspection_needs_attention_enabled = ?,
            inspection_score_needs_attention = ?,
            inspection_score_failed = ?,
            inspection_passing_threshold = ?,
            inspection_band_green_min = ?,
            inspection_band_yellow_min = ?,
            inspection_band_orange_min = ?,
            inspection_band_red_max = ?,
            updated_at = ?
        WHERE LOWER(COALESCE(shelter, '')) = ?
        """,
        (
            inspection_default_item_status,
            inspection_item_labels,
            inspection_scoring_enabled if is_pg else (1 if inspection_scoring_enabled else 0),
            inspection_lookback_months,
            inspection_include_current_open_month if is_pg else (1 if inspection_include_current_open_month else 0),
            inspection_score_passed,
            inspection_needs_attention_enabled if is_pg else (1 if inspection_needs_attention_enabled else 0),
            inspection_score_needs_attention,
            inspection_score_failed,
            inspection_passing_threshold,
            inspection_band_green_min,
            inspection_band_yellow_min,
            inspection_band_orange_min,
            inspection_band_red_max,
            now,
            shelter,
        ),
    )
