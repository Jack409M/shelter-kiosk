from __future__ import annotations

import sqlite3

import pytest
from flask import g

from core import db as core_db


def test_is_sqlite_url_true_and_false() -> None:
    assert core_db._is_sqlite_url("sqlite:///:memory:") is True
    assert core_db._is_sqlite_url("postgresql://user:pass@localhost/dbname") is False


def test_sqlite_path_from_memory_url(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        assert core_db._sqlite_path_from_url(core_db._database_url()) == ":memory:"


def test_sqlite_path_from_file_url_decodes_path(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:////tmp/test%20db.sqlite"
    with app.app_context():
        assert core_db._sqlite_path_from_url(core_db._database_url()) == "/tmp/test db.sqlite"


def test_sqlite_path_from_uri_memory_url(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///file:memdb1?mode=memory&cache=shared"
    with app.app_context():
        assert (
            core_db._sqlite_path_from_url(core_db._database_url())
            == "sqlite:///file:memdb1?mode=memory&cache=shared"
        )


def test_sqlite_path_from_non_sqlite_url_raises(app) -> None:
    app.config["DATABASE_URL"] = "postgresql://example/db"
    with app.app_context():
        with pytest.raises(RuntimeError, match="non-SQLite"):
            core_db._sqlite_path_from_url(core_db._database_url())


def test_normalize_sql_for_sqlite() -> None:
    sql = "SELECT NOW(), BTRIM(name) FROM users WHERE id = %s"
    normalized = core_db._normalize_sql(sql, db_kind="sqlite")
    assert normalized == "SELECT CURRENT_TIMESTAMP, TRIM(name) FROM users WHERE id = ?"


def test_normalize_sql_for_pg() -> None:
    sql = "SELECT * FROM users WHERE id = ? AND email = ?"
    normalized = core_db._normalize_sql(sql, db_kind="pg")
    assert normalized == "SELECT * FROM users WHERE id = %s AND email = %s"


def test_sqlite_should_skip_statement_true() -> None:
    sql = "SELECT pg_get_serial_sequence('transport_requests', 'id')"
    assert core_db._sqlite_should_skip_statement(sql) is True


def test_sqlite_should_skip_statement_false() -> None:
    sql = "SELECT id FROM transport_requests"
    assert core_db._sqlite_should_skip_statement(sql) is False


def test_rewrite_legacy_sqlite_transport_insert_rewrites_exact_match() -> None:
    sql = "INSERT INTO transport_requests (resident_identifier, shelter, status) VALUES (?, ?, ?)"
    params = ("RID123", "Haven", "pending")

    rewritten_sql, rewritten_params = core_db._rewrite_legacy_sqlite_transport_insert(sql, params)

    assert "first_name" in rewritten_sql
    assert "last_name" in rewritten_sql
    assert "needed_at" in rewritten_sql
    assert "pickup_location" in rewritten_sql
    assert "destination" in rewritten_sql
    assert "submitted_at" in rewritten_sql
    assert rewritten_params == (
        "RID123",
        "Haven",
        "pending",
        "",
        "",
        "1970-01-01T00:00:00",
        "",
        "",
        "1970-01-01T00:00:00",
    )


def test_rewrite_legacy_sqlite_transport_insert_noop_for_non_match() -> None:
    sql = "INSERT INTO transport_requests (resident_identifier, shelter, status, first_name) VALUES (?, ?, ?, ?)"
    params = ("RID123", "Haven", "pending", "Jane")

    rewritten_sql, rewritten_params = core_db._rewrite_legacy_sqlite_transport_insert(sql, params)

    assert rewritten_sql == sql
    assert rewritten_params == params


def test_prepare_sql_and_params_sqlite_skip(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        prepared_sql, prepared_params = core_db._prepare_sql_and_params(
            "SELECT pg_get_serial_sequence('transport_requests', 'id')",
            (),
        )
        assert prepared_sql is None
        assert prepared_params == ()


def test_prepare_sql_and_params_sqlite_rewrite(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        prepared_sql, prepared_params = core_db._prepare_sql_and_params(
            "INSERT INTO transport_requests (resident_identifier, shelter, status) VALUES (%s, %s, %s)",
            ("RID123", "Haven", "pending"),
        )
        assert prepared_sql is not None
        assert "first_name" in prepared_sql
        assert prepared_params[0:3] == ("RID123", "Haven", "pending")
        assert len(prepared_params) == 9


def test_prepare_sql_and_params_pg_no_skip_or_rewrite(app) -> None:
    app.config["DATABASE_URL"] = "postgresql://user:pass@localhost/dbname"
    with app.app_context():
        g.db_kind = "pg"
        prepared_sql, prepared_params = core_db._prepare_sql_and_params(
            "SELECT * FROM users WHERE id = ?",
            (7,),
        )
        assert prepared_sql == "SELECT * FROM users WHERE id = %s"
        assert prepared_params == (7,)


def test_row_to_dict_from_dict() -> None:
    row = {"id": 1, "name": "Alice"}
    assert core_db._row_to_dict(row) == {"id": 1, "name": "Alice"}


def test_row_to_dict_from_sqlite_row() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("CREATE TABLE sample (id INTEGER, name TEXT)")
    cur.execute("INSERT INTO sample (id, name) VALUES (?, ?)", (1, "Alice"))
    cur.execute("SELECT id, name FROM sample")
    row = cur.fetchone()

    assert row is not None
    assert core_db._row_to_dict(row) == {"id": 1, "name": "Alice"}

    cur.close()
    conn.close()


def test_row_to_dict_none_returns_empty_dict() -> None:
    assert core_db._row_to_dict(None) == {}


def test_row_to_dict_invalid_row_raises() -> None:
    with pytest.raises(RuntimeError, match="could not be converted to dict"):
        core_db._row_to_dict(object())


def test_set_request_connection_sets_g_state(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        conn = object()
        returned = core_db._set_request_connection(conn, kind="sqlite")
        assert returned is conn
        assert g.db is conn
        assert g.db_kind == "sqlite"
        assert g.db_in_transaction is False


def test_db_fetchone_and_fetchall_and_execute_sqlite(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        core_db.db_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        core_db.db_execute("INSERT INTO items (name) VALUES (%s)", ("alpha",))
        core_db.db_execute("INSERT INTO items (name) VALUES (%s)", ("beta",))

        row = core_db.db_fetchone("SELECT id, name FROM items WHERE name = %s", ("alpha",))
        rows = core_db.db_fetchall("SELECT id, name FROM items ORDER BY id")

        assert row is not None
        assert row["name"] == "alpha"
        assert [item["name"] for item in rows] == ["alpha", "beta"]


def test_db_execute_skips_pg_get_serial_sequence_on_sqlite(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        core_db.db_execute("SELECT pg_get_serial_sequence('transport_requests', 'id')")


def test_db_transaction_commit_sqlite(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        core_db.db_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        with core_db.db_transaction():
            core_db.db_execute("INSERT INTO items (name) VALUES (%s)", ("committed",))

        row = core_db.db_fetchone("SELECT name FROM items WHERE name = %s", ("committed",))
        assert row is not None
        assert row["name"] == "committed"


def test_db_transaction_rollback_sqlite(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        core_db.db_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")

        with pytest.raises(RuntimeError, match="boom"):
            with core_db.db_transaction():
                core_db.db_execute("INSERT INTO items (name) VALUES (%s)", ("rolled_back",))
                raise RuntimeError("boom")

        rows = core_db.db_fetchall("SELECT id, name FROM items")
        assert rows == []


def test_db_transaction_nested_uses_existing_transaction(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        core_db.db_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")

        with core_db.db_transaction():
            with core_db.db_transaction():
                core_db.db_execute("INSERT INTO items (name) VALUES (%s)", ("nested",))

        row = core_db.db_fetchone("SELECT name FROM items WHERE name = %s", ("nested",))
        assert row is not None
        assert row["name"] == "nested"


def test_close_db_sqlite_clears_request_state(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        conn = core_db.get_db()
        assert conn is not None
        assert "db" in g

        core_db.close_db()

        assert "db" not in g
        assert "db_kind" not in g
        assert "db_in_transaction" not in g
