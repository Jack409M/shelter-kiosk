from __future__ import annotations

from typing import Any

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


def _set_staff_session(client, *, shelter: str = "abba", role: str = "case_manager") -> None:
    with client.session_transaction() as sess:
        sess["staff_user_id"] = 1
        sess["username"] = "contract_tester"
        sess["role"] = role
        sess["shelter"] = shelter
        sess["allowed_shelters"] = ["abba", "haven", "gratitude"]


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as sess:
        sess["_csrf_token"] = token
    return token


def _copy_client_session_to_request(client) -> None:
    from flask import session

    with client.session_transaction() as sess:
        for key, value in sess.items():
            session[key] = value


def _insert_resident(
    *,
    shelter: str = "abba",
    level: str = "5",
    resident_code: str = "12345678",
) -> int:
    row = db_fetchone(
        """
        INSERT INTO residents (
            shelter,
            resident_identifier,
            resident_code,
            first_name,
            last_name,
            birth_year,
            phone,
            program_level,
            level_start_date,
            is_active,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
        RETURNING id
        """,
        (
            shelter,
            f"RID-{resident_code}",
            resident_code,
            "Contract",
            "Resident",
            1990,
            "8065550000",
            level,
            "2026-01-01",
            utcnow_iso(),
        ),
    )
    return int(row["id"])


def _insert_active_enrollment(
    *,
    resident_id: int,
    shelter: str = "abba",
    entry_date: str = "2026-01-01",
) -> int:
    row = db_fetchone(
        """
        INSERT INTO program_enrollments (
            resident_id,
            shelter,
            entry_date,
            exit_date,
            program_status,
            case_manager_id,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, NULL, 'active', %s, %s, %s)
        RETURNING id
        """,
        (resident_id, shelter, entry_date, 1, utcnow_iso(), utcnow_iso()),
    )
    return int(row["id"])


def _insert_rent_config(
    *,
    resident_id: int,
    shelter: str = "abba",
    level: str = "5",
    apartment: str = "1",
) -> int:
    row = db_fetchone(
        """
        INSERT INTO resident_rent_configs (
            resident_id,
            shelter,
            level_snapshot,
            apartment_number_snapshot,
            apartment_size_snapshot,
            monthly_rent,
            is_exempt,
            effective_start_date,
            effective_end_date,
            created_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, 250, FALSE, %s, NULL, 1, %s, %s)
        RETURNING id
        """,
        (
            resident_id,
            shelter,
            level,
            apartment,
            "1 Bedroom",
            "2026-01-01",
            utcnow_iso(),
            utcnow_iso(),
        ),
    )
    return int(row["id"])


def _insert_placement(
    *,
    resident_id: int,
    enrollment_id: int,
    shelter: str = "abba",
    level: str = "5",
) -> int:
    row = db_fetchone(
        """
        INSERT INTO resident_placements (
            resident_id,
            enrollment_id,
            shelter,
            program_level,
            housing_unit_id,
            placement_type,
            start_date,
            end_date,
            change_reason,
            note,
            created_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, NULL, 'apartment', %s, NULL, %s, %s, 1, %s, %s)
        RETURNING id
        """,
        (
            resident_id,
            enrollment_id,
            shelter,
            level,
            "2026-01-01",
            "test_seed",
            "Seed placement for lifecycle contract test.",
            utcnow_iso(),
            utcnow_iso(),
        ),
    )
    return int(row["id"])


