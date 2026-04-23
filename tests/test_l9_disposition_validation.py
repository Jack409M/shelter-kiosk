from routes.case_management_parts.l9_disposition_validation import (
    validate_l9_disposition_form,
)


def test_validate_l9_disposition_form_accepts_exit_now():
    form = {
        "disposition_action": "exit_now",
    }

    data, errors = validate_l9_disposition_form(form)

    assert errors == []
    assert data["disposition_action"] == "exit_now"


def test_validate_l9_disposition_form_accepts_enroll_support():
    form = {
        "disposition_action": "enroll_support",
    }

    data, errors = validate_l9_disposition_form(form)

    assert errors == []
    assert data["disposition_action"] == "enroll_support"


def test_validate_l9_disposition_form_requires_action():
    form = {}

    _, errors = validate_l9_disposition_form(form)

    assert "Level 9 disposition action is required." in errors


def test_validate_l9_disposition_form_rejects_invalid_action():
    form = {
        "disposition_action": "something_else",
    }

    _, errors = validate_l9_disposition_form(form)

    assert "Level 9 disposition action must be valid." in errors
