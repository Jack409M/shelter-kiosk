from __future__ import annotations

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import parse_iso_date, placeholder
from routes.case_management_parts.intake_income_support import (
    load_intake_income_support,
    recalculate_intake_income_support,
    upsert_intake_income_support,
)


def _load_resident_snapshot_source(resident_id: int):
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
            id,
            employment_status_current,
            employer_name,
            employment_type_current,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            current_job_start_date,
            previous_job_end_date,
            upward_job_change,
            job_change_notes
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    )


def sync_resident_income_snapshot(
    resident_id: int,
    weighted_stable_income,
    employment_status_current,
    employer_name,
    employment_type_current,
    supervisor_name,
    supervisor_phone,
    unemployment_reason,
    employment_notes,
    current_job_start_date,
    previous_job_end_date,
    upward_job_change,
    job_change_notes,
) -> None:
    ph = placeholder()
    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE residents
        SET
            employment_status_current = {ph},
            employer_name = {ph},
            employment_type_current = {ph},
            supervisor_name = {ph},
            supervisor_phone = {ph},
            unemployment_reason = {ph},
            employment_notes = {ph},
            monthly_income = {ph},
            current_job_start_date = {ph},
            previous_job_end_date = {ph},
            upward_job_change = {ph},
            job_change_notes = {ph},
            employment_updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            employment_status_current,
            employer_name,
            employment_type_current,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            weighted_stable_income,
            current_job_start_date.isoformat() if current_job_start_date else None,
            previous_job_end_date.isoformat() if previous_job_end_date else None,
            upward_job_change,
            job_change_notes,
            now,
            resident_id,
        ),
    )


def save_income_support_and_sync_snapshot_atomic(
    *,
    resident_id: int,
    enrollment_id: int,
    values,
) -> None:
    with db_transaction():
        upsert_intake_income_support(enrollment_id, values)

        intake_income_support = load_intake_income_support(enrollment_id) or {}
        weighted_stable_income = intake_income_support.get("weighted_stable_income")

        sync_resident_income_snapshot(
            resident_id=resident_id,
            weighted_stable_income=weighted_stable_income,
            employment_status_current=values["employment_status_current"],
            employer_name=values["employer_name"],
            employment_type_current=values["employment_type_current"],
            supervisor_name=values["supervisor_name"],
            supervisor_phone=values["supervisor_phone"],
            unemployment_reason=values["unemployment_reason"],
            employment_notes=values["employment_notes"],
            current_job_start_date=values["current_job_start_date"],
            previous_job_end_date=values["previous_job_end_date"],
            upward_job_change=values["upward_job_change"],
            job_change_notes=values["job_change_notes"],
        )


def recalculate_and_sync_income_state_atomic(
    *,
    resident_id: int,
    enrollment_id: int,
) -> None:
    with db_transaction():
        recalculate_intake_income_support(enrollment_id)
        intake_income_support = load_intake_income_support(enrollment_id) or {}
        resident = _load_resident_snapshot_source(resident_id)

        if not resident:
            return

        sync_resident_income_snapshot(
            resident_id=resident_id,
            weighted_stable_income=intake_income_support.get("weighted_stable_income"),
            employment_status_current=resident.get("employment_status_current"),
            employer_name=resident.get("employer_name"),
            employment_type_current=resident.get("employment_type_current"),
            supervisor_name=resident.get("supervisor_name"),
            supervisor_phone=resident.get("supervisor_phone"),
            unemployment_reason=resident.get("unemployment_reason"),
            employment_notes=resident.get("employment_notes"),
            current_job_start_date=parse_iso_date(resident.get("current_job_start_date")),
            previous_job_end_date=parse_iso_date(resident.get("previous_job_end_date")),
            upward_job_change=resident.get("upward_job_change"),
            job_change_notes=resident.get("job_change_notes"),
        )
