from __future__ import annotations

from routes.case_management_parts.recovery_snapshot_formatters import bool_display
from routes.case_management_parts.recovery_snapshot_formatters import result_display


def medication_items(rows):
    items = []
    for med in rows or []:
        items.append(
            {
                "id": med.get("id"),
                "medication_name": med.get("medication_name"),
                "dosage": med.get("dosage"),
                "frequency": med.get("frequency"),
                "purpose": med.get("purpose"),
                "prescribed_by": med.get("prescribed_by"),
                "started_on": med.get("started_on"),
                "ended_on": med.get("ended_on"),
                "is_active": med.get("is_active"),
                "notes": med.get("notes"),
            }
        )
    return items


def ua_items(rows):
    items = []
    for row in rows or []:
        items.append(
            {
                "id": row.get("id"),
                "ua_date": row.get("ua_date"),
                "result": row.get("result"),
                "result_display": result_display(row.get("result")),
                "substances_detected": row.get("substances_detected"),
                "notes": row.get("notes"),
            }
        )
    return items


def inspection_items(rows):
    items = []
    for row in rows or []:
        items.append(
            {
                "id": row.get("id"),
                "inspection_date": row.get("inspection_date"),
                "passed": row.get("passed"),
                "passed_display": bool_display(row.get("passed")),
                "notes": row.get("notes"),
            }
        )
    return items


def budget_items(rows):
    items = []
    for row in rows or []:
        items.append(
            {
                "id": row.get("id"),
                "session_date": row.get("session_date"),
                "notes": row.get("notes"),
            }
        )
    return items
