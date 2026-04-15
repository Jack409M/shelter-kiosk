from __future__ import annotations

from db import schema

VERSION = 1
NAME = "baseline"


def apply(kind: str) -> None:
    """
    Baseline migration for the current Shelter Kiosk schema.

    This intentionally reuses the existing schema initialization flow so we can
    introduce migration tracking without trying to reverse engineer every past
    schema change into separate historical migrations.

    Right now this is the safest bridge strategy:

    - fresh databases can be brought up to the current schema shape
    - existing databases can be stamped through the migration runner
    - future schema changes can move into explicit numbered migrations
    """
    schema._run_schema_initialization(kind)
