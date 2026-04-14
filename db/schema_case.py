from __future__ import annotations

from . import (
    schema_case_calendar,
    schema_case_children,
    schema_case_intake_drafts,
    schema_case_notes,
    schema_case_support,
    schema_writeups,
)


def ensure_tables(kind: str) -> None:
    schema_case_notes.ensure_tables(kind)
    schema_case_support.ensure_tables(kind)
    schema_case_calendar.ensure_tables(kind)
    schema_case_children.ensure_tables(kind)
    schema_case_intake_drafts.ensure_tables(kind)
    schema_writeups.ensure_tables(kind)


def ensure_indexes() -> None:
    schema_case_notes.ensure_case_notes_indexes()
    schema_case_support.ensure_case_support_indexes()
    schema_case_calendar.ensure_calendar_indexes()
    schema_case_children.ensure_case_children_indexes()
    schema_case_intake_drafts.ensure_case_intake_drafts_indexes()
    schema_writeups.ensure_writeups_indexes()
