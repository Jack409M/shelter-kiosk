from core.runtime import init_db


def test_create_and_fetch_resident(app):
    from core.db import db_execute, db_fetchall

    with app.app_context():
        init_db()

        db_execute(
            """
            INSERT INTO residents (
                id,
                resident_identifier,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (1, 'r1', 'John', 'Doe', 'abba', TRUE, '2026-01-01')
            """
        )

        rows = db_fetchall("SELECT * FROM residents WHERE id = 1")

    assert rows
