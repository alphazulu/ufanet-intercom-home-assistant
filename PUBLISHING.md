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

For state-changing features, distinguish three separate checks:

1. the request shape matches the observed client contract;
2. the provider accepts the request;
3. the intended physical/account side effect is actually observed.

Do not treat (1) or (2) alone as proof of (3).

## Live-validation gate

A green CI run is necessary but not sufficient for features that depend on real
provider pushes or physical side effects. If the active development PR contains a
`REQUIRED VALIDATION BEFORE ANY RELEASE` checklist, every item must be either:

- live-confirmed and recorded in the PR/documentation; or
- explicitly reviewed and waived with a documented reason.

Validation-only branches must not be tagged or published directly. In particular,
physical-key enrollment must not be released solely from reconstructed Android
behavior: a real new key must prove enrollment, `reason=key_add`, immediate
inventory refresh, and the privacy boundaries of the resulting Home Assistant
state/event. Notification actions with physical door control likewise require the
recorded real-call safety checks before final release approval.

## Release

Use a SemVer tag matching `manifest.json`, for example `v0.31.0`, and publish a GitHub Release rather than only creating a tag.

Before tagging, verify that:

- the matching CHANGELOG section exists;
- all documentation links/examples refer to the release being published;
- no validation document claims **Confirmed** for an untested provider behavior;
- all hard live-validation gates in the active release PR are resolved;
- the release commit is the exact commit reviewed/tested for publication.

Existing release tags are immutable and must not be moved to repair documentation after publication; documentation-only corrections go to `main`, while a corrected release artifact requires a new patch version.

For HACS custom-repository installation, users can add this repository as category **Integration**. A separate ZIP is optional for manual installers.

## HACS default listing

If submitting to the HACS default repositories, verify the current HACS publication requirements, ensure HACS Action and Hassfest pass without ignored checks, publish a GitHub Release, and review branding/trademark requirements.