from __future__ import annotations

from datetime import date, timedelta

from routes.case_management_parts.recovery_profile_validation import (
    validate_recovery_profile_form,
)


def test_recovery_profile_rejects_step_above_twelve():
    data, errors = validate_recovery_profile_form(
        {
            "step_current": "13",
        }
    )

    assert data["step_current"] == 13
    assert "Current Step must be between 1 and 12." in errors


def test_recovery_profile_rejects_invalid_monthly_income():
    _, errors = validate_recovery_profile_form(
        {
            "monthly_income": "abc",
        }
    )

    assert "Income must be a valid dollar amount." in errors


def test_recovery_profile_requires_employer_fields_when_employed():
    _, errors = validate_recovery_profile_form(
        {
            "employment_status_current": "employed",
        }
    )

    assert "Employer is required when Employment Status is Employed." in errors
    assert "Employment Type is required when Employment Status is Employed." in errors


def test_recovery_profile_requires_reason_when_unemployed():
    _, errors = validate_recovery_profile_form(
        {
            "employment_status_current": "unemployed",
        }
    )

    assert "Unemployment Reason is required when Employment Status is Unemployed." in errors


def test_recovery_profile_normalizes_unemployed_side_fields():
    data, errors = validate_recovery_profile_form(
        {
            "employment_status_current": "unemployed",
            "unemployment_reason": "Looking for work",
            "employer_name": "Old Job",
            "employment_type_current": "full_time",
            "supervisor_name": "Boss",
            "supervisor_phone": "8065551212",
        }
    )

    assert errors == []
    assert data["employer_name"] is None
    assert data["employment_type_current"] is None
    assert data["supervisor_name"] is None
    assert data["supervisor_phone"] is None
    assert data["unemployment_reason"] == "Looking for work"


def test_recovery_profile_normalizes_supervisor_phone_digits():
    data, errors = validate_recovery_profile_form(
        {
            "employment_status_current": "employed",
            "employer_name": "Test Employer",
            "employment_type_current": "full_time",
            "supervisor_phone": "(806) 555 1212",
        }
    )

    assert errors == []
    assert data["supervisor_phone"] == "8065551212"


def test_recovery_profile_rejects_short_supervisor_phone():
    _, errors = validate_recovery_profile_form(
        {
            "employment_status_current": "employed",
            "employer_name": "Test Employer",
            "employment_type_current": "full_time",
            "supervisor_phone": "55512",
        }
    )

    assert "Supervisor Phone must contain at least 10 digits." in errors


def test_recovery_profile_rejects_future_sobriety_date():
    future_date = (date.today() + timedelta(days=1)).isoformat()

    _, errors = validate_recovery_profile_form(
        {
            "sobriety_date": future_date,
        }
    )

    assert "Sobriety Date cannot be in the future." in errors


def test_recovery_profile_rejects_invalid_date_order():
    _, errors = validate_recovery_profile_form(
        {
            "current_job_start_date": "2026-01-01",
            "continuous_employment_start_date": "2026-02-01",
            "previous_job_end_date": "2026-03-01",
        }
    )

    assert "Continuous Employment Start Date cannot be after Current Job Start Date." in errors
    assert "Previous Job End Date cannot be after Current Job Start Date." in errors
