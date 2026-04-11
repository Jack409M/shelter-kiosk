from flask import Flask


def test_register_request_security_sets_before_request_hooks():
    from core.request_security import register_request_security

    app = Flask(__name__)

    register_request_security(
        app,
        client_ip_func=lambda: "127.0.0.1",
        is_ip_banned_func=lambda ip: False,
        is_rate_limited_func=lambda *args, **kwargs: False,
        ban_ip_func=lambda *args, **kwargs: None,
    )

    assert app.before_request_funcs
    assert app.before_request_funcs[None]


def test_request_security_blocks_banned_ip(client, app):
    from core.request_security import register_request_security

    register_request_security(
        app,
        client_ip_func=lambda: "1.2.3.4",
        is_ip_banned_func=lambda ip: True,
        is_rate_limited_func=lambda *args, **kwargs: False,
        ban_ip_func=lambda *args, **kwargs: None,
    )

    response = client.get("/")

    assert response.status_code == 403


def test_request_security_allows_request_when_not_blocked(client, app):
    from core.request_security import register_request_security

    register_request_security(
        app,
        client_ip_func=lambda: "1.2.3.4",
        is_ip_banned_func=lambda ip: False,
        is_rate_limited_func=lambda *args, **kwargs: False,
        ban_ip_func=lambda *args, **kwargs: None,
    )

    response = client.get("/")

    assert response.status_code != 403
