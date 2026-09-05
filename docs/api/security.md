# Security considerations

[Русская версия](security_RU.md)

These APIs control a physical intercom and expose private video/access data. Treat integration code as security-sensitive.

## Secrets

Never commit, log, or expose:

- Ufanet password;
- Ufanet access JWT;
- Ufanet refresh JWT;
- UCAMS bearer token;
- `token_l` / `token_r`;
- guest/share tokens;
- tokenized preview/archive/screenshot URLs.

Tokenized media URLs should be treated as credentials until expiration.

## Physical side effects

The door-open endpoint performs a real physical action:

```text
/api/v0/skud/shared/<SKUD_ID>/open/?door=1
```

Applications should:

- require explicit user intent;
- avoid automatic retries unless the user action clearly remains active;
- never use the endpoint for health checking;
- distinguish viewing video from controlling access.

The validation-branch Companion **Open door** action follows the same boundary: it
is exposed only for a real call, requires an explicit tap, uses a unique local
action ID, validates that the button belongs to the same Home Assistant device
both when the notification is built and immediately before `button.press`, and is
removed after command dispatch or timeout. A manual blueprint run cannot open the
door.

## Physical-key enrollment and management

Calling `/api/v4/key/skud/<SKUD_ID>/auto_collect/enable/` changes access-control
state: it arms a 60-second window in which a new physical key can be registered by
presenting it to the intercom reader. It is not a read-only health check and must
not be started automatically.

Home Assistant creates **Add physical key** only for an intercom that explicitly
advertises `has_key_recording_support`, and the button is unavailable for an
`is_blocked` device. A successful HTTP response proves only that enrollment mode
was armed, not that a key was actually registered.

FCM completion `reason=key_add` is handled with privacy minimization: provider
`key_id`, notification `title`/`body`, and the raw payload are not published. The
public event contains only the result, receipt time, and whether inventory refresh
succeeded. Because the observed `key_add` payload has no `skud_id`, the integration
deliberately does not guess the target intercom.

Provider physical-key `external_id` is discarded during response normalization.
Provider `key_id` remains private runtime data and is never accepted through the
public key-management services. `list_physical_keys` instead returns an opaque
ConfigEntry/intercom-scoped `key_ref`. The validation-only `rename_physical_key`
service refreshes inventory before resolving that ref, resolves it only for the
selected intercom, then refreshes again after the Android-observed `/api/v4/key/edit/`
POST and reports verified success only when the requested new name is observed.
If the write may have succeeded but verification cannot be completed, the service
reports an indeterminate error instead of claiming success.

Renaming a key changes user-visible access metadata and remains **Observed** until a
real key is used for live validation. Deleting a key is a destructive access-control
operation. The observed delete endpoint must not be added to a production UI
without live endpoint validation, strict verification that the key belongs to the
selected intercom, and a separate explicit user confirmation.

## Guest-access side effects

Creating, accepting, and revoking guest/shared access changes authorization state. Interfaces should clearly label these operations and request confirmation for destructive revocation.

## Authorized FCM sessions

Authorized-device inventory and logout are security-sensitive account operations. Raw provider FCM `device_id` values, FCM tokens and registration credentials should remain private even when a user is reviewing sessions. The Home Assistant integration exposes an opaque `session_ref` instead of the provider ID.

A session must not be classified as safe/unsafe from title, platform or age alone. Home Assistant protects only registrations whose ownership can be proved from local private state; ownership verification fails closed before revocation. Targeted logout requires explicit confirmation and a fresh inventory lookup. Bulk logout additionally requires an exact expected revocable count from the fresh snapshot so a newly appeared session causes the operation to abort rather than being removed unexpectedly.

## Diagnostics and support bundles

Recommended redaction rules:

- redact login and password;
- never include raw JWTs/tokens;
- avoid exact private addresses and apartment information unless explicitly required by the user;
- avoid tokenized URLs;
- replace exact camera identifiers with a short irreversible hash when practical;
- report token presence/expiry rather than token value.

The Home Assistant integration follows these principles in downloadable diagnostics.

At runtime, tokenized call-media URLs stay inside the coordinator. Entity state and the `ufanet_intercom_call` event publish capability flags only. An authenticated response service may return a short-lived URL when a user explicitly requests archive playback; consumers should keep that response in memory and must not copy it into persistent entity attributes or logs. A provider-issued HTTP preview URL is rewritten to HTTPS before any request; the integration never sends the media token over HTTP and blocks automatic redirects while downloading preview bytes. Preview bytes are copied to an anonymous seekable Linux `memfd` for local decoding, then closed immediately; the tokenized URL is not passed to `ffmpeg` and no named source-video file is created. Last-call image diagnostics expose only a boolean HTTPS-upgrade flag, a fixed signature-derived payload class, permanent retry-suppression state, fixed reason codes (`invalid_url`, `unsupported_scheme`, `missing_host`, `embedded_credentials`, `empty_preview`, `size_limit`, `download_error`, `decode_error`, `ffmpeg_unavailable` or `unexpected_error`) and exception class names, never response bodies, exception messages or media identifiers.

## API documentation examples

All examples in this repository must use placeholders such as:

```text
<UFANET_ACCESS_JWT>
<UCAMS_JWT>
<CAMERA_NUMBER>
<SKUD_ID>
<CALL_UUID>
<TEMP_GUEST_TOKEN>
```

Never sanitize a secret by changing only a few characters; replace it completely.

## Reverse-engineering scope

This documentation is intended for interoperability with accounts/devices developers are authorized to use. It should not be used to bypass authorization, enumerate unrelated accounts/devices, or access media belonging to other users.