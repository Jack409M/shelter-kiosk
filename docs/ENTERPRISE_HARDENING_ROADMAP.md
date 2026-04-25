# Shelter Kiosk — Enterprise Hardening Roadmap

This document defines how the system evolves from a hardened internal tool into a production-grade enterprise platform.

This is not a rewrite plan.
This is a controlled elevation plan.

---

## 1. Current State (Verified)

The system already includes:

* App factory architecture (`core/app_factory.py`)
* Dynamic blueprint loading
* Database abstraction (SQLite + Postgres)
* Transaction safety and rollback guarantees
* Migration system with version enforcement
* CSRF protection and request security hooks
* Rate limiting and IP banning
* Chicago time normalization across UI
* CI pipeline with:

  * Ruff
  * MyPy
  * Structured pytest suites
  * Dangerous diff guard
* Anti-AI corruption protections
* Explicit engineering workflow rules

This is a **controlled system**, not a prototype.

---

## 2. What This System Is Becoming

Target state:

A **single-organization enterprise operations platform** for shelter management with:

* Strict data integrity
* Full auditability
* Role-based control
* Predictable workflows
* Operational resilience
* Clean, unified UI

Comparable to internal tools built at:

* Microsoft
* Amazon
* Stripe

---

## 3. Core Architecture (Locked)

These are **not to be rewritten**:

* App factory pattern
* DB abstraction layer
* Migration runner
* Route modularization
* Pass system separation
* Intake baseline model
* Engineering workflow rules

Changes must **extend**, not replace.

---

## 4. System Domains (Must Be Formalized)

Each domain becomes a first-class module:

* Residents
* Intake
* Case Management
* Pass System
* Attendance
* Rent Tracking
* Inspections
* Reports
* Operations Settings
* Audit / Logging

No cross-domain logic leakage.

---

## 5. Phase Plan

### Phase 1 — UI Unification

Goal: Make the system feel like one product.

* Single layout template
* Consistent navigation
* Unified header + sidebar
* Standard alert system
* Standard table system
* Clean empty states

No logic changes.

---

### Phase 2 — Audit & Permissions Hardening

Goal: Every action is accountable.

* Enforce audit logging for all state changes
* Expand role enforcement
* Remove implicit permissions
* Add audit review views

---

### Phase 3 — Data Integrity Enforcement

Goal: Prevent bad data permanently.

* Add foreign key constraints
* Add uniqueness rules
* Enforce enrollment scoping
* Add migration validation tests

---

### Phase 4 — Operational Reliability

Goal: Survive real-world failure.

* Health check endpoint
* Startup diagnostics logging
* Backup verification process
* Failure mode handling

---

### Phase 5 — Product Maturity

Goal: Enterprise polish.

* Dashboard views
* Status indicators (pass, fail, warning)
* Summary cards
* Workflow clarity

---

## 6. Non-Negotiable Rules

* No full rewrites
* No breaking working flows
* No speculative refactors
* No UI changes mixed with logic changes
* Every change must align to a phase

---

## 7. Definition of Enterprise Quality

The system must be:

* Predictable
* Traceable
* Recoverable
* Understandable by staff
* Resistant to bad inputs
* Safe under failure

---

## 8. Guiding Principle

We are not building fast.

We are building something that:

* will not collapse under growth
* will not corrupt data
* will not confuse staff
* will not require rewriting in 6 months

---

## 9. Rule

Every change must answer:

"Does this move the system toward enterprise stability, or away from it?"
