# Security

Do not open a public issue containing credentials, JWTs, active guest links or other access capabilities.

Use GitHub Private Vulnerability Reporting for security-sensitive reports when enabled for this repository. If a credential, token or guest link is exposed, revoke or rotate it immediately.

Authorized FCM session data is also sensitive. Do not publish raw provider device IDs, FCM tokens, registration credentials, or full private session inventories. Ufanet Intercom v0.30.0 uses opaque session references in Home Assistant, protects locally provable Home Assistant registrations from revocation, and requires explicit confirmation for destructive session logout.

Physical-key data is access-control-sensitive. Do not publish provider `external_id` or raw provider key IDs. Validation key-management surfaces use an intercom-scoped opaque `key_ref`; rename resolves it only from a freshly refreshed inventory and verifies the requested name with a second refresh after the write. Physical-key enrollment and rename remain validation-only until controlled live tests complete. Key deletion is destructive, is not implemented in the current runtime, and requires a separately reviewed safety/confirmation model before implementation.
