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

The headless FCM path is therefore **Confirmed**.

## Home Assistant integration mode

Version 0.20.0 exposes `polling` and experimental `fcm` in the integration options. FCM registers a private virtual installation, listens for `data.reason=sip`, and immediately asks the existing call coordinator to refresh `call-history`. Polling remains enabled with a minimum 300-second interval so missed pushes or a broken MCS connection do not silently disable call events.

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

**Observed**

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
Production lifecycle cleanup remains disabled until this operation is live-confirmed.

The Android client also contains `/api/v4/fcm_device/` device-management endpoints; these are not yet live-confirmed by this project.

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

## Relationship to call history

**Confirmed**

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

## Target Home Assistant architecture

```text
FCM reason=sip
   |
   +--> immediate transient incoming/ringing event
   |
   +--> immediate UfanetCallCoordinator refresh
              |
              v
       call-history UUID
              |
       durable event + media/archive
```

Push is the low-latency wake-up signal. `call-history` remains the authoritative source for durable identity and media. Periodic polling remains as a fallback and can be slowed substantially once push handling is production-hardened.

## Research latency probe

After every SIP push, the Windows/Python PoC probes call history at offsets:

```text
0, 0.25, 0.5, 1, 2, 5 seconds
```

and measures an upper bound on when the matching history record becomes observable. This data is used to choose production retry/backoff behavior.

In four consecutive live test calls on 2026-08-29, the matching row was found by the first request every time. Request completion ranged from 0.446 to 0.916 seconds after the push (median 0.613 seconds), with a push/history timestamp delta of 0–1 second. The push UUID and durable history UUID differed in all four samples. The integration still performs short follow-up refreshes to cover network jitter and slower call-history publication.

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
- private account/location identifiers.

Although Firebase Android client configuration is technically shipped inside the client APK, this open-source project deliberately obtains it locally from the user's own copy rather than redistributing a third party's Firebase project configuration as part of the integration.
