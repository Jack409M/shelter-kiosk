from __future__ import annotations

"""Disaster recovery readiness markers for the System Health dashboard.

This file does not perform a restore by itself. It records that the app has a
manual cross region recovery path: daily Railway backups, daily local backup
copies, a documented recovery runbook, and a tested restore process.
"""

DR_CONFIG = {
    "primary_region": "railway_primary",
    "secondary_region": "manual_cross_region_restore",
    "backup_sources": "daily_railway_backups + daily_local_computer_backups",
    "runbook_documented": True,
    "secondary_ready": True,
    "restore_tested": True,
    "failover_tested": True,
}
