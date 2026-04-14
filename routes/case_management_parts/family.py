from __future__ import annotations

from datetime import datetime

from flask import current_app, flash, g, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.runtime import init_db
from db.schema_people import ensure_resident_child_income_supports_table
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.intake_income_support import recalculate_intake_income_support


def _deny_case_manager_access():
    flash("Case manager access required.", "error")
    return redirect(url_for("attendance.staff_attendance"))


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _child_services_redirect(child_id: int):
    return redirect(url_for("case_management.child_services", child_id=child_id))


def _edit_child_redirect(child_id: int):
    return redirect(url_for("case_management.edit_child", child_id=child_id))


def _edit_child_service_redirect(service_id: int):
    return redirect(url_for("case_management.edit_child_service", service_id=service_id))


def _family_intake_redirect(resident_id: int):
    return redirect(url_for("case_management.family_intake", resident_id=resident_id))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _quick_add_requested() -> bool:
    return (request.form.get("redirect_to") or "").strip().lower() == "resident_case"


def _post_child_service_redirect(child_id: int, resident_id: int):
    if _quick_add_requested():
        return _resident_case_redirect(resident_id)
    return _child_services_redirect(child_id)


def _ensure_family_income_support_schema() -> None:
    ensure_resident_child_income_supports_table(g.get("db_kind"))


def _prepare_family_request():
    if not case_manager_allowed():
        return _deny_case_manager_access()

    init_db()
    _ensure_family_income_support_schema()
    return None


def _render_family_intake(resident_id: int):
    children = _active_children_for_resident(resident_id)
    return render_template(
        "case_management/family_intake.html",
        resident_id=resident_id,
        children=children,
    )


def _render_child_services(child_id: int, resident_id: int, services):
    return render_template(
        "case_management/child_services.html",
        child_id=child_id,
        resident_id=resident_id,
        services=services,
    )


def _resident_in_scope(resident_id: int):
    ph = placeholder()
    shelter = _current_shelter()

    return db_fetchone(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.shelter
        FROM residents r
        WHERE r.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )


def _child_in_scope(child_id: int):
    ph = placeholder()
    shelter = _current_shelter()

    child = db_fetchone(
        f"""
        SELECT
            rc.id,
            rc.resident_id,
            rc.child_name,
            rc.birth_year,
            rc.relationship,
            rc.living_status,
            rc.receives_survivor_benefit,
            rc.survivor_benefit_amount,
            rc.survivor_benefit_notes,
            rc.is_active
        FROM resident_children rc
        JOIN residents r
          ON r.id = rc.resident_id
        WHERE rc.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (child_id, shelter),
    )

    if not child:
        return None

    child["income_supports"] = _load_child_income_supports(child_id)
    return child


def _child_service_in_scope(service_id: int):
    ph = placeholder()
    shelter = _current_shelter()

    return db_fetchone(
        f"""
        SELECT
            cs.id,
            cs.resident_child_id,
            cs.enrollment_id,
            cs.service_date,
            cs.service_type,
            cs.outcome,
            cs.quantity,
            cs.unit,
            cs.notes,
            rc.resident_id
        FROM child_services cs
        JOIN resident_children rc
          ON rc.id = cs.resident_child_id
        JOIN residents r
          ON r.id = rc.resident_id
        WHERE cs.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (service_id, shelter),
    )


