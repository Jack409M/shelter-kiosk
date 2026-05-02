from __future__ import annotations

"""Disaster recovery readiness markers for the System Health dashboard.

This file does not perform a restore by itself. It records the current
manual recovery model for Shelter Kiosk.

Locked backup facts:

* The live repository is backed up onto a branch.
* The production database is backed up by Railway each day.
* The production database is also backed up to the authorized work computer each day.
* Restore testing remains the proof standard before any production recovery.
"""

DR_CONFIG = {
    "primary_region": "railway_primary",
    "secondary_region": "manual_cross_region_restore",
    "repo_backup": "repository_backed_up_to_branch",
    "database_backup_sources": [
        "daily_railway_database_backup",
        "daily_authorized_work_computer_database_backup",
    ],
    "backup_sources": "repo_branch_backup + daily_railway_database_backup + daily_authorized_work_computer_database_backup",
    "runbook_documented": True,
    "secondary_ready": True,
    "restore_tested": True,
    "failover_tested": True,
}
