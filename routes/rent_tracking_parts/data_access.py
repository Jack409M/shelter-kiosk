from __future__ import annotations

from flask import g, session

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

from .dates import _month_label, _today_chicago
from .utils import _float_value, _placeholder


def _active_residents_for_shelter(shelter: str):
    ph = _placeholder()
    return db_fetchall(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND is_active = {('TRUE' if g.get('db_kind') == 'pg' else '1')}
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


def _ensure_default_rent_config(resident_id: int, shelter: str) -> dict:
    config = _active_rent_config_for_resident(resident_id, shelter)
    if config:
        return config

    now = utcnow_iso()
    today = _today_chicago().date().isoformat()

    db_execute(
        (
            """
            INSERT INTO resident_rent_configs (
                resident_id,
                shelter,
                level_snapshot,
                apartment_number_snapshot,
                apartment_size_snapshot,
                monthly_rent,
                is_exempt,
                effective_start_date,
                effective_end_date,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO resident_rent_configs (
                resident_id,
                shelter,
                level_snapshot,
                apartment_number_snapshot,
                apartment_size_snapshot,
                monthly_rent,
                is_exempt,
                effective_start_date,
                effective_end_date,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            resident_id,
            shelter,
            None,
            None,
            None,
            0.0,
            False if g.get("db_kind") == "pg" else 0,
            today,
            None,
            session.get("staff_user_id"),
            now,
            now,
        ),
    )

    return _active_rent_config_for_resident(resident_id, shelter) or {}


def _program_enrollment_for_month(resident_id: int, shelter: str, rent_year: int, rent_month: int) -> dict | None:
    from .dates import _month_start_end

    month_start, month_end = _month_start_end(rent_year, rent_month)
    ph = _placeholder()

    row = db_fetchone(
        f"""
        SELECT *
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND entry_date <= {ph}
          AND (
                COALESCE(exit_date, '') = ''
                OR exit_date >= {ph}
          )
        ORDER BY entry_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter, month_end.isoformat(), month_start.isoformat()),
    )
    return dict(row) if row else None


def _latest_prior_balance(resident_id: int, shelter: str, carry_forward_enabled: bool, rent_year: int, rent_month: int) -> float:
    if not carry_forward_enabled:
        return 0.0

    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT e.remaining_balance
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE e.resident_id = {ph}
          AND LOWER(COALESCE(e.shelter_snapshot, '')) = {ph}
          AND (
                s.rent_year < {ph}
                OR (s.rent_year = {ph} AND s.rent_month < {ph})
          )
        ORDER BY s.rent_year DESC, s.rent_month DESC, e.id DESC
        LIMIT 1
        """,
        (resident_id, shelter, rent_year, rent_year, rent_month),
    )
    return _float_value(row.get("remaining_balance") if row else 0)


def _load_sheet_entries(sheet_id: int):
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT *
        FROM resident_rent_sheet_entries
        WHERE sheet_id = {ph}
        ORDER BY resident_name_snapshot ASC, id ASC
        """,
        (sheet_id,),
    )
    return [dict(row) for row in rows]


def _history_rows_for_resident(resident_id: int):
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT
            e.*,
            s.rent_year,
            s.rent_month
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE e.resident_id = {ph}
        ORDER BY s.rent_year DESC, s.rent_month DESC, e.id DESC
        """,
        (resident_id,),
    )
    return [dict(row) for row in rows]


def _sheet_for_month(shelter: str, rent_year: int, rent_month: int):
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT *
        FROM resident_rent_sheets
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND rent_year = {ph}
          AND rent_month = {ph}
        LIMIT 1
        """,
        (shelter, rent_year, rent_month),
    )
    return dict(row) if row else None


def _insert_sheet(shelter: str, rent_year: int, rent_month: int):
    now = utcnow_iso()
    generated_on = _today_chicago().date().isoformat()
    db_execute(
        (
            """
            INSERT INTO resident_rent_sheets (
                shelter,
                rent_year,
                rent_month,
                generated_on,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO resident_rent_sheets (
                shelter,
                rent_year,
                rent_month,
                generated_on,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (shelter, rent_year, rent_month, generated_on, session.get("staff_user_id"), now, now),
    )


def _resident_for_shelter(resident_id: int, shelter: str):
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    return dict(row) if row else None


def _resident_any_shelter(resident_id: int):
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    )
    return dict(row) if row else None


def _rent_history_label(year: int, month: int) -> str:
    return _month_label(year, month)


def _ledger_balance_before_entry(resident_id: int) -> float:
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT balance_after
        FROM resident_rent_ledger_entries
        WHERE resident_id = {ph}
        ORDER BY entry_date DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (resident_id,),
    )
    return _float_value(row.get("balance_after") if row else 0)


def _insert_rent_ledger_entry(
    resident_id: int,
    shelter: str,
    entry_date: str,
    entry_type: str,
    description: str | None,
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
    now = utcnow_iso()
    balance_before = _ledger_balance_before_entry(resident_id)
    balance_after = round(balance_before + _float_value(debit_amount) - _float_value(credit_amount), 2)

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            """
            INSERT INTO resident_rent_ledger_entries (
                resident_id,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                resident_id,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resident_id,
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


def _ledger_entries_for_resident(resident_id: int):
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT
            l.*,
            r.first_name,
            r.last_name
        FROM resident_rent_ledger_entries l
        JOIN residents r ON r.id = l.resident_id
        WHERE l.resident_id = {ph}
        ORDER BY l.entry_date ASC, l.created_at ASC, l.id ASC
        """,
        (resident_id,),
    )

    chronological_entries = [dict(row) for row in rows]
    running_balance = 0.0

    for entry in chronological_entries:
        running_balance = round(
            running_balance
            + _float_value(entry.get("debit_amount"))
            - _float_value(entry.get("credit_amount")),
            2,
        )
        entry["balance_after"] = running_balance

    return sorted(
        chronological_entries,
        key=lambda row: (
            row.get("entry_date") or "",
            row.get("created_at") or "",
            row.get("id") or 0,
        ),
        reverse=True,
    )


def _ledger_summary_for_resident(resident_id: int) -> dict:
    entries = _ledger_entries_for_resident(resident_id)

    total_debits = round(sum(_float_value(row.get("debit_amount")) for row in entries), 2)
    total_credits = round(sum(_float_value(row.get("credit_amount")) for row in entries), 2)
    net_balance = round(total_debits - total_credits, 2)

    return {
        "entry_count": len(entries),
        "total_debits": total_debits,
        "total_credits": total_credits,
        "current_balance": net_balance,
        "current_credit": round(abs(net_balance), 2) if net_balance < 0 else 0.0,
        "current_due": round(net_balance, 2) if net_balance > 0 else 0.0,
    }
