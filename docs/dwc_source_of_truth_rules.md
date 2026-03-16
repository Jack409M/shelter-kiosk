# DWC Program Operations Platform
Source of Truth Rules

This document defines the official source of truth for repeated concepts in the system.

The purpose of this file is to prevent duplicate data fields, conflicting values, and inconsistent reporting.

---
## Resident Form Storage

Source of truth:
- resident submitted JotForms remain the editable external form system
- the submitted PDF is the permanent record attached to the resident
- only fields mapped to the DWC dataset update structured database records

Rule:
Do not force every JotForm field into the database.
Only fields that map to the approved DWC dataset should be stored in structured tables.
All other submitted form content must remain available through the saved PDF record.

---

## Program Reporting Dataset

Source of truth:
- the DWC approved resident dataset (currently defined in the 72 column dataset file)

Rule:
The resident reporting dataset defines the official program metrics used for reporting, dashboards, and program evaluation.

Only fields contained in the approved dataset should be treated as official reporting metrics.

New reporting fields should not be added casually to operational tables.  
If a new metric is required, it must first be added to the dataset definition before being used for program reporting.

Operational modules may contain additional fields for workflow purposes, but those fields should not be treated as official program metrics unless they are promoted into the dataset.


## Employment

Source of truth:
- case_manager_updates for current employment context
- weekly forms may capture snapshot values for historical weekly reporting only

Rule:
Do not create multiple permanent employment master fields across unrelated tables.

---

## Program Level

Source of truth:
- current operational value should live on the enrollment context or a later level_history table
- weekly modules may store level_at_submission as a historical snapshot

Rule:
Weekly forms should not become the master source for current level.

---

## Sponsor

Source of truth:
- recovery_profiles

Rule:
Sponsor information should not be permanently duplicated in weekly case management records or unrelated tables.

---

## Recovery Program and Step Work

Source of truth:
- recovery_profiles

Rule:
Current recovery program, current step, and sponsor relationship duration belong in recovery tracking, not general case management tables.

---

## Recovery Meeting Details

Source of truth:
- recovery_meeting_entries

Rule:
Detailed recovery meeting attendance should be stored as meeting entry rows, not as repeated day columns in multiple tables.

---

## Weekly Productive and Work Hours

Source of truth:
- calculated from weekly_submission_entries
- optionally cached on weekly_submissions for display and reporting speed

Rule:
Total work hours and total productive hours should never be hand entered as permanent values.

---

## Weekly General Activity Entries

Source of truth:
- weekly_submission_entries

Rule:
Planned and actual weekly activities should be stored as normalized entry rows, not as giant monday through sunday column sets.

---

## Appointments

Source of truth:
- appointments

Rule:
Appointments should not live only inside free text notes, weekly forms, or case manager narratives.
If an appointment matters for reminders or resident slips, it must exist in the appointments table.

---

## Goals

Source of truth:
- goals

Rule:
Resident goals should not exist only inside meeting notes.
If a goal needs to persist, print, or carry forward, it must exist as a structured goal record.

---

## Services Delivered

Source of truth:
- services

Rule:
Service delivery belongs in dated service records.
Case manager update screens may create service records, but the service record is the official source of truth.

---

## Case Manager One on One Meeting Records

Source of truth:
- case_manager_updates

Rule:
Staff one
