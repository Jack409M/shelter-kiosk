"""
Public database schema entry point.

This file is intentionally small.

It does not define every table directly. Instead, it orchestrates
focused schema modules so database logic stays maintainable and
does not grow back into one giant monolith.
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
    Initialize all database tables, follow up schema adjustments,
    indexes, and bootstrap data.

    Safe to call repeatedly on app startup.
    """
    kind = g.get("db_kind")
    if not kind:
        raise RuntimeError("Database kind is not set on flask.g")

    # 1. Base tables
    schema_core.ensure_tables(kind)
    schema_people.ensure_tables(kind)
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)

    # 2. Follow up schema adjustments
    # These are the "make sure this column or cleanup exists" steps.
    schema_people.ensure_columns_and_constraints(kind)
    schema_requests.ensure_columns_and_constraints(kind)

    # 3. Indexes
    schema_people.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)

    # 4. Seed / bootstrap tasks
    schema_bootstrap.ensure_all(kind)
