# Authentication

[Русская версия](auth_RU.md)

> The v0.31.0 release does not change the basic Ufanet/UCAMS login chain.
> It does add live-confirmed evidence about per-device authorization revocation and
> the authorization side effect of FCM unregister.

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

## Device authorization and refresh-chain revocation

**Status: Confirmed for the tested flows**

Live testing on 2026-09-08 separated ordinary JWT authentication from FCM transport:

- a controller created only through `auth_by_contract` and never registered for FCM successfully queried `POST /api/v4/fcm_device/authorized_devices/`;
- that same plain-JWT controller successfully revoked a different test device through `POST /api/v4/fcm_device/logout_device/`;
- after `logout_device`, the target row disappeared, the target's already-issued access JWT still returned HTTP 200, and the target refresh JWT was rejected with HTTP 401;
- the independent controller/observer JWT remained usable.

A separate controlled probe then registered a disposable probe-owned FCM device with its own JWT pair and removed it using only `DELETE /api/v0/fcm/`, without calling `logout_device`. The row disappeared, the subject access JWT still returned HTTP 200, and the subject refresh JWT was rejected with HTTP 401. The independent observer remained authorized.

Therefore the two state-changing endpoints are distinct server operations, but both have a live-confirmed authorization-destructive effect on the tested target's refresh chain:

```text
POST /api/v4/fcm_device/logout_device/
    -> row removed
    -> issued access JWT may survive until expiry
    -> tested target refresh JWT rejected

DELETE /api/v0/fcm/
    -> FCM/device registration row removed
    -> issued access JWT may survive until expiry
    -> tested target refresh JWT rejected
```

`authorized_devices` must not be treated as an exhaustive independent inventory of all JWTs. Live testing showed that an entry can disappear from this inventory after FCM unregister even though the already-issued access JWT remains temporarily usable.

The Home Assistant integration therefore presents normal `logout_device` revocation as the canonical **authorized device** action and keeps direct FCM unregister as an explicitly advanced destructive action. Raw provider `device_id` values are not exposed to users.

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

The following endpoints have been successfully queried during development, but are not fully documented on this page:

```text
GET /api/v0/contract/
GET /api/v0/object/
POST /api/v0/fcm/
DELETE /api/v0/fcm/
POST /api/v4/fcm_device/authorized_devices/
POST /api/v4/fcm_device/logout_device/
```

See [FCM / push notifications](fcm.md) for device-registration details and the exact evidence boundaries.

## Security notes

- Never log access or refresh JWTs.
- Never put tokens into examples committed to the repository.
- Tokenized media URLs are also credentials for as long as their tokens remain valid.
- A UCAMS token must not be confused with `token_l`/`token_r`; they serve different purposes.
- Do not infer authorization safety from device title, platform, age, or presence/absence in `authorized_devices` alone.
- Both normal device logout and advanced FCM unregister require explicit confirmation because the tested target refresh authorization is invalidated.
