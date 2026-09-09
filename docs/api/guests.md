# Guest and shared access

[Русская версия](guests_RU.md)

Ufanet exposes two distinct access-sharing flows observed by this project: accepted/shared users and temporary guest links.

> The combined notification/physical-key validation branch does not change the
> guest/shared-access contracts or their evidence status. This page was re-audited
> during the documentation refresh and has no functional changes.

## List temporary guest links

**Status: Confirmed**

```http
GET https://dom.ufanet.ru/api/v1/skuds/skud_share_open/
Authorization: JWT <UFANET_ACCESS_JWT>
```

The exact response schema is still being documented. Returned tokens/URLs are access credentials and must be treated as secrets.

## List accepted shared users

**Status: Confirmed**

```http
GET https://dom.ufanet.ru/api/v4/token/shared/users/?skud_id=<SKUD_ID>
Authorization: JWT <UFANET_ACCESS_JWT>
```

Used to enumerate users who have accepted shared access to the selected SKUD.

## Create a shared-access invitation

**Status: Confirmed**

```http
POST https://dom.ufanet.ru/api/v4/token/shared/create_token/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "skud_id": <SKUD_ID>
}
```

The response contains a share token used by the recipient. Never publish a real token in logs, issues, screenshots, or documentation.

## Accept shared access

**Status: Confirmed from application/API testing**

```http
POST https://dom.ufanet.ru/api/v4/token/shared_device/
Authorization: JWT <RECIPIENT_UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "token": "<SHARE_TOKEN>"
}
```

This operation is performed by the recipient account.

## Revoke accepted shared access

**Status: Confirmed — state-changing**

```http
POST https://dom.ufanet.ru/api/v4/token/delete/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "contract_object_id": <ACCESS_ID>
}
```

This removes an accepted shared-access relationship. User interfaces should request confirmation before revocation.

## Create temporary guest access

**Status: Confirmed — state-changing**

```http
POST https://dom.ufanet.ru/api/v1/skuds/skud_share_open/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "time": "180",
  "id": <SKUD_ID>
}
```

### `time` semantics

**Status: Confirmed from APK behavior and live testing**

The `time` value is a string containing **minutes**. The mobile application converts selected hours to minutes (`hours × 60`).

Examples:

| Requested lifetime | `time` |
|---|---:|
| 1 hour | `"60"` |
| 3 hours | `"180"` |
| 6 hours | `"360"` |

A three-hour guest link was created and revoked successfully during testing.

## Delete/revoke temporary guest access

**Status: Confirmed — state-changing**

```http
DELETE https://dom.ufanet.ru/api/v1/skuds/skud_share_open/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "token": "<TEMP_GUEST_TOKEN>",
  "id": <SKUD_ID>
}
```

## Security model

Guest and share tokens are bearer-style capabilities: possession can be enough to exercise the granted access. Treat them with the same care as temporary credentials.