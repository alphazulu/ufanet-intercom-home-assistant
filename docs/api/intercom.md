# Intercom / SKUD

[Русская версия](intercom_RU.md)

The Ufanet API exposes intercom access devices as SKUD objects.

## Discover shared/access-controlled intercoms

**Status: Confirmed**

```http
GET https://dom.ufanet.ru/api/v0/skud/shared/
Authorization: JWT <UFANET_ACCESS_JWT>
```

Observed SKUD fields used by the integration include:

```json
{
  "id": 123456,
  "role": "Домофон",
  "model": 39,
  "camera": null,
  "cctv_number": "<CAMERA_NUMBER>",
  "open_in_talk": "http",
  "open_type": "http",
  "relays": [],
  "private_status": 1,
  "scope": "owner"
}
```

Field presence and values may vary by device model/account. See [models.md](models.md).

## `/api/v0/skud/`

**Status: Observed**

```http
GET https://dom.ufanet.ru/api/v0/skud/
Authorization: JWT <UFANET_ACCESS_JWT>
```

For the account used in testing this endpoint returned an empty array while `/api/v0/skud/shared/` returned the actual intercom. Do not assume `/api/v0/skud/` is the preferred discovery endpoint.

## Physical-key capability

Physical-key recording support is not inferred from `model` or from an optional
field on the ordinary SKUD object. The project live-confirmed a separate filtered
request:

```http
POST /api/v0/intercoms/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json
```

```json
{
  "page": 1,
  "page_size": 10,
  "filters": {
    "has_key_recording_support": true
  }
}
```

**Status: Confirmed for capability discovery.**

Only intercoms actually returned with `has_key_recording_support=true` receive the
validation-branch **Add physical key** button and key/passage polling. The enrollment
and `reason=key_add` wire contracts are documented separately in [keys.md](keys.md)
and remain below Confirmed until a new physical key is tested.

## Open door

**Status: Confirmed — physical side effect**

```http
GET https://dom.ufanet.ru/api/v0/skud/shared/<SKUD_ID>/open/?door=1
Authorization: JWT <UFANET_ACCESS_JWT>
```

Observed successful response:

```json
{
  "result": true
}
```

> **Warning:** this endpoint performs a real physical action. Do not call it as a connectivity probe, health check, background retry test, or documentation example against a live device. Require explicit user intent in applications.

The validation-branch Companion notification does not place this provider endpoint
inside the push. **Open door** invokes the selected Home Assistant button entity and
also verifies that it belongs to the same HA device as the selected intercom. See
[../notifications.md](../notifications.md).

### `door` parameter

Only `door=1` has been tested by this project.

**Status: Confirmed for `door=1`; other values unknown.**

## Camera association

For the tested device, `camera` was `null`, while `cctv_number` contained the UCAMS camera identifier. The integration therefore uses `cctv_number` to look up video metadata.

**Status: Confirmed for the tested model; cross-model behavior is not yet characterized.**