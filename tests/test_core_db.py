from __future__ import annotations

import sqlite3

import pytest
from flask import current_app, g

from core import db as core_db


class FakeCursor:
    def __init__(self) -> None:
        self.closed = False
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetchone_result = None
        self.fetchall_result: list[object] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def close(self) -> None:
        self.closed = True


class FakePgConnection:
    def __init__(self) -> None:
        self.autocommit = True
        self.commit_calls = 0
        self.rollback_calls = 0
        self.cursor_calls: list[object] = []
        self.cursor_instance = FakeCursor()

    def cursor(self, cursor_factory=None):
        self.cursor_calls.append(cursor_factory)
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


class FakePool:
    def __init__(self, conn=None, *, raise_on_put: Exception | None = None) -> None:
        self.conn = conn if conn is not None else FakePgConnection()
        self.raise_on_put = raise_on_put
        self.getconn_calls = 0
        self.putconn_calls: list[object] = []

    def getconn(self):
        self.getconn_calls += 1
        return self.conn

    def putconn(self, conn) -> None:
        self.putconn_calls.append(conn)
        if self.raise_on_put is not None:
            raise self.raise_on_put


def test_require_database_url_raises(app) -> None:
    with app.app_context():
        app.config.pop("DATABASE_URL", None)
        with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
            core_db._require_database_url()


def test_is_sqlite_url_true_and_false() -> None:
    assert core_db._is_sqlite_url("sqlite:///:memory:") is True
    assert core_db._is_sqlite_url("postgresql://user:pass@localhost/dbname") is False


def test_db_kind_prefers_g_value(app) -> None:
    with app.app_context():
        g.db_kind = "pg"
        assert core_db._db_kind() == "pg"