def _load_child_income_supports(child_id: int):
    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            id,
            child_id,
            support_type,
            monthly_amount,
            notes,
            is_active,
            created_at,
            updated_at
        FROM resident_child_income_supports
        WHERE child_id = {ph}
          AND COALESCE(is_active, TRUE) = TRUE
        ORDER BY
            CASE
                WHEN support_type = 'survivor_benefit' THEN 1
                WHEN support_type = 'child_support' THEN 2
                ELSE 9
            END,
            id ASC
        """,
        (child_id,),
    )

    return rows or []


def _active_children_for_resident(resident_id: int):
    ph = placeholder()

    children = db_fetchall(
        f"""
        SELECT
            id,
            resident_id,
            child_name,
            birth_year,
            relationship,
            living_status,
            receives_survivor_benefit,
            survivor_benefit_amount,
            survivor_benefit_notes
        FROM resident_children
        WHERE resident_id = {ph}
          AND is_active = TRUE
        ORDER BY id ASC
        """,
        (resident_id,),
    )

    for child in children or []:
        child["income_supports"] = _load_child_income_supports(child["id"])

    return children


def _load_child_services(child_id: int):
    ph = placeholder()

    return db_fetchall(
        f"""
        SELECT
            id,
            service_date,
            service_type,
            quantity,
            unit,
            outcome,
            notes
        FROM child_services
        WHERE resident_child_id = {ph}
          AND COALESCE(is_deleted, FALSE) = FALSE
        ORDER BY service_date DESC, id DESC
        """,
        (child_id,),
    )


def _latest_enrollment_for_resident(resident_id: int):
    return fetch_current_enrollment_for_resident(resident_id, columns="id")


def _recalculate_current_enrollment_income_support(resident_id: int) -> None:
    enrollment = _latest_enrollment_for_resident(resident_id)
    if not enrollment:
        return

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
    recalculate_intake_income_support(enrollment_id)


def _parse_service_date(value: str | None) -> str | None:
    cleaned_value = clean(value)
    if not cleaned_value:
        return None

    try:
        datetime.fromisoformat(cleaned_value)
    except ValueError:
        return None

    return cleaned_value


def _is_unique_constraint_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message


def _resolve_child_service_type(form) -> str | None:
    service_type = clean(form.get("service_type"))
    service_type_other = clean(form.get("service_type_other"))

    if service_type and service_type.lower() == "other":
        return service_type_other or service_type

    if service_type_other and not service_type:
        return service_type_other

    return service_type


def _yes_no_to_bool(value: str | None):
    normalized = (value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _child_form_values(form) -> dict:
    return {
        "child_name": clean(form.get("child_name")),
        "birth_year": parse_int(form.get("birth_year")),
        "relationship": clean(form.get("relationship")),
        "living_status": clean(form.get("living_status")),
        "receives_survivor_benefit": _yes_no_to_bool(form.get("receives_survivor_benefit")),
        "survivor_benefit_amount": parse_money(form.get("survivor_benefit_amount")),
        "survivor_benefit_notes": clean(form.get("survivor_benefit_notes")),
        "child_support_amount": parse_money(form.get("child_support_amount")),
        "child_support_notes": clean(form.get("child_support_notes")),
    }


def _child_service_form_values(form) -> dict:
    requested_service_date = form.get("service_date")

    return {
        "service_type": _resolve_child_service_type(form),
        "outcome": clean(form.get("outcome")),
        "quantity": parse_int(form.get("quantity")),
        "unit": clean(form.get("unit")),
        "notes": clean(form.get("notes")),
        "service_date_input": requested_service_date,
        "service_date": _parse_service_date(requested_service_date),
    }


def _find_existing_child(*, resident_id: int, child_name: str, birth_year, exclude_child_id: int | None = None):
    ph = placeholder()

    sql = f"""
        SELECT id
        FROM resident_children
        WHERE resident_id = {ph}
          AND LOWER(child_name) = LOWER({ph})
          AND (
                (birth_year IS NULL AND {ph} IS NULL)
                OR birth_year = {ph}
              )
          AND is_active = TRUE
    """

    params = [
        resident_id,
        child_name,
        birth_year,
        birth_year,
    ]

    if exclude_child_id is not None:
        sql += f"\n          AND id <> {ph}"
        params.append(exclude_child_id)

    sql += "\n        LIMIT 1"

    return db_fetchone(sql, tuple(params))


def _load_newly_created_child_id(*, resident_id: int, child_name: str, birth_year):
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT id
        FROM resident_children
        WHERE resident_id = {ph}
          AND LOWER(child_name) = LOWER({ph})
          AND (
                (birth_year IS NULL AND {ph} IS NULL)
                OR birth_year = {ph}
              )
          AND is_active = TRUE
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            resident_id,
            child_name,
            birth_year,
            birth_year,
        ),
    )

    if not row:
        return None

    return row["id"]


def _upsert_child_income_support(child_id: int, support_type: str, monthly_amount, notes: str | None) -> None:
    ph = placeholder()
    now = _utc_now_iso()

    existing = db_fetchone(
        f"""
        SELECT id
        FROM resident_child_income_supports
        WHERE child_id = {ph}
          AND support_type = {ph}
          AND COALESCE(is_active, TRUE) = TRUE
        ORDER BY id DESC
        LIMIT 1
        """,
        (child_id, support_type),
    )

    normalized_notes = (notes or "").strip() or None
    has_value = monthly_amount not in (None, "", 0, 0.0) or bool(normalized_notes)

    if not has_value:
        if existing:
            db_execute(
                f"""
                UPDATE resident_child_income_supports
                SET
                    is_active = FALSE,
                    updated_at = {ph}
                WHERE id = {ph}
                """,
                (now, existing["id"]),
            )
        return

    if existing:
        db_execute(
            f"""
            UPDATE resident_child_income_supports
            SET
                monthly_amount = {ph},
                notes = {ph},
                is_active = TRUE,
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                monthly_amount,
                normalized_notes,
                now,
                existing["id"],
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO resident_child_income_supports
        (
            child_id,
            support_type,
            monthly_amount,
            notes,
            is_active,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph},
            {ph},
            {ph},
            {ph},
            TRUE,
            {ph},
            {ph}
        )
        """,
        (
            child_id,
            support_type,
            monthly_amount,
            normalized_notes,
            now,
            now,
        ),
    )


def _sync_child_support_records(
    child_id: int,
    receives_survivor_benefit,
    survivor_benefit_amount,
    survivor_benefit_notes,
    child_support_amount,
    child_support_notes,
) -> None:
    _upsert_child_income_support(
        child_id=child_id,
        support_type="survivor_benefit",
        monthly_amount=survivor_benefit_amount if receives_survivor_benefit else None,
        notes=survivor_benefit_notes,
    )
    _upsert_child_income_support(
        child_id=child_id,
        support_type="child_support",
        monthly_amount=child_support_amount,
        notes=child_support_notes,
    )


def _insert_child(*, resident_id: int, values: dict) -> None:
    ph = placeholder()
    now = _utc_now_iso()

    db_execute(
        f"""
        INSERT INTO resident_children
        (
            resident_id,
            child_name,
            birth_year,
            relationship,
            living_status,
            receives_survivor_benefit,
            survivor_benefit_amount,
            survivor_benefit_notes,
            is_active,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            TRUE,
            {ph},
            {ph}
        )
        """,
        (
            resident_id,
            values["child_name"],
            values["birth_year"],
            values["relationship"],
            values["living_status"],
            values["receives_survivor_benefit"],
            values["survivor_benefit_amount"],
            values["survivor_benefit_notes"],
            now,
            now,
        ),
    )


def _update_child(*, child_id: int, values: dict) -> None:
    ph = placeholder()

    db_execute(
        f"""
        UPDATE resident_children
        SET
            child_name = {ph},
            birth_year = {ph},
            relationship = {ph},
            living_status = {ph},
            receives_survivor_benefit = {ph},
            survivor_benefit_amount = {ph},
            survivor_benefit_notes = {ph},
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            values["child_name"],
            values["birth_year"],
            values["relationship"],
            values["living_status"],
            values["receives_survivor_benefit"],
            values["survivor_benefit_amount"],
            values["survivor_benefit_notes"],
            _utc_now_iso(),
            child_id,
        ),
    )


