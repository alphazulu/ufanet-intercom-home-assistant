# Publishing checklist

Repository identity is finalized:

- GitHub: `https://github.com/alphazulu/ufanet-intercom-home-assistant`
- Code owner: `@alphazulu`
- License: MIT
- Copyright: `Copyright (c) 2026 alphazulu`

## Validate

Run locally:

```bash
python scripts/release_check.py --strict-hacs
```

GitHub Actions also runs the release self-check, HACS validation and Home Assistant Hassfest.

The release self-check requires the same version in **all** release-facing locations:

- `custom_components/ufanet_intercom/manifest.json`;
- `INTEGRATION_VERSION` in `const.py`;
- Lovelace `CARD_VERSION` in `ufanet-archive-card.js`;
- main archive-card cache-bust in `__init__.py`;
- physical-keys extension cache-bust in `__init__.py`;
- key-history extension cache-bust in `__init__.py`;
- authorized-devices extension cache-bust in `authorized_devices.py`;
- the Lovelace resource URL documented in `README.md`;
- the Lovelace resource URL documented in `README_RU.md`.

The release gate also parses **every packaged frontend JavaScript file** with `node --check` when Node.js is available and verifies `_callResponseService(...)` references from all frontend files against `services.yaml`. The base-card class method-reference check remains scoped to the base card because packaged extensions intentionally monkey-patch the prototype.

This broader check is important for 0.31.0: validation introduced packaged KEYS/history and authorized-device extensions, so a stale extension cache-bust must fail release preparation rather than silently shipping an older browser resource.

When a release adds or confirms private API behavior, update the detailed EN/RU API page, the EN/RU verification matrix, relevant data-model/example pages, user-facing feature documentation and CHANGELOG in the same release work. Do not upgrade an evidence label to **Confirmed** without a live test.

The project may use **Experimental** for a user-facing interpretation deliberately exposed during validation while its semantics are unproven. Such a field must be explicitly provisional and harmless, or removed/renamed before publication.

For the current physical-key work, the `external_id` question is resolved by live testing: `external_id` is **Confirmed** as the backend selector used for per-key passage history, while a direct comparison showed that it does **not** match the number printed on the tested physical key. The previously Experimental public `number` field has therefore been removed. Provider identifiers remain private runtime data and must not be reintroduced as a guessed printed-key number.

For state-changing features, distinguish three separate checks:

1. the request shape matches the observed client contract;
2. the provider accepts the request;
3. the intended physical/account side effect is actually observed.

Do not treat (1) or (2) alone as proof of (3). When the integration has a post-write read-back verification path, successful read-back is part of the release evidence rather than an optional diagnostic.

## Current 0.31.0 preparation state

The combined validation branch is now in **0.31.0 release-candidate preparation**, not release authorization. All hard functional gates under the approved scope are closed by live evidence.

Live-confirmed release-critical areas include:

- actionable Android call notification, physical **Open door**, same-device **View camera**, timeout/post-open replacement, second-call supersession and metadata checks;
- targeted authorized-device revoke and separately warned direct FCM unregister behavior, with refresh-chain effects tested and Home Assistant-owned registrations protected;
- physical-key capability, inventory, per-key passage history, privacy-safe opaque refs and backend-verified rename;
- end-to-end enrollment of a genuinely unregistered physical key through the real 60-second `auto_collect/enable` window;
- real headless-FCM `reason=key_add` completion matching the tested success rule;
- a separate no-key timeout with no additional completion push;
- frontend resource/load regression checks.

Provider IDs/tokens/raw pushes remain private. Physical-key deletion is still outside 0.31.0 scope. iOS actionable notification delivery remains not live-tested and is not claimed as Confirmed. Unobserved provider-specific enrollment failure payloads are not inferred.

The RC synchronization must set manifest, `INTEGRATION_VERSION`, base-card `CARD_VERSION`, all packaged frontend cache-busts, and EN/RU README RC resource versions to **0.31.0** together. Merge, tag and GitHub Release remain separate actions requiring explicit approval.

## Live-validation gate

A green CI run is necessary but not sufficient for features that depend on real provider pushes or physical side effects. If the active development PR contains a `REQUIRED VALIDATION BEFORE ANY RELEASE` checklist, every item must be either:

- live-confirmed and recorded in the PR/documentation; or
- explicitly reviewed and waived/accepted with a documented reason.

Validation/RC branches must not be tagged or published directly. The physical-key enrollment requirement is now satisfied by a real new-key test with sanitized evidence in `docs/api/key_enrollment_live_2026-09-09.md`; do not regress this evidence standard or replace it with reconstructed-client assumptions.

The physical-key rename success path already has controlled live evidence, including eventual-consistent read-back and automatic read-only verification retries. Do not regress that safety model by adding automatic write retries.

The Android-observed delete-key endpoint remains outside release scope unless it receives a separate safety design and controlled live validation. Notification actions with physical door control retain their documented real-call safety evidence and the explicit second-device live-test waiver; do not reinterpret that waiver as iOS validation or as permission to remove the cross-device runtime guards.

## Release

The planned next minor version is **0.31.0**, subject to final confirmation at release time. Use a SemVer tag matching `manifest.json`, for example `v0.31.0`, and publish a GitHub Release rather than only creating a tag. An Unreleased planning heading or draft release notes are not authorization to publish.

Before tagging, verify that:

- the matching CHANGELOG section exists;
- all documentation links/examples refer to the release being published;
- no validation document claims **Confirmed** for an untested provider behavior;
- any remaining **Experimental** behavior is explicitly documented and accepted in final release review, or removed/renamed;
- all hard live-validation gates in the active release PR are resolved;
- the release commit is the exact commit reviewed/tested for publication;
- all release-facing versions/cache-bust values listed above were bumped together only after explicit release-preparation approval;
- `python scripts/release_check.py --strict-hacs` succeeds on that exact SHA;
- Tests and HACS/Hassfest succeed on that exact SHA;
- the final GitHub Release notes match the actual release candidate rather than an older validation snapshot.

Existing release tags are immutable and must not be moved to repair documentation after publication; documentation-only corrections go to `main`, while a corrected release artifact requires a new patch version.

Merge, tag and GitHub Release are separate release actions. Do not perform them without explicit user approval after validation.

For HACS custom-repository installation, users can add this repository as category **Integration**. A separate ZIP is optional for manual installers.

## HACS default listing

If submitting to the HACS default repositories, verify the current HACS publication requirements, ensure HACS Action and Hassfest pass without ignored checks, publish a GitHub Release, and review branding/trademark requirements.
