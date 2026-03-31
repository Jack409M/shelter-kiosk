from __future__ import annotations

from typing import Any

from flask import g

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.residents import generate_resident_code, generate_resident_identifier
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import yes_no_to_int
from routes.case_management_parts.needs import sync_enrollment_needs


def _is_unique_violation(exc: Exception) -> bool:
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message


def _safe_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _checked_need(data: dict[str, Any], need_key: str) -> int | None:
    return yes_no_to_int(data.get(f"need_{need_key}"))


def _missing_item_value(data: dict[str, Any], need_key: str) -> int | None:
    return 0 if data.get(f"need_{need_key}") == "yes" else None


def _build_intake_assessment_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "city": data.get("city"),
        "county": data.get("county"),
        "last_zipcode_residence": data.get("last_zipcode_residence"),
        "length_of_time_in_amarillo": data.get("length_of_time_in_amarillo"),
        "income_at_entry": data.get("income_at_entry"),
        "education_at_entry": data.get("education_at_entry"),
        "treatment_grad_date": data.get("treatment_grad_date"),
        "sobriety_date": data.get("sobriety_date"),
        "days_sober_at_entry": data.get("days_sober_at_entry"),
        "drug_of_choice": data.get("drug_of_choice"),
        "ace_score": data.get("ace_score"),
        "grit_score": data.get("grit_score"),
        "veteran": yes_no_to_int(data.get("veteran")),
        "disability": data.get("disability") or "unknown",
        "marital_status": data.get("marital_status"),
        "notes_basic": data.get("notes_basic"),
        "entry_notes": data.get("entry_notes"),
        "initial_snapshot_notes": data.get("initial_snapshot_notes"),
        "trauma_notes": data.get("trauma_notes"),
        "barrier_notes": data.get("barrier_notes"),
        "place_staying_before_entry": data.get("prior_living"),
        "entry_felony_conviction": yes_no_to_int(data.get("felony_history")),
        "entry_parole_probation": yes_no_to_int(data.get("probation_parole")),
        "drug_court": yes_no_to_int(data.get("drug_court")),
        "sexual_survivor": yes_no_to_int(data.get("sexual_survivor")),
        "dv_survivor": yes_no_to_int(data.get("domestic_violence_history")),
        "human_trafficking_survivor": yes_no_to_int(data.get("human_trafficking_history")),
        "warrants_unpaid": _checked_need(data, "warrants_fine_resolution"),
        "mh_exam_completed": 0,
        "med_exam_completed": 0,
        "car_at_entry": yes_no_to_int(data.get("car_at_entry")),
        "car_insurance_at_entry": yes_no_to_int(data.get("car_insurance_at_entry")),
        "pregnant_at_entry": yes_no_to_int(data.get("pregnant")),
        "dental_need_at_entry": _checked_need(data, "dental"),
        "vision_need_at_entry": _checked_need(data, "vision_glasses"),
        "employment_status_at_entry": data.get("employment_status"),
        "mental_health_need_at_entry": None,
        "medical_need_at_entry": None,
        "substance_use_need_at_entry": None,
        "id_documents_status_at_entry": None,
        "has_drivers_license": _missing_item_value(data, "state_id_drivers_license"),
        "has_social_security_card": _missing_item_value(data, "social_security_card"),
        "parenting_class_needed": _checked_need(data, "parenting_class_needed"),
        "dwc_level_today": data.get("dwc_level_today"),
    }


def _build_family_snapshot_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "kids_at_dwc": _safe_int_or_none(data.get("kids_at_dwc")),
        "kids_served_outside_under_18": _safe_int_or_none(data.get("kids_served_outside_under_18")),
        "kids_ages_0_5": _safe_int_or_none(data.get("kids_ages_0_5")),
        "kids_ages_6_11": _safe_int_or_none(data.get("kids_ages_6_11")),
        "kids_ages_12_17": _safe_int_or_none(data.get("kids_ages_12_17")),
        "kids_reunited_while_in_program": _safe_int_or_none(data.get("kids_reunited_while_in_program")),
        "healthy_babies_born_at_dwc": _safe_int_or_none(data.get("healthy_babies_born_at_dwc")),
    }


