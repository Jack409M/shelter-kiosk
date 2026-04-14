from __future__ import annotations

from typing import Any

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.db import db_fetchall
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.pass_rules import pass_type_label
from core.resident_portal_service import (
    chi_today_str,
    complete_chore,
    get_today_chores,
    process_notifications,
    process_pass_items,
    process_transport,
)
from core.runtime import init_db


resident_portal = Blueprint(
    "resident_portal",
    __name__,
    url_prefix="/resident",
)


def _resident_session_int(key: str) -> int | None:
    value = session.get(key)
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resident_session_text(key: str) -> str:
    return str(session.get(key) or "").strip()


def _resident_session_context() -> dict[str, Any]:
    return {
        "resident_id": _resident_session_int("resident_id"),
        "shelter": _resident_session_text("resident_shelter"),
        "resident_identifier": _resident_session_text("resident_identifier"),
    }


def _clear_resident_session_and_redirect():
    session.clear()
    flash("Your session ended. Please sign in again.", "error")
    return redirect(url_for("resident_requests.resident_signin"))


def _require_resident_session(*, require_identifier: bool = False):
    context = _resident_session_context()

    if context["resident_id"] is None or not context["shelter"]:
        return None, _clear_resident_session_and_redirect()

    if require_identifier and not context["resident_identifier"]:
        return None, _clear_resident_session_and_redirect()

    return context, None


def _load_recent_pass_items(resident_id: int, shelter: str) -> list[dict[str, Any]]:
    rows = db_fetchall(
        """
        SELECT
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            destination,
            created_at
        FROM resident_passes
        WHERE resident_id = %s
          AND shelter = %s
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (resident_id, shelter),
    )

    for row in rows:
        row["pass_type_label"] = pass_type_label(row.get("pass_type"))

    return rows


def _load_recent_notifications(resident_id: int, shelter: str) -> list[dict[str, Any]]:
    return db_fetchall(
        """
        SELECT
            id,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        FROM resident_notifications
        WHERE resident_id = %s
          AND shelter = %s
        ORDER BY is_read ASC, created_at DESC
        LIMIT 10
        """,
        (resident_id, shelter),
    )


def _load_recent_transport_requests(
    resident_identifier: str,
    shelter: str,
) -> list[dict[str, Any]]:
    if not resident_identifier:
        return []

    return db_fetchall(
        """
        SELECT
            status,
            needed_at,
            destination,
            submitted_at
        FROM transport_requests
        WHERE resident_identifier = %s
          AND shelter = %s
        ORDER BY submitted_at DESC
        LIMIT 10
        """,
        (resident_identifier, shelter),
    )


def _build_home_context(*, resident_id: int, shelter: str, resident_identifier: str) -> dict[str, Any]:
    run_pass_retention_cleanup_for_shelter(shelter)

    raw_pass_items = _load_recent_pass_items(resident_id, shelter)
    raw_notification_items = _load_recent_notifications(resident_id, shelter)
    raw_transport_items = _load_recent_transport_requests(resident_identifier, shelter)

    pass_items, active_pass = process_pass_items(raw_pass_items)
    notification_items = process_notifications(raw_notification_items, resident_id, shelter)
    transport_items = process_transport(raw_transport_items)
    chores = get_today_chores(resident_id)

    return {
        "pass_items": pass_items,
        "notification_items": notification_items,
        "transport_items": transport_items,
        "active_pass": active_pass,
        "chores": chores,
    }


@resident_portal.route("/home")
@require_resident
def home():
    init_db()

    resident_context, redirect_response = _require_resident_session(require_identifier=False)
    if redirect_response is not None:
        return redirect_response

    context = _build_home_context(
        resident_id=resident_context["resident_id"],
        shelter=resident_context["shelter"],
        resident_identifier=resident_context["resident_identifier"],
    )

    return render_template(
        "resident_home.html",
        **context,
    )


@resident_portal.route("/chores", methods=["GET", "POST"])
@require_resident
def resident_chores():
    init_db()

    resident_context, redirect_response = _require_resident_session()
    if redirect_response is not None:
        return redirect_response

    resident_id = resident_context["resident_id"]

    if request.method == "POST":
        assignment_id = str(request.form.get("assignment_id") or "").strip()

        if not assignment_id:
            flash("Missing chore assignment.", "error")
            return redirect(url_for("resident_portal.resident_chores"))

        result = complete_chore(resident_id, assignment_id)

        if not result.found:
            flash("Chore not found.", "error")
        elif result.already_completed:
            flash("Chore was already completed.", "info")
        elif result.completed:
            flash("Chore marked complete.", "success")
        else:
            flash("Chore was not updated.", "info")

        return redirect(url_for("resident_portal.resident_chores"))

    chores = get_today_chores(resident_id)

    return render_template(
        "resident/chores.html",
        chores=chores,
        today=chi_today_str(),
    )
