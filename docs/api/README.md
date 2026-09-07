# Unofficial Ufanet / UCAMS API reference

[Русская версия](README_RU.md)

This directory documents the private/undocumented APIs used by the Ufanet Intercom Home Assistant integration.

> These interfaces are not a public API contract. They are based on interoperability testing, observed mobile-app behavior, and reverse engineering. They may change without notice.

## Evidence labels

Every endpoint or behavior should carry one of these labels:

- **Confirmed** — exercised successfully against a real account/device.
- **Observed** — seen in a real response or application code, but not exhaustively tested.
- **Inferred** — inferred from client code or surrounding behavior and still needs validation.
- **Experimental** — intentionally exposed for controlled user validation, but the semantic interpretation is not yet proven.
- **Not supported** — explicitly tested and found not to work in the tested form.

When new behavior is tested, update the relevant page and move the label toward **Confirmed** only when there is direct evidence. For state-changing endpoints, an HTTP 200 alone is not enough: document separately whether the expected side effect was actually verified. Validation code and green CI alone do not promote an evidence label.

Current physical-key evidence: `external_id` is **Confirmed** as the backend selector used for per-key passage filtering. A direct comparison showed that it does **not** match the number printed on the tested physical key, so the former Experimental public key-number interpretation was removed rather than promoted. Physical-key rename through `/api/v4/key/edit/` is also **Confirmed for the tested success path**, including eventual-consistent read-back and bounded read-only verification retries after a single provider write.

## Architecture

The integration currently uses three API layers:

1. **Ufanet account / intercom API** — `https://dom.ufanet.ru`
   - contract authentication and token refresh;
   - intercom/SKUD discovery and door control;
   - call history;
   - physical keys: confirmed capability/non-empty list/history, selected-key passage filtering and rename, plus validation-only enrollment/real FCM completion;
   - guest/shared-access management;
   - FCM registration and authorized-session security management;
   - Confirmed `reason=sip` as the low-latency call signal and Observed `reason=key_add` as physical-key enrollment completion.
2. **UCAMS control API** — `https://cloud.ucams.ru`
   - exchanges the Ufanet JWT for a UCAMS bearer token;
   - returns camera metadata, live/archive tokens and media server information;
   - advertises camera analytics capabilities and provides the confirmed read-only `motion_alarm` report used by v0.28.0.
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
        +--> camera metadata / analytics reports
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
- [UCAMS camera analytics](analytics.md)
- [Archive](archive.md)
- [Call events/history](calls.md)
- [Physical keys and passage history](keys.md) — confirmed non-empty inventory/history, private `external_id` history selection and controlled rename; validation-only enrollment/real FCM completion remains the release gate. The tested provider identifiers are not presented as the printed physical-key number.
- [FCM / push notifications](fcm.md)
- [Guest and shared access](guests.md)
- [Observed data models](models.md)
- [Errors and unsupported behavior](errors.md)
- [Security considerations](security.md)

## Verification and examples

- [API verification matrix](STATUS.md) — compact list of tested endpoints and their current evidence status.
- [curl examples](examples/curl.md) — safe/read-only copy-paste examples, including analytics capability discovery and `motion_alarm` reporting.
- [Python read-only example](examples/python.md) — authentication/discovery/UCAMS flow with privacy-safe analytics handling guidance.

State-changing examples (door opening, physical-key enrollment, key rename/delete, guest creation/revocation, FCM session logout) are intentionally kept on the relevant reference pages rather than in the copy/paste examples collection. Physical-key rename is live-confirmed for the tested success path; enrollment/real `reason=key_add` and delete remain unconfirmed or out of scope as documented on the key reference page.

## Contributing new API findings

For every newly tested endpoint, record:

1. HTTP method and path;
2. authentication scheme;
3. minimal sanitized request;
4. minimal sanitized response;
5. evidence label;
6. date/conditions of the test when relevant;
7. known side effects and whether those side effects were live-verified;
8. any field whose semantics are still uncertain;
9. for write endpoints, distinguish provider acceptance from verified state/read-back.

Update both the detailed page and [STATUS.md](STATUS.md) in the same change, and update user-facing documentation/CHANGELOG when Home Assistant behavior changes.

Never commit real passwords, JWTs, refresh tokens, guest tokens, tokenized media URLs, physical-key provider IDs or `external_id` values, exact private addresses, camera/event identifiers from a live account, raw event history, or other account-specific secrets.
