from __future__ import annotations

from routes.case_management_parts.recovery_snapshot_formatters import bool_display, result_display


def _map_rows(rows, mapper):
    return [mapper(row) for row in (rows or [])]


def _map_medication(row):
    return {
        "id": row.get("id"),
        "medication_name": row.get("medication_name"),
        "dosage": row.get("dosage"),
        "frequency": row.get("frequency"),
        "purpose": row.get("purpose"),
        "prescribed_by": row.get("prescribed_by"),
        "started_on": row.get("started_on"),
        "ended_on": row.get("ended_on"),
        "is_active": row.get("is_active"),
        "notes": row.get("notes"),
    }


def _map_ua(row):
    return {
        "id": row.get("id"),
        "ua_date": row.get("ua_date"),
        "result": row.get("result"),
        "result_display": result_display(row.get("result")),
        "substances_detected": row.get("substances_detected"),
        "notes": row.get("notes"),
    }


def _map_inspection(row):
    return {
        "id": row.get("id"),
        "inspection_date": row.get("inspection_date"),
        "passed": row.get("passed"),
        "passed_display": bool_display(row.get("passed")),
        "notes": row.get("notes"),
    }


def _map_budget(row):
    return {
        "id": row.get("id"),
        "session_date": row.get("session_date"),
        "notes": row.get("notes"),
    }


def medication_items(rows):
    return _map_rows(rows, _map_medication)


def ua_items(rows):
    return _map_rows(rows, _map_ua)


def inspection_items(rows):
    return _map_rows(rows, _map_inspection)


def budget_items(rows):
    return _map_rows(rows, _map_budget)
