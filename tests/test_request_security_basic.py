from flask import Flask


def test_request_security_registration():
    from core.request_security import register_request_security

    app = Flask(__name__)

    register_request_security(
        app,
        client_ip_func=lambda: "127.0.0.1",
        is_ip_banned_func=lambda ip: False,
        is_rate_limited_func=lambda ip: False,
        ban_ip_func=lambda ip: None,
    )

    assert app.before_request_funcs is not None
