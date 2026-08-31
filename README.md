# Ufanet Intercom for Home Assistant

**English** | [Русский](README_RU.md)

Custom Home Assistant integration for Ufanet / «Умный дом» intercoms using the cloud APIs used by the official mobile application.

> This is an independent community integration. It is not affiliated with or supported by Ufanet.

## Features

- UI setup with Ufanet contract/login and password.
- Door opening through Home Assistant `button` entities.
- Live UCAMS camera stream and snapshots.
- Native archive browsing with recording ranges, timeline zoom/pan and call markers.
- Intercom call history, the `ufanet_intercom_call` event, native **Incoming call** and **Last call image** entities, and a matching device trigger for the visual automation editor.
- Selectable call updates: polling by default or experimental low-latency FCM with safety polling.
- Temporary guest keys and accepted shared-access management.
- Manual archive export to MP4 using `ffmpeg -c copy` into Home Assistant Media.
- Persistent export media library with per-camera retention and size cleanup.
- Optional automatic MP4 saving around new intercom calls.
- Options Flow and privacy-conscious Home Assistant diagnostics.
- Unified Lovelace card: `custom:ufanet-intercom-card`.

## Unofficial API documentation

The repository also contains a maintained reverse-engineered reference for the Ufanet/UCAMS interfaces used by this integration:

- [API reference](docs/api/README.md)
- [API verification matrix](docs/api/STATUS.md)
- [curl examples](docs/api/examples/curl.md)
- [Python read-only example](docs/api/examples/python.md)

The reference explicitly distinguishes **Confirmed**, **Observed**, **Inferred**, and **Not supported** behavior. It is intended to make interoperability work easier for other developers and will be expanded as new endpoints are tested.

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

The repository is HACS-compatible and already contains finalized GitHub metadata for `alphazulu/ufanet-intercom-home-assistant`.

To install it as a HACS custom repository:

1. HACS → **Custom repositories**.
2. Add the GitHub repository URL as category **Integration**.
3. Install **Ufanet Intercom**.
4. Restart Home Assistant and add the integration from **Settings → Devices & services**.

## Lovelace card

Add the resource as a JavaScript module:

```text
/ufanet_intercom/ufanet-archive-card.js?v=0.25.0
```

Minimal card:

```yaml
type: custom:ufanet-intercom-card
entity: camera.YOUR_UFANET_CAMERA
default_tab: live
```

The card contains four tabs:

- **LIVE** — video, door button, latest call and jump-to-call recording.
- **АРХИВ** — timeline, call markers, MP4 export and export media library.
- **ГОСТИ** — shared invitations, accepted guest access, temporary keys and revoke actions.
- **ДИАГНОСТИКА** — token-free runtime health, polling, UCAMS/archive status and autosave state.

## Options

Open **Settings → Devices & services → Ufanet Intercom → Configure**.

Important options include the call update mode, polling interval, call archive lead, archive duration/step, MP4 retention/size limits and automatic call-video saving. YAML values on a particular card remain local overrides where supported.

### Call update modes

- **`polling` (default)** reads `call-history` at the configured interval and needs no additional setup.
- **`fcm` (experimental)** uses a local headless FCM receiver as a low-latency wake-up signal. `call-history` remains authoritative. Normal configured polling stays active until the listener confirms its MCS connection and is restored automatically on disconnect; while FCM is healthy, a 300-second safety poll remains active.

The FCM watchdog distinguishes launched listener tasks from an established transport, lets the FCM library handle short reconnects, and recreates a terminal or stalled listener with exponential backoff. A Home Assistant Repair warning appears after a prolonged outage and closes automatically after recovery. The diagnostics tab shows listener health, watchdog state, fallback polling, reconnects and connection timestamps without exposing push payloads or credentials.

### Incoming-call automations

Every intercom with call history has an **Incoming call** binary sensor. It turns on for 30 seconds after a new call is confirmed by `call-history`; another call restarts the timer. Use it directly in dashboards and state automations, or select the matching **Incoming call** device trigger in the visual automation editor. Both interfaces work identically with polling and FCM.

The **Last call image** entity downloads the tokenized Ufanet preview privately, sends only its bytes to local `ffmpeg`, extracts one JPEG frame and caches that frame in memory. The source MP4 URL is never placed in image state or passed on the `ffmpeg` command line.

