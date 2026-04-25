from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from flask import g

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from db.schema_people import ensure_resident_child_income_supports_table
from routes.case_management_parts.helpers import placeholder


def ensure_intake_income_supports_table() -> None:
    db_kind = g.get("db_kind")

    ensure_resident_child_income_supports_table(db_kind)

    if db_kind == "pg":
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
                weighted_stable_income DOUBLE PRECISION,
                survivor_benefit_total DOUBLE PRECISION,
                survivor_benefit_weighted_total DOUBLE PRECISION,
                child_support_total DOUBLE PRECISION,
                child_support_weighted_total DOUBLE PRECISION,
                tanf_weight_applied DOUBLE PRECISION,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    else:
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
                weighted_stable_income REAL,
                survivor_benefit_total REAL,
                survivor_benefit_weighted_total REAL,
                child_support_total REAL,
                child_support_weighted_total REAL,
                tanf_weight_applied REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id) ON DELETE CASCADE
            )
            """
        )

    statements = [
        "ALTER TABLE intake_income_supports ADD COLUMN IF NOT EXISTS weighted_stable_income DOUBLE PRECISION",
        "ALTER TABLE intake_income_supports ADD COLUMN IF NOT EXISTS survivor_benefit_total DOUBLE PRECISION",
        "ALTER TABLE intake_income_supports ADD COLUMN IF NOT EXISTS survivor_benefit_weighted_total DOUBLE PRECISION",
        "ALTER TABLE intake_income_supports ADD COLUMN IF NOT EXISTS child_support_total DOUBLE PRECISION",
        "ALTER TABLE intake_income_supports ADD COLUMN IF NOT EXISTS child_support_weighted_total DOUBLE PRECISION",
        "ALTER TABLE intake_income_supports ADD COLUMN IF NOT EXISTS tanf_weight_applied DOUBLE PRECISION",
    ]
    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def _safe_money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def _to_float(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _to_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int | float):
        return value != 0

    normalized = str(value).strip().lower()
    if normalized in {"", "unknown", "none", "null"}:
        return None
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    return None


def _load_income_weight_settings_for_enrollment(enrollment_id: int) -> dict[str, float | int]:
    ph = placeholder()

    default_settings: dict[str, float | int] = {
        "income_weight_employment": 1.00,
        "income_weight_ssi_ssdi_self": 1.00,
        "income_weight_tanf": 1.00,
        "income_weight_alimony": 0.50,
        "income_weight_other_income": 0.25,
        "income_weight_survivor_cutoff_months": 18,
    }

    try:
        row = db_fetchone(
            f"""
            SELECT
                sos.income_weight_employment,
                sos.income_weight_ssi_ssdi_self,
                sos.income_weight_tanf,
                sos.income_weight_alimony,
                sos.income_weight_other_income,
                sos.income_weight_survivor_cutoff_months
            FROM program_enrollments pe
            LEFT JOIN shelter_operation_settings sos
              ON LOWER(COALESCE(sos.shelter, '')) = LOWER(COALESCE(pe.shelter, ''))
            WHERE pe.id = {ph}
            LIMIT 1
            """,
            (enrollment_id,),
        )
    except Exception:
        row = None

    if not row:
        return default_settings

    resolved = dict(default_settings)
    for key, default_value in default_settings.items():
        if row.get(key) is None:
            continue
        if isinstance(default_value, int):
            resolved[key] = _to_int(row.get(key), default_value)
        else:
            resolved[key] = _to_float(row.get(key), default_value)
    return resolved


def _child_age_from_birth_year(birth_year: Any) -> float | None:
    try:
        year = int(birth_year)
    except Exception:
        return None

    now = datetime.now(UTC)
    age = now.year - year
    if age < 0:
        return None
    return float(age)


def _age_weight_for_child(age_years: float | None, cutoff_months: int) -> float:
    if age_years is None:
        return 0.0

    months_remaining = max((18.0 - age_years) * 12.0, 0.0)
    if months_remaining < float(cutoff_months):
        return 0.0

    weight = (18.0 - age_years) / 18.0
    if weight < 0.0:
        return 0.0
    if weight > 1.0:
        return 1.0
    return weight


def _load_youngest_active_child_weight(enrollment_id: int, cutoff_months: int) -> float:
    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            rc.birth_year
        FROM resident_children rc
        JOIN program_enrollments pe
          ON pe.resident_id = rc.resident_id
        WHERE pe.id = {ph}
          AND COALESCE(rc.is_active, TRUE) = TRUE
          AND rc.birth_year IS NOT NULL
        """,
        (enrollment_id,),
    )

    youngest_age = None
    for row in rows or []:
        age_years = _child_age_from_birth_year(row.get("birth_year"))
        if age_years is None:
            continue
        if youngest_age is None or age_years < youngest_age:
            youngest_age = age_years

    return round(_age_weight_for_child(youngest_age, cutoff_months), 4)


