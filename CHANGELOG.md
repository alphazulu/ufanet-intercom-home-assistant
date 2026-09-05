# Changelog

## Unreleased (validation for 0.31.0)

- Added a native Home Assistant doorbell EventEntity for confirmed Ufanet calls and an importable Companion notification blueprint with immediate text delivery, private `/api/image_proxy/` image replacement, stable per-intercom notification tags, configurable image wait/action timeout and privacy-safe call metadata.
- Added guarded actionable notification controls: **Open door** uses a unique Home Assistant-local action ID, requires the selected button to belong to the same Ufanet device, repeats that membership check immediately before `button.press`, expires after timeout, and is disabled for manual blueprint runs; **View camera** can open the selected same-device live `camera.*` entity directly through Home Assistant More Info.
- Fixed Android Companion payload compatibility discovered during live testing (`trigger.event.context.id` rather than a missing bare context and string `authenticationRequired="true"` for the FCM data channel). Android real-call delivery, physical door opening, direct live-camera navigation and timeout replacement of the same notification have been live-tested; remaining real-call race/mismatch/metadata checks are tracked as hard release gates.
- Added **Add physical key** for intercoms that advertise `has_key_recording_support`. The button mirrors the Android-observed `POST /api/v4/key/skud/<id>/auto_collect/enable/` flow and exposes the observed 60-second enrollment window; successful HTTP dispatch is not treated as proof that a key was registered.
- Added `reason=key_add` FCM completion handling using the Android-observed success rule (`key_status == 0` plus a valid `key_id`), an immediate physical-key coordinator refresh, privacy-safe `ufanet_intercom_key_enrollment` events, and token/identifier-free key-add diagnostics. The real `key_add` wire payload remains Observed until a new physical key is available for end-to-end testing.
- Extended the **Physical keys** sensor with a read-only `keys` inventory filtered to the selected intercom. Public rows contain only `name` and UTC `created_at`; provider `external_id` is discarded at normalization and provider key IDs remain internal. The empty live state (`state=0`, `keys=[]`) has been verified in Home Assistant; non-empty inventory remains a release gate.
- Documented Android-observed physical-key rename (`POST /api/v4/key/edit/`) and delete (`POST /api/v4/key/skud/<id>/delete/key/`) contracts without implementing them. Delete remains explicitly destructive and outside the current release scope.
- Updated EN/RU user documentation, notification guide, physical-key reference, FCM reference, API verification matrix, data models, security guidance and publishing checklist to distinguish Confirmed vs Observed behavior and preserve the required live-validation gates.
- This work remains **validation-only**: do not tag or publish a release until the active combined-validation PR's `REQUIRED VALIDATION BEFORE ANY RELEASE` checklist is completed or explicitly reviewed/waived.

## 0.30.0

- Added a live-confirmed, privacy-safe authorized-device inventory based on `POST /api/v4/fcm_device/authorized_devices/`, including non-blocking verification that the Home Assistant FCM registration is present and has call access.
- Added coarse FCM authorization diagnostics (`registered`, `call_access`, last-update age bucket and bounded error type) without exposing provider device IDs, titles, exact timestamps, FCM tokens or raw responses.
- Live-confirmed `POST /api/v4/fcm_device/logout_device/` end-to-end against a disposable probe-owned registration: present before logout, absent after HTTP 200, then restored and visible again.
- Added `list_fcm_sessions`, targeted `revoke_fcm_session` and guarded `revoke_other_fcm_sessions` Home Assistant response services. Public session rows use opaque entry-scoped `session_ref` values; raw provider `device_id` values stay internal.
- Protected every locally provable Home Assistant-owned FCM registration for the same account from both targeted and bulk revocation. Ownership verification fails closed before destructive actions.
- Added fresh-inventory resolution and post-revoke disappearance checks for targeted revocation; bulk revocation requires `confirm=true` plus an exact `expected_count` and aborts if the revocable inventory changed. No session is removed automatically by age, title or platform.
- Added the **УСТРОЙСТВА** card tab with authorized-session summary, HA/MDI platform icons, last activity, call-access state, protected Home Assistant rows, explicit targeted revoke, and double-confirmed bulk revoke. Raw provider identifiers are never rendered.
- Live-tested the production targeted-revoke path in Home Assistant using only a disposable probe registration, then verified that the protected Home Assistant registration remained present. The final card layout was also visually smoke-tested on a real Home Assistant dashboard.
- Extended the standalone FCM research probe with privacy-safe authorized-device auditing and a controlled `--verify-logout-device` lifecycle check restricted to the probe-owned registration.
- Updated EN/RU user, API, security and research documentation for the new FCM authorization/session-security model and bumped integration/card/cache-bust documentation to v0.30.0.
- Added regression coverage for inventory privacy, stable opaque refs, HA ownership protection, fresh targeted revoke verification, bulk count-race protection and card privacy/safety wiring.

