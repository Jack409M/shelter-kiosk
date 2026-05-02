# Sanitized Backup Validation Runbook

This runbook explains how to create and use a sanitized database backup for restore validation without exposing production resident data.

## Purpose

The restore validation workflow proves that a database backup can be restored into a disposable database and that the application can run against the restored data.

This process is for validation only. It does not restore production.

## Safety Rules

1. Do not upload a production database backup containing resident data to GitHub Actions.
2. Do not paste production database credentials into GitHub, chat, tickets, screenshots, or documentation.
3. Do not restore into the production database from the application UI.
4. Validate backups only in disposable databases.
5. Treat free text fields as sensitive because staff may have entered names, phone numbers, addresses, or case details.
6. Keep sanitized backup links temporary and remove them after validation.

## Current Restore Validation Workflow

The GitHub Actions workflow is:

```text
.github/workflows/backup-restore-validation.yml
```

It accepts one required input:

```text
backup_url
```

That value must be an HTTPS URL to a sanitized `.sql` or `.sql.gz` backup file.

The workflow then:

1. Starts a disposable Postgres database inside GitHub Actions.
2. Downloads the sanitized backup file.
3. Refuses to restore into any non local database target.
4. Restores the backup into the disposable database.
5. Checks core table counts.
6. Runs the test suite.
7. Produces `restore-validation-report.txt` as an artifact.

## What Counts as Sanitized

A sanitized backup must not contain real resident identifying information.

At minimum, the sanitizer must scrub or replace:

- Resident first names
- Resident last names
- Resident phone numbers
- Resident email addresses
- Resident emergency contact names
- Resident emergency contact phone numbers
- Resident child names
- Free text resident notes
- Free text child notes
- SMS message content if present
- Intake draft payloads if present
- Audit details that include names, phone numbers, emails, or personal facts
- Any other free text field that may contain protected or sensitive information

The sanitizer may preserve non identifying operational values when needed for testing, such as:

- Table structure
- Record IDs
- Shelter names
- Program levels
- Dates when not identifying by themselves
- Boolean status fields
- Counts and relationships between records

## Recommended Sanitized Values

Examples of safe replacement values:

```text
Resident first_name: Test
Resident last_name: Resident0001
Phone: 5550000000
Email: resident0001@example.invalid
Emergency contact name: Test Contact0001
Emergency contact phone: 5550000001
Child name: Test Child0001
Free text notes: Sanitized for restore validation.
```

Use `.invalid` email domains so the data can never accidentally route to a real person.

## Manual Process Until a Sanitizer Script Exists

Use this process only from an authorized local machine or secured admin environment.

1. Export or obtain a production backup from Railway or the authorized local backup copy.
2. Restore the backup into a local disposable database.
3. Run sanitization SQL against the disposable database.
4. Spot check that sensitive fields were replaced.
5. Export the sanitized disposable database to a `.sql.gz` file.
6. Generate a SHA256 checksum for the sanitized file.
7. Upload the sanitized file to a temporary secure location that provides an HTTPS download URL.
8. Run the GitHub restore validation workflow with that HTTPS URL.
9. Download the `restore-validation-report.txt` artifact.
10. Enter the validation status, run ID, report link, backup SHA256, and restore notes in the app.
11. Delete the temporary sanitized backup link after validation.

## Required Spot Checks Before Uploading

Before uploading the sanitized backup anywhere, run checks against the disposable sanitized database.

Examples:

```sql
SELECT id, first_name, last_name, phone, email
FROM residents
LIMIT 10;
```

```sql
SELECT id, emergency_contact_name, emergency_contact_phone
FROM residents
WHERE emergency_contact_name IS NOT NULL OR emergency_contact_phone IS NOT NULL
LIMIT 10;
```

```sql
SELECT id, child_name, notes
FROM resident_children
LIMIT 10;
```

If any real names, phone numbers, email addresses, or personal notes remain, do not upload the file.

## Running the GitHub Validation Workflow

1. Open GitHub.
2. Go to `Jack409M/shelter-kiosk`.
3. Open **Actions**.
4. Select **Sanitized Backup Restore Validation**.
5. Click **Run workflow**.
6. Paste the HTTPS URL to the sanitized `.sql` or `.sql.gz` file.
7. Start the workflow.
8. Wait for the run to complete.
9. Open the completed run.
10. Download the artifact named `restore-validation-report`.

## Recording the Result in the App

After validation finishes, open:

```text
/staff/admin/backup-documentation
```

Record:

- Restore decision notes
- Validation status
- GitHub run ID or test reference
- Validation report link
- Backup SHA256
- Confirmation phrase: `SAVE RESTORE NOTES`

The app blocks saving unless validation status is PASS.

## Production Restore Boundary

Passing restore validation does not automatically authorize production restore.

Before production restore:

1. Confirm the incident requires database recovery.
2. Confirm the selected backup is from before the incident.
3. Confirm the validation report shows PASS.
4. Confirm expected data loss between backup time and restore time.
5. Record approval notes in the app.
6. Use Railway level database tools for the actual production restore.

The application must not perform production database restore directly.

## Future Script Target

The next safe build step is a sanitizer script that creates a sanitized backup from a disposable restored database.

The script should:

1. Require a disposable database URL.
2. Refuse production like hostnames unless an explicit safe local pattern is detected.
3. Scrub known sensitive columns.
4. Scrub free text fields where practical.
5. Export the sanitized database as `.sql.gz`.
6. Write a SHA256 file.
7. Print the file path and checksum.

Do not build a sanitizer script until the full schema has been reviewed for sensitive fields.