def _load_child_linked_support_rollups(enrollment_id: int, cutoff_months: int) -> dict[str, float]:
    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            rc.birth_year,
            rcis.support_type,
            rcis.monthly_amount
        FROM resident_child_income_supports rcis
        JOIN resident_children rc
          ON rc.id = rcis.child_id
        JOIN program_enrollments pe
          ON pe.resident_id = rc.resident_id
        WHERE pe.id = {ph}
          AND COALESCE(rc.is_active, TRUE) = TRUE
          AND COALESCE(rcis.is_active, TRUE) = TRUE
        ORDER BY rcis.id ASC
        """,
        (enrollment_id,),
    )

    survivor_total = 0.0
    survivor_weighted_total = 0.0
    child_support_total = 0.0
    child_support_weighted_total = 0.0

    for row in rows or []:
        support_type = str(row.get("support_type") or "").strip().lower()
        amount = _safe_money(row.get("monthly_amount"))
        if amount <= 0:
            continue

        age_years = _child_age_from_birth_year(row.get("birth_year"))
        age_weight = _age_weight_for_child(age_years, cutoff_months)

        if support_type == "survivor_benefit":
            survivor_total += amount
            survivor_weighted_total += round(amount * age_weight, 2)
        elif support_type == "child_support":
            child_support_total += amount
            child_support_weighted_total += round(amount * age_weight, 2)

    return {
        "survivor_benefit_total": round(survivor_total, 2),
        "survivor_benefit_weighted_total": round(survivor_weighted_total, 2),
        "child_support_total": round(child_support_total, 2),
        "child_support_weighted_total": round(child_support_weighted_total, 2),
    }


def _build_income_support_payload(enrollment_id: int, data: dict[str, Any]) -> dict[str, Any]:
    employment_income_1 = _safe_money(data.get("employment_income_1"))
    employment_income_2 = _safe_money(data.get("employment_income_2"))
    employment_income_3 = _safe_money(data.get("employment_income_3"))
    ssi_ssdi_income = _safe_money(data.get("ssi_ssdi_income"))
    tanf_income = _safe_money(data.get("tanf_income"))
    alimony_income = _safe_money(data.get("alimony_income"))
    other_income = _safe_money(data.get("other_income"))

    settings = _load_income_weight_settings_for_enrollment(enrollment_id)
    cutoff_months = _to_int(settings.get("income_weight_survivor_cutoff_months"), 18)

    child_rollups = _load_child_linked_support_rollups(enrollment_id, cutoff_months)
    youngest_child_weight = _load_youngest_active_child_weight(enrollment_id, cutoff_months)

    survivor_benefit_total = _safe_money(child_rollups.get("survivor_benefit_total"))
    survivor_benefit_weighted_total = _safe_money(
        child_rollups.get("survivor_benefit_weighted_total")
    )
    child_support_total = _safe_money(child_rollups.get("child_support_total"))
    child_support_weighted_total = _safe_money(child_rollups.get("child_support_weighted_total"))

    total_cash_support = round(
        employment_income_1
        + employment_income_2
        + employment_income_3
        + ssi_ssdi_income
        + tanf_income
        + child_support_total
        + alimony_income
        + other_income
        + survivor_benefit_total,
        2,
    )

    weighted_stable_income = round(
        (employment_income_1 + employment_income_2 + employment_income_3)
        * _to_float(settings.get("income_weight_employment"), 1.00)
        + ssi_ssdi_income * _to_float(settings.get("income_weight_ssi_ssdi_self"), 1.00)
        + tanf_income * _to_float(settings.get("income_weight_tanf"), 1.00) * youngest_child_weight
        + child_support_weighted_total
        + alimony_income * _to_float(settings.get("income_weight_alimony"), 0.50)
        + other_income * _to_float(settings.get("income_weight_other_income"), 0.25)
        + survivor_benefit_weighted_total,
        2,
    )

    return {
        "employment_income_1": employment_income_1 or None,
        "employment_income_2": employment_income_2 or None,
        "employment_income_3": employment_income_3 or None,
        "ssi_ssdi_income": ssi_ssdi_income or None,
        "tanf_income": tanf_income or None,
        "child_support_income": child_support_total or None,
        "alimony_income": alimony_income or None,
        "other_income": other_income or None,
        "other_income_description": (data.get("other_income_description") or "").strip() or None,
        "receives_snap_at_entry": _to_bool_or_none(data.get("receives_snap_at_entry")),
        "total_cash_support": total_cash_support,
        "weighted_stable_income": weighted_stable_income,
        "survivor_benefit_total": survivor_benefit_total,
        "survivor_benefit_weighted_total": survivor_benefit_weighted_total,
        "child_support_total": child_support_total,
        "child_support_weighted_total": child_support_weighted_total,
        "tanf_weight_applied": youngest_child_weight,
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
            total_cash_support,
            weighted_stable_income,
            survivor_benefit_total,
            survivor_benefit_weighted_total,
            child_support_total,
            child_support_weighted_total,
            tanf_weight_applied
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
    payload = _build_income_support_payload(enrollment_id, data)
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
                weighted_stable_income = {ph},
                survivor_benefit_total = {ph},
                survivor_benefit_weighted_total = {ph},
                child_support_total = {ph},
                child_support_weighted_total = {ph},
                tanf_weight_applied = {ph},
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
                payload["weighted_stable_income"],
                payload["survivor_benefit_total"],
                payload["survivor_benefit_weighted_total"],
                payload["child_support_total"],
                payload["child_support_weighted_total"],
                payload["tanf_weight_applied"],
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
            weighted_stable_income,
            survivor_benefit_total,
            survivor_benefit_weighted_total,
            child_support_total,
            child_support_weighted_total,
            tanf_weight_applied,
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
            payload["weighted_stable_income"],
            payload["survivor_benefit_total"],
            payload["survivor_benefit_weighted_total"],
            payload["child_support_total"],
            payload["child_support_weighted_total"],
            payload["tanf_weight_applied"],
            now,
            now,
        ),
    )


def recalculate_intake_income_support(enrollment_id: int) -> None:
    if not enrollment_id:
        return

    current = load_intake_income_support(enrollment_id) or {}
    source_data = {
        "employment_income_1": current.get("employment_income_1"),
        "employment_income_2": current.get("employment_income_2"),
        "employment_income_3": current.get("employment_income_3"),
        "ssi_ssdi_income": current.get("ssi_ssdi_income"),
        "tanf_income": current.get("tanf_income"),
        "alimony_income": current.get("alimony_income"),
        "other_income": current.get("other_income"),
        "other_income_description": current.get("other_income_description"),
        "receives_snap_at_entry": (
            "yes"
            if current.get("receives_snap_at_entry") is True
            else "no"
            if current.get("receives_snap_at_entry") is False
            else ""
        ),
    }
    upsert_intake_income_support(enrollment_id, source_data)


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
