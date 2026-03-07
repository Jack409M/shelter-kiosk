from flask import g


def is_postgres():
    return g.get("db_kind") == "pg"

def db_placeholder():
    if g.get("db_kind") == "pg":
        return "%s"
    return "?"
