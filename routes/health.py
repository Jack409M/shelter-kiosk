from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from core.db import db_fetchone
from core.runtime import init_db
from db.migration_runner import (
    database_schema_is_compatible,
    get_current_schema_version,
    get_required_schema_version,
)

health = Blueprint("health", __name__)


@health.get("/health/live")
def health_live():
    return jsonify({"status": "ok"}), 200


@health.get("/health/ready")
def health_ready():
    try:
        init_db()

        row = db_fetchone("SELECT 1 AS ok")
        if not row:
            current_app.logger.error(
                "health_ready_failed reason=db_no_response database_mode=%s schema_current=%s schema_required=%s",
                current_app.config.get("DATABASE_MODE_LABEL"),
                get_current_schema_version(),
                get_required_schema_version(),
            )
            return jsonify({"status": "error", "reason": "db_no_response"}), 500

        current_version = get_current_schema_version()
        required_version = get_required_schema_version()

        if not database_schema_is_compatible():
            current_app.logger.error(
                "health_ready_failed reason=schema_incompatible database_mode=%s schema_current=%s schema_required=%s",
                current_app.config.get("DATABASE_MODE_LABEL"),
                current_version,
                required_version,
            )
            return (
                jsonify(
                    {
                        "status": "error",
                        "reason": "schema_incompatible",
                    }
                ),
                500,
            )

        return (
            jsonify(
                {
                    "status": "ok",
                    "schema_version": current_version,
                    "required_schema_version": required_version,
                }
            ),
            200,
        )

    except Exception as exc:
        current_app.logger.exception(
            "health_ready_failed reason=db_exception exception_type=%s database_mode=%s",
            type(exc).__name__,
            current_app.config.get("DATABASE_MODE_LABEL"),
        )
        return jsonify({"status": "error", "reason": "db_exception"}), 500
