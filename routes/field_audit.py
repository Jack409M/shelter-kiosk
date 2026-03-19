from flask import Blueprint, render_template, session
from core.auth import require_login
from core.db import db_fetchone
from core.field_registry import FIELD_REGISTRY

field_audit = Blueprint(
    "field_audit",
    __name__,
    url_prefix="/admin/field-audit"
)


@field_audit.route("/")
@require_login
def index():
    results = []

    for field in FIELD_REGISTRY:
        value = None
        found = False
        error = None

        try:
            query = f"""
                SELECT {field['column']}
                FROM {field['table']}
                WHERE {field['column']} IS NOT NULL
                LIMIT 1
            """
            row = db_fetchone(query)

            if row and field["column"] in row:
                value = row[field["column"]]
                found = True

        except Exception as e:
            error = str(e)

        results.append({
            "label": field["label"],
            "stage": field["stage"],
            "table": field["table"],
            "column": field["column"],
            "form_field": field["form_field"],
            "found": found,
            "value": value,
            "error": error,
        })

    return render_template(
        "admin/field_audit.html",
        results=results
    )
