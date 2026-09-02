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

When a release adds or confirms private API behavior, update the detailed EN/RU API page, the EN/RU verification matrix, relevant data-model/example pages, and the user-facing feature documentation in the same release work. Do not upgrade an evidence label to **Confirmed** without a live test.

## Release

Use a SemVer tag matching `manifest.json`, for example `v0.28.0`, and publish a GitHub Release rather than only creating a tag.

Before tagging, verify that the matching CHANGELOG section exists and that all documentation links/examples refer to the release being published. Existing release tags are immutable and must not be moved to repair documentation after publication; documentation-only corrections go to `main`, while a corrected release artifact requires a new patch version.

For HACS custom-repository installation, users can add this repository as category **Integration**. A separate ZIP is optional for manual installers.

## HACS default listing

If submitting to the HACS default repositories, verify the current HACS publication requirements, ensure HACS Action and Hassfest pass without ignored checks, publish a GitHub Release, and review branding/trademark requirements.
