"""
Public database schema entry point.

This file stays intentionally small.
It orchestrates focused schema modules so schema logic
does not collapse back into a single monolith.
"""

from __future__ import annotations

from flask import g

from . import schema_bootstrap
from . import schema_comms
from . import schema_core
from . import schema_people
from . import schema_requests


def init_db() -> None:
    """
    Initialize all database structures, indexes, and bootstrap data.
    """
    kind = g.get("db_kind")
    if not kind:
        raise RuntimeError("Database kind is not set on flask.g")

    schema_core.ensure_tables(kind)
    schema_people.ensure_tables(kind)
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)

    schema_people.ensure_columns_and_constraints(kind)
    schema_requests.ensure_columns_and_constraints(kind)

    schema_people.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)

    schema_bootstrap.ensure_all(kind)
