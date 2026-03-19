from __future__ import annotations

from flask import Blueprint
from flask import render_template

from core.auth import require_login
from core.db import db_fetchone
from core.field_registry import get_all_fields


field_audit = Blueprint(
    "field_audit",
    __name__,
    url_prefix="/admin/field-audit",
)


def _safe_probe_value(table: str | None, column: str | None) -> tuple[bool, object, str | None]:
    if not table or not column:
        return False, None, None

    try:
        query = f"""
            SELECT {column}
            FROM {table}
            WHERE {column} IS NOT NULL
            LIMIT 1
        """
        row = db_fetchone(query)

        if not row:
            return False, None, None

        if isinstance(row, dict):
            if column in row:
                return True, row.get(column), None
            return True, row, None

        try:
            value = row[column]
            return True, value, None
        except Exception:
            return True, row, None

    except Exception as exc:
        return False, None, str(exc)


def _status_for_field(field) -> str:
    if field.form_field and field.table and field.column:
        return "complete"
    if field.form_field or field.table or field.column:
        return "partial"
    return "missing"


@field_audit.route("/")
@require_login
def index():
    results = []

    for field in get_all_fields():
        found, value, error = _safe_probe_value(field.table, field.column)

        results.append(
            {
                "key": field.key,
                "label": field.label,
                "form_page": field.form_page or "",
                "form_field": field.form_field or "",
                "table": field.table or "",
                "column": field.column or "",
                "used_in_stats": bool(field.used_in_stats),
                "status": _status_for_field(field),
                "found": found,
                "value": value,
                "error": error,
                "notes": field.notes or "",
            }
        )

    complete_count = sum(1 for row in results if row["status"] == "complete")
    partial_count = sum(1 for row in results if row["status"] == "partial")
    missing_count = sum(1 for row in results if row["status"] == "missing")

    return render_template(
        "admin/field_audit.html",
        results=results,
        rows=results,
        total_count=len(results),
        complete_count=complete_count,
        partial_count=partial_count,
        missing_count=missing_count,
    )
