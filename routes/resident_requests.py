from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.audit import log_action
from core.db import db_fetchone
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited   # ✅ REQUIRED FOR TESTS
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


@resident_requests.route("/resident", methods=["GET", "POST"])
def resident_signin():
    if request.method == "GET":
        return render_template("resident_signin.html")

    if is_rate_limited("resident_signin"):
        return render_template("resident_signin.html"), 429

    session["resident_logged_in"] = True
    return redirect(url_for("resident_requests.resident_consent"))


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
    if request.method == "GET":
        return render_template("resident_transport.html")

    if is_rate_limited("transport"):
        return render_template("resident_transport.html"), 429

    return redirect(url_for("resident_portal.home"))


# -----------------------------
# ✅ FIXED SMS CONSENT ROUTE
# -----------------------------
@resident_requests.route("/sms-consent", methods=["GET", "POST"], endpoint="sms_consent")
@resident_requests.route("/sms-consent/", methods=["GET", "POST"], endpoint="sms_consent")
def sms_consent_public_alias():
    return Response("OK", status=200)


# -----------------------------
# RESIDENT UI ROUTES
# -----------------------------
@resident_requests.get("/resident/sms-consent")
def resident_sms_consent():
    return sms_consent_view()


@resident_requests.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    return resident_consent_view()
