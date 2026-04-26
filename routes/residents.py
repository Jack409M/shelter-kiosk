from __future__ import annotations

from typing import Any

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import DbRow, db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import get_all_shelters, init_db
from routes.resident_parts.resident_profile import edit_resident_profile_view
from routes.resident_parts.resident_transfer_helpers import (
    apply_cross_shelter_transfer,
    apply_same_shelter_housing_move,
    build_cross_shelter_transfer_flash,
    build_same_shelter_housing_flash,
    extract_resident_transfer_form_data,
    load_resident_transfer_context,
    normalize_shelter_name,
    require_transfer_role,
    row_value,
    validate_resident_transfer_form,
)

residents = Blueprint("residents", __name__)


def _require_staff_or_admin() -> bool:
    return session.get("role") in {"admin", "shelter_director", "staff", "case_manager", "ra"}


def _require_resident_create_role() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _return_redirect(default_endpoint: str = "residents.staff_residents", **default_values: Any):
    next_url = (request.form.get("next") or request.args.get("next") or "").strip()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **default_values))


def _parse_birth_year(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None

    if not text.isdigit():
        return None

    year = int(text)
    if year < 1900 or year > 2100:
        return None

    return year


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        current_app.logger.warning(
            "Invalid staff_user_id in session for residents route: %r",
            raw_staff_user_id,
        )
        return None


def _resident_scope_sql(include_inactive: bool) -> str:
    if include_inactive:
        return """
            SELECT *
            FROM residents
            WHERE LOWER(COALESCE(shelter, '')) = %s
            ORDER BY is_active DESC, last_name ASC, first_name ASC
        """

    return """
        SELECT *
        FROM residents
        WHERE LOWER(COALESCE(shelter, '')) = %s
          AND is_active = TRUE
        ORDER BY last_name ASC, first_name ASC
    """


def _normalize_all_shelter_values() -> None:
    updates = [
        ("residents", "shelter"),
        ("program_enrollments", "shelter"),
        ("transport_requests", "shelter"),
        ("attendance_events", "shelter"),
        ("resident_transfers", "from_shelter"),
        ("resident_transfers", "to_shelter"),
        ("staff_shelter_assignments", "shelter"),
        ("audit_log", "shelter"),
    ]

    for table_name, column_name in updates:
        try:
            db_execute(
                f"""
                UPDATE {table_name}
                SET {column_name} = LOWER(BTRIM({column_name}))
                WHERE {column_name} IS NOT NULL
                  AND {column_name} <> LOWER(BTRIM({column_name}))
                """
            )
        except Exception:
            current_app.logger.exception(
                "Failed to normalize shelter values for %s.%s",
                table_name,
                column_name,
            )


def _ensure_rent_sheet_for_shelter(shelter: str) -> None:
    from routes.rent_tracking_parts.dates import _current_year_month
    from routes.rent_tracking_parts.views import _ensure_sheet_for_month

    try:
        rent_year, rent_month = _current_year_month()
        _ensure_sheet_for_month(shelter, rent_year, rent_month)
    except Exception:
        current_app.logger.exception(
            "Failed to ensure rent sheet for shelter=%s",
            shelter,
        )


def _build_transfer_render_context(context) -> dict[str, Any]:
    return {
        "resident": context.resident,
        "from_shelter": context.from_shelter,
        "shelters": context.shelter_choices,
        "next": context.next_url,
        "current_apartment_number": context.current_apartment_number,
        "current_apartment_size": context.current_apartment_size,
        "apartment_options": context.apartment_options,
        "availability_map": context.availability_map,
    }


def _load_resident_rows(*, shelter: str, show: str) -> list[DbRow]:
    include_inactive = show == "all"
    return db_fetchall(_resident_scope_sql(include_inactive), (shelter,))


def _resident_exists_in_shelter(*, resident_id: int, shelter: str) -> bool:
    row = db_fetchone(
        """
        SELECT id
        FROM residents
        WHERE id = %s
          AND LOWER(COALESCE(shelter, '')) = %s
        """,
        (resident_id, shelter),
    )
    return row is not None


def _create_resident() -> None:
    from core.residents import generate_resident_code, generate_resident_identifier

    shelter = _current_shelter()
    first = (request.form.get("first_name") or "").strip()
    last = (request.form.get("last_name") or "").strip()
    birth_year_raw = request.form.get("birth_year")
    phone = (request.form.get("phone") or "").strip()
    email = (request.form.get("email") or "").strip()
    emergency_contact_name = (request.form.get("emergency_contact_name") or "").strip()
    emergency_contact_relationship = (
        request.form.get("emergency_contact_relationship") or ""
    ).strip()
    emergency_contact_phone = (request.form.get("emergency_contact_phone") or "").strip()
    medical_alerts = (request.form.get("medical_alerts") or "").strip()
    medical_notes = (request.form.get("medical_notes") or "").strip()

    if not first or not last:
        raise ValueError("First and last name required.")

    birth_year = _parse_birth_year(birth_year_raw)
    if birth_year_raw and birth_year is None:
        raise ValueError("Birth year must be a valid 4 digit year.")

    resident_code = generate_resident_code()
    resident_identifier = generate_resident_identifier()

    db_execute(
        """
        INSERT INTO residents (
            resident_identifier,
            resident_code,
            first_name,
            last_name,
            birth_year,
            phone,
            email,
            emergency_contact_name,
            emergency_contact_relationship,
            emergency_contact_phone,
            medical_alerts,
            medical_notes,
            shelter,
            is_active,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_identifier,
            resident_code,
            first,
            last,
            birth_year,
            phone or None,
            email or None,
            emergency_contact_name or None,
            emergency_contact_relationship or None,
            emergency_contact_phone or None,
            medical_alerts or None,
            medical_notes or None,
            shelter,
            True,
            utcnow_iso(),
        ),
    )

    log_action(
        "resident",
        None,
        shelter,
        _staff_user_id(),
        "create",
        (
            f"code={resident_code} "
            f"name={first} {last} "
            f"birth_year={birth_year or ''} "
            f"emergency_contact={emergency_contact_name or ''}"
        ).strip(),
    )


def _handle_same_shelter_move(*, resident_id: int, form, next_url: str):
    apply_same_shelter_housing_move(
        resident_id=resident_id,
        destination_shelter=form.to_shelter,
        apartment_number=form.apartment_number,
    )

    _ensure_rent_sheet_for_shelter(form.to_shelter)

    log_action(
        "resident",
        resident_id,
        form.to_shelter,
        _staff_user_id(),
        "housing_move",
        (
            f"shelter={form.to_shelter} "
            f"apartment={form.apartment_number or ''} "
            f"unit_type={form.apartment_size or ''} "
            f"note={form.note}"
        ).strip(),
    )

    flash(
        build_same_shelter_housing_flash(form.to_shelter, form.apartment_number),
        "ok",
    )
    return _return_redirect()


def _handle_cross_shelter_transfer(*, resident_id: int, context, form):
    from core.residents import record_resident_transfer

    resident_identifier = row_value(context.resident, "resident_identifier", 2, "") or ""

    apply_cross_shelter_transfer(
        resident_id=resident_id,
        resident_identifier=str(resident_identifier),
        from_shelter=context.from_shelter,
        to_shelter=form.to_shelter,
        note=form.note,
        apartment_number=form.apartment_number,
        transfer_recorder=record_resident_transfer,
    )

    _ensure_rent_sheet_for_shelter(form.to_shelter)

    log_action(
        "resident",
        resident_id,
        form.to_shelter,
        _staff_user_id(),
        "transfer",
        (
            f"from={context.from_shelter} "
            f"to={form.to_shelter} "
            f"apartment={form.apartment_number or ''} "
            f"unit_type={form.apartment_size or ''} "
            f"note={form.note}"
        ).strip(),
    )

    flash(
        build_cross_shelter_transfer_flash(
            from_shelter=context.from_shelter,
            to_shelter=form.to_shelter,
            apartment_number=form.apartment_number,
        ),
        "ok",
    )
    return _return_redirect()


def _set_resident_active_status(*, resident_id: int, shelter: str, active: bool) -> None:
    db_execute(
        """
        UPDATE residents
        SET is_active = %s
        WHERE id = %s
          AND LOWER(COALESCE(shelter, '')) = %s
        """,
        (active, resident_id, shelter),
    )


@residents.get("/staff/residents")
@require_login
@require_shelter
def staff_residents():
    if not _require_staff_or_admin():
        flash("Staff only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _normalize_all_shelter_values()

    shelter = _current_shelter()
    show = (request.args.get("show") or "active").strip().lower()
    rows = _load_resident_rows(shelter=shelter, show=show)

    return render_template(
        "staff_residents.html",
        residents=rows,
        shelter=shelter,
        show=show,
    )


@residents.post("/staff/residents")
@require_login
@require_shelter
def staff_residents_post():
    if not _require_resident_create_role():
        flash("Admin, shelter director, or case manager only.", "error")
        return redirect(url_for("residents.staff_residents"))

    init_db()
    _normalize_all_shelter_values()

    try:
        _create_resident()
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("residents.staff_residents"))
    except Exception:
        current_app.logger.exception("Failed to create resident")
        flash("Unable to create resident. Please try again or contact an administrator.", "error")
        return redirect(url_for("residents.staff_residents"))

    flash("Resident created.", "ok")
    return redirect(url_for("residents.staff_residents"))


@residents.route("/staff/residents/<int:resident_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_resident_profile(resident_id: int):
    if not _require_resident_create_role():
        flash("Admin, shelter director, or case manager only.", "error")
        return redirect(url_for("residents.staff_residents"))

    init_db()
    return edit_resident_profile_view(resident_id)


@residents.route("/staff/residents/<int:resident_id>/transfer", methods=["GET", "POST"])
@require_login
@require_shelter
def staff_resident_transfer(resident_id: int):
    if not require_transfer_role():
        flash("Admin, shelter director, or case manager only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _normalize_all_shelter_values()

    all_shelters = [normalize_shelter_name(s) for s in get_all_shelters()]
    current_shelter = _current_shelter()
    next_url = (request.form.get("next") or request.args.get("next") or "").strip()
    destination_shelter_prefill = (
        request.form.get("to_shelter") or request.args.get("to_shelter") or ""
    ).strip().lower() or current_shelter

    context = load_resident_transfer_context(
        resident_id=resident_id,
        current_shelter=current_shelter,
        all_shelters=all_shelters,
        next_url=next_url,
        destination_shelter_prefill=destination_shelter_prefill,
    )

    if not context:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if request.method == "GET":
        return render_template(
            "staff_resident_transfer.html",
            **_build_transfer_render_context(context),
        )

    form = extract_resident_transfer_form_data(context, request.form)
    validation_error = validate_resident_transfer_form(context=context, form=form)

    if validation_error:
        flash(validation_error, "error")
        return redirect(
            url_for(
                "residents.staff_resident_transfer",
                resident_id=resident_id,
                next=next_url,
                to_shelter=form.to_shelter or context.from_shelter,
            )
        )

    try:
        if form.same_shelter_move:
            return _handle_same_shelter_move(
                resident_id=resident_id,
                form=form,
                next_url=next_url,
            )

        return _handle_cross_shelter_transfer(
            resident_id=resident_id,
            context=context,
            form=form,
        )
    except Exception:
        current_app.logger.exception(
            "Resident transfer failed for resident_id=%s from=%s to=%s",
            resident_id,
            context.from_shelter,
            form.to_shelter,
        )
        flash(
            "Unable to complete the resident transfer. Please try again or contact an administrator.",
            "error",
        )
        return redirect(
            url_for(
                "residents.staff_resident_transfer",
                resident_id=resident_id,
                next=next_url,
                to_shelter=form.to_shelter or context.from_shelter,
            )
        )


@residents.post("/staff/residents/<int:resident_id>/set-active")
@require_login
@require_shelter
def staff_resident_set_active(resident_id: int):
    if not _require_staff_or_admin():
        flash("Staff only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _normalize_all_shelter_values()

    shelter = _current_shelter()
    active_raw = (request.form.get("active") or "").strip()

    if active_raw not in {"0", "1"}:
        flash("Invalid action.", "error")
        return _return_redirect()

    if not _resident_exists_in_shelter(resident_id=resident_id, shelter=shelter):
        flash("Resident not found.", "error")
        return _return_redirect()

    try:
        _set_resident_active_status(
            resident_id=resident_id,
            shelter=shelter,
            active=(active_raw == "1"),
        )
    except Exception:
        current_app.logger.exception(
            "Failed to update resident active status for resident_id=%s shelter=%s",
            resident_id,
            shelter,
        )
        flash(
            "Unable to update resident status. Please try again or contact an administrator.",
            "error",
        )
        return _return_redirect()

    log_action(
        "resident",
        resident_id,
        shelter,
        _staff_user_id(),
        "set_active",
        f"active={active_raw}",
    )
    flash("Updated.", "ok")
    return _return_redirect()
