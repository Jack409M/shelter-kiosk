from __future__ import annotations

from typing import Any, Final

from flask import g

from core.db import DbRow, db_execute, db_fetchone
from core.helpers import utcnow_iso

DEFAULT_INSPECTION_ITEMS: Final[list[str]] = [
    "Floors clean",
    "Bed made",
    "Trash removed",
    "Bathroom clean",
    "No prohibited items visible",
    "General room condition acceptable",
]

DEFAULT_PASS_SHARED_RULES_TEXT: Final[str] = "\n".join(
    [
        "Pass requests are due by Monday at 8:00 a.m.",
        "Passes are not automatic.",
        "Free time is handled as a normal Pass.",
        "Special Pass is for funerals or similar serious situations.",
        "Special Pass requests are reviewed as exceptions.",
    ]
)

DEFAULT_PASS_GH_RULES_TEXT: Final[str] = "\n".join(
    [
        "Pass requests are due by Monday at 8:00 a.m.",
        "Passes are not automatic.",
        "Free time is handled as a normal Pass.",
        "Special Pass is for funerals or similar serious situations.",
        "Special Pass requests are reviewed as exceptions.",
        "Special Pass does not depend on productive hours in the same way as a normal pass.",
    ]
)

DEFAULT_PASS_LEVEL_RULES: Final[dict[str, str]] = {
    "pass_level_1_rules_text": "\n".join(
        [
            "Level 1 residents do not get friend or family passes.",
            "Passes are not given until completion of RAD unless special circumstances exist.",
        ]
    ),
    "pass_level_2_rules_text": "\n".join(
        [
            "Level 2 residents may have one weekly pass up to 4 hours.",
            "Normal passes require obligations to be met first.",
            "Normal passes require 29 work hours and 35 productive hours before approval.",
        ]
    ),
    "pass_level_3_rules_text": "\n".join(
        [
            "Level 3 residents may request normal passes within shelter rules.",
            "Normal passes still depend on rules, behavior, and required hours.",
        ]
    ),
    "pass_level_4_rules_text": "\n".join(
        [
            "Level 4 residents may request normal passes.",
            "Level 4 residents may have one overnight pass per month with approval.",
        ]
    ),
    "pass_gh_level_5_rules_text": "\n".join(
        [
            "No overnight passes during the first 30 days unless an exception is approved.",
            "Level 5 may have one overnight pass per month after the first 30 days.",
        ]
    ),
    "pass_gh_level_6_rules_text": "Level 6 may have two overnight passes per month.",
    "pass_gh_level_7_rules_text": "Level 7 may have three overnight passes per month.",
    "pass_gh_level_8_rules_text": "Level 8 may have three passes per month with permission.",
}

_SETTINGS_TABLE_NAME: Final[str] = "shelter_operation_settings"

