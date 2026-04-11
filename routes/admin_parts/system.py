from __future__ import annotations

from flask import abort, flash, render_template, request, session, url_for, redirect

from core.audit import log_action
from core.demo_seed import clear_demo_seed, get_demo_seed_counts, run_demo_seed
from core.runtime import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db
from routes.admin_parts.helpers import require_admin_role as _require_admin


# ------------------------------------------------------------
# Dangerous Admin System Operations
# ------------------------------------------------------------
# These routes are intentionally limited to demo data operations.
# Full destructive database wipe and schema recreation routes were
# removed on purpose and can be rewritten later if ever needed.
# ------------------------------------------------------------


def _confirm_phrase_valid(expected: str) -> bool:
    entered = (request.form.get("confirm_phrase") or "").strip()
    return entered == expected


def _require_dangerous_admin_access():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    return None


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
        flash("Confirmation phrase did not match.", "error")
        return redirect(url_for("admin.admin_demo_data"))

    init_db()

    try:
        result = run_demo_seed(per_shelter=10, weeks=12)
    except Exception as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_demo_data"))

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "seed_demo_data",
        (
            f"resident_count={result.get('resident_count', 0)}\n"
            f"weeks_per_resident={result.get('weeks_per_resident', 0)}"
        ),
    )

    flash(
        f"Demo data created. Added {result.get('resident_count', 0)} residents.",
        "ok",
    )
    return redirect(url_for("admin.admin_demo_data"))


def clear_demo_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    if request.method != "POST":
        abort(405)

    if not _confirm_phrase_valid("CLEAR DEMO DATA"):
        flash("Confirmation phrase did not match.", "error")
        return redirect(url_for("admin.admin_demo_data"))

    init_db()

    try:
        result = clear_demo_seed()
    except Exception as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_demo_data"))

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "clear_demo_data",
        f"resident_count={result.get('resident_count', 0)}",
    )

    flash(
        f"Demo data cleared. Removed {result.get('resident_count', 0)} residents.",
        "ok",
    )
    return redirect(url_for("admin.admin_demo_data"))
