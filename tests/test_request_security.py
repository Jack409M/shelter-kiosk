from flask import Flask


def test_register_request_security_sets_hooks():
    from core.request_security import register_request_security

    app = Flask(__name__)

    register_request_security(
        app,
        client_ip_func=lambda: "127.0.0.1",
        is_ip_banned_func=lambda ip: False,
        is_rate_limited_func=lambda ip: False,
        ban_ip_func=lambda ip: None,
    )

    assert app.before_request_funcs
    assert app.after_request_funcs


def test_request_security_blocks_banned_ip(client, app):
    from core.request_security import register_request_security

    register_request_security(
        app,
        client_ip_func=lambda: "1.2.3.4",
        is_ip_banned_func=lambda ip: True,
        is_rate_limited_func=lambda ip: False,
        ban_ip_func=lambda ip: None,
    )

    response = client.get("/")

    assert response.status_code in (403, 429)


def test_request_security_rate_limit_trigger(client, app):
    from core.request_security import register_request_security

    register_request_security(
        app,
        client_ip_func=lambda: "1.2.3.4",
        is_ip_banned_func=lambda ip: False,
        is_rate_limited_func=lambda ip: True,
        ban_ip_func=lambda ip: None,
    )

    response = client.get("/")

    assert response.status_code in (403, 429)
