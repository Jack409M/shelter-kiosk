from __future__ import annotations

from . import schema_case_calendar
from . import schema_case_children
from . import schema_case_intake_drafts
from . import schema_case_notes
from . import schema_case_support
from . import schema_writeups


def ensure_tables(kind: str) -> None:
    schema_case_notes.ensure_tables(kind)
    schema_case_support.ensure_tables(kind)
    schema_case_calendar.ensure_tables(kind)
    schema_case_children.ensure_tables(kind)
    schema_case_intake_drafts.ensure_tables(kind)
    schema_writeups.ensure_tables(kind)
