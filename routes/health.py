from __future__ import annotations

from flask import Blueprint, jsonify

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
            return jsonify({"status": "error", "reason": "db_no_response"}), 500

        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "reason": "db_exception",
                    "message": str(exc),
                }
            ),
            500,
        )
