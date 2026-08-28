# curl examples

These examples intentionally focus on read-only operations. Commands that open a physical door or change/revoke guest access are documented on their reference pages but are omitted here to reduce accidental execution.

Set placeholders in your shell environment or replace them manually. Never commit real values.

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
    "fields":["number","token_l","token_r","timezone","server","tariff","streams_count"],
    "token_l_ttl":20800,
    "token_r_ttl":20800,
    "numbers":["<CAMERA_NUMBER>"]
  }'
```

## 5. Query archive ranges

```bash
curl -sS \
  'https://<MEDIA_SERVER>/<CAMERA_NUMBER>/recording_status.json?from=0&request=ranges&token=<TOKEN_R>'
```

## 6. Query call history

```bash
curl -sS \
  'https://dom.ufanet.ru/api/v1/skuds/call-history/?page=1&page_size=25' \
  -H 'Authorization: JWT <UFANET_ACCESS_JWT>'
```

## 7. Get call media metadata

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
- For archive MP4 export, use the HLS method described in [../archive.md](../archive.md); the arbitrary `.mp4?token=<TOKEN_R>` form returned HTTP 403 in testing.