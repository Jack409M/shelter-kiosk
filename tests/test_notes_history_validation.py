from __future__ import annotations

from routes.case_management_parts.notes_history_validation import validate_notes_history_form


def test_notes_history_validation_smoke():
    data, errors = validate_notes_history_form({})

    assert data == {}
    assert errors == []
