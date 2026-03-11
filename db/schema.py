"""
Database schema initialization.

This module initializes all database tables by delegating to
individual schema modules. Each module is responsible for creating
its own tables and indexes.

The order here matters because some tables depend on others.
"""

from __future__ import annotations

from . import schema_core
from . import schema_shelters
from . import schema_people
from . import schema_program
from . import schema_requests
from . import schema_comms


def init_db(kind: str) -> None:
    """
    Initialize all database tables.

    kind will be either:
    - sqlite
    - postgres
    """

    # Core infrastructure tables
    schema_core.ensure_tables(kind)

    # Shelter configuration tables
    schema_shelters.ensure_tables(kind)

    # Resident identity tables
    schema_people.ensure_tables(kind)

    # Program participation tables (NEW)
    schema_program.ensure_tables(kind)

    # Operational request tables
    schema_requests.ensure_tables(kind)

    # Communication / messaging tables
    schema_comms.ensure_tables(kind)

    # --------------------------------------------------
    # Index creation
    # --------------------------------------------------

    schema_people.ensure_indexes()
    schema_program.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)
