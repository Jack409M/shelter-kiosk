from __future__ import annotations

from flask import Flask

from core.app_hooks import register_app_hooks


def _build_hardening_app(*, testing: bool, debug: bool) -> Flask:
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config.update(TESTING=testing, DEBUG=debug)

    @app.route("/")
    def index():
        return "ok", 200

    @app.route("/static/example.css")
    def static_example():
        return "body {}", 200, {"Content-Type": "text/css"}

    register_app_hooks(app)
    return app


def test_enterprise_security_headers_are_applied_on_dynamic_response():
    app = _build_hardening_app(testing=True, debug=False)
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["Origin-Agent-Cluster"] == "?1"
    assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_enterprise_cache_headers_are_private_for_dynamic_and_cacheable_for_static():
    app = _build_hardening_app(testing=True, debug=False)
    client = app.test_client()

    dynamic_response = client.get("/")
    static_response = client.get("/static/example.css")

    assert (
        dynamic_response.headers["Cache-Control"]
        == "no-store, no-cache, must-revalidate, private, max-age=0"
    )
    assert dynamic_response.headers["Pragma"] == "no-cache"
    assert dynamic_response.headers["Expires"] == "0"

    assert static_response.headers["Cache-Control"] == "public, max-age=86400"


def test_enterprise_https_redirect_is_enforced_for_production_like_http_requests():
    app = _build_hardening_app(testing=False, debug=False)
    client = app.test_client()

    response = client.get("http://localhost/", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["Location"].startswith("https://")


def test_enterprise_https_redirect_is_skipped_when_forwarded_proto_is_https():
    app = _build_hardening_app(testing=False, debug=False)
    client = app.test_client()

    response = client.get(
        "/",
        headers={"X-Forwarded-Proto": "https"},
        follow_redirects=False,
    )

    assert response.status_code == 200
