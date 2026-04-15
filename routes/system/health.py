from __future__ import annotations

from flask import Blueprint, jsonify
from core.db import db_fetchone


bp = Blueprint("health", __name__)


@bp.route("/health/live", methods=["GET"])
def health_live():
    return jsonify({"status": "ok"}), 200


@bp.route("/health/ready", methods=["GET"])
def health_ready():
    try:
        # simple DB check
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
