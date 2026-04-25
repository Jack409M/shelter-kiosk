# ENGINEERING_WORKFLOW_RULES.md

## Shelter Kiosk — Engineering Workflow Rules

This document defines how all code work must be performed on this project.

This is not optional guidance.
This is the working contract.

---

## 1. Source of Truth

The **live GitHub repository is the source of truth**.

Never rely on:

* Memory
* Assumptions
* Old snippets
* Reconstructed code

If there is a conflict between expectation and the repo, the repo wins.

---

## 2. Codespaces Lag Awareness

Codespaces can lag behind the live repository.

Do not assume the working environment is current.

All decisions, edits, and test requests must account for possible drift between:

* local environment
* Codespaces
* live repo

---

## 3. Mandatory Resync Rule

A **repo resync must be part of the normal workflow**.

It is not optional and not situational.

Resync must occur:

* before inspecting files for accuracy
* after making file changes
* before requesting any test run

This ensures all work is based on current state.

---

## 4. No Testing on Stale State

Do not request or rely on test results from a possibly stale environment.

Correct sequence:

1. resync
2. verify file state
3. then run tests

Never invert this order.

---

## 5. No Flippant Answers

Do not provide shallow or speculative answers.

Do not guess.

All responses must be based on:

* actual file inspection
* real code paths
* confirmed behavior

Speed is not the priority. Accuracy is.

---

## 6. Root Cause Investigation Required

Do not fix symptoms.

Investigate until the **real cause** is identified.

This includes:

* reading the full file
* checking surrounding logic
* tracing data flow across layers if needed
* verifying assumptions against actual code

The first visible issue is not always the real issue.

---

## 7. File First Discipline

Before suggesting any fix:

* read the actual file
* understand its structure
* review related functions and dependencies

Do not give abstract advice when the file can be examined.

---

## 8. Fix the Correct File

Do not edit the most convenient file.

Identify and fix the **actual source file** responsible for the issue.

Avoid:

* scattered edits
* speculative multi-file changes

Edits must be intentional and justified by code flow.

---

## 9. One Strong Pass Over Many Weak Passes

Prefer a **single, well-informed fix** over repeated small guesses.

This requires:

* deeper upfront analysis
* clear understanding before editing

Avoid iterative thrashing.

---

## 10. One Pass Does Not Mean Rushed

A strong pass is not rushed.

It means:

* the issue is understood
* the fix is deliberate
* the change aligns with the system

The goal is correctness, not speed.

---

## 11. Preserve Existing Functionality

Do not remove or break working features while fixing issues.

If something appears unused or unnecessary:

* do not remove it unless confirmed
* do not simplify at the cost of behavior

Stability is critical.

---

## 12. Required Working Sequence

All work must follow this sequence:

1. Treat repo as source of truth
2. Resync environment
3. Inspect real file(s)
4. Identify root cause
5. Apply deliberate fix
6. Resync again if needed
7. Request test run

Do not skip steps.

---

## 13. Expected Standard

All engineering work must be:

* repo grounded
* evidence based
* deeply investigated
* intentionally executed

---

## 14. Failure Pattern to Avoid

The following pattern is unacceptable:

* stale environment
* shallow inspection
* fast assumption
* wrong file edited
* repeated micro fixes
* wasted cycles

This document exists to prevent that.

---

## 15. Rule

**Read the real repo.
Resync as part of the workflow.
Investigate deeply.
Fix the actual problem.
Prefer one grounded pass over repeated speculation.**

You must follow these rules:

1. Never make silent terminal edits to files.
2. For any file change:
   - State the filename first
   - Show line count before and after
   - Show git diff --stat after the change
3. If a change is small, the diff must also be small. If not, stop.
4. Do not use placeholder text or partial file rewrites.
5. Prefer surgical edits unless explicitly told to rewrite full file.
6. Treat the GitHub repo as source of truth, not memory.

an explicit ban on placeholder code like SNIP, ... unchanged, or rest unchanged
an explicit ban on full file rewrites unless you specifically request one
a rule to express changes as tight diffs first for risky files
a rule that mass import failures should trigger an immediate “assume truncation first” rollback check
a formal rollback rule to restore the prior good commit for the touched file

checking the actual repo code paths and existing repo files first so the new files match the live structure instead of guessed patterns.


UI Field Width Standards
Use these classes for all new or converted forms.

Apply width classes to the .form-field wrapper, not directly to the input.

Standard Widths
Field Type	Class
First name	field-width-name-first
Last name	field-width-name-last
Full name	field-width-name-full
Phone	field-width-phone
ZIP code	field-width-zip
Birth year	field-width-year
Date	field-width-date
Time	field-width-time
Resident code / apartment / unit	field-width-code
Email	field-width-email
Address / notes	field-width-address
Rule
Do not add new one-off input widths.

Use the existing field-width-* classes unless there is a documented reason not to.