def test_db_kind_falls_back_to_database_url(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        g.pop("db_kind", None)
        assert core_db._db_kind() == "sqlite"


def test_normalize_sql_for_sqlite() -> None:
    sql = "SELECT NOW(), BTRIM(name) FROM users WHERE id = %s"
    normalized = core_db._normalize_sql(sql, db_kind="sqlite")
    assert normalized == "SELECT CURRENT_TIMESTAMP, TRIM(name) FROM users WHERE id = ?"


def test_normalize_sql_for_pg() -> None:
    sql = "SELECT * FROM users WHERE id = ? AND email = ?"
    normalized = core_db._normalize_sql(sql, db_kind="pg")
    assert normalized == "SELECT * FROM users WHERE id = %s AND email = %s"


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
    with app.app_context(), pytest.raises(RuntimeError, match="non-SQLite"):
        core_db._sqlite_path_from_url(core_db._database_url())


def test_sqlite_path_from_empty_path_raises(app) -> None:
    app.config["DATABASE_URL"] = "sqlite://"
    with app.app_context(), pytest.raises(RuntimeError, match="must include a database path"):
        core_db._sqlite_path_from_url(core_db._database_url())


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


def test_prepare_sql_and_params_sqlite_no_rewrite(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        prepared_sql, prepared_params = core_db._prepare_sql_and_params(
            "SELECT * FROM items WHERE id = %s",
            (7,),
        )
        assert prepared_sql == "SELECT * FROM items WHERE id = ?"
        assert prepared_params == (7,)


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

        with pytest.raises(RuntimeError, match="boom"), core_db.db_transaction():
            core_db.db_execute("INSERT INTO items (name) VALUES (%s)", ("rolled_back",))
            raise RuntimeError("boom")

        rows = core_db.db_fetchall("SELECT id, name FROM items")
        assert rows == []


def test_db_transaction_nested_uses_existing_transaction(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    with app.app_context():
        core_db.db_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")

        with core_db.db_transaction(), core_db.db_transaction():
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


def test_init_pg_pool_without_psycopg_raises(app, monkeypatch) -> None:
    app.config["DATABASE_URL"] = "postgresql://user:pass@localhost/dbname"
    with app.app_context():
        monkeypatch.setattr(core_db, "PG_POOL", None)
        monkeypatch.setattr(core_db, "SimpleConnectionPool", None)
        with pytest.raises(RuntimeError, match="psycopg2 is not installed"):
            core_db._init_pg_pool()


def test_init_pg_pool_creates_pool(app, monkeypatch) -> None:
    app.config["DATABASE_URL"] = "postgresql://user:pass@localhost/dbname"

    created: dict[str, object] = {}

    class RecordingPool:
        def __init__(self, *, minconn, maxconn, dsn) -> None:
            created["minconn"] = minconn
            created["maxconn"] = maxconn
            created["dsn"] = dsn

    with app.app_context():
        monkeypatch.setattr(core_db, "PG_POOL", None)
        monkeypatch.setattr(core_db, "SimpleConnectionPool", RecordingPool)
        core_db._init_pg_pool()

        assert created == {
            "minconn": 1,
            "maxconn": 10,
            "dsn": "postgresql://user:pass@localhost/dbname",
        }
        assert core_db.PG_POOL is not None


def test_get_pg_pool_returns_existing_pool(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(core_db, "PG_POOL", sentinel)
    assert core_db._get_pg_pool() is sentinel


def test_db_cursor_pg_dict_rows_uses_real_dict_cursor(app, monkeypatch) -> None:
    conn = FakePgConnection()
    cursor_factory = object()

    with app.app_context():
        g.db_kind = "pg"
        monkeypatch.setattr(core_db, "get_db", lambda: conn)
        monkeypatch.setattr(core_db, "RealDictCursor", cursor_factory)

        with core_db._db_cursor(dict_rows=True) as cur:
            assert cur is conn.cursor_instance

        assert conn.cursor_calls == [cursor_factory]
        assert conn.cursor_instance.closed is True


def test_db_cursor_pg_dict_rows_without_real_dict_cursor_raises(app, monkeypatch) -> None:
    conn = FakePgConnection()

    with app.app_context():
        g.db_kind = "pg"
        monkeypatch.setattr(core_db, "get_db", lambda: conn)
        monkeypatch.setattr(core_db, "RealDictCursor", None)

        with pytest.raises(RuntimeError, match="RealDictCursor is unavailable"):
            with core_db._db_cursor(dict_rows=True):
                pass


def test_close_db_pg_returns_connection_to_pool(app, monkeypatch) -> None:
    conn = FakePgConnection()
    pool = FakePool(conn=conn)

    with app.app_context():
        g.db = conn
        g.db_kind = "pg"
        g.db_in_transaction = True
        monkeypatch.setattr(core_db, "PG_POOL", pool)
        core_db.close_db()

        assert pool.putconn_calls == [conn]
        assert conn.autocommit is True
        assert "db" not in g
        assert "db_kind" not in g
        assert "db_in_transaction" not in g


def test_close_db_pg_poolerror_logs_warning(app, monkeypatch) -> None:
    class DuplicateReturnError(Exception):
        pass

    conn = FakePgConnection()
    pool = FakePool(conn=conn, raise_on_put=DuplicateReturnError())
    warnings: list[str] = []

    with app.app_context():
        g.db = conn
        g.db_kind = "pg"
        g.db_in_transaction = False
        monkeypatch.setattr(core_db, "PG_POOL", pool)
        monkeypatch.setattr(core_db, "PoolError", DuplicateReturnError)
        monkeypatch.setattr(current_app.logger, "warning", warnings.append)
        core_db.close_db()

        assert warnings == ["Postgres pool ignored duplicate or unknown connection return."]


def test_db_transaction_pg_commit(app, monkeypatch) -> None:
    conn = FakePgConnection()

    with app.app_context():
        g.db_kind = "pg"
        g.db_in_transaction = False
        monkeypatch.setattr(core_db, "get_db", lambda: conn)

        with core_db.db_transaction():
            pass

        assert conn.commit_calls == 1
        assert conn.rollback_calls == 0
        assert conn.autocommit is True
        assert g.db_in_transaction is False


def test_db_transaction_pg_rollback(app, monkeypatch) -> None:
    conn = FakePgConnection()

    with app.app_context():
        g.db_kind = "pg"
        g.db_in_transaction = False
        monkeypatch.setattr(core_db, "get_db", lambda: conn)

        with pytest.raises(RuntimeError, match="boom"), core_db.db_transaction():
            raise RuntimeError("boom")

        assert conn.commit_calls == 0
        assert conn.rollback_calls == 1
        assert conn.autocommit is True
        assert g.db_in_transaction is False
