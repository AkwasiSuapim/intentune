# Deployment

## Status

**Future Draft**

## Environments

### Local Development

- Local Python virtual environment
- Internal CSV catalog
- Optional local SQLite database
- `.env` for uncommitted secrets

### Test or Staging

- Hosted environment accessible only to the developer or invited testers
- Test credentials
- Safe provider quotas
- Logging enabled

### Production or Public Beta

- Secure secrets
- Persistent database when required
- HTTPS
- Rate limiting
- Monitoring
- Backup and rollback procedure

## Initial Deployment Goal

Deploy one modular-monolith application that exposes the backend and first browser interface.

## Required Deployment Inputs

- Supported Python version
- Dependency lock or reproducible dependency file
- Start command
- Environment variables
- Health endpoint
- Database migration command when persistence exists

## Release Process

1. Create a feature branch.
2. Update code and documentation.
3. Run local tests.
4. Open or review a pull request.
5. Run CI checks.
6. Deploy to test environment.
7. Complete smoke tests.
8. Release to invited users.
9. Monitor errors and feedback.
10. Roll back if critical failures appear.

## Rollback

Before public deployment, document:

- Last known good application version
- Database migration rollback limitations
- How to disable AI or YouTube integrations
- How to restore prior secrets or configuration

## Deployment Provider

Not yet selected. The decision should consider:

- Python and FastAPI support
- Static hosting for the frontend build
- Secret management
- PostgreSQL availability
- Cost
- Logging
- Ease of rollback
