# FCM / push notifications

[Русская версия](fcm_RU.md)

This page tracks reverse engineering of the official Ufanet Android push path, the confirmed headless FCM flow, and the live-confirmed relationship between device registration and Ufanet authorization.

> The repository intentionally does not distribute the official application's concrete Firebase client configuration. Users extract it locally from their own copy of the application with `tools/research/fcm_probe_py/extract_firebase_config.py`.

## Status

On 2026-08-29 a standalone Windows/Python headless client successfully:

1. created a virtual Firebase/GCM installation;
2. registered its FCM token with Ufanet;
3. connected to Google MCS;
4. received a real `reason=sip` push without Android/Google Play Services;
5. correlated the same physical call with `/api/v1/skuds/call-history/`.

The headless FCM transport and `reason=sip` path are **Confirmed**.

The official Android client also contains a physical-key enrollment completion path using `data.reason=key_add`, `key_status`, and `key_id`. On 2026-09-09 that success path was exercised end to end with a genuinely unregistered key and a real headless-FCM completion, so `reason=key_add` is **Confirmed for the tested success path**.

On 2026-09-08 controlled probes additionally confirmed that the device-registration endpoints are coupled to authorization state: both normal `logout_device` and direct FCM unregister removed the tested device row and invalidated the target refresh JWT while an already-issued access JWT remained temporarily usable.

## Home Assistant integration mode

Version 0.20.0 exposed `polling` and experimental `fcm` in the integration options. FCM registers a private virtual installation, listens for `data.reason=sip`, and immediately asks the existing call coordinator to refresh `call-history`. Polling remains enabled with a minimum 300-second interval so missed pushes or a broken MCS connection do not silently disable call events.

The current integration recognizes `data.reason=key_add`. That path does not alter the proven SIP/call flow: it classifies the key-enrollment result, requests an immediate physical-key coordinator refresh, and emits a privacy-minimized `ufanet_intercom_key_enrollment` Home Assistant event. It never publishes the provider key ID or raw notification text.

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

### Unregister / advanced FCM cleanup

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

The original probe established HTTP 200 removal/restoration for its own virtual registration. A later controlled `fcm_delete_jwt_probe.py` test went further: an independent observer deleted a disposable subject registration using only `DELETE /api/v0/fcm/`; `logout_device` was never called. After the DELETE:

- the target row disappeared from `authorized_devices`;
- the target's already-issued access JWT still returned HTTP 200;
- the target refresh JWT returned HTTP 401;
- the independent observer access JWT remained valid;
- the probe restored the device with a fresh JWT login and FCM registration.

Therefore direct FCM unregister is **authorization-destructive for the tested refresh chain** and must not be described as a harmless push unsubscribe.

Normal integration-owned cleanup still unregisters only the strictly validated `Home Assistant_<UUID>` installation when FCM is disabled or the ConfigEntry is removed. Normal reloads and Home Assistant restarts keep that registration.

## Authorized-device / registration inventory

**Confirmed**

```http
POST /api/v4/fcm_device/authorized_devices/
Authorization: JWT <UFANET_ACCESS>
```

The request has no body. A plain JWT controller that never registered for FCM can query this endpoint successfully. The live-confirmed response contains `data.device_list`. The current Android DTO consumes `device_id`, nullable `title`, `last_update`, and `is_call_access`; the server also returned `os` and `os_display`.

Sanitized structural example:

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

`last_update` is treated as provider activity time, not login time. The tested account correlated `os=0` with `Android`, but that is not documented as a universal enum. `devices_num_permission` is live-observed; exact operational semantics remain unconfirmed.

Most importantly, this is **not an exhaustive independent JWT-session inventory**. Live testing showed that a row disappears after direct FCM unregister while the already-issued access JWT can still work. Treat it as the provider device/registration inventory used by the official active-device UI and related authorization actions.

## Authorized-device logout

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

The official Android active-device UI uses this endpoint for a selected non-current device and implements "terminate all other sessions" by calling it for each other row.

Controlled live testing confirmed the cross-session authorization effect without relying on FCM for the controller:

1. a plain `auth_by_contract` controller with no FCM registration queried `authorized_devices`;
2. it selected a separate test device;
3. `logout_device` returned HTTP 200;
4. the target row disappeared;
5. the target's existing access JWT still returned HTTP 200;
6. the target refresh JWT returned HTTP 401;
7. the controller/observer authorization remained valid.

This makes `logout_device` the canonical Ufanet **authorized-device revoke** operation even though the endpoint namespace contains `fcm_device`.

