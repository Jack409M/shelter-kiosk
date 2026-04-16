from __future__ import annotations

from datetime import datetime

from flask import current_app, flash, g, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.runtime import init_db
from db.schema_people import ensure_resident_child_income_supports_table
from routes.case_management_parts.family_validation import (
    validate_child_form,
    validate_child_service_form,
)
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    fetch_current_enrollment_for_resident,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)
from routes.case_management_parts.income_state_sync import recalculate_and_sync_income_state_atomic


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _quick_add_requested() -> bool:
    return (request.form.get("redirect_to") or "").strip().lower() == "resident_case"


def _child_services_redirect(child_id: int):
    return redirect(url_for("case_management.child_services", child_id=child_id))


def _post_child_service_redirect(child_id: int, resident_id: int):
    if _quick_add_requested():
        return _resident_case_redirect(resident_id)
    return _child_services_redirect(child_id)


def _ensure_family_income_support_schema() -> None:
    ensure_resident_child_income_supports_table(g.get("db_kind"))


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


def _latest_enrollment_for_resident(resident_id: int, shelter: str):
    return fetch_current_enrollment_for_resident(
        resident_id,
        shelter=shelter,
        columns="id",
    )


def _recalculate_current_enrollment_income_support(resident_id: int) -> None:
    shelter = _current_shelter()
    enrollment = _latest_enrollment_for_resident(resident_id, shelter)
    if not enrollment:
        return
    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
    recalculate_and_sync_income_state_atomic(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
    )


def _is_unique_constraint_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message


def _upsert_child_income_support(
    child_id: int, support_type: str, monthly_amount, notes: str | None
) -> None:
    ph = placeholder()
    now = datetime.utcnow().isoformat()

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

    has_value = monthly_amount not in (None, "", 0, 0.0) or bool((notes or "").strip())

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
                (notes or "").strip() or None,
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
            (notes or "").strip() or None,
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


def _render_family_intake_error(resident_id: int, message: str):
    children = _active_children_for_resident(resident_id)
    flash(message, "error")
    return render_template(
        "case_management/family_intake.html",
        resident_id=resident_id,
        children=children,
    )


def family_intake_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_family_income_support_schema()

    resident = _resident_in_scope(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    if request.method == "POST":
        validated, errors = validate_child_form(request.form)

        if errors:
            for error in errors:
                flash(error, "error")
            children = _active_children_for_resident(resident_id)
            return render_template(
                "case_management/family_intake.html",
                resident_id=resident_id,
                children=children,
            )

        existing_child = db_fetchone(
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
            LIMIT 1
            """,
            (
                resident_id,
                validated["child_name"],
                validated["birth_year"],
                validated["birth_year"],
            ),
        )

        if existing_child:
            return _render_family_intake_error(
                resident_id,
                "This child already exists for this resident.",
            )

        now = datetime.utcnow().isoformat()

        try:
            with db_transaction():
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
                        validated["child_name"],
                        validated["birth_year"],
                        validated["relationship"],
                        validated["living_status"],
                        validated["receives_survivor_benefit"],
                        validated["survivor_benefit_amount"],
                        validated["survivor_benefit_notes"],
                        now,
                        now,
                    ),
                )

                child_row = db_fetchone(
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
                        validated["child_name"],
                        validated["birth_year"],
                        validated["birth_year"],
                    ),
                )

                if child_row:
                    _sync_child_support_records(
                        child_id=child_row["id"],
                        receives_survivor_benefit=validated["receives_survivor_benefit"],
                        survivor_benefit_amount=validated["survivor_benefit_amount"],
                        survivor_benefit_notes=validated["survivor_benefit_notes"],
                        child_support_amount=validated["child_support_amount"],
                        child_support_notes=validated["child_support_notes"],
                    )

                _recalculate_current_enrollment_income_support(resident_id)
        except Exception as exc:
            if _is_unique_constraint_error(exc):
                return _render_family_intake_error(
                    resident_id,
                    "This child already exists for this resident.",
                )

            current_app.logger.exception(
                "Failed to add child for resident_id=%s",
                resident_id,
            )
            return _render_family_intake_error(
                resident_id,
                "Unable to add child. Please try again or contact an administrator.",
            )

        flash("Child added.", "success")
        return _resident_case_redirect(resident_id)

    children = _active_children_for_resident(resident_id)

    return render_template(
        "case_management/family_intake.html",
        resident_id=resident_id,
        children=children,
    )


def edit_child_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_family_income_support_schema()

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]

    if request.method == "POST":
        validated, errors = validate_child_form(request.form)

        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("case_management.edit_child", child_id=child_id))

        ph = placeholder()
        existing_child = db_fetchone(
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
              AND id <> {ph}
            LIMIT 1
            """,
            (
                resident_id,
                validated["child_name"],
                validated["birth_year"],
                validated["birth_year"],
                child_id,
            ),
        )

        if existing_child:
            flash("This child already exists for this resident.", "error")
            return redirect(url_for("case_management.edit_child", child_id=child_id))

        try:
            with db_transaction():
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
                        validated["child_name"],
                        validated["birth_year"],
                        validated["relationship"],
                        validated["living_status"],
                        validated["receives_survivor_benefit"],
                        validated["survivor_benefit_amount"],
                        validated["survivor_benefit_notes"],
                        datetime.utcnow().isoformat(),
                        child_id,
                    ),
                )

                _sync_child_support_records(
                    child_id=child_id,
                    receives_survivor_benefit=validated["receives_survivor_benefit"],
                    survivor_benefit_amount=validated["survivor_benefit_amount"],
                    survivor_benefit_notes=validated["survivor_benefit_notes"],
                    child_support_amount=validated["child_support_amount"],
                    child_support_notes=validated["child_support_notes"],
                )

                _recalculate_current_enrollment_income_support(resident_id)
        except Exception as exc:
            if _is_unique_constraint_error(exc):
                flash("This child already exists for this resident.", "error")
                return redirect(url_for("case_management.edit_child", child_id=child_id))

            current_app.logger.exception(
                "Failed to edit child_id=%s resident_id=%s",
                child_id,
                resident_id,
            )
            flash("Unable to update child. Please try again or contact an administrator.", "error")
            return redirect(url_for("case_management.edit_child", child_id=child_id))

        flash("Child updated.", "success")
        return _resident_case_redirect(resident_id)

    return render_template(
        "case_management/edit_child.html",
        child=child,
    )


