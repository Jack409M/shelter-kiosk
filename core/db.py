from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from flask import current_app, g

try:
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import PoolError, SimpleConnectionPool
except Exception:
    RealDictCursor = None
    PoolError = Exception
    SimpleConnectionPool = None


type DbRow = dict[str, Any]
type DbConnection = Any
type DbCursor = Any

PG_POOL: Any = None
_PG_POOL_LOCK = Lock()

_LEGACY_TRANSPORT_INSERT_SQL = (
    "insert into transport_requests (resident_identifier, shelter, status) values (?, ?, ?)"
)


def _require_database_url() -> str:
    database_url = current_app.config.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")
    return str(database_url)


def _database_url() -> str:
    return _require_database_url()


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.lower().startswith("sqlite:")


def _db_kind() -> str:
    kind = g.get("db_kind")
    if kind:
        return str(kind)

    database_url = _database_url()
    return "sqlite" if _is_sqlite_url(database_url) else "pg"


def _normalize_sql(sql: str, *, db_kind: str) -> str:
    if db_kind == "sqlite":
        return (
            sql.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP").replace("BTRIM(", "TRIM(")
        )
    return sql.replace("?", "%s")


def _sqlite_path_from_url(database_url: str) -> str:
    if not _is_sqlite_url(database_url):
        raise RuntimeError("SQLite path requested for non-SQLite database URL.")

    if database_url == "sqlite:///:memory:":
        return ":memory:"

    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)

    if query.get("mode") == ["memory"]:
        return database_url

    raw_path = unquote(parsed.path or "")
    if not raw_path:
        raise RuntimeError("SQLite DATABASE_URL must include a database path.")

    if raw_path.startswith("//"):
        raw_path = raw_path[1:]

    return raw_path


def _sqlite_connect(database_url: str) -> sqlite3.Connection:
    sqlite_path = _sqlite_path_from_url(database_url)

    if sqlite_path == ":memory:":
        conn = sqlite3.connect(":memory:")
    elif database_url.startswith("sqlite:///file:"):
        conn = sqlite3.connect(database_url.removeprefix("sqlite:///"), uri=True)
    else:
        conn = sqlite3.connect(sqlite_path)

    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    return conn


def _init_pg_pool() -> None:
    global PG_POOL

    with _PG_POOL_LOCK:
        if PG_POOL is not None:
            return

        database_url = _database_url()

        if SimpleConnectionPool is None:
            raise RuntimeError("psycopg2 is not installed, but a Postgres DATABASE_URL is set.")

        PG_POOL = SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url,
        )


def _get_pg_pool() -> Any:
    _init_pg_pool()
    if PG_POOL is None:
        raise RuntimeError("Postgres pool was not initialized.")
    return PG_POOL


def _set_request_connection(conn: DbConnection, *, kind: str) -> DbConnection:
    g.db = conn
    g.db_kind = kind
    g.db_in_transaction = False
    return conn


def _get_or_create_request_connection() -> DbConnection:
    if "db" in g:
        return g.db

    database_url = _database_url()

    if _is_sqlite_url(database_url):
        conn = _sqlite_connect(database_url)
        return _set_request_connection(conn, kind="sqlite")

    pool = _get_pg_pool()
    conn = pool.getconn()
    conn.autocommit = True
    return _set_request_connection(conn, kind="pg")


def get_db() -> DbConnection:
    return _get_or_create_request_connection()


def close_db(e: Exception | None = None) -> None:
    del e

    conn = g.pop("db", None)
    kind = g.pop("db_kind", None)
    g.pop("db_in_transaction", None)

    if conn is None:
        return

    if kind == "sqlite":
        with suppress(Exception):
            conn.close()
        return

    with suppress(Exception):
        conn.autocommit = True

    global PG_POOL
    if PG_POOL is not None:
        try:
            PG_POOL.putconn(conn)
        except PoolError:
            current_app.logger.warning(
                "Postgres pool ignored duplicate or unknown connection return."
            )


