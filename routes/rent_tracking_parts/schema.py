from __future__ import annotations

from core.db import db_execute


def _ensure_tables() -> None:
    from .settings import _ensure_operations_settings_table

    _ensure_operations_settings_table()

    from flask import g

    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_configs (
                id SERIAL PRIMARY KEY,
                resident_id INTEGER NOT NULL REFERENCES residents(id),
                shelter TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                monthly_rent NUMERIC(10,2) NOT NULL DEFAULT 0,
                is_exempt BOOLEAN NOT NULL DEFAULT FALSE,
                effective_start_date TEXT NOT NULL,
                effective_end_date TEXT,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheets (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL,
                rent_year INTEGER NOT NULL,
                rent_month INTEGER NOT NULL,
                generated_on TEXT NOT NULL,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (shelter, rent_year, rent_month)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheet_entries (
                id SERIAL PRIMARY KEY,
                sheet_id INTEGER NOT NULL REFERENCES resident_rent_sheets(id),
                resident_id INTEGER NOT NULL REFERENCES residents(id),
                shelter_snapshot TEXT NOT NULL,
                resident_name_snapshot TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                prior_balance NUMERIC(10,2) NOT NULL DEFAULT 0,
                current_charge NUMERIC(10,2) NOT NULL DEFAULT 0,
                total_due NUMERIC(10,2) NOT NULL DEFAULT 0,
                amount_paid NUMERIC(10,2) NOT NULL DEFAULT 0,
                remaining_balance NUMERIC(10,2) NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Not Paid',
                compliance_score INTEGER NOT NULL DEFAULT 0,
                paid_date TEXT,
                notes TEXT,
                occupancy_start_date TEXT,
                occupancy_end_date TEXT,
                occupied_days INTEGER DEFAULT 0,
                month_day_count INTEGER DEFAULT 30,
                base_monthly_rent DOUBLE PRECISION DEFAULT 0,
                prorated_charge DOUBLE PRECISION DEFAULT 0,
                late_fee_charge DOUBLE PRECISION DEFAULT 0,
                manual_adjustment DOUBLE PRECISION DEFAULT 0,
                approved_late_arrangement BOOLEAN DEFAULT FALSE,
                calculation_notes TEXT,
                updated_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (sheet_id, resident_id)
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                monthly_rent REAL NOT NULL DEFAULT 0,
                is_exempt INTEGER NOT NULL DEFAULT 0,
                effective_start_date TEXT NOT NULL,
                effective_end_date TEXT,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (resident_id) REFERENCES residents(id)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter TEXT NOT NULL,
                rent_year INTEGER NOT NULL,
                rent_month INTEGER NOT NULL,
                generated_on TEXT NOT NULL,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (shelter, rent_year, rent_month)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheet_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_id INTEGER NOT NULL,
                resident_id INTEGER NOT NULL,
                shelter_snapshot TEXT NOT NULL,
                resident_name_snapshot TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                prior_balance REAL NOT NULL DEFAULT 0,
                current_charge REAL NOT NULL DEFAULT 0,
                total_due REAL NOT NULL DEFAULT 0,
                amount_paid REAL NOT NULL DEFAULT 0,
                remaining_balance REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Not Paid',
                compliance_score INTEGER NOT NULL DEFAULT 0,
                paid_date TEXT,
                notes TEXT,
                occupancy_start_date TEXT,
                occupancy_end_date TEXT,
                occupied_days INTEGER DEFAULT 0,
                month_day_count INTEGER DEFAULT 30,
                base_monthly_rent REAL DEFAULT 0,
                prorated_charge REAL DEFAULT 0,
                late_fee_charge REAL DEFAULT 0,
                manual_adjustment REAL DEFAULT 0,
                approved_late_arrangement INTEGER DEFAULT 0,
                calculation_notes TEXT,
                updated_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (sheet_id) REFERENCES resident_rent_sheets(id),
                FOREIGN KEY (resident_id) REFERENCES residents(id),
                UNIQUE (sheet_id, resident_id)
            )
            """
        )

    alter_statements = [
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS occupancy_start_date TEXT",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS occupancy_end_date TEXT",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS occupied_days INTEGER DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS month_day_count INTEGER DEFAULT 30",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS base_monthly_rent DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS prorated_charge DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS late_fee_charge DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS manual_adjustment DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS approved_late_arrangement BOOLEAN DEFAULT FALSE",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS calculation_notes TEXT",
    ]
    for statement in alter_statements:
        try:
            db_execute(statement)
        except Exception:
            pass
