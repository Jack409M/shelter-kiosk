from __future__ import annotations

from typing import Any

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.wrappers import Response

from core.audit import log_action
from core.demo_seed import clear_demo_seed, get_demo_seed_counts, run_demo_seed
from core.runtime import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db
from routes.admin_parts.helpers import require_admin_role as _require_admin


def _confirm_phrase_valid(expected: str) -> bool:
    entered = (request.form.get("confirm_phrase") or "").strip()
    return entered == expected


def _staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        current_app.logger.warning(
            "Invalid staff_user_id in session for admin system route: %r",
            raw_staff_user_id,
        )
        return None


def _require_dangerous_admin_access() -> Response | None:
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    return None


def _redirect_demo_data_view() -> Response:
    return redirect(url_for("admin.admin_demo_data"))


def _handle_invalid_confirm_phrase(expected: str) -> Response:
    current_app.logger.warning(
        "Admin dangerous action blocked due to confirmation phrase mismatch. expected=%s",
        expected,
    )
    flash("Confirmation phrase did not match.", "error")
    return _redirect_demo_data_view()


def _log_demo_action(action_type: str, detail: str) -> None:
    log_action(
        "admin",
        None,
        None,
        _staff_user_id(),
        action_type,
        detail,
    )


def _seed_detail(result: dict[str, Any]) -> str:
    resident_count = int(result.get("resident_count", 0) or 0)
    weeks_per_resident = int(result.get("weeks_per_resident", 0) or 0)
    return f"resident_count={resident_count}\nweeks_per_resident={weeks_per_resident}"


def _clear_detail(result: dict[str, Any]) -> str:
    resident_count = int(result.get("resident_count", 0) or 0)
    return f"resident_count={resident_count}"


def admin_demo_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    init_db()
    counts = get_demo_seed_counts()

    return render_template(
        "admin_demo_data.html",
        demo_counts=counts,
        dangerous_routes_enabled=ENABLE_DANGEROUS_ADMIN_ROUTES,
    )


def seed_demo_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    if request.method != "POST":
        abort(405)

    if not _confirm_phrase_valid("SEED DEMO DATA"):
        return _handle_invalid_confirm_phrase("SEED DEMO DATA")

    init_db()

    try:
        result = run_demo_seed(per_shelter=10, weeks=12)
    except Exception:
        current_app.logger.exception("Admin demo seed failed.")
        flash("Unable to create demo data. Please try again or contact an administrator.", "error")
        return _redirect_demo_data_view()

    _log_demo_action("seed_demo_data", _seed_detail(result))

    resident_count = int(result.get("resident_count", 0) or 0)
    flash(
        f"Demo data created. Added {resident_count} residents.",
        "ok",
    )
    return _redirect_demo_data_view()


def clear_demo_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    if request.method != "POST":
        abort(405)

    if not _confirm_phrase_valid("CLEAR DEMO DATA"):
        return _handle_invalid_confirm_phrase("CLEAR DEMO DATA")

    init_db()

    try:
        result = clear_demo_seed()
    except Exception:
        current_app.logger.exception("Admin demo clear failed.")
        flash("Unable to clear demo data. Please try again or contact an administrator.", "error")
        return _redirect_demo_data_view()

    _log_demo_action("clear_demo_data", _clear_detail(result))

    resident_count = int(result.get("resident_count", 0) or 0)
    flash(
        f"Demo data cleared. Removed {resident_count} residents.",
        "ok",
    )
    return _redirect_demo_data_view()
