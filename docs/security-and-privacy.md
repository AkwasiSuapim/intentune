# Security and Privacy

## Status

**Draft**

## Security Principles

- Never commit secrets.
- Validate data at system boundaries.
- Give components only the access they need.
- Avoid collecting data without a product reason.
- Log operational information without exposing sensitive content.

## Secrets

Store these outside source control:

- AI provider API keys
- YouTube API keys
- Database credentials
- Session or authentication secrets

Local development may use a `.env` file. Commit only `.env.example` with empty placeholder names.

## Input Validation

Validate:

- Numerical ranges
- Requested result limits
- Allowed feedback actions
- Identifier formats
- Text length
- Optional URL fields
- AI structured output

## Logging

Do not log:

- API keys
- Passwords
- Authentication tokens
- Full database connection strings
- Raw private user prompts by default

Logs may include:

- Request identifier
- Route
- Status
- Duration
- Candidate count
- Provider error category

## User Prompt Privacy

The first version should process prompts without automatically retaining them permanently. If prompts are stored later, document:

- Why they are stored
- Retention duration
- Who can access them
- Deletion process
- Whether they are used for analytics or model improvement

## Feedback Privacy

Anonymous feedback should use random session identifiers. Avoid collecting names or email addresses unless accounts become necessary.

## External Providers

Before enabling AI or YouTube in production, review:

- Data sent to the provider
- Provider retention rules
- API terms
- Quota limits
- Regional restrictions
- Key restrictions

## Authentication

Authentication is not required for the first private prototype. It may be required when profiles or saved history become persistent and accessible remotely.

## Abuse Prevention

A public deployment may need:

- Rate limiting
- Request-size limits
- Provider quota protection
- Input moderation for chatbot prompts
- Automated secret scanning

## Incident Response Placeholder

When the application is deployed, document:

- How to rotate a leaked key
- How to disable an external integration
- How to inspect logs
- How to notify affected users if stored data is involved
