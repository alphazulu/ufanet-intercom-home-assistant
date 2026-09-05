# FCM / push notifications

[Русская версия](fcm_RU.md)

This page tracks reverse engineering of the official Ufanet Android push path and the confirmed headless FCM flow.

> The repository intentionally does not distribute the official application's concrete Firebase client configuration. Users extract it locally from their own copy of the application with `tools/research/fcm_probe_py/extract_firebase_config.py`.

## Status

On 2026-08-29 a standalone Windows/Python headless client successfully:

1. created a virtual Firebase/GCM installation;
2. registered its FCM token with Ufanet;
3. connected to Google MCS;
4. received a real `reason=sip` push without Android/Google Play Services;
5. correlated the same physical call with `/api/v1/skuds/call-history/`.

The headless FCM transport and `reason=sip` path are therefore **Confirmed**.

The official Android client also contains a physical-key enrollment completion path
using `data.reason=key_add`, `key_status`, and `key_id`. That payload contract is
currently **Observed** from client code and remains a hard live-validation gate
until a new unregistered physical key can be enrolled end to end.

## Home Assistant integration mode

Version 0.20.0 exposed `polling` and experimental `fcm` in the integration options. FCM registers a private virtual installation, listens for `data.reason=sip`, and immediately asks the existing call coordinator to refresh `call-history`. Polling remains enabled with a minimum 300-second interval so missed pushes or a broken MCS connection do not silently disable call events.

The current validation branch additionally recognizes `data.reason=key_add`. That
path does not alter the proven SIP/call flow: it classifies the key-enrollment
result, requests an immediate physical-key coordinator refresh, and emits a
privacy-minimized `ufanet_intercom_key_enrollment` Home Assistant event. It never
publishes the provider key ID or raw notification text.

The required JSON is read from `ufanet_intercom/firebase_config.json` under the Home Assistant configuration directory by default. Only this relative path is stored in the config entry. Firebase values and runtime FCM credentials are kept in the local Home Assistant storage/config area and are excluded from diagnostics.

The component deliberately does not parse or retain APK files. Extraction stays a separate, auditable local step and avoids adding Android resource parsers and an APK upload surface to Home Assistant.

## Firebase client configuration

The receiver needs values present in the packaged resources of the official Android client:

```text
project_id
sender_id
app_id
package_name
api_key
```

No concrete values for these fields are built into the integration or research probe.

The local extractor:

```cmd
py tools\research\fcm_probe_py\extract_firebase_config.py "C:\path\to\decompiled-app"
```

creates a gitignored `firebase_config.json`:

```json
{
  "schema_version": 1,
  "firebase": {
    "project_id": "<extracted>",
    "sender_id": "<extracted>",
    "app_id": "<extracted>",
    "package_name": "<extracted>",
    "api_key": "<extracted>"
  }
}
```

Realtime Database URL and Storage bucket are not required by the receiver and are not stored by default.

## Device registration

### Android client

**Observed**

With Google Play Services available, the app obtains its token through:

```text
FirebaseMessaging.getInstance().getToken()
```

and passes it into the device-registration flow. `onNewToken()` repeats registration when the token rotates.

### Ufanet FCM registration

**Confirmed**

```http
POST /api/v0/fcm/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "token": "<push-provider-token>",
  "device_id": "<device-id>",
  "title": "<device-title>",
  "application": "<package-name-from-local-config>",
  "os": 0,
  "token_type": 0
}
```

The Android client also **Observed** `token_type = 2` for HMS.

### `device_id`

**Observed**

`device_id` is installation-scoped application state, not the Android hardware ID. The app stores a stable value shaped like:

```text
<device-title>_<random UUID>
```

and reuses it. The headless PoC generates an equivalent local installation ID.

### Unregister

**Confirmed**

```http
DELETE /api/v0/fcm/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "device_id": "<device-id>"
}
```

The standalone probe can live-check this contract without touching other devices:

```cmd
py tools\research\fcm_probe_py\probe.py --verify-unregister
```

