from __future__ import annotations

from flask import Flask

from core.app_hooks import register_app_hooks


def _build_error_test_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        DEBUG=False,
        SECRET_KEY="test-secret",
    )

    @app.route("/boom")
    def boom():
        raise RuntimeError("boom")

    @app.route("/forbidden")
    def forbidden():
        from flask import abort
        abort(403)

    register_app_hooks(app)

    # 🔑 Stub template rendering entirely
    @app.context_processor
    def _stub_templates():
        return {}

    return app


def test_http_exception_html_renders_http_error_template(monkeypatch):
    app = _build_error_test_app()
    client = app.test_client()

    # Stub render_template so layout is never evaluated
    monkeypatch.setattr(
        "core.app_hooks.render_template",
        lambda template, **ctx: f"HTML:{template}".encode(),
    )

    response = client.get("/forbidden")

    assert response.status_code == 403
    assert b"HTML:errors/http_error.html" in response.data
    assert response.headers.get("X-Request-ID")


def test_http_exception_json_returns_json_payload():
    app = _build_error_test_app()
    client = app.test_client()

    response = client.get(
        "/forbidden",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 403
    assert response.is_json is True
    assert response.get_json() == {
        "error": "Forbidden",
        "message": "You don't have the permission to access the requested resource. It is either read-protected or not readable by the server.",
    }
    assert response.headers.get("X-Request-ID")


def test_unexpected_exception_html_renders_500_template(monkeypatch):
    app = _build_error_test_app()
    client = app.test_client()

    monkeypatch.setattr(
        "core.app_hooks.render_template",
        lambda template, **ctx: f"HTML:{template}".encode(),
    )

    response = client.get("/boom")

    assert response.status_code == 500
    assert b"HTML:errors/server_error.html" in response.data
    assert response.headers.get("X-Request-ID")


def test_unexpected_exception_json_returns_json_payload():
    app = _build_error_test_app()
    client = app.test_client()

    response = client.get(
        "/boom",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 500
    assert response.is_json is True
    assert response.get_json() == {
        "error": "Internal Server Error",
    }
    assert response.headers.get("X-Request-ID")