def _soft_delete_child(child_id: int) -> None:
    ph = placeholder()
    now = _utc_now_iso()

    db_execute(
        f"""
        UPDATE resident_children
        SET
            is_active = FALSE,
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            now,
            child_id,
        ),
    )

    db_execute(
        f"""
        UPDATE resident_child_income_supports
        SET
            is_active = FALSE,
            updated_at = {ph}
        WHERE child_id = {ph}
          AND COALESCE(is_active, TRUE) = TRUE
        """,
        (
            now,
            child_id,
        ),
    )


def _insert_child_service(*, child_id: int, enrollment_id: int, values: dict) -> None:
    ph = placeholder()
    now = _utc_now_iso()

    db_execute(
        f"""
        INSERT INTO child_services
        (
            resident_child_id,
            enrollment_id,
            service_date,
            service_type,
            outcome,
            quantity,
            unit,
            notes,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph}
        )
        """,
        (
            child_id,
            enrollment_id,
            values["service_date"] or now,
            values["service_type"],
            values["outcome"],
            values["quantity"],
            values["unit"],
            values["notes"],
            now,
            now,
        ),
    )


def _update_child_service(*, service_id: int, values: dict) -> None:
    ph = placeholder()

    db_execute(
        f"""
        UPDATE child_services
        SET
            service_type = {ph},
            outcome = {ph},
            quantity = {ph},
            unit = {ph},
            notes = {ph},
            service_date = {ph},
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            values["service_type"],
            values["outcome"],
            values["quantity"],
            values["unit"],
            values["notes"],
            values["service_date"],
            _utc_now_iso(),
            service_id,
        ),
    )


