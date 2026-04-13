from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from threading import Lock
from typing import Any, Iterator, TypeAlias
from urllib.parse import parse_qs, unquote, urlparse

from flask import current_app, g

try:
    from psycopg2.extensions import connection as PgConnection
    from psycopg2.extensions import cursor as PgCursor
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import PoolError, SimpleConnectionPool
except Exception:
    PgConnection = Any
    PgCursor = Any
    RealDictCursor = None
    PoolError = Exception
    SimpleConnectionPool = None


DbRow: TypeAlias = dict[str, Any]
DbConnection: TypeAlias = Any
DbCursor: TypeAlias = Any

PG_POOL: Any = None
_PG_POOL_LOCK = Lock()


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


def _normalize_sql(sql: str) -> str:
    if _db_kind() == "sqlite":
        return sql.replace("%s", "?")
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

    if PG_POOL is not None:
        return

    with _PG_POOL_LOCK:
        if PG_POOL is not None:
            return

        database_url = _database_url()

        if _is_sqlite_url(database_url):
            return

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


def _get_or_create_request_connection() -> DbConnection:
    if "db" in g:
        return g.db

    database_url = _database_url()

    if _is_sqlite_url(database_url):
        conn = _sqlite_connect(database_url)
        g.db = conn
        g.db_kind = "sqlite"
        g.db_in_transaction = False
        return conn

    pool = _get_pg_pool()
    conn = pool.getconn()
    conn.autocommit = True

    g.db = conn
    g.db_kind = "pg"
    g.db_in_transaction = False
    return conn


def get_db() -> DbConnection:
    return _get_or_create_request_connection()


def close_db(e: Exception | None = None) -> None:
    conn = g.pop("db", None)
    kind = g.pop("db_kind", None)
    g.pop("db_in_transaction", None)

    if conn is None:
        return

    if kind == "sqlite":
        try:
            conn.close()
        except Exception:
            pass
        return

    try:
        conn.autocommit = True
    except Exception:
        pass

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


def db_execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    normalized_sql = _normalize_sql(sql)

    with _db_cursor(dict_rows=False) as cur:
        cur.execute(normalized_sql, params)


def db_fetchone(sql: str, params: tuple[Any, ...] = ()) -> DbRow | None:
    normalized_sql = _normalize_sql(sql)

    with _db_cursor(dict_rows=True) as cur:
        cur.execute(normalized_sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)


def db_fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[DbRow]:
    normalized_sql = _normalize_sql(sql)

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
