from __future__ import annotations

from core.db import db_fetchone


def test_family_add_child_atomic_rollback(client, monkeypatch):
    import routes.case_management_parts.family as family_module

    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "case_manager"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]
        session["_csrf_token"] = "test-csrf"

    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )

    monkeypatch.setattr(family_module, "init_db", lambda: None)
    monkeypatch.setattr(family_module, "_ensure_family_income_support_schema", lambda: None)
    monkeypatch.setattr(
        family_module,
        "_resident_in_scope",
        lambda resident_id: {"id": resident_id, "first_name": "Jane", "last_name": "Doe", "shelter": "abba"},
    )
    monkeypatch.setattr(
        family_module,
        "validate_child_form",
        lambda form: (
            {
                "child_name": "Child One",
                "birth_year": 2015,
                "relationship": "daughter",
                "living_status": "with_resident",
                "receives_survivor_benefit": True,
                "survivor_benefit_amount": 120.0,
                "survivor_benefit_notes": "note",
                "child_support_amount": 80.0,
                "child_support_notes": "support",
            },
            [],
        ),
    )

    real_db_fetchone = family_module.db_fetchone

    def _db_fetchone_wrapper(sql, params=()):
        if "SELECT id\n            FROM resident_children" in sql and params and params[0] == 1:
            with client.application.app_context():
                return real_db_fetchone(sql, params)
        return real_db_fetchone(sql, params)

    monkeypatch.setattr(family_module, "db_fetchone", _db_fetchone_wrapper)
    monkeypatch.setattr(
        family_module,
        "_recalculate_current_enrollment_income_support",
        lambda resident_id: (_ for _ in ()).throw(RuntimeError("forced recalc failure")),
    )

    client.post(
        "/staff/case-management/1/family-intake",
        data={"_csrf_token": "test-csrf"},
    )

    with client.application.app_context():
        child_row = db_fetchone(
            "SELECT * FROM resident_children WHERE resident_id = ? AND child_name = ?",
            (1, "Child One"),
        )
        support_row = db_fetchone(
            "SELECT * FROM resident_child_income_supports WHERE support_type = ?",
            ("survivor_benefit",),
        )

    assert child_row is None, "Transaction should have rolled back child creation"
    assert support_row is None, "Transaction should have rolled back child support creation"
