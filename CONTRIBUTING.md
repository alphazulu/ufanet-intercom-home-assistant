# Contributing

1. Never commit real Ufanet/UCAMS JWTs, passwords, contract credentials, active guest URLs, tokenized media URLs, FCM credentials/raw push payloads, physical-key `external_id` values, or provider key IDs.
2. Run `python scripts/release_check.py --strict-hacs` before opening/finalizing a pull request.
3. Run the automated tests with `pytest -vv` after installing `requirements_test.txt`.
4. Keep all Ufanet/UCAMS network traffic mocked in unit tests; tests must never require a real account or perform physical/access-control actions.
5. Keep physical actions such as door opening and physical-key enrollment behind explicit user intent. Never use them for startup checks, health probes, or automatic retries unrelated to the active user action.
6. Preserve same-device revalidation and action expiration in actionable door notifications. Manual notification tests must not expose a physical door action.
7. Preserve response-service validation before destructive guest/session operations. Physical-key delete must not be implemented without separate live contract validation, strict intercom/key association checks, and explicit confirmation.
8. Keep API evidence labels accurate: decompiled-client behavior is **Observed**, not **Confirmed**, until exercised against a real authorized account/device. For state-changing endpoints, an HTTP success is not enough unless the intended side effect was also verified.
9. When behavior changes, update the relevant EN/RU API page, verification matrix, data-model/security/user documentation and CHANGELOG in the same release work.
10. If frontend/release code changes for an actual release, bump the integration/card/cache-bust/documented resource version together. Do not bump validation branches merely to represent unreleased work.
11. Treat any `REQUIRED VALIDATION BEFORE ANY RELEASE` checklist in the active PR as a hard release gate unless an item is explicitly reviewed and waived with a documented reason.

## Test environment

The current test stack tracks Home Assistant 2026.8.x through `pytest-homeassistant-custom-component` and runs under Python 3.14 in GitHub Actions.

```bash
python -m pip install -r requirements_test.txt
pytest -vv
python scripts/release_check.py --strict-hacs
```

Coverage is collected in CI for critical backend modules. The suite covers authentication/token handling, API payload/response contracts, archive and media behavior, guest/session safety, FCM handling, notification blueprint state transitions, physical-key capability/enrollment/inventory logic, analytics privacy/pagination, configuration flow and integration lifecycle.

Live/provider tests are intentionally separate from unit tests. Record their sanitized results in the relevant PR and documentation; never copy credentials, raw private responses, provider media URLs or physical-key identifiers into test fixtures or public logs.
