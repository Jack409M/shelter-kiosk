from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import db_fetchall, db_fetchone
from core.report_filters import mask_small_counts
from core.stats.common import (
    base_enrollment_where,
    normalize_date_range_key,
    normalize_population,
    normalize_scope,
    row_get,
    to_int,
)


def get_family_composition(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = base_enrollment_where(
        normalize_scope(scope),
        normalize_population(population),
        normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    child_rows = (
        db_fetchall(
            f"""
        SELECT DISTINCT rc.id, rc.resident_id, rc.birth_year
        FROM resident_children rc
        JOIN program_enrollments pe ON pe.resident_id = rc.resident_id
        {where_sql}
        """,
            tuple(where_params),
        )
        or []
    )

    current_year = datetime.now().year

    resident_ids_with_children: set[int] = set()
    children_in_shelter = 0
    children_out_of_shelter = 0
    ages_0_5 = 0
    ages_6_11 = 0
    ages_12_17 = 0
    ages_18_21 = 0
    ages_22_65 = 0

    for row in child_rows:
        resident_id = row_get(row, "resident_id", 1)
        birth_year = to_int(row_get(row, "birth_year", 2), 0)

        if resident_id:
            resident_ids_with_children.add(resident_id)

        children_in_shelter += 1

        if not birth_year:
            continue

        age = current_year - birth_year

        if 0 <= age <= 5:
            ages_0_5 += 1
        elif 6 <= age <= 11:
            ages_6_11 += 1
        elif 12 <= age <= 17:
            ages_12_17 += 1
        elif 18 <= age <= 21:
            ages_18_21 += 1
        elif 22 <= age <= 65:
            ages_22_65 += 1

    family_row = db_fetchone(
        f"""
        SELECT
            COALESCE(SUM(COALESCE(fs.kids_reunited_while_in_program, 0)), 0) AS reunited,
            COALESCE(SUM(COALESCE(fs.healthy_babies_born_at_dwc, 0)), 0) AS babies_born
        FROM family_snapshots fs
        JOIN (
            SELECT DISTINCT pe.id
            FROM program_enrollments pe
            {where_sql}
        ) filtered_enrollments
          ON filtered_enrollments.id = fs.enrollment_id
        """,
        tuple(where_params),
    )

    reunited = to_int(row_get(family_row, "reunited", 0, 0), 0)
    babies_born = to_int(row_get(family_row, "babies_born", 1, 0), 0)
    residents_with_children = len(resident_ids_with_children)

    return {
        "residents_with_children": residents_with_children,
        "residents_with_children_display": mask_small_counts(residents_with_children),
        "children_in_shelter": children_in_shelter,
        "children_in_shelter_display": mask_small_counts(children_in_shelter),
        "children_out_of_shelter": children_out_of_shelter,
        "children_out_of_shelter_display": mask_small_counts(children_out_of_shelter),
        "child_age_groups": [
            {
                "label": "Ages 0 to 5",
                "value": ages_0_5,
                "display_value": mask_small_counts(ages_0_5),
            },
            {
                "label": "Ages 6 to 11",
                "value": ages_6_11,
                "display_value": mask_small_counts(ages_6_11),
            },
            {
                "label": "Ages 12 to 17",
                "value": ages_12_17,
                "display_value": mask_small_counts(ages_12_17),
            },
            {
                "label": "Ages 18 to 21",
                "value": ages_18_21,
                "display_value": mask_small_counts(ages_18_21),
            },
            {
                "label": "Ages 22 to 65",
                "value": ages_22_65,
                "display_value": mask_small_counts(ages_22_65),
            },
        ],
        "children_reunited": reunited,
        "children_reunited_display": mask_small_counts(reunited),
        "healthy_babies_born": babies_born,
        "healthy_babies_born_display": mask_small_counts(babies_born),
    }
