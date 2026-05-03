from __future__ import annotations

"""
Domain contracts for Shelter Kiosk.

These are not enforcement by themselves. They define what must remain true.
Tests should reference these to ensure we do not drift.
"""

# Route rules
NO_STATE_CHANGE_METHODS = {"GET"}
STATE_CHANGE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Pass domain contracts
PASS_DOMAIN_CONTRACTS = {
    "no_get_state_change": True,
    "passes_move_with_resident_on_transfer": True,
    "passes_independent_from_attendance": True,
    "passes_independent_from_promotion": True,
    "passes_independent_from_exit": True,
}

# Intake domain contracts
INTAKE_DOMAIN_CONTRACTS = {
    "draft_not_reportable": True,
    "final_submit_single_write": True,
    "enrollment_scoped": True,
}

# Promotion domain contracts
PROMOTION_DOMAIN_CONTRACTS = {
    "promotion_is_level_progression_only": True,
    "not_transfer": True,
    "not_exit": True,
}

# Backup domain contracts
BACKUP_DOMAIN_CONTRACTS = {
    "daily_backup": True,
    "local_copy": True,
    "restore_tested": True,
}

# Route boundary contracts
ROUTE_BOUNDARY_CONTRACTS = {
    "routes_do_not_own_business_logic": True,
    "services_own_lifecycle_decisions": True,
}
