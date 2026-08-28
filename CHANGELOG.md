# Changelog

## 0.19.1

- Added the MIT License.
- Set copyright holder to `alphazulu`.
- Finalized HACS/GitHub metadata for `https://github.com/alphazulu/ufanet-intercom-home-assistant`.
- Set Home Assistant/HACS code owner to `@alphazulu`.
- No runtime/API behavior changes from 0.19.0.

## 0.19.0

- Repository/HACS packaging layout.
- Generic community intercom brand asset.
- Release self-check that validates Python, JSON, JavaScript and card method references.
- GitHub validation workflow templates and issue forms.
- Added `media_source` as an explicit Home Assistant dependency.

## 0.18.0

- Optional automatic MP4 export around new intercom calls.
- Post-call settle/retry logic and hashed call deduplication.
- Recent-call recovery after integration restart.
- Diagnostics tab in the unified Lovelace card.
- Runtime-status response action.

## 0.17.1

- Fixed missing `_loadIntegrationSettings()` frontend method.

## 0.17.0

- Options Flow with automatic config-entry reload.
- Config-entry and device diagnostics.
- Card reads integration settings unless overridden in YAML.

## 0.16.0

- Export media library.
- Manual delete and cleanup actions.
- Automatic cleanup by retention age and maximum total size.

## 0.15.1

- Replaced unsupported arbitrary UCAMS MP4 URLs with local HLS → ffmpeg remux into Home Assistant Media.

## 0.15.0

- LIVE intercom dashboard: camera status, door button, latest call and jump to archive.

## 0.14.0

- Temporary guest-key creation/list/revoke with live-confirmed minute durations.

## 0.13.0

- Accepted shared-access revoke with live-confirmed `access_id`/`contract_object_id` flow.

## 0.12.2

- Stable unified LIVE / Archive / Guests custom card baseline and persistent local generated-invite store.

## 0.3.0–0.12.1

- Archive ranges/URL actions, native archive entities, custom timeline card, zoom/pan, call markers, guest access and invite persistence evolved across these releases.

## 0.1.0–0.2.0

- Initial Ufanet intercom integration, reauthentication fix, last-call sensor and `ufanet_intercom_call` events.
