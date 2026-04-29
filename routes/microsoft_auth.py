from __future__ import annotations

from flask import Blueprint, redirect, session, url_for, flash

from core.db import db_fetchone
from core.microsoft_sso import get_microsoft_client, microsoft_sso_enabled
from routes.auth import _load_allowed_shelters_for_user, _set_staff_session

microsoft_auth = Blueprint("microsoft_auth", __name__)


@microsoft_auth.route("/staff/login/microsoft")
def microsoft_login():
    if not microsoft_sso_enabled():
        flash("Microsoft login is not configured.", "error")
        return redirect(url_for("auth.staff_login"))

    client = get_microsoft_client()
    redirect_uri = url_for("microsoft_auth.microsoft_callback", _external=True)
    return client.authorize_redirect(redirect_uri)


@microsoft_auth.route("/staff/auth/microsoft/callback")
def microsoft_callback():
    if not microsoft_sso_enabled():
        return redirect(url_for("auth.staff_login"))

    client = get_microsoft_client()
    token = client.authorize_access_token()

    userinfo = token.get("userinfo")
    if not userinfo:
        # fallback: try id_token parsing
        try:
            userinfo = client.parse_id_token(token)
        except Exception:
            userinfo = {}

    email = (userinfo.get("email") or "").strip().lower()

    if not email:
        flash("Unable to retrieve email from Microsoft.", "error")
        return redirect(url_for("auth.staff_login"))

    row = db_fetchone(
        "SELECT id, username, role FROM staff_users WHERE LOWER(email) = %s",
        (email,),
    )

    if not row:
        flash("No matching staff account found.", "error")
        return redirect(url_for("auth.staff_login"))

    staff_user_id = row["id"]
    staff_username = row["username"]
    staff_role = row["role"]

    allowed_shelters = _load_allowed_shelters_for_user(
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        all_shelters_lower=[],
        all_shelters_lower_set=set(),
    )

    session.clear()

    # if one shelter, auto select, else force selection
    shelter = allowed_shelters[0] if len(allowed_shelters) == 1 else None

    _set_staff_session(
        staff_user_id=staff_user_id,
        staff_username=staff_username,
        staff_role=staff_role,
        shelter=shelter,
        allowed_shelters=allowed_shelters,
    )

    if shelter:
        return redirect(url_for("attendance.staff_attendance"))

    return redirect(url_for("auth.staff_select_shelter"))
