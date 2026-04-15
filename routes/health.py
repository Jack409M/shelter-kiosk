from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from core.db import db_fetchone
from core.runtime import init_db

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
                "health_ready_failed reason=db_no_response database_mode=%s",
                current_app.config.get("DATABASE_MODE_LABEL"),
            )
            return jsonify({"status": "error", "reason": "db_no_response"}), 500

        return jsonify({"status": "ok"}), 200

    except Exception as exc:
        current_app.logger.exception(
            "health_ready_failed reason=db_exception exception_type=%s database_mode=%s",
            type(exc).__name__,
            current_app.config.get("DATABASE_MODE_LABEL"),
        )
        return jsonify({"status": "error", "reason": "db_exception"}), 500
