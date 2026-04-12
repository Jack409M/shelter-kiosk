from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Any, Iterator, TypeAlias

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

PG_POOL: Any = None
_PG_POOL_LOCK = Lock()


def _require_database_url() -> str:
    database_url = current_app.config.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required. App is locked to Postgres.")
    return str(database_url)


def _normalize_sql(sql: str) -> str:
    return sql.replace("?", "%s")


def _init_pg_pool() -> None:
    global PG_POOL

    if PG_POOL is not None:
        return

    with _PG_POOL_LOCK:
        if PG_POOL is not None:
            return

        database_url = _require_database_url()

        if SimpleConnectionPool is None:
            raise RuntimeError("psycopg2 is not installed, but DATABASE_URL is set.")

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


def _get_or_create_request_connection() -> PgConnection:
    if "db" in g:
        return g.db

    _require_database_url()
    pool = _get_pg_pool()

    conn = pool.getconn()
    conn.autocommit = True

    g.db = conn
    g.db_kind = "pg"
    g.db_in_transaction = False
    return conn


def get_db() -> PgConnection:
    return _get_or_create_request_connection()


def close_db(e: Exception | None = None) -> None:
    conn = g.pop("db", None)
    g.pop("db_kind", None)
    g.pop("db_in_transaction", None)

    if conn is None:
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
def _db_cursor(*, dict_rows: bool = False) -> Iterator[PgCursor]:
    conn = get_db()
    sql_cursor_factory = RealDictCursor if dict_rows else None

    if dict_rows and sql_cursor_factory is None:
        raise RuntimeError("psycopg2.extras.RealDictCursor is unavailable.")

    cur = conn.cursor(cursor_factory=sql_cursor_factory) if sql_cursor_factory else conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


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
        return dict(row)


def db_fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[DbRow]:
    normalized_sql = _normalize_sql(sql)

    with _db_cursor(dict_rows=True) as cur:
        cur.execute(normalized_sql, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]


@contextmanager
def db_transaction() -> Iterator[PgConnection]:
    conn = get_db()
    already_in_transaction = bool(g.get("db_in_transaction"))

    if already_in_transaction:
        yield conn
        return

    previous_autocommit = conn.autocommit
    conn.autocommit = False
    g.db_in_transaction = True

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        g.db_in_transaction = False
        conn.autocommit = previous_autocommit
