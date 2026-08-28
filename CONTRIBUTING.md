# Contributing

1. Never commit real Ufanet/UCAMS JWTs, passwords, contract credentials or active guest URLs.
2. Run `python scripts/release_check.py` before opening a pull request.
3. Keep physical actions such as door opening behind an explicit user action/confirmation.
4. Preserve response-service validation before destructive guest-access operations.
5. If frontend code changes, bump the integration/card/cache-bust version together.
