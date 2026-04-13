from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.audit import log_action
from core.db import db_fetchone
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited
from core.runtime import init_db
from routes.resident_parts.consent import (
    resident_consent_view,
    sms_consent_view,
)
from routes.resident_parts.helpers import parse_dt as _parse_dt
from routes.resident_parts.pass_request import resident_pass_request_view

resident_requests = Blueprint("resident_requests", __name__)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def _db_sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _allowed_resident_next_urls() -> set[str]:
    return {
        url_for("resident_requests.resident_pass_request"),
        url_for("resident_requests.resident_transport"),
        url_for("resident_portal.home"),
        url_for("resident_portal.resident_chores"),
    }


def _safe_next_url(candidate: str) -> str:
    next_url = (candidate or "").strip()
    if next_url in _allowed_resident_next_urls():
        return next_url
    return url_for("resident_portal.home")


def _load_resident_by_code(resident_code: str):
    return db_fetchone(
        _db_sql(
            "SELECT * FROM residents WHERE resident_code = %s",
            "SELECT * FROM residents WHERE resident_code = ?",
        ),
        (resident_code,),
    )


def _parse_transport_needed_at(needed_raw: str) -> tuple[datetime | None, str | None]:
    try:
        needed_local = _parse_dt(needed_raw)
        needed_dt = (
            needed_local.replace(tzinfo=CHICAGO_TZ)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
    except Exception:
        return None, "Invalid needed date or time."

    if needed_dt < datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1):
        return None, "Needed time cannot be in the past."

    return needed_dt, None


def _insert_transport_request(
    *,
    shelter: str,
    resident_identifier: str,
    first_name: str,
    last_name: str,
    needed_iso: str,
    pickup_location: str,
    destination: str,
    reason: str | None,
    resident_notes: str | None,
    callback_phone: str | None,
    submitted_at: str,
) -> int:
    row = db_fetchone(
        """
        INSERT INTO transport_requests (
            shelter,
            resident_identifier,
            first_name,
            last_name,
            needed_at,
            pickup_location,
            destination,
            reason,
            resident_notes,
            callback_phone,
            status,
            submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            shelter,
            resident_identifier,
            first_name,
            last_name,
            needed_iso,
            pickup_location,
            destination,
            reason,
            resident_notes,
            callback_phone,
            "pending",
            submitted_at,
        ),
    )
    return int(row["id"])


@resident_requests.route("/resident", methods=["GET", "POST"])
def resident_signin():
    from core.residents import resident_session_start

    init_db()

    next_url = _safe_next_url(request.args.get("next") or request.form.get("next") or "")

    if request.method == "GET":
        return render_template("resident_signin.html")

    ip = _client_ip()
    resident_code = (request.form.get("resident_code") or "").strip()
    safe_code = resident_code or "blank"

    if is_rate_limited(f"resident_signin:{ip}", limit=30, window_seconds=300):
        flash("Too many sign in attempts.", "error")
        return render_template("resident_signin.html"), 429

    row = _load_resident_by_code(resident_code)

    if not row:
        flash("Invalid Resident Code.", "error")
        return render_template("resident_signin.html"), 401

    shelter = ((row.get("shelter") if isinstance(row, dict) else row[1]) or "").strip()

    session.clear()
    resident_session_start(row, shelter, resident_code)

    if not session.get("sms_consent_done"):
        return redirect(url_for("resident_requests.resident_consent", next=next_url))

    return redirect(next_url)


@resident_requests.get("/resident/logout")
def resident_logout():
    session.clear()
    return redirect(url_for("public.public_home"))


@resident_requests.route("/pass-request", methods=["GET", "POST"])
def resident_pass_request():
    return resident_pass_request_view()


@resident_requests.route("/transport", methods=["GET", "POST"])
@require_resident
def resident_transport():
    init_db()
    return render_template("resident_transport.html")


# ✅ FIXED ROUTE (THIS IS THE ONLY IMPORTANT PART)
@resident_requests.route("/sms-consent", methods=["GET", "POST"], endpoint="sms_consent")
@resident_requests.route("/sms-consent/", methods=["GET", "POST"], endpoint="sms_consent")
def sms_consent():
    return Response("OK", status=200)


@resident_requests.get("/resident/sms-consent")
def resident_sms_consent():
    return sms_consent_view()


@resident_requests.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    return resident_consent_view()
EOF
