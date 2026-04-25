# Shelter Kiosk Recovery Drill Checklist

This document is the emergency recovery runbook for the Shelter Kiosk repo and database.

Use this when files are deleted, overwritten, truncated, corrupted, or when the app must be rebuilt from a clean state.

The goal is simple: restore known good code, restore known good data, and prove the system works before trusting it again.

---

## 1. Operating Rules

The live GitHub repository is the source of truth.

Before inspecting, testing, or fixing anything, resync first:

```bash
git fetch origin
git reset --hard origin/main
```

Never test stale local state.

Never guess which file is correct. Verify against the live repo or a known good snapshot branch.

---

## 2. Code Corruption or File Loss

Use this when a file is deleted, truncated, overwritten, or corrupted.

### Step 1: Resync to current main

```bash
git fetch origin
git reset --hard origin/main
```

### Step 2: Run the integrity tests

```bash
pytest tests/test_failure_hardening.py tests/test_file_integrity_manifest.py tests/test_enterprise_workflow_contracts.py -q
```

### Step 3: If main is bad, restore from a snapshot branch

Daily snapshot branches are named like:

```text
snapshot/main-YYYY-MM-DD
```

Restore one file:

```bash
git fetch origin
git checkout snapshot/main-YYYY-MM-DD -- path/to/file.py
```

Restore the whole repo working tree from a snapshot:

```bash
git fetch origin
git checkout snapshot/main-YYYY-MM-DD -- .
```

### Step 4: Verify the restored code

```bash
pytest -q
```

If tests fail, restore from an earlier snapshot and test again.

---

## 3. Full Local Restore Verification

Use this when rebuilding a local development environment from scratch.

```bash
bash scripts/verify_restore.sh
```

That script will:

1. Fetch origin.
2. Hard reset to `origin/main`.
3. Create a fresh virtual environment.
4. Install runtime and dev dependencies.
5. Run the full test suite.

A passing run means the repo can be rebuilt cleanly from source.

---

## 4. Database Restore Drill

Daily production database backups are maintained separately.

Run this drill periodically against a test database, not production.

### Step 1: Create or reset a test restore database

Example Postgres commands:

```bash
dropdb shelter_kiosk_restore_test || true
createdb shelter_kiosk_restore_test
```

### Step 2: Restore the backup into the test database

```bash
psql shelter_kiosk_restore_test < backup.sql
```

### Step 3: Point the app at the restored test database

```bash
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/shelter_kiosk_restore_test"
export FLASK_SECRET_KEY="test-secret-key"
export COOKIE_SECURE="0"
export CLOUDFLARE_ONLY="0"
export TWILIO_ENABLED="0"
export TWILIO_INBOUND_ENABLED="0"
export TWILIO_STATUS_ENABLED="0"
```

### Step 4: Run the system tests

```bash
pytest -q
```

### Step 5: Spot check critical counts

```sql
SELECT COUNT(*) FROM residents;
SELECT COUNT(*) FROM program_enrollments;
SELECT COUNT(*) FROM resident_passes;
SELECT COUNT(*) FROM intake_assessments;
SELECT COUNT(*) FROM family_snapshots;
```

Expected counts depend on the backup, but obvious zero counts in important tables should be treated as a failed restore unless the backup is known to be empty.

---

## 5. Partial Data Corruption

Use this when only part of the system looks wrong, such as missing passes, broken family records, or incomplete intake data.

### Step 1: Run integrity and workflow contract tests

```bash
pytest tests/test_failure_hardening.py tests/test_enterprise_workflow_contracts.py -q
```

### Step 2: Decide between full restore and targeted repair

Prefer full database restore if corruption is broad or uncertain.

Use targeted repair only when:

1. The bad records are clearly identified.
2. The affected workflow is understood.
3. A backup exists before repair.
4. The repair can be verified with tests and spot checks.

### Step 3: Verify after repair

```bash
pytest -q
```

---

## 6. Full Disaster Recovery

Use this when a new machine or clean environment must be built.

```bash
git clone <repo-url>
cd shelter-kiosk
bash scripts/verify_restore.sh
```

Then restore the database backup into the target database and run:

```bash
pytest -q
```

Do not declare recovery complete until the full test suite passes.

---

## 7. Weekly Drill Checklist

Run this checklist weekly or after major schema and workflow changes.

```bash
git fetch origin
git reset --hard origin/main
pytest -q
bash scripts/verify_restore.sh
```

For database backups, restore the latest backup into a test database and run:

```bash
pytest -q
```

Record:

- Backup date tested.
- Restore database name.
- Test result.
- Any failures.
- Fixes made.

---

## 8. Emergency Quick Commands

Reset code to main:

```bash
git fetch origin
git reset --hard origin/main
```

Restore one file from snapshot:

```bash
git checkout snapshot/main-YYYY-MM-DD -- path/to/file.py
```

Verify full repo:

```bash
pytest -q
```

Run restore verification:

```bash
bash scripts/verify_restore.sh
```

Restore a Postgres backup into a test database:

```bash
psql shelter_kiosk_restore_test < backup.sql
```

---

## 9. Recovery Completion Standard

Recovery is complete only when:

1. Code is restored from `origin/main` or a known good snapshot.
2. Database is restored from a known good backup if data was affected.
3. Full tests pass.
4. Critical workflow checks pass.
5. The restored environment is verified before users rely on it.
