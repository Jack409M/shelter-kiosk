# Shelter Kiosk Service Boundaries

This document defines the working architecture boundary rules for Shelter Kiosk. The goal is not to add ceremony. The goal is to keep the app understandable as it grows.

## Core Rule

Routes should handle web concerns. Services should own business decisions.

A route may:

- read request data
- validate basic web form presence
- check login and role access
- call one service function
- render a template
- redirect with a flash message

A route should not own:

- lifecycle decisions
- cross table write rules
- scoring formulas
- pass status transitions
- transfer side effects
- intake baseline rules
- backup and restore policy logic

## Domain Ownership

### Resident Domain

Resident identity, active status, shelter assignment, enrollment status, and resident level belong to resident domain services.

Resident domain owns these decisions:

- whether a resident is active
- which shelter currently owns the resident
- whether an enrollment is active
- whether a resident can be transferred
- how transfer side effects are applied

Resident domain must not own:

- pass approval decisions
- intake field mapping
- rent scoring formulas
- inspection scoring formulas

### Intake Domain

The official intake baseline belongs to intake services.

Intake domain owns these decisions:

- draft intake versus final intake
- official entry baseline creation
- updates to intake_assessments
- enrollment scoped intake records
- family snapshot creation at intake final submit

Locked rule:

Draft data is not reportable. Final submit writes the official baseline once to program_enrollments, intake_assessments, and family_snapshots.

### Pass Domain

Resident movement permission belongs to pass services.

Pass domain owns these decisions:

- pass request creation
- pass eligibility evaluation
- pass approval
- pass denial
- pass check in
- overdue expiration
- resident notification side effects
- approved pass printability

Locked rules:

- GET routes must never change pass state.
- Staff canonical POST routes are the only state changing pass routes.
- Passes are independent from Attendance, Transfer, Promotion, and Exit logic.
- Pending and approved passes move with the resident during transfer.

### Promotion Domain

Promotion and level progression belong to promotion services.

Promotion domain owns these decisions:

- attendance readiness
- rent readiness
- inspection readiness
- employment readiness
- income readiness
- hard blockers
- promotion approval readiness

Locked rule:

Promotion is level progression only. It is not transfer, exit, or manual deactivation.

### Backup Domain

Backup status, restore notes, export links, and restore testing evidence belong to backup services.

Backup domain owns these decisions:

- last successful backup status
- backup destination reporting
- restore testing notes
- backup download notes
- backup corruption checks

Locked rule:

Backup documentation should state that backups are done daily on Railway, backed up to the work computer daily, and tested to confirm they are not corrupted and can be restored.

## Route Part Rule

`routes/case_management_parts` may remain split by web feature, but the parts should not become separate business domains.

A route part can coordinate the page. It should call services for decisions.

When a route part starts needing cross table rules, duplicate formulas, lifecycle transitions, or large data shaping, that logic should move into a service module.

## Service Naming Rule

Service modules should be named by domain, not by template page.

Preferred examples:

- `core/intake_service.py`
- `core/pass_service.py`
- `core/resident_service.py`
- `core/promotion_service.py`
- `core/backup_service.py`

Avoid names that describe only a screen or button unless the module is strictly presentation glue.

## Contract Rule

A contract is a rule the app must not accidentally break.

Contracts should be captured in one or both places:

- `core/domain_contracts.py` for named architectural rules
- tests that fail when critical routes, tables, symbols, or lifecycle behavior disappear

## Practical Refactor Order

Do not move everything at once.

Use this order when touching related files naturally:

1. Keep the current route working.
2. Identify one business decision inside the route.
3. Move that decision into the owning service.
4. Keep the route as request, service call, render, redirect.
5. Add or update a contract test only for behavior that must never regress.

## Definition of Done For Future Route Work

A route change is architecturally clean when:

- the route does not directly own lifecycle policy
- business rules live in the correct service
- existing behavior is preserved
- state changing routes use POST
- user facing timestamps render in Chicago time
- no unrelated functionality is removed
- any locked domain rule touched by the change has a test or documented contract
