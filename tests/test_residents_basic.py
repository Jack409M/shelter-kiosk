from core.runtime import init_db


def test_create_and_fetch_resident(app):
    from core.db import db_execute, db_fetchall

    resident_identifier = "test_resident_fetch_001"

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM residents
            WHERE resident_identifier = %s
            """,
            (resident_identifier,),
        )

        db_execute(
            """
            SELECT setval(
                pg_get_serial_sequence('residents', 'id'),
                COALESCE((SELECT MAX(id) FROM residents), 1),
                true
            )
            """
        )

        db_execute(
            """
            INSERT INTO residents (
                resident_identifier,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                resident_identifier,
                "John",
                "Doe",
                "abba",
                True,
                "2026-01-01",
            ),
        )

        rows = db_fetchall(
            """
            SELECT resident_identifier, first_name, last_name, shelter
            FROM residents
            WHERE resident_identifier = %s
            """,
            (resident_identifier,),
        )

    assert rows
    row = rows[0]
    assert row["resident_identifier"] == resident_identifier
    assert row["first_name"] == "John"
    assert row["last_name"] == "Doe"
    assert row["shelter"] == "abba"