def _insert_pass(
    *,
    resident_id: int,
    shelter: str = "abba",
    status: str = "pending",
    pass_type: str = "pass",
) -> int:
    row = db_fetchone(
        """
        INSERT INTO resident_passes (
            resident_id,
            shelter,
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            destination,
            reason,
            resident_notes,
            staff_notes,
            approved_by,
            approved_at,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, NULL, NULL, NULL, NULL, %s, %s)
        RETURNING id
        """,
        (
            resident_id,
            shelter,
            pass_type,
            status,
            "2026-12-01T14:00:00",
            "2026-12-01T18:00:00",
            "Store",
            "Errand",
            utcnow_iso(),
            utcnow_iso(),
        ),
    )
    pass_id = int(row["id"])
    db_execute(
        """
        INSERT INTO resident_pass_request_details (
            pass_id,
            resident_phone,
            request_date,
            resident_level,
            reason_for_request,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            pass_id,
            "8065550000",
            "2026-11-30",
            "5",
            "Errand",
            utcnow_iso(),
            utcnow_iso(),
        ),
    )
    return pass_id


def _fetch_resident(resident_id: int) -> dict[str, Any]:
    row = db_fetchone("SELECT * FROM residents WHERE id = %s", (resident_id,))
    assert row is not None
    return dict(row)


def _fetch_enrollments(resident_id: int) -> list[dict[str, Any]]:
    rows = db_fetchall(
        """
        SELECT *
        FROM program_enrollments
        WHERE resident_id = %s
        ORDER BY id ASC
        """,
        (resident_id,),
    )
    return [dict(row) for row in rows]


def _active_enrollment_count(resident_id: int) -> int:
    row = db_fetchone(
        """
        SELECT COUNT(*) AS row_count
        FROM program_enrollments
        WHERE resident_id = %s
          AND program_status = 'active'
        """,
        (resident_id,),
    )
    return int(row["row_count"])


def test_lifecycle_intake_contract_creates_official_baseline(app):
    from core.intake_service import create_intake

    data = {
        "first_name": "Intake",
        "last_name": "Contract",
        "birth_year": 1992,
        "phone": "8065550100",
        "email": "intake@example.org",
        "emergency_contact_name": "Emergency Contact",
        "emergency_contact_relationship": "Friend",
        "emergency_contact_phone": "8065550199",
        "gender": "Female",
        "race": "",
        "ethnicity": "",
        "entry_date": "2026-01-10",
        "program_status": "active",
        "city": "Amarillo",
        "county": "Potter",
        "last_zipcode_residence": "79101",
        "length_of_time_in_amarillo": "1 year",
        "income_at_entry": 0,
        "education_at_entry": "GED",
        "treatment_grad_date": None,
        "sobriety_date": "2025-12-01",
        "days_sober_at_entry": 40,
        "drug_of_choice": "",
        "ace_score": 0,
        "grit_score": 0,
        "veteran": "no",
        "disability": "unknown",
        "marital_status": "",
        "notes_basic": "",
        "entry_notes": "",
        "initial_snapshot_notes": "",
        "trauma_notes": "",
        "barrier_notes": "",
        "prior_living": "Shelter",
        "felony_history": "no",
        "probation_parole": "no",
        "drug_court": "no",
        "sexual_survivor": "no",
        "domestic_violence_history": "no",
        "human_trafficking_history": "no",
        "car_at_entry": "no",
        "car_insurance_at_entry": "no",
        "pregnant": "no",
        "employment_status": "Unemployed",
        "dwc_level_today": "1",
        "kids_at_dwc": 0,
        "kids_served_outside_under_18": 0,
        "kids_ages_0_5": 0,
        "kids_ages_6_11": 0,
        "kids_ages_12_17": 0,
        "kids_reunited_while_in_program": 0,
        "healthy_babies_born_at_dwc": 0,
        "entry_need_keys": [],
    }

    with app.app_context():
        result = create_intake(current_shelter="abba", data=data, draft_id=None)

        resident = _fetch_resident(result.resident_id)
        enrollments = _fetch_enrollments(result.resident_id)
        assert resident["resident_identifier"] == result.resident_identifier
        assert resident["resident_code"] == result.resident_code
        assert _active_enrollment_count(result.resident_id) == 1
        assert len(enrollments) == 1

        enrollment_id = enrollments[0]["id"]
        intake = db_fetchone(
            "SELECT * FROM intake_assessments WHERE enrollment_id = %s",
            (enrollment_id,),
        )
        family = db_fetchone(
            "SELECT * FROM family_snapshots WHERE enrollment_id = %s",
            (enrollment_id,),
        )
        assert intake is not None
        assert family is not None


def test_lifecycle_transfer_contract_closes_old_and_opens_new_enrollment(app, client):
    from routes.case_management_parts.transfer import submit_transfer_resident_view

    with app.app_context():
        resident_id = _insert_resident(shelter="abba", level="5")
        old_enrollment_id = _insert_active_enrollment(resident_id=resident_id, shelter="abba")
        _insert_rent_config(resident_id=resident_id, shelter="abba", level="5")

    _set_staff_session(client, shelter="abba")
    with app.test_request_context(
        f"/staff/case-management/{resident_id}/transfer",
        method="POST",
        data={"target_shelter": "haven", "transfer_date": "2026-02-01"},
    ):
        _copy_client_session_to_request(client)
        response = submit_transfer_resident_view(resident_id)
        assert response.status_code == 302

    with app.app_context():
        enrollments = _fetch_enrollments(resident_id)
        resident = _fetch_resident(resident_id)
        old_enrollment = next(row for row in enrollments if row["id"] == old_enrollment_id)
        new_enrollment = next(row for row in enrollments if row["id"] != old_enrollment_id)

        assert old_enrollment["program_status"] == "transferred"
        assert old_enrollment["exit_date"] == "2026-02-01"
        assert new_enrollment["program_status"] == "active"
        assert new_enrollment["shelter"] == "haven"
        assert resident["shelter"] == "haven"
        assert bool(resident["is_active"])
        assert _active_enrollment_count(resident_id) == 1

        rent_config = db_fetchone(
            "SELECT * FROM resident_rent_configs WHERE resident_id = %s ORDER BY id DESC LIMIT 1",
            (resident_id,),
        )
        assert rent_config is not None
        assert rent_config["effective_end_date"] == "2026-02-01"


def test_lifecycle_resident_transfer_helper_moves_open_passes_only(app):
    from routes.resident_parts.resident_transfer_helpers import apply_cross_shelter_transfer

    with app.app_context():
        resident_with_pending_id = _insert_resident(
            shelter="abba",
            level="5",
            resident_code="12345678",
        )
        _insert_active_enrollment(resident_id=resident_with_pending_id, shelter="abba")
        pending_pass_id = _insert_pass(
            resident_id=resident_with_pending_id,
            shelter="abba",
            status="pending",
        )

        resident_with_closed_id = _insert_resident(
            shelter="abba",
            level="5",
            resident_code="87654321",
        )
        _insert_active_enrollment(resident_id=resident_with_closed_id, shelter="abba")
        denied_pass_id = _insert_pass(
            resident_id=resident_with_closed_id,
            shelter="abba",
            status="denied",
        )
        completed_pass_id = _insert_pass(
            resident_id=resident_with_closed_id,
            shelter="abba",
            status="completed",
        )

        with app.test_request_context("/"):
            from flask import session

            session["staff_user_id"] = 1
            session["username"] = "contract_tester"
            apply_cross_shelter_transfer(
                resident_id=resident_with_pending_id,
                resident_identifier="RID-12345678",
                from_shelter="abba",
                to_shelter="haven",
                note="Contract transfer",
                apartment_number=None,
                transfer_recorder=lambda **kwargs: None,
            )
            apply_cross_shelter_transfer(
                resident_id=resident_with_closed_id,
                resident_identifier="RID-87654321",
                from_shelter="abba",
                to_shelter="haven",
                note="Contract transfer",
                apartment_number=None,
                transfer_recorder=lambda **kwargs: None,
            )

        pass_rows = {
            row["id"]: dict(row)
            for row in db_fetchall(
                """
                SELECT id, shelter, status
                FROM resident_passes
                WHERE resident_id IN (%s, %s)
                """,
                (resident_with_pending_id, resident_with_closed_id),
            )
        }
        assert pass_rows[pending_pass_id]["shelter"] == "haven"
        assert pass_rows[denied_pass_id]["shelter"] == "abba"
        assert pass_rows[completed_pass_id]["shelter"] == "abba"


def test_lifecycle_promotion_contract_changes_level_without_closing_enrollment(app, client):
    from routes.case_management_parts.promotion_review import promotion_review_view

    with app.app_context():
        resident_id = _insert_resident(shelter="abba", level="5")
        enrollment_id = _insert_active_enrollment(resident_id=resident_id, shelter="abba")
        _insert_rent_config(resident_id=resident_id, shelter="abba", level="5")
        _insert_placement(resident_id=resident_id, enrollment_id=enrollment_id, shelter="abba", level="5")

        db_execute(
            """
            INSERT INTO case_manager_updates (
                enrollment_id,
                staff_user_id,
                meeting_date,
                notes,
                action_items,
                ready_for_next_level,
                recommended_next_level,
                created_at,
                updated_at
            )
            VALUES (%s, 1, %s, %s, %s, TRUE, %s, %s, %s)
            """,
            (
                enrollment_id,
                "2026-02-01",
                "Ready for promotion.",
                "Saved promotion review.",
                "9",
                utcnow_iso(),
                utcnow_iso(),
            ),
        )

    _set_staff_session(client, shelter="abba")
    with app.test_request_context(
        f"/staff/case-management/{resident_id}/promotion-review",
        method="POST",
        data={
            "form_action": "apply_promotion",
            "confirm_apply_promotion": "1",
            "meeting_date": "2026-02-02",
            "notes": "Apply promotion.",
            "recommended_next_level": "9",
        },
    ):
        _copy_client_session_to_request(client)
        response = promotion_review_view(resident_id)
        assert response.status_code == 302

    with app.app_context():
        resident = _fetch_resident(resident_id)
        enrollment = db_fetchone("SELECT * FROM program_enrollments WHERE id = %s", (enrollment_id,))
        active_rent = db_fetchone(
            """
            SELECT *
            FROM resident_rent_configs
            WHERE resident_id = %s
              AND COALESCE(effective_end_date, '') = ''
            """,
            (resident_id,),
        )
        active_placement = db_fetchone(
            """
            SELECT *
            FROM resident_placements
            WHERE resident_id = %s
              AND COALESCE(end_date, '') = ''
            """,
            (resident_id,),
        )
        promotion_log_count = db_fetchone(
            """
            SELECT COUNT(*) AS row_count
            FROM case_manager_updates
            WHERE enrollment_id = %s
              AND COALESCE(action_items, '') LIKE '%%Applied promotion%%'
            """,
            (enrollment_id,),
        )

        assert resident["program_level"] == "9"
        assert enrollment["program_status"] == "active"
        assert bool(resident["is_active"])
        assert active_rent is None
        assert active_placement is None
        assert int(promotion_log_count["row_count"]) >= 1


def test_lifecycle_exit_contract_closes_enrollment_without_deleting_resident(app, client):
    from routes.case_management_parts.exit import submit_exit_assessment_view

    with app.app_context():
        resident_id = _insert_resident(shelter="abba", level="5")
        enrollment_id = _insert_active_enrollment(resident_id=resident_id, shelter="abba")
        _insert_rent_config(resident_id=resident_id, shelter="abba", level="5")

    _set_staff_session(client, shelter="abba")
    with app.test_request_context(
        f"/staff/case-management/{resident_id}/exit-assessment",
        method="POST",
        data={
            "date_exit_dwc": "2026-03-01",
            "exit_category": "Successful Completion",
            "exit_reason": "Program Graduated",
            "graduate_dwc": "yes",
            "date_graduated": "2026-03-01",
            "leave_ama": "no",
            "income_at_exit": "500",
            "education_at_exit": "GED",
            "grit_at_exit": "5",
            "received_car": "no",
            "car_insurance": "no",
            "dental_needs_met": "yes",
            "vision_needs_met": "yes",
            "obtained_public_insurance": "yes",
            "private_insurance": "no",
        },
    ):
        _copy_client_session_to_request(client)
        response = submit_exit_assessment_view(resident_id)
        assert response.status_code == 302

    with app.app_context():
        resident = _fetch_resident(resident_id)
        enrollment = db_fetchone("SELECT * FROM program_enrollments WHERE id = %s", (enrollment_id,))
        exit_assessment = db_fetchone(
            "SELECT * FROM exit_assessments WHERE enrollment_id = %s",
            (enrollment_id,),
        )
        active_rent = db_fetchone(
            """
            SELECT *
            FROM resident_rent_configs
            WHERE resident_id = %s
              AND COALESCE(effective_end_date, '') = ''
            """,
            (resident_id,),
        )

        assert resident is not None
        assert not bool(resident["is_active"])
        assert enrollment["program_status"] == "exited"
        assert enrollment["exit_date"] == "2026-03-01"
        assert exit_assessment is not None
        assert active_rent is None


def test_lifecycle_pass_contract_pending_to_approved_to_completed(app, client, monkeypatch):
    monkeypatch.setattr("routes.attendance_parts.pass_action_helpers.send_sms", lambda *args, **kwargs: None)

    with app.app_context():
        resident_id = _insert_resident(shelter="abba", level="5")
        _insert_active_enrollment(resident_id=resident_id, shelter="abba")
        pass_id = _insert_pass(resident_id=resident_id, shelter="abba", status="pending")

    _set_staff_session(client, shelter="abba")
    csrf_token = _set_csrf_token(client)
    approve_response = client.post(
        f"/staff/passes/{pass_id}/approve",
        data={"_csrf_token": csrf_token},
    )
    assert approve_response.status_code == 302

    with app.app_context():
        approved_pass = db_fetchone("SELECT * FROM resident_passes WHERE id = %s", (pass_id,))
        approval_notification = db_fetchone(
            """
            SELECT *
            FROM resident_notifications
            WHERE resident_id = %s
              AND related_pass_id = %s
              AND notification_type = 'pass_approved'
            """,
            (resident_id, pass_id),
        )
        assert approved_pass["status"] == "approved"
        assert approved_pass["approved_by"] == 1
        assert approved_pass["approved_at"]
        assert approval_notification is not None

    legacy_get_response = client.get(f"/staff/passes/deny/{pass_id}")
    assert legacy_get_response.status_code == 302
    with app.app_context():
        still_approved = db_fetchone("SELECT status FROM resident_passes WHERE id = %s", (pass_id,))
        assert still_approved["status"] == "approved"

    check_in_response = client.post(
        f"/staff/passes/{pass_id}/check-in",
        data={"_csrf_token": csrf_token},
    )
    assert check_in_response.status_code == 302

    with app.app_context():
        completed_pass = db_fetchone("SELECT * FROM resident_passes WHERE id = %s", (pass_id,))
        check_in_event = db_fetchone(
            """
            SELECT *
            FROM attendance_events
            WHERE resident_id = %s
              AND event_type = 'check_in'
              AND note = 'Pass return check in'
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )
        assert completed_pass["status"] == "completed"
        assert check_in_event is not None
