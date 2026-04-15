from flask import Blueprint, jsonify

from db.migration_runner import (
    get_current_schema_version,
    get_required_schema_version,
    database_schema_is_compatible,
)
from core.db import get_db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    status = "ok"
    db_ok = True

    try:
        get_db()
    except Exception:
        db_ok = False
        status = "error"

    current_version = get_current_schema_version()
    required_version = get_required_schema_version()
    compatible = database_schema_is_compatible()

    if not compatible:
        status = "error"

    return jsonify(
        {
            "status": status,
            "database": {
                "connected": db_ok,
                "current_version": current_version,
                "required_version": required_version,
                "compatible": compatible,
            },
        }
    )