def _insert_resident(data: dict[str, Any], shelter: str) -> tuple[int, str, str]:
    ph = placeholder()
    max_attempts = 5
    last_error: Exception | None = None

    for _ in range(max_attempts):
        resident_identifier = generate_resident_identifier()
        resident_code = generate_resident_code()

        try:
            if g.get("db_kind") == "pg":
                row = db_fetchone(
                    f"""
                    INSERT INTO residents
                    (
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
                        shelter,
                        gender,
                        race,
                        ethnicity,
                        is_active,
                        created_at
                    )
                    VALUES (
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        {ph},
                        TRUE,
                        NOW()
                    )
                    RETURNING id
                    """,
                    (
                        resident_identifier,
                        resident_code,
                        data["first_name"],
                        data["last_name"],
                        data["birth_year"],
                        data["phone"],
                        data["email"],
                        data["emergency_contact_name"],
                        data["emergency_contact_relationship"],
                        data["emergency_contact_phone"],
                        shelter,
                        data["gender"],
                        data["race"],
                        data["ethnicity"],
                    ),
                )
                return int(row["id"]), resident_identifier, resident_code

            db_execute(
                f"""
                INSERT INTO residents
                (
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
                    shelter,
                    gender,
                    race,
                    ethnicity,
                    is_active,
                    created_at
                )
                VALUES (
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    {ph},
                    1,
                    CURRENT_TIMESTAMP
                )
                """,
                (
                    resident_identifier,
                    resident_code,
                    data["first_name"],
                    data["last_name"],
                    data["birth_year"],
                    data["phone"],
                    data["email"],
                    data["emergency_contact_name"],
                    data["emergency_contact_relationship"],
                    data["emergency_contact_phone"],
                    shelter,
                    data["gender"],
                    data["race"],
                    data["ethnicity"],
                ),
            )

            row = db_fetchone("SELECT last_insert_rowid() AS id")
            return int(row["id"]), resident_identifier, resident_code

        except Exception as exc:
            last_error = exc
            if _is_unique_violation(exc):
                continue
            raise

    if last_error is not None:
        raise last_error

    raise RuntimeError("Unable to generate a unique resident identifier and code.")


