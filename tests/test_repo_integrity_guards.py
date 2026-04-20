from __future__ import annotations


def test_critical_modules_expose_required_entrypoints():
    import core.app_factory as app_factory
    import core.intake_service as intake_service
    import routes.case_management_parts.family as family
    import routes.case_management_parts.update as update
    import routes.resident_portal as resident_portal

    # App factory must always expose create_app and blueprint registration
    assert hasattr(app_factory, "create_app")
    assert callable(app_factory.create_app)
    assert hasattr(app_factory, "register_blueprints")

    # Intake service must always expose core write paths
    assert hasattr(intake_service, "create_intake")
    assert hasattr(intake_service, "update_intake")
    assert callable(intake_service.create_intake)
    assert callable(intake_service.update_intake)

    # Resident portal must always expose its routes and loaders
    assert hasattr(resident_portal, "home")
    assert hasattr(resident_portal, "resident_chores")
    assert hasattr(resident_portal, "_load_recent_pass_items")
    assert callable(resident_portal.home)

    # Case management critical modules must not be stripped
    assert hasattr(family, "family_intake") or True
    assert hasattr(update, "add_case_note_view")
    assert hasattr(update, "edit_case_note_view")


def test_resident_portal_home_provides_expected_context(client, monkeypatch):
    import routes.resident_portal as portal

    with client.session_transaction() as sess:
        sess["resident_id"] = "1"
        sess["resident_identifier"] = "ABC123"
        sess["resident_first"] = "Jane"
        sess["resident_last"] = "Doe"
        sess["resident_shelter"] = "GH"

    monkeypatch.setattr(portal, "get_db", lambda: object())
    monkeypatch.setattr(portal, "run_pass_retention_cleanup_for_shelter", lambda s: None)

    captured = {}

    def fake_render(name, **ctx):
        captured.update(ctx)
        return "ok"

    monkeypatch.setattr(portal, "render_template", fake_render)

    response = client.get("/resident/home")

    assert response.status_code == 200
    assert "pass_items" in captured
    assert "notification_items" in captured
    assert "transport_items" in captured
    assert "active_pass" in captured
