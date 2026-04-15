# Security Policy

## Scope

Shelter Kiosk is an internal DWC operations platform that handles shelter workflows including resident intake, attendance, case management, resident requests, pass workflows, reporting, and staff operations.

Because this system may involve sensitive operational and resident related information, security issues must be handled carefully and privately.

## Reporting a security issue

Do not open public or broadly visible issues for suspected security problems.

Report security concerns privately to the project owner or authorized administrator through an approved private channel.

Include:

- a clear description of the issue
- the affected area or file
- steps to reproduce if known
- the possible impact
- screenshots or logs only if they do not expose sensitive data
- whether the issue is known to affect production, test, or local only

## Do not include

Do not include any of the following in a report unless specifically requested through a secure channel:

- resident personal data
- staff passwords
- full session cookies
- API secrets
- database dumps
- Twilio credentials
- environment files
- full production URLs with attack payloads if a safer reproduction is possible

## Response expectations

Security reports should be reviewed as quickly as possible and prioritized based on risk.

Target internal handling order:

- critical issues first
- then high risk auth, data exposure, or privilege escalation issues
- then abuse, integrity, and reliability related security issues
- then low risk hardening items

## Examples of security issues

Examples include:

- authentication bypass
- privilege escalation
- unauthorized resident or staff data access
- insecure direct object reference issues
- broken access controls across shelters or roles
- session fixation or session leakage
- CSRF bypass
- missing authorization checks on staff or resident routes
- secret exposure
- insecure bootstrap behavior
- sensitive data written to logs
- injection vulnerabilities
- unsafe file handling
- Twilio webhook trust or spoofing issues
- rate limit or lockout bypass
- kiosk mode escape paths that expose privileged workflows

## Supported handling approach

When a valid security issue is confirmed, the preferred approach is:

- contain the risk
- fix the root cause
- review nearby code paths for the same pattern
- add or update tests
- document any operational follow up required

## Configuration and secret handling

Secrets must not be committed to the repository.

Use environment variables or approved secret management only.

The following must always be treated as secrets when populated:

- `FLASK_SECRET_KEY`
- `DATABASE_URL` credentials
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- bootstrap admin credentials
- any session or token material

## Operational security expectations

Production expectations include:

- HTTPS only
- Postgres backed production runtime
- least privilege access
- careful handling of resident and staff data
- audit logging for sensitive actions
- private handling of security incidents
- controlled deployment and rollback procedures

## Secure development expectations

Before merging security sensitive changes, review the affected code for:

- auth and authorization boundaries
- shelter boundary enforcement
- resident versus staff access separation
- CSRF protection
- rate limit behavior
- audit logging
- secret exposure
- error handling that may leak internal state

## Notes

This file is an internal process baseline, not a guarantee of support windows or external disclosure commitments.

Security handling should remain private unless leadership explicitly approves broader disclosure.