@contextmanager
def _db_cursor(*, dict_rows: bool = False) -> Iterator[DbCursor]:
    conn = get_db()
    kind = _db_kind()

    if kind == "sqlite":
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
        return

    sql_cursor_factory = RealDictCursor if dict_rows else None

    if dict_rows and sql_cursor_factory is None:
        raise RuntimeError("psycopg2.extras.RealDictCursor is unavailable.")

    cur = conn.cursor(cursor_factory=sql_cursor_factory) if sql_cursor_factory else conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def _row_to_dict(row: Any) -> DbRow:
    if row is None:
        return {}

    if isinstance(row, dict):
        return dict(row)

    if isinstance(row, sqlite3.Row):
        return dict(row)

    try:
        return dict(row)
    except Exception as err:
        raise RuntimeError("Database row could not be converted to dict.") from err


def _sqlite_should_skip_statement(normalized_sql: str) -> bool:
    compact_sql = " ".join(normalized_sql.lower().split())
    return "pg_get_serial_sequence(" in compact_sql


def _rewrite_legacy_sqlite_transport_insert(
    normalized_sql: str,
    params: tuple[Any, ...],
) -> tuple[str, tuple[Any, ...]]:
    compact_sql = " ".join(normalized_sql.lower().split())

    if compact_sql != _LEGACY_TRANSPORT_INSERT_SQL or len(params) != 3:
        return normalized_sql, params

    rewritten_sql = """
        INSERT INTO transport_requests (
            resident_identifier,
            shelter,
            status,
            first_name,
            last_name,
            needed_at,
            pickup_location,
            destination,
            submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    rewritten_params = (
        params[0],
        params[1],
        params[2],
        "",
        "",
        "1970-01-01T00:00:00",
        "",
        "",
        "1970-01-01T00:00:00",
    )

    return rewritten_sql, rewritten_params


def _prepare_sql_and_params(
    sql: str,
    params: tuple[Any, ...],
) -> tuple[str | None, tuple[Any, ...]]:
    kind = _db_kind()
    normalized_sql = _normalize_sql(sql, db_kind=kind)

    if kind != "sqlite":
        return normalized_sql, params

    if _sqlite_should_skip_statement(normalized_sql):
        return None, params

    rewritten_sql, rewritten_params = _rewrite_legacy_sqlite_transport_insert(
        normalized_sql,
        params,
    )
    return rewritten_sql, rewritten_params


def db_execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    prepared_sql, prepared_params = _prepare_sql_and_params(sql, params)
    if prepared_sql is None:
        return

    with _db_cursor(dict_rows=False) as cur:
        cur.execute(prepared_sql, prepared_params)


def db_fetchone(sql: str, params: tuple[Any, ...] = ()) -> DbRow | None:
    normalized_sql = _normalize_sql(sql, db_kind=_db_kind())

    with _db_cursor(dict_rows=True) as cur:
        cur.execute(normalized_sql, params)
        row = cur.fetchone()

    if row is None:
        return None

    return _row_to_dict(row)


def db_fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[DbRow]:
    normalized_sql = _normalize_sql(sql, db_kind=_db_kind())

    with _db_cursor(dict_rows=True) as cur:
        cur.execute(normalized_sql, params)
        rows = cur.fetchall()

    return [_row_to_dict(row) for row in rows]


@contextmanager
def db_transaction() -> Iterator[DbConnection]:
    conn = get_db()
    kind = _db_kind()
    already_in_transaction = bool(g.get("db_in_transaction"))

    if already_in_transaction:
        yield conn
        return

    g.db_in_transaction = True

    if kind == "sqlite":
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            g.db_in_transaction = False
        return

    previous_autocommit = conn.autocommit
    conn.autocommit = False

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        g.db_in_transaction = False
        conn.autocommit = previous_autocommit
