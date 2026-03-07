from __future__ import annotations

import os
import sqlite3
from typing import Any

from flask import current_app, g

try:
    from psycopg2.pool import SimpleConnectionPool
except Exception:
    SimpleConnectionPool = None


PG_POOL = None


def _init_pg_pool() -> None:
    global PG_POOL

    if PG_POOL is not None:
        return

    database_url = current_app.config.get("DATABASE_URL")
    if not database_url:
        return

    if SimpleConnectionPool is None:
        raise RuntimeError("psycopg2 is not installed, but DATABASE_URL is set.")

    PG_POOL = SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=database_url,
    )


def get_db() -> Any:
    if "db" in g:
        return g.db

    database_url = current_app.config.get("DATABASE_URL")
    sqlite_path = current_app.config.get("SQLITE_PATH")

    if database_url:
        _init_pg_pool()
        if PG_POOL is None:
            raise RuntimeError("Postgres pool was not initialized.")
        conn = PG_POOL.getconn()
        conn.autocommit = True
        g.db = conn
        g.db_kind = "pg"
        return conn

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    g.db = conn
    g.db_kind = "sqlite"
    return conn


def close_db(e: Exception | None = None) -> None:
    conn = g.pop("db", None)
    kind = g.pop("db_kind", None)

    if conn is None:
        return

    if kind == "pg":
        global PG_POOL
        if PG_POOL is not None:
            PG_POOL.putconn(conn)
        return

    conn.close()


def db_execute(sql: str, params: tuple = ()) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)

    if g.get("db_kind") != "pg":
        conn.commit()

    cur.close()


def db_fetchone(sql: str, params: tuple = ()) -> Any:
    conn = get_db()
    kind = g.get("db_kind")

    if kind == "pg":
        import psycopg2.extras

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        row = cur.fetchone()
        cur.close()
        return row

    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    return row


def db_fetchall(sql: str, params: tuple = ()) -> list[Any]:
    conn = get_db()
    kind = g.get("db_kind")

    if kind == "pg":
        import psycopg2.extras

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows
