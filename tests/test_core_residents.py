from core.runtime import init_db


def test_generate_resident_code_and_identifier(app):
    from core.residents import generate_resident_code, generate_resident_identifier

    code = generate_resident_code()
    identifier = generate_resident_identifier()

    assert isinstance(code, str)
    assert isinstance(identifier, str)
    assert len(code) > 0
    assert len(identifier) > 0


def test_record_resident_transfer_basic(app):
    from core.residents import record_resident_transfer
    from core.db import db_execute, db_fetchall

    with app.app_context():
        init_db()

        # clean
        db_execute("DELETE FROM residents WHERE resident_identifier = %s", ("transfer_test",))

        db_execute(
            """
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "transfer_test",
                "99999999",
                "Test",
                "User",
                "abba",
                True,
                "2026-01-01",
            ),
        )

        resident = db_fetchall(
            "SELECT id FROM residents WHERE resident_identifier = %s",
            ("transfer_test",),
        )[0]

        record_resident_transfer(
            resident_id=resident["id"],
            from_shelter="abba",
            to_shelter="haven",
            note="test move",
        )

        rows = db_fetchall(
            "SELECT * FROM resident_transfers WHERE resident_id = %s",
            (resident["id"],),
        )

    assert rows
