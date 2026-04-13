from __future__ import annotations

from flask import g

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso

from .utils import _placeholder


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
                hh_rent_amount REAL NOT NULL DEFAULT 150.00,
                hh_rent_due_day INTEGER NOT NULL DEFAULT 1,
                hh_rent_late_day INTEGER NOT NULL DEFAULT 5,
                hh_rent_late_fee_per_day REAL NOT NULL DEFAULT 1.00,
                hh_late_arrangement_required INTEGER NOT NULL DEFAULT 1,
                hh_payment_methods_text TEXT,
                hh_payment_accepted_by_roles_text TEXT,
                hh_work_off_enabled INTEGER NOT NULL DEFAULT 1,
                hh_work_off_hourly_rate REAL NOT NULL DEFAULT 10.00,
                hh_work_off_required_hours INTEGER NOT NULL DEFAULT 15,
                hh_work_off_deadline_day INTEGER NOT NULL DEFAULT 10,
                hh_work_off_location_text TEXT,
                hh_work_off_notes_text TEXT,
                gh_rent_due_day INTEGER NOT NULL DEFAULT 1,
                gh_rent_late_fee_per_day REAL NOT NULL DEFAULT 1.00,
                gh_late_arrangement_required INTEGER NOT NULL DEFAULT 1,
                gh_level_5_one_bedroom_rent REAL NOT NULL DEFAULT 250.00,
                gh_level_5_two_bedroom_rent REAL NOT NULL DEFAULT 300.00,
                gh_level_5_townhome_rent REAL NOT NULL DEFAULT 300.00,
                gh_level_8_sliding_scale_enabled INTEGER NOT NULL DEFAULT 1,
                gh_level_8_sliding_scale_basis_text TEXT,
                gh_level_8_first_increase_amount REAL NOT NULL DEFAULT 50.00,
                gh_level_8_second_increase_amount REAL NOT NULL DEFAULT 50.00,
                gh_level_8_increase_schedule_text TEXT,
                inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
                inspection_item_labels TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def _load_settings(shelter: str) -> dict:
    _ensure_operations_settings_table()
    ph = _placeholder()

    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    if row:
        return dict(row)

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
                hh_rent_amount,
                hh_rent_due_day,
                hh_rent_late_day,
                hh_rent_late_fee_per_day,
                hh_late_arrangement_required,
                hh_payment_methods_text,
                hh_payment_accepted_by_roles_text,
                hh_work_off_enabled,
                hh_work_off_hourly_rate,
                hh_work_off_required_hours,
                hh_work_off_deadline_day,
                hh_work_off_location_text,
                hh_work_off_notes_text,
                gh_rent_due_day,
                gh_rent_late_fee_per_day,
                gh_late_arrangement_required,
                gh_level_5_one_bedroom_rent,
                gh_level_5_two_bedroom_rent,
                gh_level_5_townhome_rent,
                gh_level_8_sliding_scale_enabled,
                gh_level_8_sliding_scale_basis_text,
                gh_level_8_first_increase_amount,
                gh_level_8_second_increase_amount,
                gh_level_8_increase_schedule_text,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else """
            INSERT INTO shelter_operation_settings (
                shelter,
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                hh_rent_amount,
                hh_rent_due_day,
                hh_rent_late_day,
                hh_rent_late_fee_per_day,
                hh_late_arrangement_required,
                hh_payment_methods_text,
                hh_payment_accepted_by_roles_text,
                hh_work_off_enabled,
                hh_work_off_hourly_rate,
                hh_work_off_required_hours,
                hh_work_off_deadline_day,
                hh_work_off_location_text,
                hh_work_off_notes_text,
                gh_rent_due_day,
                gh_rent_late_fee_per_day,
                gh_late_arrangement_required,
                gh_level_5_one_bedroom_rent,
                gh_level_5_two_bedroom_rent,
                gh_level_5_townhome_rent,
                gh_level_8_sliding_scale_enabled,
                gh_level_8_sliding_scale_basis_text,
                gh_level_8_first_increase_amount,
                gh_level_8_second_increase_amount,
                gh_level_8_increase_schedule_text,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            150.00,
            1,
            5,
            1.00,
            True if g.get("db_kind") == "pg" else 1,
            "Money order\nCashier check",
            "Case managers only",
            True if g.get("db_kind") == "pg" else 1,
            10.00,
            15,
            10,
            "Thrift City",
            "If unemployed, resident may work off rent at 10 dollars per hour. Hours must be completed by the 10th unless arrangements are made in advance.",
            1,
            1.00,
            True if g.get("db_kind") == "pg" else 1,
            250.00,
            300.00,
            300.00,
            True if g.get("db_kind") == "pg" else 1,
            "Sliding scale based on income, household size, and accepted expenses.",
            50.00,
            50.00,
            "Increase a minimum of 50 the month after graduation, then another 50 one year later.",
            "passed",
            None,
            now,
            now,
        ),
    )

    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    return dict(row) if row else {}