## Home Assistant device-management services

The current integration separates normal device authorization from advanced FCM cleanup:

```text
list_authorized_devices
revoke_authorized_device
revoke_other_authorized_devices

list_fcm_registrations
unregister_fcm_registration
unregister_other_fcm_registrations
```

Normal authorization services use `logout_device`. Advanced FCM services use `DELETE /api/v0/fcm/` and explicitly warn that the tested refresh authorization is invalidated even though `logout_device` is not called.

Public rows use opaque `authorization_ref` or `fcm_ref` values. Raw provider `device_id` values and FCM tokens are never returned. Home Assistant-owned registrations proven from private local state are protected, and ownership verification fails closed before destructive operations. Bulk actions require an exact expected target count from the current snapshot and abort if the inventory changes.

The historical services:

```text
list_fcm_sessions
revoke_fcm_session
revoke_other_fcm_sessions
```

remain compatibility aliases. Despite their names, their revoke operations use `logout_device`; new automations should use the canonical authorized-device service names.

The **УСТРОЙСТВА / Devices** card tab uses the canonical authorization services and exposes advanced FCM cleanup only in a separate collapsed technical section. This UI path has been live-tested with successful removal of test entries while the locally owned Home Assistant registration remained protected.

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

The Android live-call path consumes at least `username`, `password`, `server`, and `skud_id`, and does not require the call-history UUID to start the live SIP flow.

## Physical-key completion push

**Confirmed for the tested success path**

The client contains a separate completion path selected by:

```text
data.reason = key_add
```

The observed success logic uses `key_status` and `key_id`. Success requires `key_status == 0` and a present, parseable `key_id`; the observed payload does not provide a `skud_id`.

The integration handles this message without exposing provider identifiers:

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

Provider `key_id`, notification `title`/`body`, and the raw push are never retained in the event or diagnostics. Diagnostics expose only `received_key_add_push_count`, `last_key_add_push_at`, and `last_key_add_result`.

Because the message has no observed `skud_id`, the event is deliberately account-level. The refreshed key inventory determines actual intercom association through each key's `devices` field.

## Relationship to call history

**Confirmed for `reason=sip`**

For the same physical call:

```text
push.data.time == call-history.called_at   (matched to the second)
push.data.uuid != call-history.uuid
```

Therefore `push.data.uuid` is not the durable history UUID, `fcmMessageId` is a separate delivery identifier, and `call-history.uuid` is the canonical durable identifier for completed/archive events.

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

Push is a low-latency wake-up/completion signal. `call-history` remains authoritative for durable call identity and media; `/api/v4/key/list/` is authoritative after key enrollment. Periodic polling remains as a fallback.

## Research latency probe

After every SIP push, the Windows/Python PoC probes call history at offsets `0, 0.25, 0.5, 1, 2, 5` seconds. In four consecutive live test calls on 2026-08-29, the matching row was found by the first request every time. Request completion ranged from 0.446 to 0.916 seconds after the push (median 0.613 seconds), with a push/history timestamp delta of 0–1 second. The integration still performs short follow-up refreshes to cover network jitter and slower publication.

## Physical-key completion live validation

On 2026-09-09 the physical-key completion path was confirmed end to end:

1. Home Assistant armed the real 60-second enrollment window through `auto_collect/enable`;
2. a genuinely unregistered key was presented and registered;
3. the active headless listener received real `reason=key_add` completion pushes;
4. the tested success matched `key_status == 0` plus a parseable `key_id`;
5. the immediate key-inventory refresh remained healthy and the registered key was present.

A separate no-key test allowed the complete 60-second window to expire and produced no additional `reason=key_add` completion push. No HTTP 400, `key_status != 0`, or separate FCM error completion was observed in that case, so those provider-specific error semantics remain uncharacterized rather than inferred.

Sanitized evidence is recorded in `key_enrollment_live_2026-09-09.md`.

## Security

Do not publish or commit:

- `firebase_config.json`;
- `fcm_state.json`;
- FCM/GCM registration tokens;
- Firebase Installation auth/refresh credentials;
- Android/GCM security tokens;
- WebPush private keys/auth secrets;
- Ufanet JWTs;
- raw provider device IDs from account inventory;
- real SIP username/password/server values;
- physical-key `external_id` or provider `key_id` values;
- private account/location identifiers.

Although Firebase Android client configuration is technically shipped inside the client APK, this open-source project deliberately obtains it locally from the user's own copy rather than redistributing a third party's Firebase project configuration as part of the integration.
