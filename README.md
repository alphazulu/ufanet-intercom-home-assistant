# Ufanet Intercom for Home Assistant

**English** | [Русский](README_RU.md)

Custom Home Assistant integration for Ufanet / «Умный дом» intercoms using the cloud APIs used by the official mobile application.

> This is an independent community integration. It is not affiliated with or supported by Ufanet.

## Features

- UI setup with Ufanet contract/login and password.
- Door opening through Home Assistant `button` entities.
- Live UCAMS camera stream and snapshots.
- Native archive browsing with recording ranges, timeline zoom/pan, call markers, and read-only motion-event markers.
- Intercom call history, `ufanet_intercom_call`, native **Incoming call** / **Last call image** entities, a doorbell EventEntity and visual device trigger.
- Companion notification blueprint with immediate text delivery, private HA image replacement, optional guarded **Open door** action and direct **View camera** navigation.
- Physical-key support for capable intercoms: read-only count/inventory, latest passage timestamp, passage EventEntity/device trigger, validation-only **Add physical key**, privacy-safe list/rename services using opaque `key_ref` values, and a **KEYS** Lovelace tab.
- Read-only UCAMS `motion_alarm` analytics with a **Motion detected** event entity, `ufanet_intercom_motion` event, visual device trigger and archive timeline markers.
- Selectable call updates: polling by default or experimental low-latency FCM with safety polling.
- Privacy-safe FCM authorization/session inventory and explicit guarded session revocation.
- Temporary guest keys and accepted shared-access management.
- Manual archive export to MP4 using `ffmpeg -c copy` into Home Assistant Media.
- Persistent export media library with per-camera retention and size cleanup.
- Optional automatic MP4 saving around new intercom calls.
- Options Flow and privacy-conscious Home Assistant diagnostics.
- Unified Lovelace card: `custom:ufanet-intercom-card`.

## Current validation work

The `codex/combined-validation` branch contains unreleased notification-action and
physical-key enrollment/management work. It is intentionally **validation-only** and must not
be tagged/published until the live gates in the active validation PR are complete.
The installed integration version therefore remains `0.30.0` until explicit
release preparation begins.

Already live-validated on the development Home Assistant installation:

- Android actionable incoming-call notification delivery;
- real Ufanet call notification;
- notification **Open door** action physically opening the configured door;
- **View camera** opening More Info for the selected live camera;
- timeout updating the existing notification in place and removing the stale door action;
- combined notification + physical-key build loading without observed regression;
- physical-key capability/coordinator health and empty read-only inventory (`state=0`, `keys=[]`);
- `ufanet_intercom.list_physical_keys` returning `count: 0`, `keys: []` on the current zero-key account.

Still mandatory before release: the remaining real-call race/mismatch/metadata checks
and a complete registration of a **new physical key**, including the real
`reason=key_add` push, a non-empty inventory row, privacy-safe `list_physical_keys`,
and a real rename through the validation-only `rename_physical_key` service. See
[Home Assistant call notifications](docs/notifications.md) and
[Physical keys and passage history](docs/api/keys.md).

## Unofficial API documentation

The repository contains a maintained reverse-engineered reference for the Ufanet/UCAMS interfaces used by this integration:

- [API reference](docs/api/README.md)
- [API verification matrix](docs/api/STATUS.md)
- [Physical keys and passage history](docs/api/keys.md)
- [FCM / push notifications](docs/api/fcm.md)
- [Security considerations](docs/api/security.md)
- [curl examples](docs/api/examples/curl.md)
- [Python read-only example](docs/api/examples/python.md)

The reference explicitly distinguishes **Confirmed**, **Observed**, **Inferred**, and
**Not supported** behavior. State-changing behavior is not promoted to Confirmed
from decompiled-client evidence alone.

## Requirements

- Home Assistant **2026.8.0 or newer**.
- Network access from Home Assistant to `dom.ufanet.ru`, `cloud.ucams.ru` and the UCAMS media servers returned by the API.
- Experimental FCM additionally needs outbound HTTPS access to Google Firebase/GCM registration endpoints and TLS access to `mtalk.google.com:5228`.
- For MP4 export and last-call JPEG extraction: `ffmpeg` available in the Home Assistant runtime. Home Assistant OS/Container normally provides it; Core/venv installs may need an OS package.
- A Ufanet account/contract that already has access to the intercom in the official application.

## Installation

### Manual

1. Copy `custom_components/ufanet_intercom` into your Home Assistant configuration directory:
   `config/custom_components/ufanet_intercom`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**.
4. Search for **Ufanet Intercom** and enter the same contract/login and password used by the official application.

### HACS custom repository

1. HACS → **Custom repositories**.
2. Add this GitHub repository as category **Integration**.
3. Install **Ufanet Intercom**.
4. Restart Home Assistant and add the integration from **Settings → Devices & services**.

## Lovelace card

Add the resource as a JavaScript module. The currently published release is v0.30.0, so its cache-bust URL is:

