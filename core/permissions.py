# core/permissions.py

PERMISSION_MAP = {
    "admin.admin_dashboard": "admin.dashboard.view",
    "reports.reports_index": "reports.view",
    "case_management.index": "residents.manage",
    "attendance.staff_attendance": "attendance.view",
}

ROLE_PERMISSIONS = {
    "admin": {"*"},
    "shelter_director": {
        "admin.dashboard.view",
        "reports.view",
        "residents.manage",
    },
    "case_manager": {
        "residents.manage",
        "attendance.view",
    },
    "staff": {
        "attendance.view",
    },
}
