# Contributing

1. Never commit real Ufanet/UCAMS JWTs, passwords, contract credentials, active guest URLs, FCM credentials, or provider physical-key identifiers such as `id`, `key_id` or `external_id`.
2. Run `python scripts/release_check.py` before opening a pull request.
3. Run the automated tests with `pytest -vv` after installing `requirements_test.txt`.
4. Keep all Ufanet/UCAMS network traffic mocked in unit tests; tests must never require a real account or perform physical/state-changing actions.
5. Keep physical actions such as door opening and physical-key enrollment behind an explicit user action/confirmation.
6. Preserve fresh provider-state validation before destructive or identity-sensitive operations. Public physical-key management must use opaque refs rather than accepting raw provider key IDs. Rename must issue at most one provider write for one user action and verify eventual-consistent post-write inventory with bounded read-only retries before claiming success.
7. Do not implement physical-key deletion merely because the endpoint is present in the Android client. It is destructive and requires a separately reviewed confirmation/ownership model and controlled live validation.
8. Preserve response-service validation before destructive guest-access/FCM-session operations.
9. If frontend code changes, bump the integration/card/cache-bust version together only during an approved release-preparation step on the exact release candidate.
10. Never promote Android-observed or decompiled-client behavior to **Confirmed** without direct live evidence; green unit/CI results do not replace controlled live validation of state-changing endpoints.
11. Use **Experimental** only for a deliberately exposed user-facing interpretation whose semantics are not yet proven. Make the uncertainty visible in UI/docs and define the live test that resolves it. When live evidence disproves an interpretation, remove or rename the public field rather than preserving a misleading label; the former physical-key `number` candidate is the current example.
12. When a live test changes evidence status, update the detailed API page, EN/RU verification matrix, relevant data-model/security/user docs, CHANGELOG, and active release PR in the same workstream.

## Test environment

The current test stack tracks Home Assistant 2026.8.x through `pytest-homeassistant-custom-component` and runs under Python 3.14 in GitHub Actions.

```bash
python -m pip install -r requirements_test.txt
pytest -vv
```

CI enforces both a protected critical-module coverage threshold and an audit of the complete integration package. Standalone-camera modules also have their own coverage floor. The suite covers authentication/token handling, API contracts, archive/media behavior, guest/FCM safety flows, notification actions, physical-key privacy/enrollment/inventory/history/rename validation behavior, standalone-camera lifecycle/services/entities, frontend resource loading, and configuration-flow error mapping.

## Validation-only development / release preparation

The published baseline is v0.31.0. The current v0.32.0 candidate contains the standalone UCAMS camera work merged through PR #17 and live-validated on 2026-09-15. Release-facing versions may be synchronized only on an explicitly approved release-preparation branch.

Documentation preparation and a green candidate PR are not publication authorization. Before every release, inspect **Tests**, both coverage gates, the standalone-module coverage floor, **HACS and Hassfest validation**, and **Release self-check** on the exact candidate SHA. Merge, tag and GitHub Release remain separately approved actions.

Historical scope boundaries remain in force unless a later change explicitly addresses them: physical-key deletion is unimplemented, iOS notification actions are not live-confirmed, provider-specific payload behavior is not inferred, and private provider identifiers must not be introduced into public fixtures or output.