```text
/ufanet_intercom/ufanet-archive-card.js?v=0.30.0
```

The `?v=` value must match the installed release. Do not change this documentation
value on validation branches until the integration/card version is actually bumped
for release preparation.

Minimal card:

```yaml
type: custom:ufanet-intercom-card
entity: camera.YOUR_UFANET_CAMERA
default_tab: live
```

The validation card contains six tabs:

- **LIVE** — video, door control, latest call and jump-to-call recording.
- **АРХИВ** — timeline, call/motion markers, MP4 export and export media library.
- **ГОСТИ** — shared invitations, accepted guest access, temporary keys and revoke actions.
- **УСТРОЙСТВА** — authorized Ufanet sessions, Home Assistant ownership protection, targeted revocation and guarded bulk revocation.
- **KEYS / КЛЮЧИ** — fresh privacy-safe physical-key inventory, explicit 60-second new-key enrollment and rename through opaque `key_ref`; key deletion is absent.
- **ДИАГНОСТИКА** — token-free runtime health, polling, FCM authorization state, UCAMS/archive status and autosave state.

The **KEYS** tab is provided by the packaged validation extension
`ufanet-physical-keys-card.js`. The integration loads it automatically; it waits for
`custom:ufanet-intercom-card` to be registered, so no second manual Lovelace Resource
entry is required. The visual editor also allows `keys` as `default_tab` on the
validation branch.

## Options

Open **Settings → Devices & services → Ufanet Intercom → Configure**.

Important options include the call update mode, polling interval, call archive lead,
archive duration/step, MP4 retention/size limits and automatic call-video saving.
YAML values on a particular card remain local overrides where supported.

### Call update modes

- **`polling` (default)** reads `call-history` at the configured interval and needs no additional setup.
- **`fcm` (experimental)** uses a local headless FCM receiver as a low-latency wake-up signal. `call-history` remains authoritative. Normal polling stays active until the listener confirms MCS connectivity and is restored automatically on disconnect; while FCM is healthy, a 300-second safety poll remains active.

The FCM watchdog distinguishes task startup from an established transport, lets the
library handle short reconnects, and recreates a terminal/stalled listener with
backoff. Repairs warnings cover prolonged listener failure, recovered private state
and pending unregister cleanup without exposing credentials or push payloads.

FCM configuration values are not distributed by this repository. Advanced users
extract them locally from their own decompiled copy of the official Android app:

```bash
python tools/research/fcm_probe_py/extract_firebase_config.py /path/to/decompiled-app -o firebase_config.json
```

Copy the result to `/config/ufanet_intercom/firebase_config.json`, choose `fcm`, and
keep the default relative path `ufanet_intercom/firebase_config.json`. The
integration reads the file but does not copy Firebase values into ConfigEntry or
diagnostics. See [FCM API notes](docs/api/fcm.md).

## Incoming-call automations and Companion notifications

Every intercom with call history has an **Incoming call** binary sensor and matching
visual device trigger. A native doorbell EventEntity represents the same confirmed
call with Home Assistant's `ring` event type.

The **Last call image** entity privately downloads the tokenized provider preview,
decodes a JPEG through local `ffmpeg` using an anonymous seekable source, and keeps
only the JPEG in memory. Tokenized preview/archive URLs are not published through
entity state or `ufanet_intercom_call`.

The recommended blueprint is
[`incoming_call_notification.yaml`](blueprints/automation/ufanet_intercom/incoming_call_notification.yaml).
Select the intercom, Companion device, matching **Last call** / **Last call image**,
and optionally:

- the matching live `camera.*` entity;
- the exact same-device **Open door** button;
- image delay, action timeout, dashboard fallback URI and Android notification channel.

The blueprint sends text immediately, then replaces the same stable-tag notification
with the private HA image when ready. On a real call the optional **Open door**
action is accepted only for the configured timeout and only when the button belongs
to the same Home Assistant device. Membership is revalidated immediately before
`button.press`. A manual blueprint run deliberately has **no physical door action**.

**View camera** opens the selected live camera through Home Assistant More Info using
`more-info-entity-id`; if the selection is missing/mismatched, navigation falls back
to the configured dashboard URI. Because one Ufanet device can expose live and
archive cameras, select the live entity explicitly.

Android has been live-tested. The payload uses the shared Android/iOS Companion
action schema, but iOS action delivery has not been live-tested and is not claimed
as such. Full safety behavior and remaining gates are documented in
[docs/notifications.md](docs/notifications.md).

## Physical keys and passage events

For every intercom advertising key-recording support, the integration creates:

- **Physical keys** — numeric count; the validation branch also exposes read-only `keys` rows containing only `name` and UTC `created_at`;
- **Last key passage** — latest known passage timestamp;
- **Physical key passage** EventEntity and matching visual device trigger.

The dedicated coordinator polls every 60 seconds. Its first successful history poll
is a baseline and does not replay older passages. A private cursor prevents duplicate
passage delivery after reloads. Public passage events contain only `key_name` and
`occurred_at`; provider `external_id` and full history are not exposed.