def _soft_delete_child_service(service_id: int) -> None:
    ph = placeholder()
    now = _utc_now_iso()

    db_execute(
        f"""
        UPDATE child_services
        SET
            is_deleted = TRUE,
            deleted_at = {ph},
            deleted_by_staff_user_id = {ph},
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            now,
            session.get("staff_user_id"),
            now,
            service_id,
        ),
    )


def family_intake_view(resident_id: int):
    denied = _prepare_family_request()
    if denied is not None:
        return denied

    resident = _resident_in_scope(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if request.method != "POST":
        return _render_family_intake(resident_id)

    values = _child_form_values(request.form)

    if not values["child_name"]:
        flash("Child name is required.", "error")
        return _render_family_intake(resident_id)

    existing_child = _find_existing_child(
        resident_id=resident_id,
        child_name=values["child_name"],
        birth_year=values["birth_year"],
    )
    if existing_child:
        flash("This child already exists for this resident.", "error")
        return _render_family_intake(resident_id)

    try:
        _insert_child(resident_id=resident_id, values=values)

        child_id = _load_newly_created_child_id(
            resident_id=resident_id,
            child_name=values["child_name"],
            birth_year=values["birth_year"],
        )
        if child_id is not None:
            _sync_child_support_records(
                child_id=child_id,
                receives_survivor_benefit=values["receives_survivor_benefit"],
                survivor_benefit_amount=values["survivor_benefit_amount"],
                survivor_benefit_notes=values["survivor_benefit_notes"],
                child_support_amount=values["child_support_amount"],
                child_support_notes=values["child_support_notes"],
            )

        _recalculate_current_enrollment_income_support(resident_id)
    except Exception as exc:
        if _is_unique_constraint_error(exc):
            flash("This child already exists for this resident.", "error")
            return _render_family_intake(resident_id)

        current_app.logger.exception(
            "Failed to add child for resident_id=%s",
            resident_id,
        )
        flash("Unable to add child. Please try again or contact an administrator.", "error")
        return _render_family_intake(resident_id)

    flash("Child added.", "success")
    return _resident_case_redirect(resident_id)


def edit_child_view(child_id: int):
    denied = _prepare_family_request()
    if denied is not None:
        return denied

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]

    if request.method != "POST":
        return render_template(
            "case_management/edit_child.html",
            child=child,
        )

    values = _child_form_values(request.form)

    if not values["child_name"]:
        flash("Child name is required.", "error")
        return _edit_child_redirect(child_id)

    existing_child = _find_existing_child(
        resident_id=resident_id,
        child_name=values["child_name"],
        birth_year=values["birth_year"],
        exclude_child_id=child_id,
    )
    if existing_child:
        flash("This child already exists for this resident.", "error")
        return _edit_child_redirect(child_id)

    try:
        _update_child(child_id=child_id, values=values)
        _sync_child_support_records(
            child_id=child_id,
            receives_survivor_benefit=values["receives_survivor_benefit"],
            survivor_benefit_amount=values["survivor_benefit_amount"],
            survivor_benefit_notes=values["survivor_benefit_notes"],
            child_support_amount=values["child_support_amount"],
            child_support_notes=values["child_support_notes"],
        )
        _recalculate_current_enrollment_income_support(resident_id)
    except Exception as exc:
        if _is_unique_constraint_error(exc):
            flash("This child already exists for this resident.", "error")
            return _edit_child_redirect(child_id)

        current_app.logger.exception(
            "Failed to edit child_id=%s resident_id=%s",
            child_id,
            resident_id,
        )
        flash("Unable to update child. Please try again or contact an administrator.", "error")
        return _edit_child_redirect(child_id)

    flash("Child updated.", "success")
    return _resident_case_redirect(resident_id)


def delete_child_view(child_id: int):
    denied = _prepare_family_request()
    if denied is not None:
        return denied

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]

    try:
        _soft_delete_child(child_id)
        _recalculate_current_enrollment_income_support(resident_id)
    except Exception:
        current_app.logger.exception(
            "Failed to delete child_id=%s resident_id=%s",
            child_id,
            resident_id,
        )
        flash("Unable to remove child. Please try again or contact an administrator.", "error")
        return _family_intake_redirect(resident_id)

    flash("Child removed.", "success")
    return _resident_case_redirect(resident_id)


def child_services_view(child_id: int):
    denied = _prepare_family_request()
    if denied is not None:
        return denied

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]
    enrollment = _latest_enrollment_for_resident(resident_id)

    if not enrollment:
        flash("No active enrollment found.", "error")
        return _resident_case_redirect(resident_id)

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    if request.method != "POST":
        services = _load_child_services(child_id)
        return _render_child_services(child_id, resident_id, services)

    values = _child_service_form_values(request.form)

    if values["service_date_input"] and not values["service_date"]:
        flash("Service date must be valid.", "error")
        return _post_child_service_redirect(child_id, resident_id)

    try:
        _insert_child_service(
            child_id=child_id,
            enrollment_id=enrollment_id,
            values=values,
        )
    except Exception:
        current_app.logger.exception(
            "Failed to add child service for child_id=%s resident_id=%s enrollment_id=%s",
            child_id,
            resident_id,
            enrollment_id,
        )
        flash("Unable to add child service. Please try again or contact an administrator.", "error")
        return _post_child_service_redirect(child_id, resident_id)

    flash("Child service added.", "success")
    return _resident_case_redirect(resident_id)


def edit_child_service_view(service_id: int):
    denied = _prepare_family_request()
    if denied is not None:
        return denied

    service = _child_service_in_scope(service_id)
    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    child_id = service["resident_child_id"]
    resident_id = service["resident_id"]

    if request.method != "POST":
        return render_template(
            "case_management/edit_child_service.html",
            service=service,
            resident_id=resident_id,
        )

    values = _child_service_form_values(request.form)

    if values["service_date_input"] and not values["service_date"]:
        flash("Service date must be valid.", "error")
        return _edit_child_service_redirect(service_id)

    try:
        _update_child_service(service_id=service_id, values=values)
    except Exception:
        current_app.logger.exception(
            "Failed to edit child service_id=%s resident_id=%s",
            service_id,
            resident_id,
        )
        flash("Unable to update child service. Please try again or contact an administrator.", "error")
        return _edit_child_service_redirect(service_id)

    flash("Service updated.", "success")
    return _resident_case_redirect(resident_id)


def delete_child_service_view(service_id: int):
    denied = _prepare_family_request()
    if denied is not None:
        return denied

    service = _child_service_in_scope(service_id)
    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    child_id = service["resident_child_id"]
    resident_id = service["resident_id"]

    try:
        _soft_delete_child_service(service_id)
    except Exception:
        current_app.logger.exception(
            "Failed to delete child service_id=%s child_id=%s",
            service_id,
            child_id,
        )
        flash("Unable to remove child service. Please try again or contact an administrator.", "error")
        return _child_services_redirect(child_id)

    flash("Service deleted.", "success")
    return _resident_case_redirect(resident_id)
