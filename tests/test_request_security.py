from __future__ import annotations

from flask import Flask
from jinja2 import DictLoader


def _build_app(
    *,
    client_ip: str = "1.2.3.4",
    banned_ips: set[str] | None = None,
    rate_limited_keys: set[str] | None = None,
    cloudflare_only: bool = False,
) -> tuple[Flask, dict[str, list[tuple[str, int]]]]:
    import core.request_security as request_security_module

    request_security_module.log_action = lambda *args, **kwargs: None

    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    app.config.update(
        TESTING=True,
        CLOUDFLARE_ONLY="1" if cloudflare_only else "0",
    )
    app.jinja_loader = DictLoader(
        {
            "resident_signin.html": "Resident Sign In",
        }
    )

    @app.route("/", methods=["GET", "POST", "TRACE", "TRACK", "CONNECT"])
    def home():
        return "ok", 200

    @app.route("/resident", methods=["GET", "POST", "TRACE", "TRACK", "CONNECT"])
    def resident():
        return "resident ok", 200

    @app.route("/leave", methods=["GET", "POST", "TRACE", "TRACK", "CONNECT"])
    def leave_request():
        return "leave ok", 200

    state: dict[str, list[tuple[str, int]]] = {
        "ban_calls": [],
    }

    banned_ip_set = set(banned_ips or set())
    rate_limited_key_set = set(rate_limited_keys or set())

    request_security_module.register_request_security(
        app,
        client_ip_func=lambda: client_ip,
        is_ip_banned_func=lambda ip: ip in banned_ip_set,
        is_rate_limited_func=lambda key, limit, window_seconds: key in rate_limited_key_set,
        ban_ip_func=lambda ip, seconds: state["ban_calls"].append((ip, seconds)),
    )

    return app, state


def test_request_security_blocks_banned_ip():
    app, _state = _build_app(banned_ips={"1.2.3.4"})
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 403


def test_request_security_allows_request_when_not_blocked():
    app, _state = _build_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert response.data == b"ok"


def test_request_security_blocks_non_cloudflare_request_when_required():
    app, _state = _build_app(cloudflare_only=True)
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 403


def test_request_security_allows_cloudflare_request_when_header_present():
    app, _state = _build_app(cloudflare_only=True)
    client = app.test_client()

    response = client.get(
        "/",
        headers={"CF-Connecting-IP": "9.9.9.9"},
    )

    assert response.status_code == 200
    assert response.data == b"ok"


def test_request_security_blocks_trace_method():
    app, _state = _build_app()
    client = app.test_client()

    response = client.open("/", method="TRACE")

    assert response.status_code == 405


def test_request_security_bans_bad_user_agent():
    app, state = _build_app()
    client = app.test_client()

    response = client.get(
        "/",
        headers={"User-Agent": "sqlmap/1.8"},
    )

    assert response.status_code == 403
    assert state["ban_calls"] == [("1.2.3.4", 3600)]


def test_request_security_allows_twilio_user_agent():
    app, state = _build_app()
    client = app.test_client()

    response = client.get(
        "/",
        headers={"User-Agent": "TwilioProxy/1.1"},
    )

    assert response.status_code == 200
    assert state["ban_calls"] == []


def test_request_security_returns_404_for_first_scanner_probe():
    app, state = _build_app()
    client = app.test_client()

    response = client.get("/.env")

    assert response.status_code == 404
    assert state["ban_calls"] == []


def test_request_security_bans_repeated_scanner_probe():
    app, state = _build_app(
        rate_limited_keys={"scanner_probe:1.2.3.4"},
    )
    client = app.test_client()

    response = client.get("/.env")

    assert response.status_code == 403
    assert state["ban_calls"] == [("1.2.3.4", 3600)]


def test_public_bot_throttle_renders_resident_signin_on_resident_post():
    app, state = _build_app(
        rate_limited_keys={"public_post:/resident:1.2.3.4"},
    )
    client = app.test_client()

    response = client.post("/resident")

    assert response.status_code == 429
    assert b"Resident Sign In" in response.data
    assert state["ban_calls"] == [("1.2.3.4", 1800)]


def test_public_bot_throttle_returns_plain_429_on_leave_post():
    app, state = _build_app(
        rate_limited_keys={"public_post:/leave:1.2.3.4"},
    )
    client = app.test_client()

    response = client.post("/leave")

    assert response.status_code == 429
    assert b"Too many requests. Please wait a few minutes and try again." in response.data
    assert state["ban_calls"] == [("1.2.3.4", 1800)]