def delete_child_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_family_income_support_schema()

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]
    ph = placeholder()

    try:
        now = datetime.utcnow().isoformat()

        with db_transaction():
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

            _recalculate_current_enrollment_income_support(resident_id)
    except Exception:
        current_app.logger.exception(
            "Failed to delete child_id=%s resident_id=%s",
            child_id,
            resident_id,
        )
        flash("Unable to remove child. Please try again or contact an administrator.", "error")
        return redirect(url_for("case_management.family_intake", resident_id=resident_id))

    flash("Child removed.", "success")
    return _resident_case_redirect(resident_id)


def edit_child_service_view(service_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_family_income_support_schema()

    service = _child_service_in_scope(service_id)
    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = service["resident_id"]

    if request.method == "POST":
        validated, errors = validate_child_service_form(request.form)

        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("case_management.edit_child_service", service_id=service_id))

        ph = placeholder()

        try:
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
                    validated["service_type"],
                    validated["outcome"],
                    validated["quantity"],
                    validated["unit"],
                    validated["notes"],
                    validated["service_date"],
                    datetime.utcnow().isoformat(),
                    service_id,
                ),
            )
        except Exception:
            current_app.logger.exception(
                "Failed to edit child service_id=%s resident_id=%s",
                service_id,
                resident_id,
            )
            flash(
                "Unable to update child service. Please try again or contact an administrator.",
                "error",
            )
            return redirect(url_for("case_management.edit_child_service", service_id=service_id))

        flash("Service updated.", "success")
        return _resident_case_redirect(resident_id)

    return render_template(
        "case_management/edit_child_service.html",
        service=service,
        resident_id=resident_id,
    )


def delete_child_service_view(service_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_family_income_support_schema()

    service = _child_service_in_scope(service_id)
    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    child_id = service["resident_child_id"]
    resident_id = service["resident_id"]
    ph = placeholder()

    try:
        now = datetime.utcnow().isoformat()
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
    except Exception:
        current_app.logger.exception(
            "Failed to delete child service_id=%s child_id=%s",
            service_id,
            child_id,
        )
        flash(
            "Unable to remove child service. Please try again or contact an administrator.",
            "error",
        )
        return redirect(url_for("case_management.child_services", child_id=child_id))

    flash("Service deleted.", "success")
    return _resident_case_redirect(resident_id)


def child_services_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_family_income_support_schema()

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]
    shelter = _current_shelter()
    enrollment = _latest_enrollment_for_resident(resident_id, shelter)

    if not enrollment:
        flash("No active enrollment found.", "error")
        return _resident_case_redirect(resident_id)

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
    ph = placeholder()

    if request.method == "POST":
        validated, errors = validate_child_service_form(request.form)

        if errors:
            for error in errors:
                flash(error, "error")
            return _post_child_service_redirect(child_id, resident_id)

        now = datetime.utcnow().isoformat()

        try:
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
                    validated["service_date"] or now,
                    validated["service_type"],
                    validated["outcome"],
                    validated["quantity"],
                    validated["unit"],
                    validated["notes"],
                    now,
                    now,
                ),
            )
        except Exception:
            current_app.logger.exception(
                "Failed to add child service for child_id=%s resident_id=%s enrollment_id=%s",
                child_id,
                resident_id,
                enrollment_id,
            )
            flash(
                "Unable to add child service. Please try again or contact an administrator.",
                "error",
            )
            return _post_child_service_redirect(child_id, resident_id)

        flash("Child service added.", "success")
        return _resident_case_redirect(resident_id)

    services = db_fetchall(
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

    return render_template(
        "case_management/child_services.html",
        child_id=child_id,
        resident_id=resident_id,
        services=services,
    )
