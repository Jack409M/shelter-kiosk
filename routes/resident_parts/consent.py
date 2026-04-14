from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited
from core.runtime import init_db

# Resident SMS consent flows
#
# Future extraction note
# If this area grows, split into:
# public_consent_pages.py
# resident_consent_flow.py


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def sms_consent_public_alias_view():
    return redirect(url_for("resident_requests.sms_consent"), code=302)


def sms_consent_public_alias_slash_view():
    return redirect(url_for("resident_requests.sms_consent_public_alias"), code=301)


def sms_consent_view():
    privacy_url = url_for("public.privacy_policy")
    terms_url = url_for("public.terms_and_conditions")

    return f"""
    <html>
        <head>
            <title>SMS Consent - Downtown Women’s Center</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
            <h2>SMS Updates from Downtown Women’s Center</h2>

            <p>
                SMS updates are available for current Downtown Women’s Center residents regarding
                shelter leave approvals, transportation notifications, and service reminders.
            </p>

            <p>
                To receive SMS updates, a resident must complete the resident sign in and consent flow
                through the DWC resident portal.
            </p>

            <p>
                Message frequency varies. Message and data rates may apply.
                Reply STOP to opt out. Reply HELP for help.
            </p>

            <p>
                <a href="{privacy_url}">Privacy Policy</a><br>
                <a href="{terms_url}">Terms and Conditions</a>
            </p>
        </body>
    </html>
    """


def resident_consent_view():
    init_db()

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    allowed_next = {
        url_for("resident_requests.resident_pass_request"),
        url_for("resident_requests.resident_transport"),
        url_for("resident_portal.home"),
        url_for("resident_portal.resident_chores"),
    }

    if next_url not in allowed_next:
        next_url = url_for("resident_portal.home")

    resident_id = session.get("resident_id")
    resident_identifier = (session.get("resident_identifier") or "").strip()
    shelter = (session.get("resident_shelter") or "").strip()

    if not resident_id or not shelter:
        flash("Please sign in again.", "error")
        return redirect(url_for("resident_requests.resident_signin", next=next_url))

    if request.method == "GET":
        return render_template("resident_consent.html", next=next_url)

    ip = _client_ip()
    rl_key = f"resident_consent:{ip}:{resident_identifier or resident_id}"
    if is_rate_limited(rl_key, limit=10, window_seconds=300):
        flash("Too many consent attempts. Please wait a few minutes and try again.", "error")
        return render_template("resident_consent.html", next=next_url), 429

    choice = (request.form.get("choice") or "").strip().lower()
    if choice not in ["accept", "decline"]:
        flash("Select accept or decline.", "error")
        return render_template("resident_consent.html", next=next_url), 400

    now = utcnow_iso()
    kind = g.get("db_kind")

    if choice == "accept":
        session["sms_consent_done"] = True
        session["sms_opt_in"] = True

        db_execute(
            """
            UPDATE residents
            SET sms_opt_in = %s, sms_opt_in_at = %s
            WHERE id = %s
            """
            if kind == "pg"
            else """
            UPDATE residents
            SET sms_opt_in = ?, sms_opt_in_at = ?
            WHERE id = ?
            """,
            (True, now, resident_id),
        )

        log_action(
            "resident", resident_id, shelter, None, "sms_opt_in", "Resident accepted SMS consent"
        )
        flash("Thank you. SMS consent recorded.", "ok")
        return redirect(next_url)

    session["sms_consent_done"] = True
    session["sms_opt_in"] = False

    db_execute(
        """
        UPDATE residents
        SET sms_opt_in = %s, sms_opt_in_at = NULL
        WHERE id = %s
        """
        if kind == "pg"
        else """
        UPDATE residents
        SET sms_opt_in = ?, sms_opt_in_at = NULL
        WHERE id = ?
        """,
        (False, resident_id),
    )

    log_action(
        "resident", resident_id, shelter, None, "sms_opt_out", "Resident declined SMS consent"
    )
    flash("Preference saved.", "ok")
    return redirect(next_url)
