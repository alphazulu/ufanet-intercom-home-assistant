# Changelog

## 0.25.4

- Moved archive export directory creation, duplicate lookup, file metadata checks and partial-file cleanup out of Home Assistant's event loop.
- Replaced the non-seekable preview pipe with an anonymous seekable Linux `memfd`, allowing `ffmpeg` to decode MP4 files whose metadata is stored after the media payload without exposing the tokenized URL or writing a named source file.
- Retained the first-frame fallback and per-call permanent-error suppression introduced in 0.25.3.

## 0.25.3

- Added a first-decodable-frame fallback when the preferred one-second preview frame is unavailable.
- Stopped repeating permanent validation/decoding failures for the same call every five minutes; transient download failures retain their bounded retry behavior.
- Added token-free payload-signature and retry-suppression diagnostics so invalid HTTPS media responses can be distinguished without exposing response bodies or URLs.

## 0.25.2

- Securely rewrote provider-issued HTTP call-preview URLs to HTTPS before any network request, without permitting an HTTP fallback.
- Reused the same HTTPS-only normalizer for explicit Preview-video responses and blocked automatic redirects while the integration downloads private preview bytes.
- Added a token-free `preview_https_upgraded` diagnostic plus distinct `unsupported_scheme`, `missing_host` and `embedded_credentials` failure codes.

## 0.25.1

- Added fixed privacy-safe `last_error_code` diagnostics for last-call image failures: `invalid_url`, `empty_preview`, `size_limit`, `download_error`, `decode_error`, `ffmpeg_unavailable` or `unexpected_error`.
- Displayed the human-readable failure reason separately from the exception type in the custom card, without logging or exposing the tokenized preview URL.
- Kept the strict absolute-HTTPS requirement unchanged so diagnostic improvements cannot weaken media-token transport security.

## 0.25.0

- Removed tokenized Ufanet `preview_url` and `archive_url` values from the Last call sensor state and `ufanet_intercom_call` event; capability-only `has_preview` and `has_archive` flags remain.
- Updated the custom card to open the cached Last call image through Home Assistant's authenticated image proxy; preview-video URLs are now requested through an authenticated response service only after an explicit click.
- Added token-free last-call image health to downloadable and card diagnostics, including ffmpeg availability, extraction counters and safe exception types.
- Added an auto-closing Repairs warning when local ffmpeg is unavailable or JPEG extraction repeatedly fails.
- Stopped returning raw ffmpeg stderr from archive-export failures and added privacy regression coverage for states, events, diagnostics, card source and logs.

## 0.24.0

- Added a native **Last call image** entity that privately downloads the confirmed call preview, extracts one JPEG frame through local `ffmpeg`, and keeps only the JPEG in memory.
- Tokenized preview URLs are not passed to `ffmpeg`, exposed in image state, persisted to disk, or added to diagnostics.
- Added an importable incoming-call notification blueprint for the Home Assistant Companion app with a configurable image preparation delay and no door-opening action.

## 0.23.0

- Added a native **Incoming call** binary sensor for every intercom with call history.
- The sensor turns on for 30 seconds after a confirmed `call-history` event and retriggers the timer for a subsequent call.
- The same entity works with polling and FCM because both paths continue to use authoritative call-history events; no raw FCM payload is exposed.

## 0.22.0

- Added an FCM watchdog that distinguishes listener task startup from a confirmed MCS connection and recreates terminal or stalled listeners with exponential backoff.
- Call-history polling now stays at the configured interval until FCM is healthy, switches to the 300-second safety interval after connection, and returns automatically after a disconnect.
- Added an automatically resolving Home Assistant Repair warning for prolonged FCM outages.
- Expanded privacy-preserving diagnostics with actual listener health, watchdog/fallback state, reconnect and failure counters, and connection timestamps.

## 0.21.0

- Added an **Incoming call** device trigger for every Ufanet intercom in Home Assistant's visual automation editor.
- The trigger reuses the confirmed, privacy-preserving `ufanet_intercom_call` event and works with both FCM and polling; FCM provides the lower-latency path.

## 0.20.1

- Added explicit token-free FCM startup diagnostics for Firebase registration, Ufanet device registration and the headless listener.
- The Lovelace diagnostics tab now shows which FCM startup stage succeeded instead of only reporting a combined active flag.

## 0.20.0

- Added a selectable call update mode: existing polling remains the default, while advanced users can enable an experimental headless FCM listener.
- FCM uses a user-owned local `firebase_config.json`, reacts to `reason=sip`, refreshes authoritative `call-history` immediately and retains a 300-second safety poll.
- The integration does not embed Firebase application values or parse/store APKs; the existing local extraction utility remains the explicit setup path.
- FCM/Firebase credentials, push payloads and the local config path are excluded from diagnostics and ConfigEntry data.
- Added token-free FCM health counters to diagnostics and the Lovelace diagnostics tab.
- Hardened probe sanitization for sender/message/call identifiers, removed brute-forceable hashes of short sensitive values, and documented four first-request call-history correlations (0.446–0.916 seconds).

## 0.19.2

- Hardened call-history response validation: malformed object responses without a `results` field now raise `UfanetResponseError` instead of being treated as an empty history.
- Added regression coverage for Ufanet/UCAMS authentication, archive handling, call autosave, MP4 export and cleanup, privacy diagnostics, integration lifecycle and coordinators.
- Added atomic MP4 export/deduplication tests, path-safety and retention tests, and explicit diagnostics redaction checks.
- CI now enforces at least 85% coverage across critical backend modules; the release suite contains 140 tests and currently exceeds 93% coverage.
- No Ufanet endpoint contract, door-control behavior, or user configuration migration is required from 0.19.1.

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
