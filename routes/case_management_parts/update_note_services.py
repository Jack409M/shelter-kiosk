from __future__ import annotations

from core.db import db_execute
from routes.case_management_parts.helpers import placeholder


def insert_client_services(
    *,
    enrollment_id: int,
    note_id: int,
    service_date: str,
    services: list[dict],
    now: str,
):
    ph = placeholder()

    for service in services:
        db_execute(
            f"""
            INSERT INTO client_services
            (
                enrollment_id,
                case_manager_update_id,
                service_type,
                service_date,
                quantity,
                unit,
                notes,
                created_at,
                updated_at
            )
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """,
            (
                enrollment_id,
                note_id,
                service["service_type"],
                service_date,
                service["quantity"],
                service["unit"],
                service["service_note"],
                now,
                now,
            ),
        )
