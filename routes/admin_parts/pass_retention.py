from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, session

from core.helpers import utcnow_iso
from core.pass_retention import run_pass_retention_cleanup_for_shelter

bp = Blueprint("admin_pass_retention", __name__)

SHELTERS = ("abba", "haven", "gratitude")


@bp.route("/admin/run-pass-cleanup", methods=["POST"])
def run_pass_cleanup():
    role = session.get("role")

    if role != "admin":
        abort(403)

    staff_id = session.get("staff_user_id")
    staff_name = (session.get("username") or "").strip()

    results = []
    total_backfilled = 0
    total_deleted = 0

    for shelter in SHELTERS:
        result = run_pass_retention_cleanup_for_shelter(shelter)

        total_backfilled += int(result.get("backfilled", 0))
        total_deleted += int(result.get("deleted", 0))

        results.append(result)

    timestamp = utcnow_iso()

    current_app.logger.info(
        "manual pass cleanup run by staff_id=%s staff_name=%s at=%s total_backfilled=%s total_deleted=%s",
        staff_id,
        staff_name,
        timestamp,
        total_backfilled,
        total_deleted,
    )

    return jsonify(
        {
            "status": "ok",
            "ran_at": timestamp,
            "staff_id": staff_id,
            "staff_name": staff_name,
            "total_backfilled": total_backfilled,
            "total_deleted": total_deleted,
            "results": results,
        }
    )
