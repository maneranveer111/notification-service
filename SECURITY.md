# Security Policy

## Supported Versions

Security fixes are applied to the latest commit on the `main` branch. We do not backport fixes to older releases.

| Branch | Supported |
|---|---|
| `main` (latest) | ✅ Yes |
| Older tags | ❌ No |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report privately using one of these methods:

- **GitHub Security Advisories:** Go to the repository's Security tab and click "Report a vulnerability".
- **Email:** security@example.com (replace with a real address before publishing).

Include as much detail as possible: steps to reproduce, affected versions, and any proof-of-concept code.

## What We Consider a Security Issue

- Authentication or authorisation bypass
- Sensitive data exposure (credentials, tokens, PII)
- Server-side request forgery (SSRF)
- SQL injection or other injection attacks
- Insecure direct object references
- Cryptographic weaknesses in token signing or secret handling

## Response Timeline

| Stage | Target |
|---|---|
| Acknowledge receipt | Within 48 hours |
| Confirm and assess severity | Within 5 business days |
| Release patch (critical / high) | Within 14 days |
| Release patch (medium / low) | Best effort |

## Credits

We thank everyone who responsibly discloses vulnerabilities. Contributors will be credited in the release notes unless they prefer to remain anonymous.