The validation branch also adds **Add physical key** (`mdi:key-plus`) only for
supported intercoms. It mirrors the Android-observed 60-second
`auto_collect/enable` flow. A successful button request means only that enrollment
mode was armed; the new key still has to be presented to the reader within 60
seconds.

The FCM listener recognizes the Android-observed `reason=key_add` completion path.
It refreshes the key inventory immediately and emits the account-level,
privacy-minimized `ufanet_intercom_key_enrollment` event. Provider `key_id`,
`external_id`, raw message text and push payload are not published. The real
`key_add` path and non-empty inventory remain **Observed/pending live validation**.

For key management, the validation branch exposes
`ufanet_intercom.list_physical_keys`, returning only `name`, `created_at`, and a
local opaque `key_ref`. `ufanet_intercom.rename_physical_key` accepts that ref,
refreshes inventory before mutation, resolves it only inside the selected intercom,
then calls the Android-observed `/api/v4/key/edit/` contract internally and performs
a second refresh. It reports success only when the requested new name is observed
after that refresh. Raw provider `key_id` is neither accepted nor returned. The
rename endpoint itself remains **Observed/pending live validation** until a real key
exists. Key deletion is not implemented.

The **KEYS** tab uses the same privacy-safe response services. **Add key** invokes
only the same-device Home Assistant `button.*_add_physical_key`, shows the observed
60-second countdown, then refreshes inventory. Rename asks for explicit confirmation
and accepts success only when the backend returns `verified: true`. No key-delete
action exists in the UI. See [docs/api/keys.md](docs/api/keys.md).

## Motion analytics

For cameras that explicitly advertise the live-confirmed `motion_alarm` capability,
the integration creates a **Motion detected** EventEntity/device trigger and the
privacy-minimized `ufanet_intercom_motion` bus event. The archive timeline can also
show read-only motion timestamps. Provider camera/cursor IDs, screenshots,
recognition data and raw history are not exposed. See
[docs/api/analytics.md](docs/api/analytics.md).

## Automatic call recording and local media

Automatic call-video saving is disabled by default. When enabled, a call is exported
asynchronously after the requested post-call interval is present in UCAMS archive.
The raw call UUID is hashed before local filename deduplication.

Manual and automatic MP4 exports are stored under Home Assistant Media in
`ufanet_intercom/`. The Archive tab lists only exports for the selected camera and
supports open/download/delete plus configured retention/size cleanup.

## Security notes

- Ufanet/UCAMS JWTs and Firebase/FCM credentials are not intentionally exposed by diagnostics.
- Generated guest links are access capabilities and should be treated as temporary credentials.
- Opening the door is a real physical action; the card/notification require explicit user interaction and notification actions add same-device guards.
- Starting physical-key enrollment changes access-control state and must not be used as a health check or automatic action.
- Physical-key `external_id` is discarded at normalization; provider `key_id` remains internal and is not exposed in sensor attributes/events/diagnostics.
- Public physical-key management uses only an intercom-scoped opaque `key_ref`; rename refreshes inventory before mutation and verifies the result with a second refresh after POST.
- Tokenized call-media URLs remain internal runtime data; only the generated last-call JPEG is cached for the image entity.
- Authorized-session management exposes opaque refs rather than raw provider FCM device IDs and protects locally provable Home Assistant registrations.
- Motion analytics stores provider cursor data only in private storage and publishes only normalized timestamps.

See [docs/api/security.md](docs/api/security.md) for the detailed boundaries.

## Troubleshooting

Run the repository self-check before reporting packaging/frontend problems:

```bash
python scripts/release_check.py
```

Use either the **ДИАГНОСТИКА** card tab or **Download diagnostics** on the
integration/device page for privacy-redacted support data.

If local `ffmpeg` is unavailable or last-call JPEG extraction repeatedly fails,
Home Assistant creates a Repairs warning. Call detection, archive viewing and door
control remain available; the warning closes automatically after image extraction
recovers.

## Development / release validation

`python scripts/release_check.py --strict-hacs` plus GitHub CI validates packaging,
Python/JSON/JavaScript, card method/service references, HACS/Hassfest and release
version consistency.

**Green CI does not replace required physical/live validation.** Before tagging a
release, resolve the active PR's `REQUIRED VALIDATION BEFORE ANY RELEASE` checklist,
update evidence labels/documents/CHANGELOG, then bump all release-facing versions
and cache-bust URLs together. See [PUBLISHING.md](PUBLISHING.md).

## License

Licensed under the [MIT License](LICENSE).

Copyright © 2026 [alphazulu](https://github.com/alphazulu).

Commercial use, modification, redistribution, sublicensing, and inclusion in
proprietary products are permitted. The copyright notice and MIT permission notice
must be retained in copies or substantial portions of the software.

## Repository

https://github.com/alphazulu/ufanet-intercom-home-assistant