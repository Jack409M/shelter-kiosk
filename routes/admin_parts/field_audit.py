from __future__ import annotations

from flask import render_template

from core.field_registry import get_all_fields


def _field_status(field) -> str:
    if field.form_field and field.table and field.column:
        return "complete"
    if field.form_field or field.table or field.column:
        return "partial"
    return "missing"


def admin_field_audit_view():
    fields = get_all_fields()
    rows = []

    for field in fields:
        rows.append(
            {
                "key": field.key,
                "label": field.label,
                "form_page": field.form_page or "",
                "form_field": field.form_field or "",
                "table": field.table or "",
                "column": field.column or "",
                "used_in_stats": bool(field.used_in_stats),
                "notes": field.notes or "",
                "status": _field_status(field),
            }
        )

    complete_count = sum(1 for row in rows if row["status"] == "complete")
    partial_count = sum(1 for row in rows if row["status"] == "partial")
    missing_count = sum(1 for row in rows if row["status"] == "missing")

    return render_template(
        "admin/field_audit.html",
        rows=rows,
        complete_count=complete_count,
        partial_count=partial_count,
        missing_count=missing_count,
        total_count=len(rows),
    )
