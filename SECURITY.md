# Security Policy

## Sensitive data

Do not commit real account credentials, access credentials, vehicle identifiers, exact location history, trip databases, or Discord credentials to this repository.

Use a local `.env` file for development and the secret-management feature provided by your deployment platform for hosted environments. GitHub Actions credentials should be stored as repository secrets rather than tracked files.

## If a secret is exposed

1. Revoke or rotate the exposed credential immediately.
2. Remove it from the current repository state.
3. Review Git history and GitHub Actions logs for additional exposure.
4. Replace any dependent credentials if necessary.

Removing a secret from the latest commit does not remove it from earlier Git history.

## Vehicle controls

This project is intended for read-only vehicle telemetry. Contributions that add remote vehicle-control commands should be treated as a separate security-sensitive design decision and should not be enabled by default.

## Reporting a vulnerability

For issues that do not contain sensitive information, open a GitHub issue. Do not post credentials, private vehicle data, or location history in public issues.
