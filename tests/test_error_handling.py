from __future__ import annotations

from flask import Flask

from core.app_hooks import register_app_hooks


def _build_error_test_app() -> Flask:
    app = Flask(__name__, template_folder="../templates")
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
    return app


def test_http_exception_html_renders_http_error_template():
    app = _build_error_test_app()
    client = app.test_client()

    response = client.get("/forbidden")

    assert response.status_code == 403
    assert b"Forbidden" in response.data
    assert b"Return to home" in response.data
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


def test_unexpected_exception_html_renders_500_template():
    app = _build_error_test_app()
    client = app.test_client()

    response = client.get("/boom")

    assert response.status_code == 500
    assert b"Something went wrong" in response.data
    assert b"Return to home" in response.data
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
