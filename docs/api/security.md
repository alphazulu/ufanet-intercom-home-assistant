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

## Guest-access side effects

Creating, accepting, and revoking guest/shared access changes authorization state. Interfaces should clearly label these operations and request confirmation for destructive revocation.

## Diagnostics and support bundles

Recommended redaction rules:

- redact login and password;
- never include raw JWTs/tokens;
- avoid exact private addresses and apartment information unless explicitly required by the user;
- avoid tokenized URLs;
- replace exact camera identifiers with a short irreversible hash when practical;
- report token presence/expiry rather than token value.

The Home Assistant integration follows these principles in downloadable diagnostics.

At runtime, tokenized call-media URLs stay inside the coordinator. Entity state and the `ufanet_intercom_call` event publish capability flags only. An authenticated response service may return a short-lived URL when a user explicitly requests archive playback; consumers should keep that response in memory and must not copy it into persistent entity attributes or logs.

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
