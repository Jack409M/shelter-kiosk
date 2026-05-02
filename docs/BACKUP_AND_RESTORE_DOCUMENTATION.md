Shelter Kiosk Backup and Restore Documentation
Current setup, backup locations, testing process, local download process, restore process, and proof standard
Prepared May 2, 2026
Executive Summary
The Shelter Kiosk backup posture now has four real pieces in place: Railway daily production database backups, a daily database copy saved to the authorized work computer, repository protection through GitHub main plus snapshot branches, and documented restore validation before production recovery. The app also includes an admin only Backup and Restore Documentation page and a System Health backup status card.
The strongest part of the current setup is that restoration is treated as the proof standard. A backup is not considered trusted merely because it exists. It must be validated in a disposable restore environment, checked for critical tables, and tested before it is used for any production recovery decision.
The main remaining documentation gap is operational detail outside the repo: the exact folder path on the authorized work computer, the exact person responsible for the daily download, and the written log showing each backup date, file size, checksum, and restore test result. Those details should be filled in by DWC because they are not visible in the code repository.
What Has Been Built
Area	What it does	Status
Production database backups	Railway performs daily production database backups. The repo records this as a locked backup fact and the admin documentation page repeats it.	In place
Local work computer backup copy	A daily database backup copy is saved to the authorized local work computer.	In place by policy, exact local folder should be recorded
Manual export script	scripts/export_postgres_backup.sh exports a Postgres database with pg_dump, compresses it, creates a latest copy, and writes SHA256 checksum files.	In place
Restore runbook	RECOVERY.md explains code recovery, database restore drill, full disaster recovery, weekly drill checklist, and completion standard.	In place
Restore validation workflow	GitHub Actions workflow restores a sanitized sql or sql.gz backup into a disposable Postgres database, checks core tables, and runs pytest.	In place for sanitized backups
In app backup documentation	Admin route /staff/admin/backup-documentation renders a backup summary, restore boundaries, daily checklist, and recovery procedure.	In place
System Health backup card	System Health reports that Railway daily backups and local daily backups are in place and points staff to the backup documentation page.	In place
Disaster recovery markers	core/dr_config.py records repo branch backups, daily Railway backups, daily work computer backups, restore testing, and failover readiness markers.	In place
Backup Sources and Locations
1. Railway production database backup
Railway is the primary hosting and database platform. The documented operating model says the production database is backed up by Railway each day. This is the first recovery source for production database loss, corruption, or accidental data damage.
•	Location: Railway project database backup area.
•	Frequency: Daily.
•	Use: Primary production database recovery source.
•	Important boundary: Production restore should be performed through controlled Railway level database tools, not through the application user interface.
2. Authorized work computer database backup copy
The documented operating model also says a daily database backup copy is saved to the authorized work computer. This gives DWC a local copy outside Railway.
•	Location: Authorized DWC work computer. The exact folder path should be written here by the system owner.
•	Frequency: Daily.
•	Recommended naming format: shelter_kiosk_YYYYMMDD_HHMM.sql.gz
•	Recommended companion file: same file name ending in .sha256
•	Use: Local recovery copy and independent backup evidence.
3. GitHub repository and snapshot branch backup
The live GitHub repository remains the source of truth for code. The recovery runbook also describes daily snapshot branches named snapshot/main/YYYY/MM/DD style in concept as snapshot main by date. These +++protect against accidental file deletion, truncation, or bad code changes.
•	Location: GitHub repository Jack409M/shelter-kiosk.
•	Primary code source: origin/main.
•	Snapshot source: snapshot branches named by date.
•	Use: Restore one file, restore several files, or rebuild a clean environment.
4. Manual Postgres export file
The export script creates a compressed SQL backup using pg_dump. It requires SOURCE_DATABASE_URL and refuses to run unless the value is a Postgres URL. It writes a timestamped .sql.gz file, copies it to a latest .sql.gz file, and creates SHA256 checksum files for both.
•	Script: scripts/export_postgres_backup.sh
•	Default output folder: ./backups/postgres
•	Default prefix: shelter-kiosk
•	Backup format: plain SQL compressed with gzip
•	Integrity check: test that the output file exists and is not empty, then create SHA256 checksum files
How Backups Are Created
Railway backup
Railway is responsible for the daily platform database backup. The app does not create those Railway snapshots itself. DWC should verify the Railway backup panel daily and record the date and time of the latest successful backup.
Local computer backup
The local backup copy should be downloaded or exported daily to the authorized work computer. The repository does not expose the exact local folder path. That path should be added to this document once confirmed.
Manual export command
Use this only from an authorized environment with access to the source database URL. Do not paste production credentials into chat, tickets, screenshots, GitHub Actions, or documentation.
export SOURCE_DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
export BACKUP_DIR="./backups/postgres"
bash scripts/export_postgres_backup.sh
How Backups Are Tested
The current proof standard is restore testing. A backup is considered usable only after it has been restored into a disposable database and checked. The repo provides two restore testing models.
Model A: Local restore drill
1.	Create or reset a test database.
2.	Restore the backup into that test database.
3.	Point the app at the restored test database using DATABASE_URL.
4.	Run pytest against the restored database.
5.	Spot check critical tables and counts.
6.	Record backup date, file name, file size, checksum, restore result, and test result.
Model B: GitHub Actions sanitized backup restore validation
The workflow named Sanitized Backup Restore Validation accepts an HTTPS URL for a sanitized .sql or .sql.gz backup. It starts a disposable Postgres 15 service, downloads the backup, refuses non local restore targets, restores the backup, checks core tables, and runs the full test suite.
•	This workflow is appropriate for sanitized backups only.
•	Production credentials should never be placed into GitHub Actions for this process.
•	The workflow checks residents, program_enrollments, intake_assessments, and resident_passes.
Restore Procedure
Before any restore
7.	Identify the incident and decide whether recovery is actually required.
8.	Select the cleanest backup from before the incident.
9.	Validate that backup in a disposable restore environment first.
10.	Confirm the backup date, source, file size, checksum, and restore test result.
11.	Document the expected data gap between the backup time and the restore time.
12.	Do not restore directly into production from the application UI.
Database restore drill commands
dropdb shelter_kiosk_restore_test || true
createdb shelter_kiosk_restore_test
gunzip -c shelter_kiosk_latest.sql.gz | psql shelter_kiosk_restore_test
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/shelter_kiosk_restore_test"
pytest -q
Critical table spot checks
SELECT COUNT(*) FROM residents;
SELECT COUNT(*) FROM program_enrollments;
SELECT COUNT(*) FROM resident_passes;
SELECT COUNT(*) FROM intake_assessments;
SELECT COUNT(*) FROM family_snapshots;
Code Restore Procedure
The code recovery standard is to resync to the live GitHub repository first, because the live repository is the source of truth and local environments can lag.
git fetch origin
git reset --hard origin/main
pytest -q
bash scripts/verify_restore.sh
For a corrupted file, the recovery runbook allows restoring a single file from a dated snapshot branch, then running tests. For broad corruption, restore the working tree from a known good snapshot branch and test again.
System Health and In App Documentation
The admin system includes a backup documentation page at /staff/admin/backup-documentation. That page is admin protected and explains the backup summary, restore boundaries, daily checklist, and recovery procedure. The System Health dashboard also includes a Backup System card that reports daily Railway backups, daily local computer backups, and the requirement for restore testing before production recovery.
Current Strengths
•	The system has both cloud platform database backups and a local daily backup copy.
•	The export script creates timestamped compressed backups and checksum files.
•	The recovery runbook is explicit about resyncing code before testing or repairing.
•	The restore process requires a disposable database before production recovery.
•	The sanitized GitHub Actions workflow tests whether a backup can restore and whether the app tests pass afterward.
•	The application exposes backup status and backup documentation to admins.
Current Gaps to Close
Gap	Why it matters	Recommended fix
Exact local folder path	The repo says backups are saved to the authorized work computer, but it does not record the exact folder path.	Add the exact folder path and owner name to this document.
Backup evidence log	The repo does not show a daily human readable backup evidence log.	Create a simple spreadsheet or page with date, source, file name, file size, checksum, tester, restore result, and notes.
Automated production backup download proof	The repo documents the policy, but does not prove the daily local download happened.	Add a daily checklist or admin record that confirms the file was downloaded.
Production restore runbook details	The repo correctly says use Railway level tools, but does not include exact Railway screen steps.	Add exact Railway restore steps after confirming them in the Railway dashboard.
Retention policy	The repo does not clearly state how long local backups are kept.	Set a retention rule such as daily for 30 days, weekly for 12 weeks, monthly for 12 months.
Encrypted local storage proof	The repo does not show whether the local backup folder is encrypted.	Confirm BitLocker or equivalent protection on the work computer.
Recommended Backup Log Template
Field	Value
Backup date	
Source	Railway or manual export
File name	
Storage location	Railway or authorized work computer folder
File size	
SHA256 checksum	
Downloaded by	
Restore tested by	
Restore test date	
Disposable database used	
Core table checks passed	Yes or No
Full tests passed	Yes or No
Notes or incident number	
Plain English Recovery Standard
Recovery is not complete when a backup file is found. Recovery is complete only when the selected backup has been restored, critical tables are present, tests have passed, and the restored system has been checked before users rely on it again.
Source Files Reviewed
•	scripts/export_postgres_backup.sh
•	RECOVERY.md
•	.github/workflows/backup-restore-validation.yml
•	routes/admin_parts/backup_docs.py
•	core/dr_config.py
•	routes/admin_parts/sh_dashboard.py
•	routes/admin.py
•	templates/admin_backup_documentation.html
•	scripts/verify_restore.sh
Owner Fill In Section
Item	Answer
Authorized work computer name	
Local backup folder path	
Person responsible for daily download	
Person responsible for weekly restore test	
Railway project name	
Backup retention rule	
Last successful restore test date	
Last full disaster recovery drill date	