It deletes only its own locally generated virtual registration, immediately
registers the same device and token again, and exits without starting the listener.
The live service returned HTTP 200 with `{"status": "ok"}` for both DELETE and the
immediate restoring POST. The Home Assistant integration therefore unregisters only
its strictly validated `Home Assistant_<UUID>` installation when FCM is disabled or
the ConfigEntry is removed. Normal reloads and Home Assistant restarts keep it.

## Authorized-device inventory

**Confirmed**

```http
POST /api/v4/fcm_device/authorized_devices/
Authorization: JWT <UFANET_ACCESS>
```

The request has no body. The live-confirmed response contains `data.device_list`. The current Android DTO consumes `device_id`, nullable `title`, `last_update`, and `is_call_access`; the server also returned `os` and `os_display`, which the current Android DTO does not declare. A sanitized structural example is:

```json
{
  "data": {
    "device_list": [
      {
        "device_id": "<opaque-device-id>",
        "title": "<device-title>",
        "last_update": "<offset-aware ISO-8601>",
        "is_call_access": true,
        "os": 0,
        "os_display": "Android"
      }
    ],
    "devices_num_permission": false
  }
}
```

The tested account returned unique `device_id` values and parseable timestamps. The live sample correlated opaque OS code `0` with normalized display `Android` for all returned rows, but this is only an observed correlation for that account and is not documented as a universal enum mapping. The Android response model names `devices_num_permission` as `isQuantityLimited`; the current active-devices screen does not use the flag, so its exact operational semantics remain unconfirmed.

Treat this endpoint as an **authorized registration/session inventory**, not a guaranteed list of physical phones or distinct current raw FCM tokens. Re-registration/token refresh can update an existing installation-scoped `device_id`, and old authorized rows can remain for a long time.

## Authorized-session logout

**Confirmed**

```http
POST /api/v4/fcm_device/logout_device/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "device_id": "<device-id>"
}
```

The official Android active-device UI uses this endpoint for one selected non-current device and implements "terminate all other sessions" by calling the same endpoint for each other row. On 2026-09-03 the project live-confirmed the destructive contract only against a disposable probe-owned virtual registration: the row was present before logout, the POST returned HTTP 200, the row disappeared from `authorized_devices`, and re-registering through `/api/v0/fcm/` restored it. No existing phone or Home Assistant registration was used for that provider-contract test.

Home Assistant v0.30.0 exposes this capability through privacy/safety guards rather than raw provider IDs. `list_fcm_sessions` returns bounded user-facing metadata plus an opaque entry-scoped `session_ref`; HA-owned registrations proven from private local state are marked protected. `revoke_fcm_session` re-fetches the inventory, resolves exactly one non-protected ref, performs logout and verifies disappearance. `revoke_other_fcm_sessions` requires explicit confirmation plus an exact expected revocable count from a fresh snapshot and never removes sessions automatically by age/title/platform. The custom **УСТРОЙСТВА** tab uses the same services and never renders raw provider `device_id` values.

## Headless transport

**Confirmed**

```text
local firebase_config.json
        |
        v
Firebase Installation registration
        |
        v
GCM/Android check-in + registration
        |
        v
FCM registration token
        |
        v
POST /api/v0/fcm/
        |
        v
TLS/MCS -> mtalk.google.com:5228
        |
        v
real Ufanet data push
```

Android, Frida, and Google Play Services are not required after successful virtual registration.

## Incoming SIP push

**Confirmed**

A sanitized real message has this shape:

```json
{
  "data": {
    "contract": "<redacted>",
    "flat": "<redacted>",
    "house_id": "<redacted>",
    "password": "<redacted>",
    "reason": "sip",
    "server": "<redacted>",
    "skud_id": "<redacted>",
    "time": "<offset-aware ISO-8601>",
    "transport": "UDP",
    "username": "<redacted>",
    "uuid": "<push-event-uuid>"
  },
  "fcmMessageId": "<fcm-message-uuid>",
  "from": "<sender-id>",
  "priority": "normal"
}
```

Runtime capture confirms that the selector is `data.reason`, equal to `sip` for an incoming call.

