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

The project also uses **Experimental** for a user-facing interpretation that is deliberately exposed for validation but whose semantics are not yet proven. An Experimental field may ship only when its provisional nature is explicit, non-destructive and accepted during release review; otherwise it must be renamed/removed before release.

For the current physical-key work, provider `external_id` is **Confirmed** as the selector used by the official Android client for per-key passage history, while its interpretation as the digits printed on the physical key is **not confirmed**. On 2026-09-07 the user explicitly chose to keep the user-facing `number` candidate as Experimental for now. Therefore the release requirement is to preserve the explicit Experimental label in UI/docs and never present the mapping as Confirmed; matching it to a known physical key can happen later without blocking 0.31.0 solely on that semantic question.

For state-changing features, distinguish three separate checks:

1. the request shape matches the observed client contract;
2. the provider accepts the request;
3. the intended physical/account side effect is actually observed.

Do not treat (1) or (2) alone as proof of (3). When the integration has a post-write read-back verification path, successful read-back is part of the release evidence rather than an optional diagnostic.

## Current 0.31.0 preparation state

The combined validation branch is now in **release-preparation documentation freeze**, not release authorization.

Already live-confirmed for the physical-key/read-only path:

- capability discovery;
- empty and non-empty physical-key inventory;
- non-empty physical-key item fields;
- live passage-history item schema;
- selected-key `filters.key=<external_id>` behavior;
- Home Assistant/Lovelace selected-key history with real passage rows.

Reviewed design decision:

- the `external_id` -> printed-key-number interpretation remains **Experimental by design** for the current candidate; it is not promoted to Confirmed and real values remain excluded from diagnostics/logs/public support data.

Still unresolved before publication:

- real `auto_collect/enable` enrollment with a new unregistered key;
- real `reason=key_add` completion;
- live rename plus post-write confirmation;
- documented enrollment/rename error behavior;
- remaining notification safety gates tracked in PR #15.

Do **not** bump release-facing versions merely because documentation/release notes are being prepared. The version/cache-bust bump belongs to the exact release-candidate commit after the hard gates are resolved or explicitly waived.

## Live-validation gate

A green CI run is necessary but not sufficient for features that depend on real provider pushes or physical side effects. If the active development PR contains a `REQUIRED VALIDATION BEFORE ANY RELEASE` checklist, every item must be either:

- live-confirmed and recorded in the PR/documentation; or
- explicitly reviewed and waived/accepted with a documented reason.

Validation-only branches must not be tagged or published directly. In particular, physical-key enrollment must not be released solely from reconstructed Android behavior: a real new key must prove enrollment, `reason=key_add`, immediate inventory refresh and the privacy boundaries of resulting Home Assistant state/event. The Android-observed rename contract likewise requires a controlled live rename with post-write verification before it is promoted to Confirmed. The Android-observed delete-key endpoint remains outside release scope unless it receives a separate safety design and controlled live validation. Notification actions with physical door control likewise require the recorded real-call safety checks before final release approval.

## Release

The planned next minor version is **0.31.0**, subject to final confirmation at release time. Use a SemVer tag matching `manifest.json`, for example `v0.31.0`, and publish a GitHub Release rather than only creating a tag. An Unreleased planning heading or draft release notes are not authorization to publish.

Before tagging, verify that:

- the matching CHANGELOG section exists;
- all documentation links/examples refer to the release being published;
- no validation document claims **Confirmed** for an untested provider behavior;
- any **Experimental** behavior is explicitly documented as such and accepted in the final release review, or removed/renamed;
- all hard live-validation gates in the active release PR are resolved;
- the release commit is the exact commit reviewed/tested for publication;
- all release-facing versions/cache-bust values were bumped together only after explicit release-preparation approval;
- the final GitHub Release notes match the actual release candidate rather than an older validation snapshot.

Existing release tags are immutable and must not be moved to repair documentation after publication; documentation-only corrections go to `main`, while a corrected release artifact requires a new patch version.

Merge, tag and GitHub Release are separate release actions. Do not perform them without explicit user approval after validation.

For HACS custom-repository installation, users can add this repository as category **Integration**. A separate ZIP is optional for manual installers.

## HACS default listing

If submitting to the HACS default repositories, verify the current HACS publication requirements, ensure HACS Action and Hassfest pass without ignored checks, publish a GitHub Release, and review branding/trademark requirements.
