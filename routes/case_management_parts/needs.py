from __future__ import annotations

from typing import Any

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder


NEED_DEFINITIONS = [
    {
        "need_key": "dental",
        "need_label": "Dental",
        "source_field": "dental_need_at_entry",
        "trigger_value": 1,
    },
    {
        "need_key": "vision",
        "need_label": "Vision",
        "source_field": "vision_need_at_entry",
        "trigger_value": 1,
    },
    {
        "need_key": "parenting_class",
        "need_label": "Parenting Class",
        "source_field": "parenting_class_needed",
        "trigger_value": 1,
    },
    {
        "need_key": "warrants_fines",
        "need_label": "Warrants/Fines",
        "source_field": "warrants_unpaid",
        "trigger_value": 1,
    },
    {
        "need_key": "mental_health",
        "need_label": "Mental Health",
        "source_field": "mental_health_need_at_entry",
        "trigger_value": 1,
    },
    {
        "need_key": "medical",
        "need_label": "Medical",
        "source_field": "medical_need_at_entry",
        "trigger_value": 1,
    },
    {
        "need_key": "drivers_license",
        "need_label": "Drivers License",
        "source_field": "has_drivers_license",
        "trigger_value": 0,
    },
    {
        "need_key": "social_security_card",
        "need_label": "Social Security Card",
        "source_field": "has_social_security_card",
        "trigger_value": 0,
    },
]

VALID_NEED_STATUSES = {"open", "addressed", "not_applicable"}


def normalize_need_status(value: Any) -> str | None:
    normalized = (str(value or "").strip().lower()).replace(" ", "_")
    if normalized in VALID_NEED_STATUSES:
        return normalized
    return None


def _source_value_display(value: Any) -> str:
    if value in (1, True, "1", "true", "True", "yes", "Yes"):
        return "Yes"
    if value in (0, False, "0", "false", "False", "no", "No"):
        return "No"
    if value is None:
        return ""
    return str(value)


def _is_triggered(value: Any, trigger_value: Any) -> bool:
    if value == trigger_value:
        return True

    if trigger_value == 1 and value in (True, "1", "true", "True", "yes", "Yes"):
        return True

    if trigger_value == 0 and value in (False, "0", "false", "False", "no", "No"):
        return True

    return False


def build_triggered_needs(intake_row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not intake_row:
        return []

    triggered: list[dict[str, Any]] = []

    for definition in NEED_DEFINITIONS:
        source_field = definition["source_field"]
        source_value = intake_row.get(source_field)

        if _is_triggered(source_value, definition["trigger_value"]):
            triggered.append(
                {
                    "need_key": definition["need_key"],
                    "need_label": definition["need_label"],
                    "source_field": source_field,
                    "source_value": _source_value_display(source_value),
                }
            )

    return triggered


def sync_enrollment_needs(enrollment_id: int, intake_row: dict[str, Any] | None) -> None:
    if not enrollment_id or not intake_row:
        return

    ph = placeholder()
    now = utcnow_iso()

    existing_rows = db_fetchall(
        f"""
        SELECT
            id,
            need_key,
            status
        FROM resident_needs
        WHERE enrollment_id = {ph}
        """,
        (enrollment_id,),
    )

    existing_by_key = {row["need_key"]: row for row in existing_rows}
    triggered_needs = build_triggered_needs(intake_row)

    for need in triggered_needs:
        existing = existing_by_key.get(need["need_key"])

        if existing:
            db_execute(
                f"""
                UPDATE resident_needs
                SET
                    need_label = {ph},
                    source_field = {ph},
                    source_value = {ph},
                    updated_at = {ph}
                WHERE id = {ph}
                """,
                (
                    need["need_label"],
                    need["source_field"],
                    need["source_value"],
                    now,
                    existing["id"],
                ),
            )
            continue

        db_execute(
            f"""
            INSERT INTO resident_needs
            (
                enrollment_id,
                need_key,
                need_label,
                source_field,
                source_value,
                status,
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
                {ph}
            )
            """,
            (
                enrollment_id,
                need["need_key"],
                need["need_label"],
                need["source_field"],
                need["source_value"],
                "open",
                now,
                now,
            ),
        )


def get_open_enrollment_needs(enrollment_id: int) -> list[dict[str, Any]]:
    if not enrollment_id:
        return []

    ph = placeholder()

    return db_fetchall(
        f"""
        SELECT
            id,
            need_key,
            need_label,
            source_field,
            source_value,
            status,
            resolution_note,
            resolved_at,
            resolved_by_staff_user_id,
            created_at,
            updated_at
        FROM resident_needs
        WHERE enrollment_id = {ph}
          AND status = 'open'
        ORDER BY need_label ASC, id ASC
        """,
        (enrollment_id,),
    )