The Android live-call path consumes at least:

```text
username
password
server
skud_id
```

and does not require the call-history UUID to start the live SIP flow.

## Physical-key completion push

**Observed in the Android client; live validation pending**

The client contains a separate completion path selected by:

```text
data.reason = key_add
```

The fields used by the observed success logic are:

```text
key_status
key_id
```

Success requires `key_status == 0` and a present, parseable `key_id`. Missing or
invalid status is treated as an error. The observed payload does not provide a
`skud_id`.

The validation branch handles this message without exposing provider identifiers:

```text
FCM reason=key_add
        |
        +--> classify success/error
        |
        +--> immediate UfanetKeyPassageCoordinator refresh
        |        |
        |        v
        |    POST /api/v4/key/list/
        |
        v
ufanet_intercom_key_enrollment
```

The public Home Assistant event contains only:

```text
type
source
result
received_at
inventory_refresh_succeeded
```

Provider `key_id`, notification `title`/`body`, and the raw push are never retained
in the event or diagnostics. Diagnostics expose only
`received_key_add_push_count`, `last_key_add_push_at`, and
`last_key_add_result`.

Because the message has no observed `skud_id`, the event is deliberately
account-level. The refreshed key inventory determines actual intercom association
through each key's `devices` field.

## Relationship to call history

**Confirmed for `reason=sip`**

For the same physical call:

```text
push.data.time == call-history.called_at   (matched to the second)
push.data.uuid != call-history.uuid
```

Therefore:

- `push.data.uuid` is not the durable history-record UUID;
- `fcmMessageId` is a separate FCM message identifier;
- `call-history.uuid` is the canonical durable identifier for completed/archive events.

Two earlier SIP pushes about twelve seconds apart were two separate manually initiated test calls, not confirmed retries of one call.

## Home Assistant architecture

For calls:

```text
FCM reason=sip
   |
   +--> immediate UfanetCallCoordinator refresh
              |
              v
       call-history UUID
              |
       durable event + media/archive
```

For physical-key enrollment completion:

```text
FCM reason=key_add
   |
   +--> immediate key inventory refresh
   |
   +--> privacy-minimized account-level completion event
```

Push is a low-latency wake-up/completion signal. `call-history` remains the authoritative source for durable call identity and media; `/api/v4/key/list/` is the authoritative inventory source after key enrollment. Periodic polling remains as a fallback.

## Research latency probe

After every SIP push, the Windows/Python PoC probes call history at offsets:

```text
0, 0.25, 0.5, 1, 2, 5 seconds
```

and measures an upper bound on when the matching history record becomes observable. This data is used to choose production retry/backoff behavior.

In four consecutive live test calls on 2026-08-29, the matching row was found by the first request every time. Request completion ranged from 0.446 to 0.916 seconds after the push (median 0.613 seconds), with a push/history timestamp delta of 0–1 second. The push UUID and durable history UUID differed in all four samples. The integration still performs short follow-up refreshes to cover network jitter and slower call-history publication.

## Required key-add live validation

Before the physical-key block is eligible for release, a new unregistered key must
confirm that:

1. the real completion push is actually delivered through the headless listener;
2. its wire shape matches the observed `reason=key_add`, `key_status`, `key_id`
   contract;
3. the immediate coordinator refresh succeeds and the key appears in the
   read-only inventory;
4. `ufanet_intercom_key_enrollment` reports the correct result without exposing
   provider identifiers or message text.

Until then, `key_add` remains **Observed**, not **Confirmed**.

## Security

Do not publish or commit:

- `firebase_config.json`;
- `fcm_state.json`;
- FCM/GCM registration tokens;
- Firebase Installation auth/refresh credentials;
- Android/GCM security tokens;
- WebPush private keys/auth secrets;
- Ufanet JWTs;
- real SIP username/password/server values;
- physical-key `external_id` or provider `key_id` values;
- private account/location identifiers.

Although Firebase Android client configuration is technically shipped inside the client APK, this open-source project deliberately obtains it locally from the user's own copy rather than redistributing a third party's Firebase project configuration as part of the integration.