_CREATE_TABLE_SQL: Final[str] = f"""
CREATE TABLE IF NOT EXISTS {_SETTINGS_TABLE_NAME} (
    id SERIAL PRIMARY KEY,
    shelter TEXT NOT NULL UNIQUE,
    rent_late_day_of_month INTEGER NOT NULL DEFAULT 6,
    rent_score_paid INTEGER NOT NULL DEFAULT 100,
    rent_score_partially_paid INTEGER NOT NULL DEFAULT 75,
    rent_score_paid_late INTEGER NOT NULL DEFAULT 75,
    rent_score_not_paid INTEGER NOT NULL DEFAULT 0,
    rent_score_exempt INTEGER NOT NULL DEFAULT 100,
    rent_carry_forward_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    hh_rent_amount DOUBLE PRECISION NOT NULL DEFAULT 150.00,
    hh_rent_due_day INTEGER NOT NULL DEFAULT 1,
    hh_rent_late_day INTEGER NOT NULL DEFAULT 5,
    hh_rent_late_fee_per_day DOUBLE PRECISION NOT NULL DEFAULT 1.00,
    hh_late_arrangement_required BOOLEAN NOT NULL DEFAULT TRUE,
    hh_payment_methods_text TEXT,
    hh_payment_accepted_by_roles_text TEXT,
    hh_work_off_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    hh_work_off_hourly_rate DOUBLE PRECISION NOT NULL DEFAULT 10.00,
    hh_work_off_required_hours INTEGER NOT NULL DEFAULT 15,
    hh_work_off_deadline_day INTEGER NOT NULL DEFAULT 10,
    hh_work_off_location_text TEXT,
    hh_work_off_notes_text TEXT,
    gh_rent_due_day INTEGER NOT NULL DEFAULT 1,
    gh_rent_late_fee_per_day DOUBLE PRECISION NOT NULL DEFAULT 1.00,
    gh_late_arrangement_required BOOLEAN NOT NULL DEFAULT TRUE,
    gh_level_5_one_bedroom_rent DOUBLE PRECISION NOT NULL DEFAULT 250.00,
    gh_level_5_two_bedroom_rent DOUBLE PRECISION NOT NULL DEFAULT 300.00,
    gh_level_5_townhome_rent DOUBLE PRECISION NOT NULL DEFAULT 300.00,
    gh_level_8_sliding_scale_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    gh_level_8_sliding_scale_basis_text TEXT,
    gh_level_8_first_increase_amount DOUBLE PRECISION NOT NULL DEFAULT 50.00,
    gh_level_8_second_increase_amount DOUBLE PRECISION NOT NULL DEFAULT 50.00,
    gh_level_8_increase_schedule_text TEXT,
    inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
    inspection_item_labels TEXT,
    inspection_scoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    inspection_lookback_months INTEGER NOT NULL DEFAULT 9,
    inspection_include_current_open_month BOOLEAN NOT NULL DEFAULT FALSE,
    inspection_score_passed INTEGER NOT NULL DEFAULT 100,
    inspection_needs_attention_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    inspection_score_needs_attention INTEGER NOT NULL DEFAULT 70,
    inspection_score_failed INTEGER NOT NULL DEFAULT 0,
    inspection_passing_threshold INTEGER NOT NULL DEFAULT 83,
    inspection_band_green_min INTEGER NOT NULL DEFAULT 83,
    inspection_band_yellow_min INTEGER NOT NULL DEFAULT 78,
    inspection_band_orange_min INTEGER NOT NULL DEFAULT 56,
    inspection_band_red_max INTEGER NOT NULL DEFAULT 55,
    employment_income_module_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    employment_income_graduation_minimum DOUBLE PRECISION NOT NULL DEFAULT 1200.00,
    employment_income_band_green_min DOUBLE PRECISION NOT NULL DEFAULT 1200.00,
    employment_income_band_yellow_min DOUBLE PRECISION NOT NULL DEFAULT 1000.00,
    employment_income_band_orange_min DOUBLE PRECISION NOT NULL DEFAULT 700.00,
    employment_income_band_red_max DOUBLE PRECISION NOT NULL DEFAULT 699.99,
    income_weight_employment DOUBLE PRECISION NOT NULL DEFAULT 1.00,
    income_weight_ssi_ssdi_self DOUBLE PRECISION NOT NULL DEFAULT 1.00,
    income_weight_tanf DOUBLE PRECISION NOT NULL DEFAULT 1.00,
    income_weight_alimony DOUBLE PRECISION NOT NULL DEFAULT 0.50,
    income_weight_other_income DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    income_weight_survivor_cutoff_months INTEGER NOT NULL DEFAULT 18,
    pass_deadline_weekday INTEGER NOT NULL DEFAULT 0,
    pass_deadline_hour INTEGER NOT NULL DEFAULT 8,
    pass_deadline_minute INTEGER NOT NULL DEFAULT 0,
    pass_late_submission_block_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    pass_work_required_hours INTEGER NOT NULL DEFAULT 29,
    pass_productive_required_hours INTEGER NOT NULL DEFAULT 35,
    special_pass_bypass_hours_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    pass_shared_rules_text TEXT,
    pass_gh_rules_text TEXT,
    pass_level_1_rules_text TEXT,
    pass_level_2_rules_text TEXT,
    pass_level_3_rules_text TEXT,
    pass_level_4_rules_text TEXT,
    pass_gh_level_5_rules_text TEXT,
    pass_gh_level_6_rules_text TEXT,
    pass_gh_level_7_rules_text TEXT,
    pass_gh_level_8_rules_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_REQUIRED_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("rent_late_day_of_month", "INTEGER DEFAULT 6"),
    ("rent_score_paid", "INTEGER DEFAULT 100"),
    ("rent_score_partially_paid", "INTEGER DEFAULT 75"),
    ("rent_score_paid_late", "INTEGER DEFAULT 75"),
    ("rent_score_not_paid", "INTEGER DEFAULT 0"),
    ("rent_score_exempt", "INTEGER DEFAULT 100"),
    ("rent_carry_forward_enabled", "BOOLEAN DEFAULT TRUE"),
    ("hh_rent_amount", "DOUBLE PRECISION DEFAULT 150.00"),
    ("hh_rent_due_day", "INTEGER DEFAULT 1"),
    ("hh_rent_late_day", "INTEGER DEFAULT 5"),
    ("hh_rent_late_fee_per_day", "DOUBLE PRECISION DEFAULT 1.00"),
    ("hh_late_arrangement_required", "BOOLEAN DEFAULT TRUE"),
    ("hh_payment_methods_text", "TEXT"),
    ("hh_payment_accepted_by_roles_text", "TEXT"),
    ("hh_work_off_enabled", "BOOLEAN DEFAULT TRUE"),
    ("hh_work_off_hourly_rate", "DOUBLE PRECISION DEFAULT 10.00"),
    ("hh_work_off_required_hours", "INTEGER DEFAULT 15"),
    ("hh_work_off_deadline_day", "INTEGER DEFAULT 10"),
    ("hh_work_off_location_text", "TEXT"),
    ("hh_work_off_notes_text", "TEXT"),
    ("gh_rent_due_day", "INTEGER DEFAULT 1"),
    ("gh_rent_late_fee_per_day", "DOUBLE PRECISION DEFAULT 1.00"),
    ("gh_late_arrangement_required", "BOOLEAN DEFAULT TRUE"),
    ("gh_level_5_one_bedroom_rent", "DOUBLE PRECISION DEFAULT 250.00"),
    ("gh_level_5_two_bedroom_rent", "DOUBLE PRECISION DEFAULT 300.00"),
    ("gh_level_5_townhome_rent", "DOUBLE PRECISION DEFAULT 300.00"),
    ("gh_level_8_sliding_scale_enabled", "BOOLEAN DEFAULT TRUE"),
    ("gh_level_8_sliding_scale_basis_text", "TEXT"),
    ("gh_level_8_first_increase_amount", "DOUBLE PRECISION DEFAULT 50.00"),
    ("gh_level_8_second_increase_amount", "DOUBLE PRECISION DEFAULT 50.00"),
    ("gh_level_8_increase_schedule_text", "TEXT"),
    ("inspection_default_item_status", "TEXT DEFAULT 'passed'"),
    ("inspection_item_labels", "TEXT"),
    ("inspection_scoring_enabled", "BOOLEAN DEFAULT TRUE"),
    ("inspection_lookback_months", "INTEGER DEFAULT 9"),
    ("inspection_include_current_open_month", "BOOLEAN DEFAULT FALSE"),
    ("inspection_score_passed", "INTEGER DEFAULT 100"),
    ("inspection_needs_attention_enabled", "BOOLEAN DEFAULT FALSE"),
    ("inspection_score_needs_attention", "INTEGER DEFAULT 70"),
    ("inspection_score_failed", "INTEGER DEFAULT 0"),
    ("inspection_passing_threshold", "INTEGER DEFAULT 83"),
    ("inspection_band_green_min", "INTEGER DEFAULT 83"),
    ("inspection_band_yellow_min", "INTEGER DEFAULT 78"),
    ("inspection_band_orange_min", "INTEGER DEFAULT 56"),
    ("inspection_band_red_max", "INTEGER DEFAULT 55"),
    ("employment_income_module_enabled", "BOOLEAN DEFAULT TRUE"),
    ("employment_income_graduation_minimum", "DOUBLE PRECISION DEFAULT 1200.00"),
    ("employment_income_band_green_min", "DOUBLE PRECISION DEFAULT 1200.00"),
    ("employment_income_band_yellow_min", "DOUBLE PRECISION DEFAULT 1000.00"),
    ("employment_income_band_orange_min", "DOUBLE PRECISION DEFAULT 700.00"),
    ("employment_income_band_red_max", "DOUBLE PRECISION DEFAULT 699.99"),
    ("income_weight_employment", "DOUBLE PRECISION DEFAULT 1.00"),
    ("income_weight_ssi_ssdi_self", "DOUBLE PRECISION DEFAULT 1.00"),
    ("income_weight_tanf", "DOUBLE PRECISION DEFAULT 1.00"),
    ("income_weight_alimony", "DOUBLE PRECISION DEFAULT 0.50"),
    ("income_weight_other_income", "DOUBLE PRECISION DEFAULT 0.25"),
    ("income_weight_survivor_cutoff_months", "INTEGER DEFAULT 18"),
    ("pass_deadline_weekday", "INTEGER DEFAULT 0"),
    ("pass_deadline_hour", "INTEGER DEFAULT 8"),
    ("pass_deadline_minute", "INTEGER DEFAULT 0"),
    ("pass_late_submission_block_enabled", "BOOLEAN DEFAULT TRUE"),
    ("pass_work_required_hours", "INTEGER DEFAULT 29"),
    ("pass_productive_required_hours", "INTEGER DEFAULT 35"),
    ("special_pass_bypass_hours_enabled", "BOOLEAN DEFAULT TRUE"),
    ("pass_shared_rules_text", "TEXT"),
    ("pass_gh_rules_text", "TEXT"),
    ("pass_level_1_rules_text", "TEXT"),
    ("pass_level_2_rules_text", "TEXT"),
    ("pass_level_3_rules_text", "TEXT"),
    ("pass_level_4_rules_text", "TEXT"),
    ("pass_gh_level_5_rules_text", "TEXT"),
    ("pass_gh_level_6_rules_text", "TEXT"),
    ("pass_gh_level_7_rules_text", "TEXT"),
    ("pass_gh_level_8_rules_text", "TEXT"),
    ("created_at", "TEXT"),
    ("updated_at", "TEXT"),
)

_DEFAULT_INSERT_COLUMNS: Final[tuple[str, ...]] = (
    "shelter",
    "rent_late_day_of_month",
    "rent_score_paid",
    "rent_score_partially_paid",
    "rent_score_paid_late",
    "rent_score_not_paid",
    "rent_score_exempt",
    "rent_carry_forward_enabled",
    "hh_rent_amount",
    "hh_rent_due_day",
    "hh_rent_late_day",
    "hh_rent_late_fee_per_day",
    "hh_late_arrangement_required",
    "hh_payment_methods_text",
    "hh_payment_accepted_by_roles_text",
    "hh_work_off_enabled",
    "hh_work_off_hourly_rate",
    "hh_work_off_required_hours",
    "hh_work_off_deadline_day",
    "hh_work_off_location_text",
    "hh_work_off_notes_text",
    "gh_rent_due_day",
    "gh_rent_late_fee_per_day",
    "gh_late_arrangement_required",
    "gh_level_5_one_bedroom_rent",
    "gh_level_5_two_bedroom_rent",
    "gh_level_5_townhome_rent",
    "gh_level_8_sliding_scale_enabled",
    "gh_level_8_sliding_scale_basis_text",
    "gh_level_8_first_increase_amount",
    "gh_level_8_second_increase_amount",
    "gh_level_8_increase_schedule_text",
    "inspection_default_item_status",
    "inspection_item_labels",
    "inspection_scoring_enabled",
    "inspection_lookback_months",
    "inspection_include_current_open_month",
    "inspection_score_passed",
    "inspection_needs_attention_enabled",
    "inspection_score_needs_attention",
    "inspection_score_failed",
    "inspection_passing_threshold",
    "inspection_band_green_min",
    "inspection_band_yellow_min",
    "inspection_band_orange_min",
    "inspection_band_red_max",
    "employment_income_module_enabled",
    "employment_income_graduation_minimum",
    "employment_income_band_green_min",
    "employment_income_band_yellow_min",
    "employment_income_band_orange_min",
    "employment_income_band_red_max",
    "income_weight_employment",
    "income_weight_ssi_ssdi_self",
    "income_weight_tanf",
    "income_weight_alimony",
    "income_weight_other_income",
    "income_weight_survivor_cutoff_months",
    "pass_deadline_weekday",
    "pass_deadline_hour",
    "pass_deadline_minute",
    "pass_late_submission_block_enabled",
    "pass_work_required_hours",
    "pass_productive_required_hours",
    "special_pass_bypass_hours_enabled",
    "pass_shared_rules_text",
    "pass_gh_rules_text",
    "pass_level_1_rules_text",
    "pass_level_2_rules_text",
    "pass_level_3_rules_text",
    "pass_level_4_rules_text",
    "pass_gh_level_5_rules_text",
    "pass_gh_level_6_rules_text",
    "pass_gh_level_7_rules_text",
    "pass_gh_level_8_rules_text",
    "created_at",
    "updated_at",
)


def _placeholder() -> str:
    return "%s"


def _default_labels_text() -> str:
    return "\n".join(DEFAULT_INSPECTION_ITEMS)


def _default_pass_shared_rules_text() -> str:
    return DEFAULT_PASS_SHARED_RULES_TEXT


def _default_pass_gh_rules_text() -> str:
    return DEFAULT_PASS_GH_RULES_TEXT


def _default_pass_level_rules_text(key: str) -> str:
    return DEFAULT_PASS_LEVEL_RULES.get(key, "")


def _currency(value: Any) -> str:
    if value in (None, ""):
        return "—"

    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _require_postgres() -> None:
    db_kind = str(g.get("db_kind") or "").strip().lower()
    if db_kind and db_kind != "pg":
        raise RuntimeError(
            "operations settings store received a non Postgres database kind, "
            f"which is unsupported: {db_kind!r}"
        )


def _normalize_shelter_value(shelter: str) -> str:
    return shelter.strip().lower()


def _column_exists(column_name: str) -> bool:
    row = db_fetchone(
        """
        SELECT 1 AS present
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (_SETTINGS_TABLE_NAME, column_name),
    )
    return row is not None


