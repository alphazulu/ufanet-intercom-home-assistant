# Unofficial Ufanet / UCAMS API reference

[Русская версия](README_RU.md)

This directory documents the private/undocumented APIs used by the Ufanet Intercom Home Assistant integration.

> These interfaces are not a public API contract. They are based on interoperability testing, observed mobile-app behavior, and reverse engineering. They may change without notice.

## Evidence labels

Every endpoint or behavior should carry one of these labels:

- **Confirmed** — exercised successfully against a real account/device.
- **Observed** — seen in a real response or application code, but not exhaustively tested.
- **Inferred** — inferred from client code or surrounding behavior and still needs validation.
- **Not supported** — explicitly tested and found not to work in the tested form.

When new behavior is tested, update the relevant page and move the label toward **Confirmed** only when there is direct evidence.

## Architecture

The integration currently uses three API layers:

1. **Ufanet account / intercom API** — `https://dom.ufanet.ru`
   - contract authentication and token refresh;
   - intercom/SKUD discovery and door control;
   - call history;
   - guest/shared-access management.
2. **UCAMS control API** — `https://cloud.ucams.ru`
   - exchanges the Ufanet JWT for a UCAMS bearer token;
   - returns camera metadata, live/archive tokens and media server information.
3. **UCAMS media servers** — hostnames returned by the UCAMS API
   - live HLS;
   - archive ranges and archive HLS;
   - screenshots and call media.

## Authentication chain

```text
Ufanet contract/password
        |
        v
Ufanet access + refresh JWT
        |
        | POST cloud.ucams.ru/api/v0/auth/
        v
UCAMS bearer token
        |
        v
camera metadata -> token_l / token_r -> media servers
```

Important distinction:

- Ufanet authenticated requests use `Authorization: JWT <access-token>`.
- UCAMS control API requests use `Authorization: Bearer <ucams-token>`.

## Reference pages

- [Authentication](auth.md)
- [Intercom / SKUD](intercom.md)
- [UCAMS camera control and live video](ucams.md)
- [Archive](archive.md)
- [Call events/history](calls.md)
- [Guest and shared access](guests.md)
- [Observed data models](models.md)
- [Errors and unsupported behavior](errors.md)
- [Security considerations](security.md)

## Verification and examples

- [API verification matrix](STATUS.md) — compact list of tested endpoints and their current evidence status.
- [curl examples](examples/curl.md) — read-only command-line examples.
- [Python read-only example](examples/python.md) — minimal authentication/discovery/UCAMS flow.

State-changing examples (door opening, guest creation/revocation) are intentionally kept on the relevant reference pages rather than in the copy/paste examples collection.

## Contributing new API findings

For every newly tested endpoint, record:

1. HTTP method and path;
2. authentication scheme;
3. minimal sanitized request;
4. minimal sanitized response;
5. evidence label;
6. date/conditions of the test when relevant;
7. known side effects;
8. any field whose semantics are still uncertain.

Update both the detailed page and [STATUS.md](STATUS.md) in the same change.

Never commit real passwords, JWTs, refresh tokens, guest tokens, tokenized media URLs, exact private addresses, or other account-specific secrets.