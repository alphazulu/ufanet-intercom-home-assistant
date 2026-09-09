# curl examples

These examples intentionally focus on read-only operations. Commands that open a physical door, arm physical-key enrollment, rename/delete a physical key, change/revoke guest access, or terminate an FCM session are documented on their reference pages but are omitted here to reduce accidental execution.

Set placeholders in your shell environment or replace them manually. Never commit real values. UCAMS analytics and physical-key responses can contain private provider identifiers; inspect them locally and do not paste raw responses into public issues or CI logs.

## 1. Authenticate with Ufanet

```bash
curl -sS \
  -X POST 'https://dom.ufanet.ru/api/v1/auth/auth_by_contract/' \
  -H 'Content-Type: application/json' \
  --data '{"contract":"<LOGIN_OR_CONTRACT>","password":"<PASSWORD>"}'
```

Extract `token.access` and `token.refresh` from the response without printing them into CI logs.

## 2. List intercoms

```bash
curl -sS \
  'https://dom.ufanet.ru/api/v0/skud/shared/' \
  -H 'Authorization: JWT <UFANET_ACCESS_JWT>'
```

Use the required object's `id` as `<SKUD_ID>` and `cctv_number` as `<CAMERA_NUMBER>`.

## 3. Get UCAMS bearer token

```bash
curl -sS \
  -X POST 'https://cloud.ucams.ru/api/v0/auth/?ttl=20800' \
  -H 'Authorization: JWT <UFANET_ACCESS_JWT>'
```

## 4. Get camera metadata

```bash
curl -sS \
  -X POST 'https://cloud.ucams.ru/api/v0/cameras/this/' \
  -H 'Authorization: Bearer <UCAMS_JWT>' \
  -H 'Content-Type: application/json' \
  --data '{
    "fields":["number","token_l","token_r","timezone","server","analytics","tariff","streams_count"],
    "token_l_ttl":20800,
    "token_r_ttl":20800,
    "numbers":["<CAMERA_NUMBER>"]
  }'
```

For analytics capability discovery alone, v0.28.0 uses the smaller read-only request:

```bash
curl -sS \
  -X POST 'https://cloud.ucams.ru/api/v0/cameras/this/' \
  -H 'Authorization: Bearer <UCAMS_JWT>' \
  -H 'Content-Type: application/json' \
  --data '{
    "fields":["number","analytics"],
    "numbers":["<CAMERA_NUMBER>"]
  }'
```

Only call the motion report for a camera that explicitly advertises `motion_alarm`. `perimeter_security` remains Observed only and is not a production feature.

## 5. Query the confirmed motion report

```bash
curl -sS \
  -X POST 'https://cloud.ucams.ru/api/v0/analytics/motion_alarm/report/' \
  -H 'Authorization: Bearer <UCAMS_JWT>' \
  -H 'Content-Type: application/json' \
  --data '{
    "camera_number":"<CAMERA_NUMBER>",
    "start":"<START_ISO_8601_UTC>",
    "end":"<END_ISO_8601_UTC>",
    "limit":25,
    "order_by_date":"desc"
  }'
```

The confirmed response envelope contains `count`, `page`, and `results`; confirmed result fields are `id`, `date`, and `length`. `date` is the authoritative live timestamp. The provider `id` is private cursor material, not public event data.

Do not assume `limit` bounds the response: the live service returned `page_size=60` despite a smaller requested limit. No `page`/`offset` request field has been live-confirmed for this endpoint. Production v0.28.0 handles incomplete windows by splitting only the confirmed `start`/`end` interval and fails without cursor advancement if it cannot safely resolve the window. See [../analytics.md](../analytics.md).

## 6. Query archive ranges

```bash
curl -sS \
  'https://<MEDIA_SERVER>/<CAMERA_NUMBER>/recording_status.json?from=0&request=ranges&token=<TOKEN_R>'
```

## 7. Query call history

```bash
curl -sS \
  'https://dom.ufanet.ru/api/v1/skuds/call-history/?page=1&page_size=25' \
  -H 'Authorization: JWT <UFANET_ACCESS_JWT>'
```

## 8. Get call media metadata

```bash
curl -sS \
  -X POST 'https://dom.ufanet.ru/api/v1/cctv/history/' \
  -H 'Authorization: JWT <UFANET_ACCESS_JWT>' \
  -H 'Content-Type: application/json' \
  --data '{"uuid":"<CALL_UUID>"}'
```

The returned media URLs can contain active tokens. Do not paste the response into public issues.

## Notes

- Ufanet uses `JWT`; UCAMS uses `Bearer`.
- `token_l` and `token_r` are media tokens, not substitutes for the UCAMS bearer token.
- `motion_alarm` is the only analytics report currently Confirmed and used by production runtime.
- Physical-key `external_id` and provider `key_id` values are private; do not publish raw key-list responses.
- Physical-key enrollment/rename/delete are state-changing and intentionally have no copy/paste commands on this page; see [../keys.md](../keys.md) for evidence status and safety notes.
- Never publish raw analytics responses, provider camera/event IDs, exact event history, or tokens.
- For archive MP4 export, use the HLS method described in [../archive.md](../archive.md); the arbitrary `.mp4?token=<TOKEN_R>` form returned HTTP 403 in testing.
