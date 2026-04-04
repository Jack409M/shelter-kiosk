from __future__ import annotations

from typing import Any

from flask import g

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import yes_no_to_int


def ensure_intake_income_supports_table() -> None:
    ph = placeholder()
    del ph

    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS intake_income_supports (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL UNIQUE REFERENCES program_enrollments(id) ON DELETE CASCADE,
                employment_income_1 DOUBLE PRECISION,
                employment_income_2 DOUBLE PRECISION,
                employment_income_3 DOUBLE PRECISION,
                ssi_ssdi_income DOUBLE PRECISION,
                tanf_income DOUBLE PRECISION,
                child_support_income DOUBLE PRECISION,
                alimony_income DOUBLE PRECISION,
                other_income DOUBLE PRECISION,
                other_income_description TEXT,
                receives_snap_at_entry BOOLEAN,
                total_cash_support DOUBLE PRECISION,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        return

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS intake_income_supports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL UNIQUE,
            employment_income_1 REAL,
            employment_income_2 REAL,
            employment_income_3 REAL,
            ssi_ssdi_income REAL,
            tanf_income REAL,
            child_support_income REAL,
            alimony_income REAL,
            other_income REAL,
            other_income_description TEXT,
            receives_snap_at_entry INTEGER,
            total_cash_support REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id) ON DELETE CASCADE
        )
        """
    )


def _safe_money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def _build_income_support_payload(data: dict[str, Any]) -> dict[str, Any]:
    employment_income_1 = _safe_money(data.get("employment_income_1"))
    employment_income_2 = _safe_money(data.get("employment_income_2"))
    employment_income_3 = _safe_money(data.get("employment_income_3"))
    ssi_ssdi_income = _safe_money(data.get("ssi_ssdi_income"))
    tanf_income = _safe_money(data.get("tanf_income"))
    child_support_income = _safe_money(data.get("child_support_income"))
    alimony_income = _safe_money(data.get("alimony_income"))
    other_income = _safe_money(data.get("other_income"))

    total_cash_support = round(
        employment_income_1
        + employment_income_2
        + employment_income_3
        + ssi_ssdi_income
        + tanf_income
        + child_support_income
        + alimony_income
        + other_income,
        2,
    )

    return {
        "employment_income_1": employment_income_1 or None,
        "employment_income_2": employment_income_2 or None,
        "employment_income_3": employment_income_3 or None,
        "ssi_ssdi_income": ssi_ssdi_income or None,
        "tanf_income": tanf_income or None,
        "child_support_income": child_support_income or None,
        "alimony_income": alimony_income or None,
        "other_income": other_income or None,
        "other_income_description": (data.get("other_income_description") or "").strip() or None,
        "receives_snap_at_entry": yes_no_to_int(data.get("receives_snap_at_entry")),
        "total_cash_support": total_cash_support,
    }


def load_intake_income_support(enrollment_id: int):
    if not enrollment_id:
        return None

    ensure_intake_income_supports_table()
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
            employment_income_1,
            employment_income_2,
            employment_income_3,
            ssi_ssdi_income,
            tanf_income,
            child_support_income,
            alimony_income,
            other_income,
            other_income_description,
            receives_snap_at_entry,
            total_cash_support
        FROM intake_income_supports
        WHERE enrollment_id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )


def upsert_intake_income_support(enrollment_id: int, data: dict[str, Any]) -> None:
    if not enrollment_id:
        return

    ensure_intake_income_supports_table()
    payload = _build_income_support_payload(data)
    ph = placeholder()
    now = utcnow_iso()

    existing = db_fetchone(
        f"""
        SELECT id
        FROM intake_income_supports
        WHERE enrollment_id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if existing:
        db_execute(
            f"""
            UPDATE intake_income_supports
            SET
                employment_income_1 = {ph},
                employment_income_2 = {ph},
                employment_income_3 = {ph},
                ssi_ssdi_income = {ph},
                tanf_income = {ph},
                child_support_income = {ph},
                alimony_income = {ph},
                other_income = {ph},
                other_income_description = {ph},
                receives_snap_at_entry = {ph},
                total_cash_support = {ph},
                updated_at = {ph}
            WHERE enrollment_id = {ph}
            """,
            (
                payload["employment_income_1"],
                payload["employment_income_2"],
                payload["employment_income_3"],
                payload["ssi_ssdi_income"],
                payload["tanf_income"],
                payload["child_support_income"],
                payload["alimony_income"],
                payload["other_income"],
                payload["other_income_description"],
                payload["receives_snap_at_entry"],
                payload["total_cash_support"],
                now,
                enrollment_id,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO intake_income_supports
        (
            enrollment_id,
            employment_income_1,
            employment_income_2,
            employment_income_3,
            ssi_ssdi_income,
            tanf_income,
            child_support_income,
            alimony_income,
            other_income,
            other_income_description,
            receives_snap_at_entry,
            total_cash_support,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph}
        )
        """,
        (
            enrollment_id,
            payload["employment_income_1"],
            payload["employment_income_2"],
            payload["employment_income_3"],
            payload["ssi_ssdi_income"],
            payload["tanf_income"],
            payload["child_support_income"],
            payload["alimony_income"],
            payload["other_income"],
            payload["other_income_description"],
            payload["receives_snap_at_entry"],
            payload["total_cash_support"],
            now,
            now,
        ),
    )


def benefits_screening_needed(data: dict[str, Any]) -> bool:
    total_cash_support = _safe_money(data.get("income_at_entry"))
    if total_cash_support < 1200.0:
        return True

    if str(data.get("pregnant") or "").strip().lower() == "yes":
        return True

    if str(data.get("veteran") or "").strip().lower() == "yes":
        return True

    disability = str(data.get("disability") or "").strip()
    if disability and disability.lower() != "unknown":
        return True

    employment_status = str(data.get("employment_status") or "").strip().lower()
    if employment_status in {"unemployed", "disabled", "unknown"}:
        return True

    for field_name in [
        "kids_at_dwc",
        "kids_served_outside_under_18",
        "kids_ages_0_5",
        "kids_ages_6_11",
        "kids_ages_12_17",
    ]:
        try:
            if int(data.get(field_name) or 0) > 0:
                return True
        except Exception:
            pass

    return False
