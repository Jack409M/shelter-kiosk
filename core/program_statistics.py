from __future__ import annotations

from core.stats.common import (
    normalize_date_range_key,
    normalize_population,
    normalize_scope,
    window_dates,
)
from core.stats.demographics import get_demographics
from core.stats.family import get_family_composition
from core.stats.outcomes import get_exit_outcomes
from core.stats.recovery import (
    get_recovery_and_sobriety,
    get_trauma_and_vulnerability,
)
from core.stats.snapshot import (
    get_capacity_snapshot,
    get_program_snapshot,
    get_scope_comparison,
    get_shelter_distribution,
)
from core.stats.stability import (
    get_barriers_to_stability,
    get_education_and_income,
)


def get_dashboard_statistics(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    normalized_scope = normalize_scope(scope)
    normalized_population = normalize_population(population)
    normalized_date_range = normalize_date_range_key(date_range)
    start_date, end_date = window_dates(normalized_date_range, start, end)

    return {
        "filters": {
            "scope": normalized_scope,
            "population": normalized_population,
            "date_range": normalized_date_range,
            "start_date": start_date,
            "end_date": end_date,
        },
        "program_snapshot": get_program_snapshot(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "scope_comparison": get_scope_comparison(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "capacity_snapshot": get_capacity_snapshot(),
        "shelter_distribution": get_shelter_distribution(
            normalized_population, normalized_date_range, start, end
        ),
        "demographics": get_demographics(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "family_composition": get_family_composition(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "recovery_and_sobriety": get_recovery_and_sobriety(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "trauma_and_vulnerability": get_trauma_and_vulnerability(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "barriers_to_stability": get_barriers_to_stability(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "education_and_income": get_education_and_income(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "exit_outcomes": get_exit_outcomes(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
    }
