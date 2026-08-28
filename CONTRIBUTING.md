# Contributing

1. Never commit real Ufanet/UCAMS JWTs, passwords, contract credentials or active guest URLs.
2. Run `python scripts/release_check.py` before opening a pull request.
3. Run the automated tests with `pytest -vv` after installing `requirements_test.txt`.
4. Keep all Ufanet/UCAMS network traffic mocked in unit tests; tests must never require a real account or perform physical actions.
5. Keep physical actions such as door opening behind an explicit user action/confirmation.
6. Preserve response-service validation before destructive guest-access operations.
7. If frontend code changes, bump the integration/card/cache-bust version together.

## Test environment

The current test stack tracks Home Assistant 2026.8.x through `pytest-homeassistant-custom-component` and runs under Python 3.14 in GitHub Actions.

```bash
python -m pip install -r requirements_test.txt
pytest -vv
```

Coverage is collected in CI for the API client and config flow. The initial suite focuses on authentication/token handling, API payload/response contracts, archive URL construction, guest access, and configuration-flow error mapping.
