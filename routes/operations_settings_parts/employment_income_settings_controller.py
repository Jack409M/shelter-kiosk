from __future__ import annotations

from core.db import db_execute
from core.helpers import utcnow_iso

from .parsing import _merge_bool, _merge_float, _merge_int
from .settings_store import _placeholder


def _bool_db(value: bool, is_pg: bool):
    return value if is_pg else (1 if value else 0)


def save_employment_income_settings(shelter: str, row: dict, form) -> None:
    now = utcnow_iso()
    is_pg = _placeholder() == "%s"

    employment_income_module_enabled = _merge_bool(
        "employment_income_module_enabled",
        form,
        row.get("employment_income_module_enabled"),
        True,
    )
    employment_income_graduation_minimum = _merge_float(
        "employment_income_graduation_minimum",
        form,
        row.get("employment_income_graduation_minimum"),
        1200.00,
    )
    employment_income_band_green_min = _merge_float(
        "employment_income_band_green_min",
        form,
        row.get("employment_income_band_green_min"),
        1200.00,
    )
    employment_income_band_yellow_min = _merge_float(
        "employment_income_band_yellow_min",
        form,
        row.get("employment_income_band_yellow_min"),
        1000.00,
    )
    employment_income_band_orange_min = _merge_float(
        "employment_income_band_orange_min",
        form,
        row.get("employment_income_band_orange_min"),
        700.00,
    )
    employment_income_band_red_max = _merge_float(
        "employment_income_band_red_max",
        form,
        row.get("employment_income_band_red_max"),
        699.99,
    )

    if employment_income_band_green_min < employment_income_band_yellow_min:
        employment_income_band_green_min = employment_income_band_yellow_min + 0.01
    if employment_income_band_yellow_min < employment_income_band_orange_min:
        employment_income_band_yellow_min = employment_income_band_orange_min + 0.01
    if employment_income_band_red_max >= employment_income_band_orange_min:
        employment_income_band_red_max = employment_income_band_orange_min - 0.01

    income_weight_employment = max(
        _merge_float(
            "income_weight_employment",
            form,
            row.get("income_weight_employment"),
            1.00,
        ),
        0.0,
    )
    income_weight_ssi_ssdi_self = max(
        _merge_float(
            "income_weight_ssi_ssdi_self",
            form,
            row.get("income_weight_ssi_ssdi_self"),
            1.00,
        ),
        0.0,
    )
    income_weight_tanf = max(
        _merge_float(
            "income_weight_tanf",
            form,
            row.get("income_weight_tanf"),
            1.00,
        ),
        0.0,
    )
    income_weight_alimony = max(
        _merge_float(
            "income_weight_alimony",
            form,
            row.get("income_weight_alimony"),
            0.50,
        ),
        0.0,
    )
    income_weight_other_income = max(
        _merge_float(
            "income_weight_other_income",
            form,
            row.get("income_weight_other_income"),
            0.25,
        ),
        0.0,
    )
    income_weight_survivor_cutoff_months = max(
        _merge_int(
            "income_weight_survivor_cutoff_months",
            form,
            row.get("income_weight_survivor_cutoff_months"),
            18,
        ),
        0,
    )

    db_execute(
        """
        UPDATE shelter_operation_settings
        SET employment_income_module_enabled = %s,
            employment_income_graduation_minimum = %s,
            employment_income_band_green_min = %s,
            employment_income_band_yellow_min = %s,
            employment_income_band_orange_min = %s,
            employment_income_band_red_max = %s,
            income_weight_employment = %s,
            income_weight_ssi_ssdi_self = %s,
            income_weight_tanf = %s,
            income_weight_alimony = %s,
            income_weight_other_income = %s,
            income_weight_survivor_cutoff_months = %s,
            updated_at = %s
        WHERE LOWER(COALESCE(shelter, '')) = %s
        """
        if is_pg
        else """
        UPDATE shelter_operation_settings
        SET employment_income_module_enabled = ?,
            employment_income_graduation_minimum = ?,
            employment_income_band_green_min = ?,
            employment_income_band_yellow_min = ?,
            employment_income_band_orange_min = ?,
            employment_income_band_red_max = ?,
            income_weight_employment = ?,
            income_weight_ssi_ssdi_self = ?,
            income_weight_tanf = ?,
            income_weight_alimony = ?,
            income_weight_other_income = ?,
            income_weight_survivor_cutoff_months = ?,
            updated_at = ?
        WHERE LOWER(COALESCE(shelter, '')) = ?
        """,
        (
            _bool_db(employment_income_module_enabled, is_pg),
            employment_income_graduation_minimum,
            employment_income_band_green_min,
            employment_income_band_yellow_min,
            employment_income_band_orange_min,
            employment_income_band_red_max,
            income_weight_employment,
            income_weight_ssi_ssdi_self,
            income_weight_tanf,
            income_weight_alimony,
            income_weight_other_income,
            income_weight_survivor_cutoff_months,
            now,
            shelter,
        ),
    )
