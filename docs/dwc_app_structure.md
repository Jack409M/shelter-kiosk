# DWC Program Operations Platform
Application Structure

This document defines the planned file and module layout for the program operations platform.

The goal is to keep the codebase modular, readable, and free from giant monolithic files.

---

## Core Rule

Each layer should do one job.

- schema files create tables
- query files read and write data
- service files calculate, validate, and transform
- route files handle requests and choose templates
- templates render pages
- partial templates break large screens into smaller maintainable pieces

If a file starts doing more than one type of job, it should be split.

---

## Planned Directory Structure

```text
app/
├── app.py
├── routes/
│   ├── outcomes_dashboard.py
│   ├── outcomes_intake.py
│   ├── outcomes_updates.py
│   ├── outcomes_services.py
│   ├── outcomes_exit.py
│   ├── outcomes_followups.py
│   ├── weekly_accountability.py
│   ├── recovery_engagement.py
│   ├── case_management_checkins.py
│   ├── appointments.py
│   ├── goals.py
│   ├── reports.py
│   └── imports.py
│
├── db/
│   ├── connection.py
│   ├── queries/
│   │   ├── outcomes_queries.py
│   │   ├── weekly_queries.py
│   │   ├── recovery_queries.py
│   │   ├── case_mgmt_queries.py
│   │   ├── appointments_queries.py
│   │   └── reports_queries.py
│   └── schema/
│       ├── outcomes_core.py
│       ├── outcomes_assessments.py
│       ├── weekly_accountability.py
│       ├── recovery_engagement.py
│       ├── case_management.py
│       ├── appointments.py
│       └── goals.py
│
├── services/
│   ├── metrics_engine.py
│   ├── weekly_calculator.py
│   ├── validation_engine.py
│   ├── appointment_reminders.py
│   ├── import_engine.py
│   └── report_generator.py
│
├── templates/
│   ├── outcomes/
│   │   ├── dashboard.html
│   │   ├── intake_form.html
│   │   ├── update_form.html
│   │   ├── exit_form.html
│   │   ├── followup_form.html
│   │   └── partials/
│   │       ├── intake_demographics.html
│   │       ├── intake_recovery.html
│   │       ├── intake_trauma.html
│   │       ├── intake_family.html
│   │       └── update_services.html
│   │
│   ├── weekly_accountability/
│   ├── recovery/
│   ├── case_management/
│   ├── appointments/
│   ├── reports/
│   └── print/
│
└── static/
    ├── js/
    └── css/
