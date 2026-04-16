from __future__ import annotations

from flask import g, session

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import assert_enrollment_belongs_to_resident

from .dates import _month_label, _today_chicago
from .utils import _float_value, _placeholder


def _active_residents_for_shelter(shelter: str):
    ph = _placeholder()
    return db_fetchall(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND is_active = {("TRUE" if g.get("db_kind") == "pg" else "1")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )


def _active_rent_config_for_resident(resident_id: int, shelter: str):
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT *
        FROM resident_rent_configs
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND COALESCE(effective_end_date, '') = ''
        ORDER BY effective_start_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    return dict(row) if row else None

# ... (rest unchanged until insert)

def _insert_rent_ledger_entry(
    resident_id: int,
    enrollment_id: int | None = None,
    shelter: str = "",
    entry_date: str = "",
    entry_type: str = "",
    description: str | None = None,
    debit_amount: float = 0.0,
    credit_amount: float = 0.0,
    related_sheet_id: int | None = None,
    related_sheet_entry_id: int | None = None,
    related_month_year: int | None = None,
    related_month_month: int | None = None,
    source_code: str | None = None,
    source_reference: str | None = None,
    notes: str | None = None,
) -> int | None:
    # Enforce integrity when enrollment_id is provided
    if enrollment_id is not None:
        assert_enrollment_belongs_to_resident(
            enrollment_id=enrollment_id,
            resident_id=resident_id,
            shelter=shelter or None,
        )

    now = utcnow_iso()
    balance_before = _ledger_balance_before_entry(resident_id)
    balance_after = round(
        balance_before + _float_value(debit_amount) - _float_value(credit_amount), 2
    )

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            """
            INSERT INTO resident_rent_ledger_entries (
                resident_id,
                enrollment_id,
                shelter,
                entry_date,
                entry_type,
                description,
                debit_amount,
                credit_amount,
                balance_after,
                related_sheet_id,
                related_sheet_entry_id,
                related_month_year,
                related_month_month,
                source_code,
                source_reference,
                notes,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                resident_id,
                enrollment_id,
                shelter,
                entry_date,
                entry_type,
                description,
                _float_value(debit_amount),
                _float_value(credit_amount),
                balance_after,
                related_sheet_id,
                related_sheet_entry_id,
                related_month_year,
                related_month_month,
                source_code,
                source_reference,
                notes,
                session.get("staff_user_id"),
                now,
                now,
            ),
        )
        return row["id"] if row else None

    db_execute(
        """
        INSERT INTO resident_rent_ledger_entries (
            resident_id,
            enrollment_id,
            shelter,
            entry_date,
            entry_type,
            description,
            debit_amount,
            credit_amount,
            balance_after,
            related_sheet_id,
            related_sheet_entry_id,
            related_month_year,
            related_month_month,
            source_code,
            source_reference,
            notes,
            created_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resident_id,
            enrollment_id,
            shelter,
            entry_date,
            entry_type,
            description,
            _float_value(debit_amount),
            _float_value(credit_amount),
            balance_after,
            related_sheet_id,
            related_sheet_entry_id,
            related_month_year,
            related_month_month,
            source_code,
            source_reference,
            notes,
            session.get("staff_user_id"),
            now,
            now,
        ),
    )

    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT id
        FROM resident_rent_ledger_entries
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )
    return row["id"] if row else None
