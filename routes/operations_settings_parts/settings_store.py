from __future__ import annotations

from flask import g

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso


DEFAULT_INSPECTION_ITEMS = [
    "Floors clean",
    "Bed made",
    "Trash removed",
    "Bathroom clean",
    "No prohibited items visible",
    "General room condition acceptable",
]


DEFAULT_PASS_SHARED_RULES_TEXT = "\n".join(
    [
        "Pass requests are due by Monday at 8:00 a.m.",
        "Passes are not automatic.",
        "Free time is handled as a normal Pass.",
        "Special Pass is for funerals or similar serious situations.",
        "Special Pass requests are reviewed as exceptions.",
    ]
)

DEFAULT_PASS_GH_RULES_TEXT = "\n".join(
    [
        "Pass requests are due by Monday at 8:00 a.m.",
        "Passes are not automatic.",
        "Free time is handled as a normal Pass.",
        "Special Pass is for funerals or similar serious situations.",
        "Special Pass requests are reviewed as exceptions.",
        "Special Pass does not depend on productive hours in the same way as a normal pass.",
    ]
)

DEFAULT_PASS_LEVEL_RULES = {
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


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _default_labels_text() -> str:
    return "\n".join(DEFAULT_INSPECTION_ITEMS)


def _default_pass_shared_rules_text() -> str:
    return DEFAULT_PASS_SHARED_RULES_TEXT


def _default_pass_gh_rules_text() -> str:
    return DEFAULT_PASS_GH_RULES_TEXT


def _default_pass_level_rules_text(key: str) -> str:
    return DEFAULT_PASS_LEVEL_RULES.get(key, "")


def _currency(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "—"


def _ensure_operations_settings_table() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS shelter_operation_settings (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL UNIQUE,
                rent_late_day_of_month INTEGER NOT NULL DEFAULT 6,
                rent_score_paid INTEGER NOT NULL DEFAULT 100,
                rent_score_partially_paid INTEGER NOT NULL DEFAULT 75,
                rent_score_paid_late INTEGER NOT NULL DEFAULT 75,
                rent_score_not_paid INTEGER NOT NULL DEFAULT 0,
                rent_score_exempt INTEGER NOT NULL DEFAULT 100,
                rent_carry_forward_enabled BOOLEAN NOT NULL DEFAULT TRUE,
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
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS shelter_operation_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter TEXT NOT NULL UNIQUE,
                rent_late_day_of_month INTEGER NOT NULL DEFAULT 6,
                rent_score_paid INTEGER NOT NULL DEFAULT 100,
                rent_score_partially_paid INTEGER NOT NULL DEFAULT 75,
                rent_score_paid_late INTEGER NOT NULL DEFAULT 75,
                rent_score_not_paid INTEGER NOT NULL DEFAULT 0,
                rent_score_exempt INTEGER NOT NULL DEFAULT 100,
                rent_carry_forward_enabled INTEGER NOT NULL DEFAULT 1,
                inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
                inspection_item_labels TEXT,
                inspection_scoring_enabled INTEGER NOT NULL DEFAULT 1,
                inspection_lookback_months INTEGER NOT NULL DEFAULT 9,
                inspection_include_current_open_month INTEGER NOT NULL DEFAULT 0,
                inspection_score_passed INTEGER NOT NULL DEFAULT 100,
                inspection_needs_attention_enabled INTEGER NOT NULL DEFAULT 0,
                inspection_score_needs_attention INTEGER NOT NULL DEFAULT 70,
                inspection_score_failed INTEGER NOT NULL DEFAULT 0,
                inspection_passing_threshold INTEGER NOT NULL DEFAULT 83,
                inspection_band_green_min INTEGER NOT NULL DEFAULT 83,
                inspection_band_yellow_min INTEGER NOT NULL DEFAULT 78,
                inspection_band_orange_min INTEGER NOT NULL DEFAULT 56,
                inspection_band_red_max INTEGER NOT NULL DEFAULT 55,
                employment_income_module_enabled INTEGER NOT NULL DEFAULT 1,
                employment_income_graduation_minimum REAL NOT NULL DEFAULT 1200.00,
                employment_income_band_green_min REAL NOT NULL DEFAULT 1200.00,
                employment_income_band_yellow_min REAL NOT NULL DEFAULT 1000.00,
                employment_income_band_orange_min REAL NOT NULL DEFAULT 700.00,
                employment_income_band_red_max REAL NOT NULL DEFAULT 699.99,
                income_weight_employment REAL NOT NULL DEFAULT 1.00,
                income_weight_ssi_ssdi_self REAL NOT NULL DEFAULT 1.00,
                income_weight_tanf REAL NOT NULL DEFAULT 1.00,
                income_weight_alimony REAL NOT NULL DEFAULT 0.50,
                income_weight_other_income REAL NOT NULL DEFAULT 0.25,
                income_weight_survivor_cutoff_months INTEGER NOT NULL DEFAULT 18,
                pass_deadline_weekday INTEGER NOT NULL DEFAULT 0,
                pass_deadline_hour INTEGER NOT NULL DEFAULT 8,
                pass_deadline_minute INTEGER NOT NULL DEFAULT 0,
                pass_late_submission_block_enabled INTEGER NOT NULL DEFAULT 1,
                pass_work_required_hours INTEGER NOT NULL DEFAULT 29,
                pass_productive_required_hours INTEGER NOT NULL DEFAULT 35,
                special_pass_bypass_hours_enabled INTEGER NOT NULL DEFAULT 1,
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
        )

    statements = [
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_late_day_of_month INTEGER DEFAULT 6",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_paid INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_partially_paid INTEGER DEFAULT 75",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_paid_late INTEGER DEFAULT 75",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_not_paid INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_exempt INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_carry_forward_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_default_item_status TEXT DEFAULT 'passed'",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_item_labels TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_scoring_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_lookback_months INTEGER DEFAULT 9",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_include_current_open_month BOOLEAN DEFAULT FALSE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_passed INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_needs_attention_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_needs_attention INTEGER DEFAULT 70",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_failed INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_passing_threshold INTEGER DEFAULT 83",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_green_min INTEGER DEFAULT 83",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_yellow_min INTEGER DEFAULT 78",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_orange_min INTEGER DEFAULT 56",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_red_max INTEGER DEFAULT 55",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_module_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_graduation_minimum DOUBLE PRECISION DEFAULT 1200.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_green_min DOUBLE PRECISION DEFAULT 1200.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_yellow_min DOUBLE PRECISION DEFAULT 1000.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_orange_min DOUBLE PRECISION DEFAULT 700.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_red_max DOUBLE PRECISION DEFAULT 699.99",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_employment DOUBLE PRECISION DEFAULT 1.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_ssi_ssdi_self DOUBLE PRECISION DEFAULT 1.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_tanf DOUBLE PRECISION DEFAULT 1.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_alimony DOUBLE PRECISION DEFAULT 0.50",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_other_income DOUBLE PRECISION DEFAULT 0.25",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_survivor_cutoff_months INTEGER DEFAULT 18",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_deadline_weekday INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_deadline_hour INTEGER DEFAULT 8",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_deadline_minute INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_late_submission_block_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_work_required_hours INTEGER DEFAULT 29",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_productive_required_hours INTEGER DEFAULT 35",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS special_pass_bypass_hours_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_shared_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_gh_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_level_1_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_level_2_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_level_3_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_level_4_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_gh_level_5_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_gh_level_6_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_gh_level_7_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS pass_gh_level_8_rules_text TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def _settings_row_for_shelter(shelter: str):
    _ensure_operations_settings_table()
    ph = _placeholder()
    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    if row:
        return row

    now = utcnow_iso()
    db_execute(
        (
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                inspection_default_item_status,
                inspection_item_labels,
                inspection_scoring_enabled,
                inspection_lookback_months,
                inspection_include_current_open_month,
                inspection_score_passed,
                inspection_needs_attention_enabled,
                inspection_score_needs_attention,
                inspection_score_failed,
                inspection_passing_threshold,
                inspection_band_green_min,
                inspection_band_yellow_min,
                inspection_band_orange_min,
                inspection_band_red_max,
                employment_income_module_enabled,
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max,
                income_weight_employment,
                income_weight_ssi_ssdi_self,
                income_weight_tanf,
                income_weight_alimony,
                income_weight_other_income,
                income_weight_survivor_cutoff_months,
                pass_deadline_weekday,
                pass_deadline_hour,
                pass_deadline_minute,
                pass_late_submission_block_enabled,
                pass_work_required_hours,
                pass_productive_required_hours,
                special_pass_bypass_hours_enabled,
                pass_shared_rules_text,
                pass_gh_rules_text,
                pass_level_1_rules_text,
                pass_level_2_rules_text,
                pass_level_3_rules_text,
                pass_level_4_rules_text,
                pass_gh_level_5_rules_text,
                pass_gh_level_6_rules_text,
                pass_gh_level_7_rules_text,
                pass_gh_level_8_rules_text,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                inspection_default_item_status,
                inspection_item_labels,
                inspection_scoring_enabled,
                inspection_lookback_months,
                inspection_include_current_open_month,
                inspection_score_passed,
                inspection_needs_attention_enabled,
                inspection_score_needs_attention,
                inspection_score_failed,
                inspection_passing_threshold,
                inspection_band_green_min,
                inspection_band_yellow_min,
                inspection_band_orange_min,
                inspection_band_red_max,
                employment_income_module_enabled,
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max,
                income_weight_employment,
                income_weight_ssi_ssdi_self,
                income_weight_tanf,
                income_weight_alimony,
                income_weight_other_income,
                income_weight_survivor_cutoff_months,
                pass_deadline_weekday,
                pass_deadline_hour,
                pass_deadline_minute,
                pass_late_submission_block_enabled,
                pass_work_required_hours,
                pass_productive_required_hours,
                special_pass_bypass_hours_enabled,
                pass_shared_rules_text,
                pass_gh_rules_text,
                pass_level_1_rules_text,
                pass_level_2_rules_text,
                pass_level_3_rules_text,
                pass_level_4_rules_text,
                pass_gh_level_5_rules_text,
                pass_gh_level_6_rules_text,
                pass_gh_level_7_rules_text,
                pass_gh_level_8_rules_text,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            shelter,
            6,
            100,
            75,
            75,
            0,
            100,
            True if g.get("db_kind") == "pg" else 1,
            "passed",
            _default_labels_text(),
            True if g.get("db_kind") == "pg" else 1,
            9,
            False if g.get("db_kind") == "pg" else 0,
            100,
            False if g.get("db_kind") == "pg" else 0,
            70,
            0,
            83,
            83,
            78,
            56,
            55,
            True if g.get("db_kind") == "pg" else 1,
            1200.00,
            1200.00,
            1000.00,
            700.00,
            699.99,
            1.00,
            1.00,
            1.00,
            0.50,
            0.25,
            18,
            0,
            8,
            0,
            True if g.get("db_kind") == "pg" else 1,
            29,
            35,
            True if g.get("db_kind") == "pg" else 1,
            _default_pass_shared_rules_text(),
            _default_pass_gh_rules_text(),
            _default_pass_level_rules_text("pass_level_1_rules_text"),
            _default_pass_level_rules_text("pass_level_2_rules_text"),
            _default_pass_level_rules_text("pass_level_3_rules_text"),
            _default_pass_level_rules_text("pass_level_4_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_5_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_6_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_7_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_8_rules_text"),
            now,
            now,
        ),
    )
    return db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