def _ensure_column(column_name: str, column_definition: str) -> None:
    if _column_exists(column_name):
        return

    db_execute(f"ALTER TABLE {_SETTINGS_TABLE_NAME} ADD COLUMN {column_name} {column_definition}")


def _ensure_operations_settings_table() -> None:
    _require_postgres()
    db_execute(_CREATE_TABLE_SQL)

    for column_name, column_definition in _REQUIRED_COLUMNS:
        _ensure_column(column_name, column_definition)


def _default_settings_values(shelter: str) -> dict[str, Any]:
    normalized_shelter = _normalize_shelter_value(shelter)
    now = utcnow_iso()

    return {
        "shelter": normalized_shelter,
        "rent_late_day_of_month": 6,
        "rent_score_paid": 100,
        "rent_score_partially_paid": 75,
        "rent_score_paid_late": 75,
        "rent_score_not_paid": 0,
        "rent_score_exempt": 100,
        "rent_carry_forward_enabled": True,
        "hh_rent_amount": 150.00,
        "hh_rent_due_day": 1,
        "hh_rent_late_day": 5,
        "hh_rent_late_fee_per_day": 1.00,
        "hh_late_arrangement_required": True,
        "hh_payment_methods_text": "Money order\nCashier check",
        "hh_payment_accepted_by_roles_text": "Case managers only",
        "hh_work_off_enabled": True,
        "hh_work_off_hourly_rate": 10.00,
        "hh_work_off_required_hours": 15,
        "hh_work_off_deadline_day": 10,
        "hh_work_off_location_text": "Thrift City",
        "hh_work_off_notes_text": (
            "If unemployed, resident may work off rent at 10 dollars per hour. "
            "Hours must be completed by the 10th unless arrangements are made in advance."
        ),
        "gh_rent_due_day": 1,
        "gh_rent_late_fee_per_day": 1.00,
        "gh_late_arrangement_required": True,
        "gh_level_5_one_bedroom_rent": 250.00,
        "gh_level_5_two_bedroom_rent": 300.00,
        "gh_level_5_townhome_rent": 300.00,
        "gh_level_8_sliding_scale_enabled": True,
        "gh_level_8_sliding_scale_basis_text": (
            "Sliding scale based on income, household size, and accepted expenses."
        ),
        "gh_level_8_first_increase_amount": 50.00,
        "gh_level_8_second_increase_amount": 50.00,
        "gh_level_8_increase_schedule_text": (
            "Increase a minimum of 50 the month after graduation, then another 50 one year later."
        ),
        "inspection_default_item_status": "passed",
        "inspection_item_labels": _default_labels_text(),
        "inspection_scoring_enabled": True,
        "inspection_lookback_months": 9,
        "inspection_include_current_open_month": False,
        "inspection_score_passed": 100,
        "inspection_needs_attention_enabled": False,
        "inspection_score_needs_attention": 70,
        "inspection_score_failed": 0,
        "inspection_passing_threshold": 83,
        "inspection_band_green_min": 83,
        "inspection_band_yellow_min": 78,
        "inspection_band_orange_min": 56,
        "inspection_band_red_max": 55,
        "employment_income_module_enabled": True,
        "employment_income_graduation_minimum": 1200.00,
        "employment_income_band_green_min": 1200.00,
        "employment_income_band_yellow_min": 1000.00,
        "employment_income_band_orange_min": 700.00,
        "employment_income_band_red_max": 699.99,
        "income_weight_employment": 1.00,
        "income_weight_ssi_ssdi_self": 1.00,
        "income_weight_tanf": 1.00,
        "income_weight_alimony": 0.50,
        "income_weight_other_income": 0.25,
        "income_weight_survivor_cutoff_months": 18,
        "pass_deadline_weekday": 0,
        "pass_deadline_hour": 8,
        "pass_deadline_minute": 0,
        "pass_late_submission_block_enabled": True,
        "pass_work_required_hours": 29,
        "pass_productive_required_hours": 35,
        "special_pass_bypass_hours_enabled": True,
        "pass_shared_rules_text": _default_pass_shared_rules_text(),
        "pass_gh_rules_text": _default_pass_gh_rules_text(),
        "pass_level_1_rules_text": _default_pass_level_rules_text("pass_level_1_rules_text"),
        "pass_level_2_rules_text": _default_pass_level_rules_text("pass_level_2_rules_text"),
        "pass_level_3_rules_text": _default_pass_level_rules_text("pass_level_3_rules_text"),
        "pass_level_4_rules_text": _default_pass_level_rules_text("pass_level_4_rules_text"),
        "pass_gh_level_5_rules_text": _default_pass_level_rules_text("pass_gh_level_5_rules_text"),
        "pass_gh_level_6_rules_text": _default_pass_level_rules_text("pass_gh_level_6_rules_text"),
        "pass_gh_level_7_rules_text": _default_pass_level_rules_text("pass_gh_level_7_rules_text"),
        "pass_gh_level_8_rules_text": _default_pass_level_rules_text("pass_gh_level_8_rules_text"),
        "created_at": now,
        "updated_at": now,
    }


