from __future__ import annotations

from flask import Blueprint, abort, jsonify, session

from core.timestamp_normalization import normalize_timestamp_columns

bp = Blueprint("admin_timestamp_cleanup", __name__)


@bp.route("/admin/timestamp-cleanup", methods=["POST"])
def run_timestamp_cleanup():
    role = session.get("role")

    if role != "admin":
        abort(403)

    apply_flag = bool(session.get("_apply_flag"))

    # default to dry run unless explicit apply flag is passed
    apply = bool(session.get("timestamp_cleanup_apply", False))

    result = normalize_timestamp_columns(apply=apply)

    return jsonify(result.as_dict())