## 0.29.0

- Added privacy-safe UCAMS motion-event markers to the Lovelace archive timeline for cameras that advertise the live-confirmed `motion_alarm` capability.
- Added the authenticated `ufanet_intercom.get_motion_events` response service for one camera-local day; frontend responses contain only normalized event times and support/count metadata, never provider camera numbers, event/cursor IDs, `length`, raw history, media, screenshots or recognition data.
- Kept production history loading on the already live-confirmed `POST /api/v0/analytics/motion_alarm/report/` contract with safe `start`/`end` window splitting; the Android-observed `/api/v0/analytics/archive_events/` endpoint remains documented as Observed only and is not used at runtime.
- Drew analytics events as point markers at their authoritative timestamps and start archive playback approximately 18 seconds before a selected event, matching the observed Android `EVENT_TIME_OFFSET=18000` behavior without shifting the marker itself.
- Added capability recovery for archive-marker loading after startup or a temporary analytics outage, while keeping unsupported analytics optional and non-blocking for normal archive playback.
- Refreshed call and motion markers together, preserved timeline zoom/pan behavior, and added EN/RU documentation for the archive analytics model.
- Added regression coverage for timestamp-only privacy reduction, service-response privacy, unsupported cameras, capability recovery, sanitized UCAMS errors and frontend marker wiring.
- Live-tested the feature on Home Assistant: motion positions rendered on the archive timeline and visually matched the corresponding event times during verification.

## 0.28.0

- Added live-confirmed, read-only UCAMS `motion_alarm` support for intercom cameras that explicitly advertise the capability.
- Added a Motion `EventEntity`, the privacy-minimized `ufanet_intercom_motion` event and a matching visual device trigger; motion entity discovery recovers automatically after a temporary analytics outage.
- Persisted only a private per-camera replay cursor while exposing only coarse motion time to Home Assistant; camera identifiers, UCAMS cursor IDs, media, screenshots, recognition data and raw event history remain excluded from entities, logs and diagnostics.
- Preserved fractional event timestamps across reloads, established an empty first-poll baseline at poll time, and retained same-timestamp ID deduplication without replaying historical events.
- Added safe handling for oversized UCAMS report pages using only the live-confirmed `start`/`end` contract; dense windows fail without cursor advancement rather than silently skipping unseen events.
- Made multi-camera analytics polling transactional and sanitized coordinator failures so server response text cannot leak through Home Assistant logs.
- Updated the privacy-safe UCAMS analytics research probe and EN/RU API documentation with the confirmed `date` wire field, response envelope and observed pagination behavior.
- Added targeted regression coverage for analytics pagination, cursor persistence, error privacy, coordinator-to-bus events, Motion EventEntity recovery, diagnostics and device triggers.

## 0.27.0

- Live-confirmed the read-only account-feature, key-capable intercom, physical-key list and passage-history request forms; the tested account returned one supported intercom with valid empty key/history collections.
- Added a dedicated 60-second physical-key coordinator, a registered-key count sensor, a latest-passage timestamp sensor, a passage `EventEntity`, the `ufanet_intercom_key_passage` event and a matching visual device trigger.
- Persisted only a private timestamp/internal-key cursor so reloads do not replay old passages; the first successful poll establishes a baseline instead of generating historical events.
- Kept key names transient and limited them to an actual passage event; `external_id`, full history, names and event timestamps are excluded from diagnostics.
- Updated event and autosave device lookup to the current Home Assistant device-registry API.
- Kept the feature read-only: key creation, rename, deletion and BLE access are not implemented.

## 0.26.0

- Live-confirmed `DELETE /api/v0/fcm/` against the probe-owned virtual device and restored the same registration immediately with HTTP 200 responses.
- Added automatic unregister for the strictly validated integration-owned `Home Assistant_<UUID>` when switching from FCM to polling or removing the ConfigEntry; ordinary reloads and Home Assistant restarts preserve the registration.
- Kept polling operational when unregister fails, persisted a bounded cleanup retry, and added an automatically closing Home Assistant Repair warning plus token-free cleanup diagnostics.
- Added schema validation and safe regeneration for damaged private FCM state without exposing credentials or device IDs.
- Fixed standalone probe cleanup so `--verify-unregister` closes its Ufanet HTTP session without stopping an MCS listener that was never started.

## 0.25.5

- Moved the packaged Lovelace card file check out of Home Assistant's event loop.
- Moved Firebase configuration path resolution, including filesystem canonicalization, into the executor together with the existing local JSON read.
- Kept update discovery and installation exclusively under GitHub Releases and HACS; the integration does not implement a self-updater.

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