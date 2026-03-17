from __future__ import annotations

from core.db import db_fetchall
from core.helpers import is_postgres


# Shelter lookup helpers
#
# Future extraction note
# Additional shelter related query helpers can move here later,
# including active shelter metadata, lookup by id, and caching.


def get_all_shelters() -> list[str]:
    rows = db_fetchall(
        """
        SELECT name
        FROM shelters
        WHERE is_active = %s
        ORDER BY name ASC
        """
        if is_postgres()
        else """
        SELECT name
        FROM shelters
        WHERE is_active = 1
        ORDER BY name ASC
        """,
        (True,) if is_postgres() else (),
    )

    names: list[str] = []

    for row in rows:
        if isinstance(row, dict):
            name = row.get("name") or ""
        else:
            name = row[0] or ""

        if name:
            names.append(name)

    return names
