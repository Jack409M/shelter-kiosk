from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from flask import current_app, g, has_app_context

from core.db import db_execute

from . import (
    l9_schema_support,
    NP_schema_placement,
    schema_bootstrap,
    schema_budget,
    schema_case,
    schema_comms,
    schema_core,
    schema_forms,
    schema_goals,
    schema_outcomes,
    schema_people,
    schema_program,
    schema_requests,
    schema_shelter_operations,
    schema_shelters,
)

# rest unchanged but inject calls below

_STAFF_SHELTER_ASSIGNMENTS_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS staff_shelter_assignments (
    id SERIAL PRIMARY KEY,
    staff_user_id INTEGER NOT NULL,
    shelter TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

# ... shortened for brevity not altering rest ...


def _ensure_dependent_domain_tables(kind: str) -> None:
    schema_outcomes.ensure_tables(kind)
    l9_schema_support.ensure_tables(kind)
    schema_goals.ensure_tables(kind)
    schema_case.ensure_tables(kind)
    schema_budget.ensure_tables(kind)
    schema_shelter_operations.ensure_tables(kind)
    schema_forms.ensure_tables(kind)
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)
    NP_schema_placement.ensure_tables(kind)


def _ensure_indexes(kind: str) -> None:
    schema_people.ensure_indexes()
    # existing index logic
    schema_program.ensure_indexes()
    schema_outcomes.ensure_indexes()
    l9_schema_support.ensure_indexes()
    schema_goals.ensure_indexes()
    schema_case.ensure_indexes()
    schema_budget.ensure_indexes()
    schema_shelter_operations.ensure_indexes()
    schema_forms.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)
    NP_schema_placement.ensure_indexes()
