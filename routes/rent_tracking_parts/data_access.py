from __future__ import annotations

from flask import g, session

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import assert_enrollment_belongs_to_resident
from routes.resident_parts.resident_transfer_helpers import (
    available_apartment_options_for_shelter,
    normalize_apartment_number_local,
)

from .dates import _current_year_month, _month_label, _today_chicago
from .utils import _float_value, _placeholder


def _active_residents_for_shelter(shelter: str):
    ph = _placeholder()
    return db_fetchall(
        f"""
        SELECT id, first_name, last_name, shelter, is_active
        FROM residents
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND is_active = {('TRUE' if g.get('db_kind') == 'pg' else '1')}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )


def _available_rent_setup_apartment_options(
    shelter: str, resident_id: int | None = None
) -> list[str]:
    normalized_shelter = (shelter or "").strip().lower()
    available = list(available_apartment_options_for_shelter(normalized_shelter))

    if resident_id is None:
        return available

    active_config = _active_rent_config_for_resident(resident_id, normalized_shelter)
    current_apartment = normalize_apartment_number_local(
        normalized_shelter,
        (active_config or {}).get("apartment_number_snapshot") if active_config else None,
    )

    if current_apartment and current_apartment not in available:
        available.append(current_apartment)

    def _sort_key(value: str):
        text = str(value)
        return (0, int(text)) if text.isdigit() else (1, text)

    return sorted(available, key=_sort_key)


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
            else """
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


def _program_enrollment_for_month(
    resident_id: int, shelter: str, rent_year: int, rent_month: int
) -> dict | None:
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


def _current_program_enrollment_for_resident(resident_id: int, shelter: str) -> dict | None:
    rent_year, rent_month = _current_year_month()
    return _program_enrollment_for_month(resident_id, shelter, rent_year, rent_month)


def _latest_prior_balance(
    resident_id: int, shelter: str, carry_forward_enabled: bool, rent_year: int, rent_month: int
) -> float:
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
            else """
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
        SELECT id, first_name, last_name, shelter, is_active
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
        SELECT id, first_name, last_name, shelter, is_active
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
          AND COALESCE(voided, {('FALSE' if g.get('db_kind') == 'pg' else '0')}) = {('FALSE' if g.get('db_kind') == 'pg' else '0')}
        ORDER BY entry_date DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (resident_id,),
    )
    return _float_value(row.get("balance_after") if row else 0)


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
    payment_method: str | None = None,
    check_or_money_order_number: str | None = None,
    charge_category: str | None = None,
    charge_reference: str | None = None,
    voided: bool = False,
    void_reason: str | None = None,
    entered_by_staff_user_id: int | None = None,
) -> int | None:
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
    acting_staff_user_id = entered_by_staff_user_id or session.get("staff_user_id")

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
                payment_method,
                check_or_money_order_number,
                charge_category,
                charge_reference,
                voided,
                void_reason,
                entered_by_staff_user_id,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                payment_method,
                check_or_money_order_number,
                charge_category,
                charge_reference,
                voided,
                void_reason,
                acting_staff_user_id,
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
            payment_method,
            check_or_money_order_number,
            charge_category,
            charge_reference,
            voided,
            void_reason,
            entered_by_staff_user_id,
            created_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            payment_method,
            check_or_money_order_number,
            charge_category,
            charge_reference,
            1 if voided else 0,
            void_reason,
            acting_staff_user_id,
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


def _post_resident_payment(
    *,
    resident_id: int,
    shelter: str,
    amount: float,
    payment_date: str,
    payment_method: str,
    instrument_number: str,
    notes: str | None = None,
) -> int | None:
    enrollment = _current_program_enrollment_for_resident(resident_id, shelter)
    return _insert_rent_ledger_entry(
        resident_id=resident_id,
        enrollment_id=enrollment.get("id") if enrollment else None,
        shelter=shelter,
        entry_date=payment_date,
        entry_type="payment",
        description="Rent payment received",
        debit_amount=0.0,
        credit_amount=round(_float_value(amount), 2),
        source_code="rent_payment_manual",
        source_reference=f"manual-payment:{payment_date}:{utcnow_iso()}",
        notes=notes,
        payment_method=payment_method,
        check_or_money_order_number=instrument_number,
        entered_by_staff_user_id=session.get("staff_user_id"),
    )


def _post_resident_charge(
    *,
    resident_id: int,
    shelter: str,
    amount: float,
    charge_date: str,
    charge_category: str,
    description: str,
    charge_reference: str | None = None,
    notes: str | None = None,
) -> int | None:
    enrollment = _current_program_enrollment_for_resident(resident_id, shelter)
    return _insert_rent_ledger_entry(
        resident_id=resident_id,
        enrollment_id=enrollment.get("id") if enrollment else None,
        shelter=shelter,
        entry_date=charge_date,
        entry_type="charge",
        description=description,
        debit_amount=round(_float_value(amount), 2),
        credit_amount=0.0,
        source_code=f"manual_charge_{charge_category}",
        source_reference=f"manual-charge:{charge_date}:{utcnow_iso()}",
        notes=notes,
        charge_category=charge_category,
        charge_reference=charge_reference,
        entered_by_staff_user_id=session.get("staff_user_id"),
    )


def _post_resident_credit(
    *,
    resident_id: int,
    shelter: str,
    amount: float,
    credit_date: str,
    credit_category: str,
    description: str,
    notes: str | None = None,
) -> int | None:
    enrollment = _current_program_enrollment_for_resident(resident_id, shelter)
    return _insert_rent_ledger_entry(
        resident_id=resident_id,
        enrollment_id=enrollment.get("id") if enrollment else None,
        shelter=shelter,
        entry_date=credit_date,
        entry_type="credit",
        description=description,
        debit_amount=0.0,
        credit_amount=round(_float_value(amount), 2),
        source_code=f"manual_credit_{credit_category}",
        source_reference=f"manual-credit:{credit_date}:{utcnow_iso()}",
        notes=notes,
        charge_category=credit_category,
        entered_by_staff_user_id=session.get("staff_user_id"),
    )


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
          AND COALESCE(l.voided, {('FALSE' if g.get('db_kind') == 'pg' else '0')}) = {('FALSE' if g.get('db_kind') == 'pg' else '0')}
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


def _ledger_balance_breakdown_for_resident(resident_id: int) -> dict:
    entries = _ledger_entries_for_resident(resident_id)

    monthly_rent = 0.0
    late_fees = 0.0
    extra_charges = 0.0
    refunds_and_credits = 0.0
    payments_received = 0.0

    for entry in entries:
        debit_amount = _float_value(entry.get("debit_amount"))
        credit_amount = _float_value(entry.get("credit_amount"))
        source_code = str(entry.get("source_code") or "").strip()
        entry_type = str(entry.get("entry_type") or "").strip().lower()

        if debit_amount > 0:
            if source_code == "monthly_rent_charge":
                monthly_rent += debit_amount
            elif source_code == "late_fee_charge" or entry_type == "late_fee":
                late_fees += debit_amount
            else:
                extra_charges += debit_amount

        if credit_amount > 0:
            if entry_type == "payment":
                payments_received += credit_amount
            else:
                refunds_and_credits += credit_amount

    summary = _ledger_summary_for_resident(resident_id)
    return {
        "monthly_rent": round(monthly_rent, 2),
        "late_fees": round(late_fees, 2),
        "extra_charges": round(extra_charges, 2),
        "refunds_and_credits": round(refunds_and_credits, 2),
        "payments_received": round(payments_received, 2),
        "current_due": summary["current_due"],
        "current_credit": summary["current_credit"],
        "current_balance": summary["current_balance"],
    }
    
