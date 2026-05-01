from __future__ import annotations

from flask import abort, current_app, jsonify, render_template, request, session

from core.timestamp_normalization import normalize_timestamp_columns


def _require_admin() -> None:
    if session.get("role") != "admin":
        abort(403)


def timestamp_cleanup_page_view():
    _require_admin()
    return render_template("admin_timestamp_cleanup.html", title="Timestamp Data Cleanup")


def run_timestamp_cleanup():
    _require_admin()

    apply = str(request.form.get("apply") or "").strip().lower() in {"1", "true", "yes"}
    result = normalize_timestamp_columns(apply=apply)

    current_app.logger.info(
        "timestamp_cleanup_run staff_id=%s staff_name=%s applied=%s scanned=%s would_update=%s updated=%s skipped=%s",
        session.get("staff_user_id"),
        session.get("username"),
        apply,
        result.scanned,
        result.would_update,
        result.updated,
        result.skipped,
    )

    return jsonify(result.as_dict())
