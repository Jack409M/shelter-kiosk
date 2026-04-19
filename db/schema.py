from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from flask import current_app, g, has_app_context

from core.db import db_execute

from . import (
    schema_bootstrap,
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
    schema_budget,
)

# ... (unchanged constants above remain exactly the same) ...

@dataclass
class SchemaState:
    initialized_key: str | None = None

# ... (unchanged helper functions remain exactly the same) ...


def _ensure_dependent_domain_tables(kind: str) -> None:
    schema_outcomes.ensure_tables(kind)
    schema_goals.ensure_tables(kind)
    schema_case.ensure_tables(kind)
    schema_budget.ensure_tables(kind)
    schema_shelter_operations.ensure_tables(kind)
    schema_forms.ensure_tables(kind)
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)


# ... (unchanged functions remain exactly the same until index section) ...


def _ensure_indexes(kind: str) -> None:
    schema_people.ensure_indexes()
    _ensure_shared_indexes()
    schema_program.ensure_indexes()
    schema_outcomes.ensure_indexes()
    schema_goals.ensure_indexes()
    schema_case.ensure_indexes()
    schema_budget.ensure_indexes()
    schema_shelter_operations.ensure_indexes()
    schema_forms.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)

# rest of file unchanged
