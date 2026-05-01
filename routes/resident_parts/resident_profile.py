from flask import flash, redirect, render_template, request, url_for, session

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.field_change_logger import log_field_change
from routes.case_management_parts.helpers import placeholder


def _safe_next_url() -> str:
    next_url = (request.form.get("next") or request.args.get("next") or "").strip()

    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url

    return ""


def edit_resident_profile_view(resident_id: int):
    ph = placeholder()
    next_url = _safe_next_url()

    resident = db_fetchone(
        f"""
        SELECT *
        FROM residents
        WHERE id = {ph}
        """,
        (resident_id,),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if request.method == "POST":
        old_phone = resident.get("phone")
        old_birth_year = resident.get("birth_year")

        phone = (request.form.get("phone") or "").strip()
        birth_year = request.form.get("birth_year")

        db_execute(
            f"""
            UPDATE residents
            SET phone = {ph},
                birth_year = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (phone, birth_year or None, utcnow_iso(), resident_id),
        )

        staff_user_id = session.get("staff_user_id")
        shelter = resident.get("shelter")

        try:
            log_field_change(
                entity_type="resident",
                entity_id=resident_id,
                table_name="residents",
                field_name="phone",
                old_value=old_phone,
                new_value=phone,
                changed_by_user_id=staff_user_id,
                shelter=shelter,
                change_reason="profile_edit",
            )

            log_field_change(
                entity_type="resident",
                entity_id=resident_id,
                table_name="residents",
                field_name="birth_year",
                old_value=old_birth_year,
                new_value=birth_year,
                changed_by_user_id=staff_user_id,
                shelter=shelter,
                change_reason="profile_edit",
            )
        except Exception:
            # Do not block user flow if audit logging fails.
            pass

        flash("Resident profile updated.", "ok")
        if next_url:
            return redirect(next_url)
        return redirect(url_for("residents.edit_resident_profile", resident_id=resident_id))

    return render_template(
        "resident_profile_edit.html",
        resident=resident,
        next=next_url,
    )
