from core.runtime import init_db


def test_audit_write(app):
    from core.audit import log_action
    from core.db import db_fetchall

    with app.app_context():
        init_db()

        log_action(
            "test",
            1,
            "abba",
            1,
            "unit_test",
            "testing audit",
        )

        rows = db_fetchall("SELECT * FROM audit_log")

    assert rows
