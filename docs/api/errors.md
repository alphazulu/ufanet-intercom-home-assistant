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

## Physical-key enrollment errors

The Android client contains a dedicated HTTP 400 branch when starting `auto_collect/enable`, but the exact server-side status/body semantics have not been live-confirmed by this project. The validation runtime therefore does not assign a specific provider meaning to every HTTP 400 without real evidence.

**Status: Observed from Android client; live error contract unconfirmed.**

## Physical-key rename verification and indeterminate results

`POST /api/v4/key/edit/` is **Confirmed for the tested success path**: a controlled Home Assistant rename changed the selected physical key name on the provider side.

The provider inventory is eventually consistent. In live testing the first immediate read-back could still show the previous name, while a later refresh returned the requested new name. The validation `rename_physical_key` service therefore sends the state-changing POST exactly once and performs bounded read-only inventory refresh retries before reporting `verified: true`.

If the POST has already been sent but verification still cannot complete within those bounded retries, the key disappears from fresh inventory, or the requested new name is never observed, Home Assistant reports that the key may have changed but the result could not be verified. This deliberately distinguishes an indeterminate state-changing result from proven success/failure and avoids an automatic repeated POST that could duplicate a user action.

The project still does not claim provider-specific error semantics for invalid/stale key IDs, duplicate names, server-side length limits, or other failure cases that have not been directly observed.

## Reporting a new API error

When adding a newly observed error, record:

- endpoint and method;
- sanitized request context;
- HTTP status;
- sanitized response body;
- whether retrying changed the result;
- token state/expiry without exposing token values;
- whether the operation has side effects;
- for write endpoints, whether the final state was independently confirmed by a read-back request.

Do not generalize a single observed status code to all failure modes without additional evidence, and do not publish provider physical-key IDs/`external_id` in diagnostic examples.
