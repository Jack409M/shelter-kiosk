from __future__ import annotations

from typing import Any

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder


OFFICIAL_NEEDS = [
    {
        "need_key": "dental",
        "need_label": "Dental",
    },
    {
        "need_key": "vision_glasses",
        "need_label": "Vision/Glasses",
    },
    {
        "need_key": "rhn_physical",
        "need_label": "RHN Physical",
    },
    {
        "need_key": "pap_smear",
        "need_label": "Pap Smear",
    },
    {
        "need_key": "jo_wyatt",
        "need_label": "JO Wyatt",
    },
    {
        "need_key": "birth_certificate",
        "need_label": "Birth Certificate",
    },
    {
        "need_key": "social_security_card",
        "need_label": "Social Security Card",
    },
    {
        "need_key": "state_id_drivers_license",
        "need_label": "State ID/Driver’s License",
    },
    {
        "need_key": "warrants_fine_resolution",
        "need_label": "Warrants/Fine Resolution",
    },
    {
        "need_key": "food_stamps_snap",
        "need_label": "Food Stamps/SNAP",
    },
    {
        "need_key": "parenting_class_needed",
        "need_label": "Parenting Class Needed",
    },
]

OFFICIAL_NEEDS_BY_KEY = {row["need_key"]: row for row in OFFICIAL_NEEDS}

LEGACY_INTAKE_RULES = [
    {
        "need_key": "dental",
        "source_field": "dental_need_at_entry",
        "trigger_value": 1,
    },
    {
        "need_key": "vision_glasses",
        "source_field": "vision_need_at_entry",
        "trigger_value": 1,
    },
    {
        "need_key": "parenting_class_needed",
        "source_field": "parenting_class_needed",
        "trigger_value": 1,
    },
    {
        "need_key": "warrants_fine_resolution",
        "source_field": "warrants_unpaid",
        "trigger_value": 1,
    },
    {
        "need_key": "social_security_card",
        "source_field": "has_social_security_card",
        "trigger_value": 0,
    },
    {
        "need_key": "state_id_drivers_license",
        "source_field": "has_drivers_license",
        "trigger_value": 0,
    },
]

VALID_NEED_STATUSES = {"open", "addressed", "not_applicable"}


def normalize_need_status(value: Any) -> str | None:
    normalized = (str(value or "").strip().lower()).replace(" ", "_")
    if normalized in VALID_NEED_STATUSES:
        return normalized
    return None


def normalize_selected_need_keys(raw_values: Any) -> list[str]:
    if raw_values is None:
        return []

    if isinstance(raw_values, str):
        values = [raw_values]
    else:
        values = list(raw_values)

    cleaned: list[str] = []
    seen: set[str] = set()

    for value in values:
        key = (str(value or "").strip().lower()).replace(" ", "_")
        if not key:
            continue
        if key not in OFFICIAL_NEEDS_BY_KEY:
            continue
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(key)

    return cleaned


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


def build_triggered_needs(
    intake_row: dict[str, Any] | None = None,
    selected_need_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected_keys = normalize_selected_need_keys(selected_need_keys)

    if selected_keys:
        return [
            {
                "need_key": need_key,
                "need_label": OFFICIAL_NEEDS_BY_KEY[need_key]["need_label"],
                "source_field": "entry_needs",
                "source_value": "Yes",
            }
            for need_key in selected_keys
        ]

    if not intake_row:
        return []

    triggered: list[dict[str, Any]] = []

    for definition in LEGACY_INTAKE_RULES:
        source_field = definition["source_field"]
        source_value = intake_row.get(source_field)

        if _is_triggered(source_value, definition["trigger_value"]):
            need_key = definition["need_key"]
            need_meta = OFFICIAL_NEEDS_BY_KEY.get(need_key)
            if not need_meta:
                continue

            triggered.append(
                {
                    "need_key": need_key,
                    "need_label": need_meta["need_label"],
                    "source_field": source_field,
                    "source_value": _source_value_display(source_value),
                }
            )

    return triggered


def list_enrollment_need_keys(enrollment_id: int) -> list[str]:
    if not enrollment_id:
        return []

    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT need_key
        FROM resident_needs
        WHERE enrollment_id = {ph}
        ORDER BY id ASC
        """,
        (enrollment_id,),
    )

    return normalize_selected_need_keys([row["need_key"] for row in rows])


def sync_enrollment_needs(
    enrollment_id: int,
    intake_row: dict[str, Any] | None = None,
    selected_need_keys: list[str] | None = None,
) -> None:
    if not enrollment_id:
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
    triggered_needs = build_triggered_needs(
        intake_row=intake_row,
        selected_need_keys=selected_need_keys,
    )
    triggered_by_key = {need["need_key"]: need for need in triggered_needs}

    for need_key, need in triggered_by_key.items():
        existing = existing_by_key.get(need_key)

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

    for need_key, existing in existing_by_key.items():
        if need_key in triggered_by_key:
            continue
        if existing["status"] != "open":
            continue

        db_execute(
            f"""
            UPDATE resident_needs
            SET
                status = 'not_applicable',
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                now,
                existing["id"],
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