def _insert_default_settings_row(shelter: str) -> None:
    values = _default_settings_values(shelter)
    columns_sql = ", ".join(_DEFAULT_INSERT_COLUMNS)
    placeholders_sql = ", ".join(["%s"] * len(_DEFAULT_INSERT_COLUMNS))
    insert_values = tuple(values[column_name] for column_name in _DEFAULT_INSERT_COLUMNS)

    db_execute(
        f"""
        INSERT INTO {_SETTINGS_TABLE_NAME} ({columns_sql})
        VALUES ({placeholders_sql})
        ON CONFLICT (shelter) DO NOTHING
        """,
        insert_values,
    )


def _fetch_settings_row(shelter: str) -> DbRow | None:
    normalized_shelter = _normalize_shelter_value(shelter)
    return db_fetchone(
        f"""
        SELECT *
        FROM {_SETTINGS_TABLE_NAME}
        WHERE LOWER(COALESCE(shelter, '')) = %s
        LIMIT 1
        """,
        (normalized_shelter,),
    )


def _settings_row_for_shelter(shelter: str) -> DbRow:
    normalized_shelter = _normalize_shelter_value(shelter)
    if not normalized_shelter:
        raise ValueError("shelter is required")

    _ensure_operations_settings_table()

    row = _fetch_settings_row(normalized_shelter)
    if row is not None:
        return row

    _insert_default_settings_row(normalized_shelter)

    row = _fetch_settings_row(normalized_shelter)
    if row is None:
        raise RuntimeError(
            "failed to load shelter operation settings row after insert "
            f"for shelter={normalized_shelter!r}"
        )

    return row
