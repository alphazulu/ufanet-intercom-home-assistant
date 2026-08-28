# Errors and unsupported behavior

[Русская версия](errors_RU.md)

This page intentionally distinguishes tested failures from unknown behavior.

## Direct arbitrary archive MP4

**Status: Not supported in the tested form**

```text
https://<MEDIA_SERVER>/<CAMERA_NUMBER>/archive-<START>-<DURATION>.mp4?token=<TOKEN_R>
```

Observed result: **HTTP 403**.

Use archive HLS plus ffmpeg remuxing instead. See [archive.md](archive.md).

## Wrong authorization scheme

Ufanet and UCAMS do not use the same Authorization scheme:

```text
Ufanet API: Authorization: JWT <UFANET_ACCESS>
UCAMS API:  Authorization: Bearer <UCAMS_TOKEN>
```

Using one scheme in place of the other should be treated as a client error. Exact HTTP status/body combinations have not yet been systematically catalogued.

**Status: Authentication behavior Confirmed; error-code matrix not yet documented.**

## Expired tokens

The integration tracks expirations and refreshes/reacquires tokens. Exact server error payloads for every expiration scenario have not yet been normalized in this reference.

**Status: Operational behavior Confirmed; detailed error responses still to be collected.**

## Archive not yet available

Immediately after a real-time event, the requested post-event interval may not yet be present in the archive. The integration therefore waits a settle interval and retries automatic call exports.

This retry strategy is integration behavior, not a documented vendor guarantee.

## Empty `/api/v0/skud/`

For the tested account:

```http
GET /api/v0/skud/
```

returned `[]`, while:

```http
GET /api/v0/skud/shared/
```

returned the actual intercom.

Do not interpret an empty `/api/v0/skud/` response as proof that the account has no intercoms.

## Reporting a new API error

When adding a newly observed error, record:

- endpoint and method;
- sanitized request context;
- HTTP status;
- sanitized response body;
- whether retrying changed the result;
- token state/expiry without exposing token values;
- whether the operation has side effects.

Do not generalize a single observed status code to all failure modes without additional evidence.