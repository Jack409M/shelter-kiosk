from __future__ import annotations

from threading import Lock
from typing import Any

from flask import current_app, g

try:
    from psycopg2.pool import PoolError, SimpleConnectionPool
except Exception:
    PoolError = Exception
    SimpleConnectionPool = None


PG_POOL = None
_PG_POOL_LOCK = Lock()


def _init_pg_pool() -> None:
    global PG_POOL

    if PG_POOL is not None:
        return

    with _PG_POOL_LOCK:
        if PG_POOL is not None:
            return

        database_url = current_app.config.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required. App is locked to Postgres.")

        if SimpleConnectionPool is None:
            raise RuntimeError("psycopg2 is not installed, but DATABASE_URL is set.")

        PG_POOL = SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url,
        )


def _normalize_sql(sql: str) -> str:
    return sql.replace("?", "%s")


def get_db() -> Any:
    if "db" in g:
        return g.db

    database_url = current_app.config.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is required. App is locked to Postgres.")

    _init_pg_pool()
    if PG_POOL is None:
        raise RuntimeError("Postgres pool was not initialized.")
    conn = PG_POOL.getconn()
    conn.autocommit = True
    g.db = conn
    g.db_kind = "pg"
    return conn


def close_db(e: Exception | None = None) -> None:
    conn = g.pop("db", None)
    g.pop("db_kind", None)

    if conn is None:
        return

    global PG_POOL
    if PG_POOL is not None:
        try:
            PG_POOL.putconn(conn)
        except PoolError:
            current_app.logger.warning(
                "Postgres pool ignored duplicate or unknown connection return."
            )


def db_execute(sql: str, params: tuple = ()) -> None:
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(_normalize_sql(sql), params)
    finally:
        cur.close()


def db_fetchone(sql: str, params: tuple = ()) -> Any:
    conn = get_db()
    sql = _normalize_sql(sql)

    import psycopg2.extras

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        cur.close()


def db_fetchall(sql: str, params: tuple = ()) -> list[Any]:
    conn = get_db()
    sql = _normalize_sql(sql)

    import psycopg2.extras

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()
