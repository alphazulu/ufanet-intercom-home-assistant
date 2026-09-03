# Security

Do not open a public issue containing credentials, JWTs, active guest links or other access capabilities.

Use GitHub Private Vulnerability Reporting for security-sensitive reports when enabled for this repository. If a credential, token or guest link is exposed, revoke or rotate it immediately.

Authorized FCM session data is also sensitive. Do not publish raw provider device IDs, FCM tokens, registration credentials, or full private session inventories. Ufanet Intercom v0.30.0 uses opaque session references in Home Assistant, protects locally provable Home Assistant registrations from revocation, and requires explicit confirmation for destructive session logout.
