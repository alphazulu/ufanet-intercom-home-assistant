# Authentication

[Русская версия](auth_RU.md)

> The combined notification/physical-key validation branch does not change the
> Ufanet/UCAMS authentication chain. This page was re-audited during the
> documentation refresh and its existing Confirmed claims remain unchanged.

## Ufanet login

**Status: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/auth/auth_by_contract/
Content-Type: application/json

{
  "contract": "<LOGIN_OR_CONTRACT>",
  "password": "<PASSWORD>"
}
```

Observed response contains token data including:

```json
{
  "token": {
    "access": "<UFANET_ACCESS_JWT>",
    "refresh": "<UFANET_REFRESH_JWT>"
  },
  "exp": "<...>"
}
```

Do not assume the example is a complete schema; only the fields required by the integration are documented here.

## Ufanet Authorization header

**Status: Confirmed**

Authenticated Ufanet requests use:

```http
Authorization: JWT <UFANET_ACCESS_JWT>
```

`Bearer` is not the scheme used by the tested Ufanet endpoints.

## Token refresh

**Status: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/auth/refresh/
Content-Type: application/json

{
  "token": "<UFANET_REFRESH_JWT>"
}
```

The integration refreshes the access token instead of storing a password-derived session indefinitely.

## Exchange Ufanet JWT for UCAMS token

**Status: Confirmed**

```http
POST https://cloud.ucams.ru/api/v0/auth/?ttl=20800
Authorization: JWT <UFANET_ACCESS_JWT>
```

Observed response:

```json
{
  "token": "<UCAMS_JWT>"
}
```

The requested `ttl` above is the value used and tested by this project. Other TTL values have not been systematically characterized.

## UCAMS Authorization header

**Status: Confirmed**

Subsequent UCAMS control API calls use:

```http
Authorization: Bearer <UCAMS_JWT>
```

## Ancillary authenticated Ufanet endpoints

The following endpoints have been successfully queried during development, but are not fully documented yet:

```text
GET /api/v0/contract/
GET /api/v0/object/
POST /api/v0/fcm/
```

**Status: Confirmed for reachability; response semantics not yet documented.**

## Security notes

- Never log access or refresh JWTs.
- Never put tokens into examples committed to the repository.
- Tokenized media URLs are also credentials for as long as their tokens remain valid.
- A UCAMS token must not be confused with `token_l`/`token_r`; they serve different purposes.