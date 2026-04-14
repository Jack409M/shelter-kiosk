from __future__ import annotations

from core.db import db_fetchone
from routes.case_management_parts.helpers import (
    fetch_current_enrollment_for_resident,
    placeholder,
    shelter_equals_sql,
)


def load_current_enrollment(resident_id: int):
    return fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        """,
    )


def load_resident_in_scope(resident_id: int, shelter: str):
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )
