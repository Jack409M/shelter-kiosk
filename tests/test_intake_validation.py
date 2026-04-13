from __future__ import annotations


def _base_form():
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "birth_year": "1988",
        "phone": "(806) 555-1111",
        "email": "jane@example.com",
        "entry_date": "2026-04-12",
        "shelter": "abba",
    }


def test_validation_accepts_valid_minimal_form(monkeypatch):
    from routes.case_management_parts import intake_validation as v

    data, errors = v._validate_intake_form(_base_form(), "abba")

    assert errors == []
    assert data["first_name"] == "Jane"
    assert data["last_name"] == "Doe"
    assert data["birth_year"] == 1988


def test_validation_rejects_missing_required_fields(monkeypatch):
    from routes.case_management_parts import intake_validation as v

    form = _base_form()
    form["first_name"] = ""
    form["entry_date"] = ""

    data, errors = v._validate_intake_form(form, "abba")

    assert errors
    assert any("required" in e.lower() for e in errors)


def test_validation_normalizes_phone_to_digits(monkeypatch):
    from routes.case_management_parts import intake_validation as v

    form = _base_form()
    form["phone"] = "(806) 555-9999"

    data, errors = v._validate_intake_form(form, "abba")

    assert errors == []
    assert data["phone"] == "8065559999"


def test_validation_invalid_birth_year_rejected(monkeypatch):
    from routes.case_management_parts import intake_validation as v

    form = _base_form()
    form["birth_year"] = "1800"  # unrealistic

    data, errors = v._validate_intake_form(form, "abba")

    assert errors
    assert any("birth" in e.lower() for e in errors)


def test_validation_invalid_email_rejected(monkeypatch):
    from routes.case_management_parts import intake_validation as v

    form = _base_form()
    form["email"] = "not-an-email"

    data, errors = v._validate_intake_form(form, "abba")

    assert errors
    assert any("email" in e.lower() for e in errors)


def test_validation_invalid_entry_date_rejected(monkeypatch):
    from routes.case_management_parts import intake_validation as v

    form = _base_form()
    form["entry_date"] = "not-a-date"

    data, errors = v._validate_intake_form(form, "abba")

    assert errors
    assert any("date" in e.lower() for e in errors)


def test_validation_shelter_scope_enforced(monkeypatch):
    from routes.case_management_parts import intake_validation as v

    form = _base_form()
    form["shelter"] = "haven"  # mismatch

    data, errors = v._validate_intake_form(form, "abba")

    assert errors
    assert any("shelter" in e.lower() for e in errors)
