from routes.case_management_parts.exit_validation import validate_exit_form


def test_validate_exit_form_accepts_valid_successful_completion():
    form = {
        "date_graduated": "2026-04-10",
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Successful Completion",
        "exit_reason": "Program Graduated",
        "graduate_dwc": "yes",
        "leave_ama": "no",
        "leave_amarillo_city": "",
        "leave_amarillo_unknown": "no",
        "income_at_exit": "1450",
        "education_at_exit": "GED",
        "grit_at_exit": "82",
        "received_car": "yes",
        "car_insurance": "yes",
        "dental_needs_met": "yes",
        "vision_needs_met": "no",
        "obtained_public_insurance": "yes",
        "private_insurance": "no",
    }

    data, errors = validate_exit_form(form, "2025-01-01")

    assert errors == []
    assert data["date_graduated"] == "2026-04-10"
    assert data["date_exit_dwc"] == "2026-04-10"
    assert data["income_at_exit"] == 1450.0
    assert data["grit_at_exit"] == 82.0
    assert data["graduate_dwc"] == "yes"
    assert data["car_insurance"] == "yes"


def test_validate_exit_form_requires_valid_exit_date():
    form = {
        "date_exit_dwc": "not-a-date",
        "exit_category": "Positive Exit",
        "exit_reason": "Permanent Housing",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Date Exit DWC is required and must be a valid date." in errors


def test_validate_exit_form_requires_valid_category_and_reason_pairing():
    form = {
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Positive Exit",
        "exit_reason": "Program Graduated",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Exit Reason must match the selected Exit Category." in errors


def test_validate_exit_form_requires_graduation_date_when_graduate_dwc_yes():
    form = {
        "date_graduated": "",
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Successful Completion",
        "exit_reason": "Program Graduated",
        "graduate_dwc": "yes",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Date Graduated is required when Graduate DWC is Yes." in errors


def test_validate_exit_form_requires_graduate_dwc_yes_when_date_graduated_present():
    form = {
        "date_graduated": "2026-04-10",
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Successful Completion",
        "exit_reason": "Program Graduated",
        "graduate_dwc": "no",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Graduate DWC must be Yes when Date Graduated is entered." in errors


def test_validate_exit_form_blocks_car_insurance_without_received_car():
    form = {
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Positive Exit",
        "exit_reason": "Permanent Housing",
        "graduate_dwc": "no",
        "received_car": "no",
        "car_insurance": "yes",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Car Insurance cannot be Yes unless Received Car is Yes." in errors


def test_validate_exit_form_requires_leave_city_or_unknown_when_leave_ama_yes():
    form = {
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Positive Exit",
        "exit_reason": "Permanent Housing",
        "graduate_dwc": "no",
        "leave_ama": "yes",
        "leave_amarillo_city": "",
        "leave_amarillo_unknown": "no",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Enter the city left for or mark it Unknown when Leave Amarillo is Yes." in errors


def test_validate_exit_form_clears_leave_city_when_unknown_yes():
    form = {
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Positive Exit",
        "exit_reason": "Permanent Housing",
        "graduate_dwc": "no",
        "leave_ama": "yes",
        "leave_amarillo_city": "Dallas",
        "leave_amarillo_unknown": "yes",
    }

    data, errors = validate_exit_form(form, "2025-01-01")

    assert errors == []
    assert data["leave_amarillo_city"] == ""
    assert data["leave_amarillo_unknown"] == "yes"


def test_validate_exit_form_rejects_negative_income_and_grit():
    form = {
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Positive Exit",
        "exit_reason": "Permanent Housing",
        "income_at_exit": "-1",
        "grit_at_exit": "-5",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Current Monthly Income cannot be negative." in errors
    assert "Grit at Exit cannot be negative." in errors


def test_validate_exit_form_rejects_exit_date_before_entry_date():
    form = {
        "date_exit_dwc": "2024-12-31",
        "exit_category": "Positive Exit",
        "exit_reason": "Permanent Housing",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Date Exit DWC cannot be earlier than the entry date." in errors


def test_validate_exit_form_normalizes_deceased_exit_fields():
    form = {
        "date_graduated": "2026-04-01",
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Administrative Exit",
        "exit_reason": "Deceased",
        "graduate_dwc": "yes",
        "leave_ama": "yes",
        "leave_amarillo_city": "Amarillo",
        "leave_amarillo_unknown": "yes",
        "income_at_exit": "999",
        "education_at_exit": "GED",
        "grit_at_exit": "80",
        "received_car": "yes",
        "car_insurance": "yes",
        "dental_needs_met": "yes",
        "vision_needs_met": "yes",
        "obtained_public_insurance": "yes",
        "private_insurance": "yes",
    }

    data, errors = validate_exit_form(form, "2025-01-01")

    assert errors == []
    assert data["date_graduated"] is None
    assert data["graduate_dwc"] == "no"
    assert data["leave_ama"] == "no"
    assert data["leave_amarillo_city"] == ""
    assert data["leave_amarillo_unknown"] == "no"
    assert data["income_at_exit"] is None
    assert data["education_at_exit"] == ""
    assert data["grit_at_exit"] is None
    assert data["received_car"] == ""
    assert data["car_insurance"] == ""


def test_validate_exit_form_rejects_invalid_education_level():
    form = {
        "date_exit_dwc": "2026-04-10",
        "exit_category": "Positive Exit",
        "exit_reason": "Permanent Housing",
        "education_at_exit": "Middle School",
    }

    _, errors = validate_exit_form(form, "2025-01-01")

    assert "Education at Exit must be one of the approved education levels." in errors
