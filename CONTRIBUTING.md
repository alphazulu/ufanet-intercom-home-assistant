# Contributing

1. Never commit real Ufanet/UCAMS JWTs, passwords, contract credentials, active guest URLs, FCM credentials, provider physical-key IDs or `external_id`/key-number values.
2. Run `python scripts/release_check.py` before opening a pull request.
3. Run the automated tests with `pytest -vv` after installing `requirements_test.txt`.
4. Keep all Ufanet/UCAMS network traffic mocked in unit tests; tests must never require a real account or perform physical/state-changing actions.
5. Keep physical actions such as door opening and physical-key enrollment behind an explicit user action/confirmation.
6. Preserve fresh provider-state validation before destructive or identity-sensitive operations. Public physical-key management must use opaque refs rather than accepting raw provider key IDs, and rename must verify the post-write inventory before claiming success.
7. Do not implement physical-key deletion merely because the endpoint is present in the Android client. It is destructive and requires a separately reviewed confirmation/ownership model and controlled live validation.
8. Preserve response-service validation before destructive guest-access/FCM-session operations.
9. If frontend code changes, bump the integration/card/cache-bust version together only during an approved release-preparation step on the exact release candidate.
10. Never promote Android-observed or decompiled-client behavior to **Confirmed** without direct live evidence; green unit/CI results do not replace controlled live validation of state-changing endpoints.
11. Use **Experimental** for a deliberately exposed user-facing interpretation whose semantics are not yet proven. Make that uncertainty visible in both UI and documentation, define the live test that would confirm it, and either confirm, rename, remove, or explicitly accept the Experimental status before release. The current physical-key `number` candidate is the reference example.
12. When a live test changes evidence status, update the detailed API page, EN/RU verification matrix, relevant data-model/security/user docs, CHANGELOG, and active release PR in the same workstream.

## Test environment

The current test stack tracks Home Assistant 2026.8.x through `pytest-homeassistant-custom-component` and runs under Python 3.14 in GitHub Actions.

```bash
python -m pip install -r requirements_test.txt
pytest -vv
```

Coverage is collected in CI for the API client and config flow. The suite covers authentication/token handling, API contracts, archive/media behavior, guest/FCM safety flows, notification actions, physical-key privacy/enrollment/inventory/history/rename validation behavior, frontend resource loading, and configuration-flow error mapping.

## Validation-only development / release preparation

The active combined validation PR intentionally keeps the published version at `0.30.0` while documentation and draft 0.31.0 release notes are prepared. Do not merge/tag/release or bump release-facing versions until the hard live gates are complete or explicitly reviewed/waived and the user separately approves release preparation on the exact candidate.

Documentation preparation is not release authorization. Read the active PR handoff/checklist before continuing work from a new branch or conversation, and inspect **Tests**, **HACS and Hassfest validation**, and **Release self-check** after every final branch change.