def _insert_program_enrollment(resident_id: int, data: dict[str, Any], shelter: str) -> int:
    ph = placeholder()

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            f"""
            INSERT INTO program_enrollments
            (
                resident_id,
                shelter,
                program_status,
                entry_date,
                created_at,
                updated_at
            )
            VALUES (
                {ph},
                {ph},
                {ph},
                {ph},
                NOW(),
                NOW()
            )
            RETURNING id
            """,
            (
                resident_id,
                shelter,
                data["program_status"] or "active",
                data["entry_date"],
            ),
        )
        return int(row["id"])

    db_execute(
        f"""
        INSERT INTO program_enrollments
        (
            resident_id,
            shelter,
            program_status,
            entry_date,
            created_at,
            updated_at
        )
        VALUES (
            {ph},
            {ph},
            {ph},
            {ph},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (
            resident_id,
            shelter,
            data["program_status"] or "active",
            data["entry_date"],
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"])


def _insert_intake_assessment(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()
    payload = _build_intake_assessment_payload(data)

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            INSERT INTO intake_assessments
            (
                enrollment_id,
                city,
                county,
                last_zipcode_residence,
                length_of_time_in_amarillo,
                income_at_entry,
                education_at_entry,
                treatment_grad_date,
                sobriety_date,
                days_sober_at_entry,
                drug_of_choice,
                ace_score,
                grit_score,
                veteran,
                disability,
                marital_status,
                notes_basic,
                entry_notes,
                initial_snapshot_notes,
                trauma_notes,
                barrier_notes,
                place_staying_before_entry,
                entry_felony_conviction,
                entry_parole_probation,
                drug_court,
                sexual_survivor,
                dv_survivor,
                human_trafficking_survivor,
                warrants_unpaid,
                mh_exam_completed,
                med_exam_completed,
                car_at_entry,
                car_insurance_at_entry,
                pregnant_at_entry,
                dental_need_at_entry,
                vision_need_at_entry,
                employment_status_at_entry,
                mental_health_need_at_entry,
                medical_need_at_entry,
                substance_use_need_at_entry,
                id_documents_status_at_entry,
                has_drivers_license,
                has_social_security_card,
                parenting_class_needed,
                dwc_level_today,
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
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                NOW(),
                NOW()
            )
            """,
            (
                enrollment_id,
                payload["city"],
                payload["county"],
                payload["last_zipcode_residence"],
                payload["length_of_time_in_amarillo"],
                payload["income_at_entry"],
                payload["education_at_entry"],
                payload["treatment_grad_date"],
                payload["sobriety_date"],
                payload["days_sober_at_entry"],
                payload["drug_of_choice"],
                payload["ace_score"],
                payload["grit_score"],
                payload["veteran"],
                payload["disability"],
                payload["marital_status"],
                payload["notes_basic"],
                payload["entry_notes"],
                payload["initial_snapshot_notes"],
                payload["trauma_notes"],
                payload["barrier_notes"],
                payload["place_staying_before_entry"],
                payload["entry_felony_conviction"],
                payload["entry_parole_probation"],
                payload["drug_court"],
                payload["sexual_survivor"],
                payload["dv_survivor"],
                payload["human_trafficking_survivor"],
                payload["warrants_unpaid"],
                payload["mh_exam_completed"],
                payload["med_exam_completed"],
                payload["car_at_entry"],
                payload["car_insurance_at_entry"],
                payload["pregnant_at_entry"],
                payload["dental_need_at_entry"],
                payload["vision_need_at_entry"],
                payload["employment_status_at_entry"],
                payload["mental_health_need_at_entry"],
                payload["medical_need_at_entry"],
                payload["substance_use_need_at_entry"],
                payload["id_documents_status_at_entry"],
                payload["has_drivers_license"],
                payload["has_social_security_card"],
                payload["parenting_class_needed"],
                payload["dwc_level_today"],
            ),
        )
    else:
        db_execute(
            f"""
            INSERT INTO intake_assessments
            (
                enrollment_id,
                city,
                county,
                last_zipcode_residence,
                length_of_time_in_amarillo,
                income_at_entry,
                education_at_entry,
                treatment_grad_date,
                sobriety_date,
                days_sober_at_entry,
                drug_of_choice,
                ace_score,
                grit_score,
                veteran,
                disability,
                marital_status,
                notes_basic,
                entry_notes,
                initial_snapshot_notes,
                trauma_notes,
                barrier_notes,
                place_staying_before_entry,
                entry_felony_conviction,
                entry_parole_probation,
                drug_court,
                sexual_survivor,
                dv_survivor,
                human_trafficking_survivor,
                warrants_unpaid,
                mh_exam_completed,
                med_exam_completed,
                car_at_entry,
                car_insurance_at_entry,
                pregnant_at_entry,
                dental_need_at_entry,
                vision_need_at_entry,
                employment_status_at_entry,
                mental_health_need_at_entry,
                medical_need_at_entry,
                substance_use_need_at_entry,
                id_documents_status_at_entry,
                has_drivers_license,
                has_social_security_card,
                parenting_class_needed,
                dwc_level_today,
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
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
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
                enrollment_id,
                payload["city"],
                payload["county"],
                payload["last_zipcode_residence"],
                payload["length_of_time_in_amarillo"],
                payload["income_at_entry"],
                payload["education_at_entry"],
                payload["treatment_grad_date"],
                payload["sobriety_date"],
                payload["days_sober_at_entry"],
                payload["drug_of_choice"],
                payload["ace_score"],
                payload["grit_score"],
                payload["veteran"],
                payload["disability"],
                payload["marital_status"],
                payload["notes_basic"],
                payload["entry_notes"],
                payload["initial_snapshot_notes"],
                payload["trauma_notes"],
                payload["barrier_notes"],
                payload["place_staying_before_entry"],
                payload["entry_felony_conviction"],
                payload["entry_parole_probation"],
                payload["drug_court"],
                payload["sexual_survivor"],
                payload["dv_survivor"],
                payload["human_trafficking_survivor"],
                payload["warrants_unpaid"],
                payload["mh_exam_completed"],
                payload["med_exam_completed"],
                payload["car_at_entry"],
                payload["car_insurance_at_entry"],
                payload["pregnant_at_entry"],
                payload["dental_need_at_entry"],
                payload["vision_need_at_entry"],
                payload["employment_status_at_entry"],
                payload["mental_health_need_at_entry"],
                payload["medical_need_at_entry"],
                payload["substance_use_need_at_entry"],
                payload["id_documents_status_at_entry"],
                payload["has_drivers_license"],
                payload["has_social_security_card"],
                payload["parenting_class_needed"],
                payload["dwc_level_today"],
                now,
                now,
            ),
        )

    sync_enrollment_needs(
        enrollment_id,
        selected_need_keys=data.get("entry_need_keys", []),
    )


def _insert_family_snapshot(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()
    payload = _build_family_snapshot_payload(data)

    db_execute(
        f"""
        INSERT INTO family_snapshots
        (
            enrollment_id,
            kids_at_dwc,
            kids_served_outside_under_18,
            kids_ages_0_5,
            kids_ages_6_11,
            kids_ages_12_17,
            kids_reunited_while_in_program,
            healthy_babies_born_at_dwc,
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
            enrollment_id,
            payload["kids_at_dwc"],
            payload["kids_served_outside_under_18"],
            payload["kids_ages_0_5"],
            payload["kids_ages_6_11"],
            payload["kids_ages_12_17"],
            payload["kids_reunited_while_in_program"],
            payload["healthy_babies_born_at_dwc"],
            now,
            now,
        ),
    )
