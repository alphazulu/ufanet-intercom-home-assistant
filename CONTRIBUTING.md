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

Coverage is collected in CI for the API client and config flow. The suite covers authentication/token handling, API contracts, archive/media behavior, guest/FCM safety flows, notification actions, physical-key privacy/enrollment/inventory/history/rename validation behavior, frontend resource loading, and configuration-flow error mapping.

## Validation-only development / release preparation

The active combined validation PR intentionally keeps the published version at `0.30.0` while documentation and draft 0.31.0 release notes are prepared. Do not merge/tag/release or bump release-facing versions until the remaining hard live gates are complete or explicitly reviewed/waived and the user separately approves release preparation on the exact candidate.

Current evidence handoff:

- Android notification validation is complete for the planned candidate; the unavailable second-Ufanet-device negative live test is explicitly waived after targeted security review, while the cross-device safety invariant remains mandatory;
- physical-key capability, non-empty inventory/history, selected-key filtering and the negative printed-number result are live-confirmed;
- physical-key rename is live-confirmed, including eventual-consistent provider read-back and automatic bounded read-only verification retries after one provider write;
- the remaining hard functional blocker is new-key enrollment: real `auto_collect/enable`, physical registration, real `reason=key_add`, FCM-triggered inventory/event refresh and live enrollment error semantics;
- physical-key delete remains unimplemented and outside the current release scope;
- iOS notification actions remain not live-tested.

Documentation preparation is not release authorization. Read the active PR handoff/checklist before continuing work from a new branch or conversation, and inspect **Tests**, **HACS and Hassfest validation**, and **Release self-check** after every final branch change.