The Last call sensor and `ufanet_intercom_call` event expose only `has_preview` / `has_archive` capability flags, never the temporary Ufanet URLs themselves. The custom card's **Call image** button opens the cached JPEG through Home Assistant's authenticated image proxy. **Preview video** requests a fresh temporary URL through an authenticated response service only after an explicit click and keeps it out of Recorder-backed state. Image diagnostics report ffmpeg availability, safe exception types and extraction counters; a Repairs warning opens after repeated failures and closes after a successful extraction.

An optional Companion app notification blueprint is available at [incoming_call_notification.yaml](blueprints/automation/ufanet_intercom/incoming_call_notification.yaml). Import that GitHub URL in **Settings → Automations & scenes → Blueprints**, select the Ufanet intercom, its Last call image entity and the phone. It waits three seconds by default for JPEG preparation; the delay is configurable. The blueprint intentionally contains no door-opening action.

FCM values are not distributed by this repository. Advanced users extract them on their own computer from their own decompiled copy of the official Android app:

```bash
python tools/research/fcm_probe_py/extract_firebase_config.py /path/to/decompiled-app -o firebase_config.json
```

Copy the result to `/config/ufanet_intercom/firebase_config.json`, choose `fcm` in the integration options and keep the default relative path `ufanet_intercom/firebase_config.json`. The file must remain inside the Home Assistant configuration directory. The integration reads the JSON but never stores its values in ConfigEntry options or diagnostics.

The extractor accepts a JADX/apktool/decompiled directory (or the relevant resources XML plus an explicit package name); the integration itself does not upload, retain or parse APK files. See [FCM API notes](docs/api/fcm.md) and the [extractor guide](tools/research/fcm_probe_py/README_RU.md).

## Automatic call recording

Disabled by default. When enabled, a new call is exported asynchronously after the requested post-call interval has entered the UCAMS archive. For example:

- archive lead: 15 seconds;
- save after call: 45 seconds;
- resulting requested clip: 60 seconds.

The call UUID is hashed before it is used for deduplication in the local filename; the raw UUID is not stored in the filename.

## Local media

Manual and automatic MP4 exports are saved under the Home Assistant media directory in `ufanet_intercom/`. The Archive tab lists only exports belonging to the selected camera and supports open/download/delete.

## Security notes

- Ufanet and UCAMS JWTs are kept in runtime memory and are never intentionally exposed by the diagnostics output.
- Generated guest links are access capabilities: treat them like temporary credentials.
- Opening the door is a real physical action and requires an explicit button press/confirmation in the custom card.
- Downloadable diagnostics redact login/password and avoid guest/media URLs and exact camera identifiers.
- The last-call image keeps only a generated JPEG in memory; tokenized preview video and its URL are not persisted.
- Tokenized call-media URLs remain internal runtime data and are not published in entity state or `ufanet_intercom_call` events. Explicit authenticated archive service responses may still contain a temporary URL required for playback.
- Firebase values, FCM credentials and the local Firebase config path are never included in diagnostics. Do not commit `firebase_config.json`.

## Troubleshooting

Run the repository release self-check before reporting a packaging/frontend problem:

```bash
python scripts/release_check.py
```

In Home Assistant, use either the **ДИАГНОСТИКА** card tab for live operational state or **Download diagnostics** on the integration/device page for privacy-redacted support data.

If local `ffmpeg` is unavailable or last-call JPEG extraction repeatedly fails, Home Assistant creates a Repairs warning. Call detection, archive viewing and door control remain available; the warning closes automatically after image extraction recovers.

## Development / release validation

`python scripts/release_check.py` verifies, among other things:

- Python compilation and JSON validity;
- JavaScript syntax when Node.js is installed;
- matching integration/card/cache-bust versions;
- unresolved custom-card `this._method()` calls;
- service names referenced by the card;
- absence of packaged `__pycache__`, `.pyc`, obvious JWTs and live guest links.

See [PUBLISHING.md](PUBLISHING.md) for HACS/GitHub publication steps.

## License

Licensed under the [MIT License](LICENSE).

Copyright © 2026 [alphazulu](https://github.com/alphazulu).

Commercial use, modification, redistribution, sublicensing, and inclusion in
proprietary products are permitted. The copyright notice and MIT permission
notice must be retained in copies or substantial portions of the software.

## Repository

https://github.com/alphazulu/ufanet-intercom-home-assistant
