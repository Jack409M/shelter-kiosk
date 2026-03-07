from flask import g


def is_postgres():
    return g.get("db_kind") == "pg"
