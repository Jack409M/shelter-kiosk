from __future__ import annotations

from flask import Blueprint, flash, redirect, session, url_for

from core.db import db_fetchone
from core.microsoft_sso import get_microsoft_client, microsoft_sso_enabled
from core.runtime import get_all_shelters
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


def _load_all_shelter_names() -> tuple[list[str], set[str]]:
    shelters: list[str] = []
    shelter_set: set[str] = set()

    for shelter_name in get_all_shelters():
        cleaned = (shelter_name or "").strip().lower()
        if cleaned and cleaned not in shelter_set:
            shelters.append(cleaned)
            shelter_set.add(cleaned)

    return shelters, shelter_set


def _post_login_redirect_for_role(staff_role: str):
    if staff_role == "admin":
        return redirect(url_for("admin.admin_dashboard"))

    if staff_role == "demographics_viewer":
        return redirect(url_for("reports.reports_index"))

    if staff_role in {"shelter_director", "case_manager"}:
        return redirect(url_for("case_management.index"))

    return redirect(url_for("attendance.staff_attendance"))


@microsoft_auth.route("/staff/auth/microsoft/callback")
def microsoft_callback():
    if not microsoft_sso_enabled():
        return redirect(url_for("auth.staff_login"))

    client = get_microsoft_client()
    token = client.authorize_access_token()

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = client.parse_id_token(token)
        except Exception:
            userinfo = {}

    email = (userinfo.get("email") or "").strip().lower()

    if not email:
        flash("Unable to retrieve email from Microsoft.", "error")
        return redirect(url_for("auth.staff_login"))

    row = db_fetchone(
        "SELECT id, username, role FROM staff_users WHERE LOWER(email) = %s AND is_active = TRUE",
        (email,),
    )

    if not row:
        flash("No active matching staff account found.", "error")
        return redirect(url_for("auth.staff_login"))

    staff_user_id = row["id"]
    staff_username = row["username"]
    staff_role = row["role"]

    all_shelters_lower, all_shelters_lower_set = _load_all_shelter_names()
    allowed_shelters = _load_allowed_shelters_for_user(
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        all_shelters_lower=all_shelters_lower,
        all_shelters_lower_set=all_shelters_lower_set,
    )

    if not allowed_shelters:
        flash("Your account does not have any shelter access assigned. Please contact an administrator.", "error")
        return redirect(url_for("auth.staff_login"))

    session.clear()

    shelter = allowed_shelters[0] if len(allowed_shelters) == 1 else ""

    _set_staff_session(
        staff_user_id=staff_user_id,
        staff_username=staff_username,
        staff_role=staff_role,
        shelter=shelter,
        allowed_shelters=allowed_shelters,
    )

    if not shelter:
        session["post_shelter_redirect"] = _post_login_redirect_for_role(staff_role).location
        return redirect(url_for("auth.staff_select_shelter"))

    return _post_login_redirect_for_role(staff_role)
