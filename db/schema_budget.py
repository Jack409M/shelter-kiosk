"""
Budget and financial coaching schema.

Adds structured budgeting on top of the existing case management budget
session anchor without replacing the current resident_budget_sessions table.
"""

from __future__ import annotations

import contextlib

from core.db import db_execute

from .schema_helpers import create_table


def ensure_resident_budget_session_budget_columns(kind: str) -> None:
    if kind == "pg":
        statements = [
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS budget_month TEXT",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS projected_total_income DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS actual_total_income DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS projected_total_expenses DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS actual_total_expenses DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS projected_remaining_income DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS actual_remaining_income DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS last_month_savings DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS this_month_savings DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS house_contribution_amount DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS personal_amount DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS amount_left_for_abba DOUBLE PRECISION",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS client_signed_at TEXT",
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS staff_signed_at TEXT",
        ]
    else:
        statements = [
            "ALTER TABLE resident_budget_sessions ADD COLUMN budget_month TEXT",
            "ALTER TABLE resident_budget_sessions ADD COLUMN projected_total_income REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN actual_total_income REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN projected_total_expenses REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN actual_total_expenses REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN projected_remaining_income REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN actual_remaining_income REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN last_month_savings REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN this_month_savings REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN house_contribution_amount REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN personal_amount REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN amount_left_for_abba REAL",
            "ALTER TABLE resident_budget_sessions ADD COLUMN client_signed_at TEXT",
            "ALTER TABLE resident_budget_sessions ADD COLUMN staff_signed_at TEXT",
        ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_budget_line_items_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_session_id INTEGER NOT NULL,
            line_group TEXT,
            line_key TEXT,
            line_label TEXT NOT NULL,
            projected_amount REAL,
            actual_amount REAL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_resident_visible BOOLEAN NOT NULL DEFAULT TRUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (budget_session_id) REFERENCES resident_budget_sessions(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_line_items (
            id SERIAL PRIMARY KEY,
            budget_session_id INTEGER NOT NULL REFERENCES resident_budget_sessions(id) ON DELETE CASCADE,
            line_group TEXT,
            line_key TEXT,
            line_label TEXT NOT NULL,
            projected_amount DOUBLE PRECISION,
            actual_amount DOUBLE PRECISION,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_resident_visible BOOLEAN NOT NULL DEFAULT TRUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_budget_transactions_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_session_id INTEGER NOT NULL,
            resident_id INTEGER NOT NULL,
            enrollment_id INTEGER NOT NULL,
            line_item_id INTEGER,
            transaction_date TEXT NOT NULL,
            amount REAL NOT NULL,
            merchant_or_note TEXT,
            entered_by_role TEXT,
            entered_by_staff_user_id INTEGER,
            entered_by_resident_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            FOREIGN KEY (budget_session_id) REFERENCES resident_budget_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id),
            FOREIGN KEY (line_item_id) REFERENCES resident_budget_line_items(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_transactions (
            id SERIAL PRIMARY KEY,
            budget_session_id INTEGER NOT NULL REFERENCES resident_budget_sessions(id) ON DELETE CASCADE,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            line_item_id INTEGER REFERENCES resident_budget_line_items(id),
            transaction_date TEXT NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            merchant_or_note TEXT,
            entered_by_role TEXT,
            entered_by_staff_user_id INTEGER,
            entered_by_resident_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """,
    )


def ensure_budget_assistance_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_assistance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_session_id INTEGER NOT NULL UNIQUE,
            hud_client_rent_amount REAL,
            hud_paid_amount REAL,
            medicaid_or_district_clinic TEXT,
            medicaid_or_district_clinic_why_not TEXT,
            receives_food_stamps BOOLEAN,
            food_stamps_monthly_amount REAL,
            no_food_stamps_reason TEXT,
            outstanding_warrants BOOLEAN,
            outstanding_warrants_explanation TEXT,
            unpaid_tickets BOOLEAN,
            unpaid_tickets_explanation TEXT,
            other_assistance_received_last_year TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (budget_session_id) REFERENCES resident_budget_sessions(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_assistance (
            id SERIAL PRIMARY KEY,
            budget_session_id INTEGER NOT NULL UNIQUE REFERENCES resident_budget_sessions(id) ON DELETE CASCADE,
            hud_client_rent_amount DOUBLE PRECISION,
            hud_paid_amount DOUBLE PRECISION,
            medicaid_or_district_clinic TEXT,
            medicaid_or_district_clinic_why_not TEXT,
            receives_food_stamps BOOLEAN,
            food_stamps_monthly_amount DOUBLE PRECISION,
            no_food_stamps_reason TEXT,
            outstanding_warrants BOOLEAN,
            outstanding_warrants_explanation TEXT,
            unpaid_tickets BOOLEAN,
            unpaid_tickets_explanation TEXT,
            other_assistance_received_last_year TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_budget_goal_details_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_goal_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_session_id INTEGER NOT NULL,
            goal_type TEXT,
            goal_text TEXT NOT NULL,
            target_date TEXT,
            action_steps TEXT,
            support_people TEXT,
            barriers TEXT,
            rewards TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (budget_session_id) REFERENCES resident_budget_sessions(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_budget_goal_details (
            id SERIAL PRIMARY KEY,
            budget_session_id INTEGER NOT NULL REFERENCES resident_budget_sessions(id) ON DELETE CASCADE,
            goal_type TEXT,
            goal_text TEXT NOT NULL,
            target_date TEXT,
            action_steps TEXT,
            support_people TEXT,
            barriers TEXT,
            rewards TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_tables(kind: str) -> None:
    ensure_resident_budget_session_budget_columns(kind)
    ensure_budget_line_items_table(kind)
    ensure_budget_transactions_table(kind)
    ensure_budget_assistance_table(kind)
    ensure_budget_goal_details_table(kind)


def ensure_indexes() -> None:
    statements = [
        """
        CREATE INDEX IF NOT EXISTS resident_budget_line_items_session_idx
        ON resident_budget_line_items (budget_session_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_line_items_session_sort_idx
        ON resident_budget_line_items (budget_session_id, sort_order)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_transactions_session_idx
        ON resident_budget_transactions (budget_session_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_transactions_resident_idx
        ON resident_budget_transactions (resident_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_transactions_enrollment_idx
        ON resident_budget_transactions (enrollment_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_transactions_line_item_idx
        ON resident_budget_transactions (line_item_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_transactions_date_idx
        ON resident_budget_transactions (transaction_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_goal_details_session_idx
        ON resident_budget_goal_details (budget_session_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS resident_budget_goal_details_session_sort_idx
        ON resident_budget_goal_details (budget_session_id, sort_order)
        """,
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)
