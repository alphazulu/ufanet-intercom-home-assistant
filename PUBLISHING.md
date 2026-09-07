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

The release self-check requires the same version in all release-facing locations:

- `custom_components/ufanet_intercom/manifest.json`;
- `INTEGRATION_VERSION`;
- Lovelace `CARD_VERSION`;
- the runtime frontend cache-bust URL;
- the Lovelace resource URL documented in `README.md`;
- the Lovelace resource URL documented in `README_RU.md`.

When a release adds or confirms private API behavior, update the detailed EN/RU API page, the EN/RU verification matrix, relevant data-model/example pages, user-facing feature documentation and CHANGELOG in the same release work. Do not upgrade an evidence label to **Confirmed** without a live test.

The project may use **Experimental** for a user-facing interpretation deliberately exposed during validation while its semantics are unproven. Such a field must be explicitly provisional and harmless, or removed/renamed before publication.

For the current physical-key work, the `external_id` question is resolved by live testing: `external_id` is **Confirmed** as the backend selector used for per-key passage history, while a direct comparison showed that it does **not** match the number printed on the tested physical key. The previously Experimental public `number` field has therefore been removed. Provider identifiers remain private runtime data and must not be reintroduced as a guessed printed-key number.

For state-changing features, distinguish three separate checks:

1. the request shape matches the observed client contract;
2. the provider accepts the request;
3. the intended physical/account side effect is actually observed.

Do not treat (1) or (2) alone as proof of (3). When the integration has a post-write read-back verification path, successful read-back is part of the release evidence rather than an optional diagnostic.

## Current 0.31.0 preparation state

The combined validation branch is in **release-preparation documentation freeze**, not release authorization.

Already live-confirmed for the physical-key path:

- capability discovery;
- empty and non-empty physical-key inventory;
- non-empty physical-key item fields;
- live passage-history item schema;
- selected-key `filters.key=<external_id>` behavior;
- Home Assistant/Lovelace selected-key history with real passage rows;
- negative printed-number comparison: the tested physical marking does not match candidate server identifiers, while `external_id` still selects the correct updating key history;
- controlled `rename_physical_key` success against `/api/v4/key/edit/`;
- eventual-consistent provider read-back;
- one provider write followed by bounded read-only verification retries;
- automatic post-write verification without requiring a manual refresh.

The Android notification block is also complete for current release validation. Real-call delivery, Open door, View camera, timeout replacement, post-open replacement, second-call supersession and expected real-call metadata have been live-tested. The unavailable negative test with a second Ufanet device was explicitly waived after targeted security/code review; only that live test was waived, not the cross-device safety invariant. iOS action delivery remains not live-tested and is not claimed as Confirmed.

Resolved design decisions:

- no physical-key number is exposed from provider identifiers; `external_id` stays private and is used only where its backend semantics are confirmed;
- physical-key rename is Confirmed for the tested success path and must never use an automatic write retry;
- notification cross-device isolation retains all runtime guards despite the documented second-device live-test waiver.

Still unresolved before publication:

- real `auto_collect/enable` enrollment with a new unregistered key;
- real `reason=key_add` completion;
- prompt FCM-triggered inventory/read-only-surface refresh after actual registration;
- privacy-safe `ufanet_intercom_key_enrollment` live result;
- documented live enrollment error behavior, including any observed HTTP 400/status semantics.

Do **not** bump release-facing versions merely because documentation/release notes are being prepared. The version/cache-bust bump belongs to the exact release-candidate commit after the remaining hard gates are resolved or explicitly waived.

## Live-validation gate

A green CI run is necessary but not sufficient for features that depend on real provider pushes or physical side effects. If the active development PR contains a `REQUIRED VALIDATION BEFORE ANY RELEASE` checklist, every item must be either:

- live-confirmed and recorded in the PR/documentation; or
- explicitly reviewed and waived/accepted with a documented reason.

Validation-only branches must not be tagged or published directly. In particular, physical-key enrollment must not be released solely from reconstructed Android behavior: a real new key must prove enrollment, `reason=key_add`, immediate inventory refresh and the privacy boundaries of resulting Home Assistant state/event.

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
- all release-facing versions/cache-bust values were bumped together only after explicit release-preparation approval;
- the final GitHub Release notes match the actual release candidate rather than an older validation snapshot.

Existing release tags are immutable and must not be moved to repair documentation after publication; documentation-only corrections go to `main`, while a corrected release artifact requires a new patch version.

Merge, tag and GitHub Release are separate release actions. Do not perform them without explicit user approval after validation.

For HACS custom-repository installation, users can add this repository as category **Integration**. A separate ZIP is optional for manual installers.

## HACS default listing

If submitting to the HACS default repositories, verify the current HACS publication requirements, ensure HACS Action and Hassfest pass without ignored checks, publish a GitHub Release, and review branding/trademark requirements.
