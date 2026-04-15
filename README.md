# Shelter Kiosk

Shelter Kiosk is the DWC internal program operations platform for resident intake, attendance, case management, resident requests, pass workflows, reporting, kiosk flows, and shelter operations.

This application is a Flask based web app with a modular route structure, shared core services, and a Postgres first production runtime. SQLite is used in tests and isolated local scenarios.

## Current status

This is an active production style application under continued hardening.

Current strengths already in the repo include:

- app factory architecture
- modular route registration
- request security hooks
- audit logging
- rate limiting and security state persistence
- CI with linting, typing, and test coverage
- Docker based runtime

Current engineering direction is to keep the codebase modular, reduce monolithic files, and harden the system toward enterprise grade reliability, security, and operational quality.

## High level architecture

Main application areas:

- `app.py` and `main.py` create the Flask app
- `core/` contains shared runtime, security, database, audit, helpers, pass logic, and service logic
- `db/` contains schema creation and schema upgrade helpers
- `routes/` contains blueprints and route handlers
- `templates/` contains Jinja templates
- `static/` contains styles and static assets
- `tests/` contains pytest coverage for auth, security, resident flows, intake, pass workflows, and performance sanity checks
- `docs/` contains architecture and project rule documents

## Runtime model

Production runtime expectations:

- Flask application served by Gunicorn
- Postgres database via `DATABASE_URL`
- environment driven configuration
- HTTPS enforced outside debug and test mode
- request level security headers applied in app hooks

Important note:

- production should be treated as **Postgres first**
- SQLite support exists for tests and isolated local workflows, but production assumptions should follow Postgres behavior

## Local development setup

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
