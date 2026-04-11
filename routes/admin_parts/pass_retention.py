from __future__ import annotations

from flask import Blueprint, abort, jsonify, session

from core.pass_retention import run_pass_retention_cleanup_for_shelter

bp = Blueprint("admin_pass_retention", __name__)

SHELTERS = ("abba", "haven", "gratitude")


@bp.route("/admin/run-pass-cleanup", methods=["POST"])
def run_pass_cleanup():
    role = session.get("role")

    if role != "admin":
        abort(403)

    results = []
    total_backfilled = 0
    total_deleted = 0

    for shelter in SHELTERS:
        result = run_pass_retention_cleanup_for_shelter(shelter)

        total_backfilled += int(result.get("backfilled", 0))
        total_deleted += int(result.get("deleted", 0))

        results.append(result)

    return jsonify(
        {
            "status": "ok",
            "total_backfilled": total_backfilled,
            "total_deleted": total_deleted,
            "results": results,
        }
    )
