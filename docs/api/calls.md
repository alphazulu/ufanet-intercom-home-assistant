# Call events and history

[Русская версия](calls_RU.md)

## Call history

**Status: Confirmed**

```http
GET https://dom.ufanet.ru/api/v1/skuds/call-history/?page=1&page_size=25
Authorization: JWT <UFANET_ACCESS_JWT>
```

Observed call fields include:

```json
{
  "uuid": "<CALL_UUID>",
  "called_at": "<OFFSET_AWARE_DATETIME>",
  "timezone": "<TIMEZONE_NAME>",
  "camera_number": "<CAMERA_NUMBER>",
  "address": "<ADDRESS>",
  "porch": "<PORCH>",
  "flat": "<FLAT>"
}
```

Do not treat this snippet as a complete schema; these are the fields relevant to the integration.

## Call media

**Status: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/cctv/history/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "uuid": "<CALL_UUID>"
}
```

Observed response includes tokenized URLs for:

- a `preview` MP4;
- an archive/media `url` MP4.

These URLs contain temporary access credentials and must not be logged, included in
diagnostics, persisted in Recorder-backed attributes, or copied into automation
payloads.

## Time semantics

**Status: Confirmed from observed call data**

`called_at` is offset-aware and represents the authoritative absolute instant of the call. The separate `timezone` field can differ from the offset/name expected by the client.

Recommended handling:

1. parse `called_at` as an aware datetime;
2. preserve the represented instant;
3. convert that instant to the desired display timezone;
4. never replace the timezone/offset on the parsed datetime without conversion.

Incorrect behavior such as blindly assigning the separate `timezone` field can shift the event to a different absolute time.

## Event identity

The integration uses the call `uuid` as the event identity for deduplication. For local automatic MP4 filenames it stores only a truncated SHA-256 reference, not the raw UUID.

**Status: Integration behavior, not an API requirement.**

## Home Assistant exposure

A confirmed `call-history` row remains the authoritative source for the durable
Home Assistant event even in FCM mode. `reason=sip` is used as a low-latency refresh
signal, but the push UUID does not replace `call-history.uuid`.

The public `ufanet_intercom_call` event and doorbell EventEntity deliberately omit
`preview_url`/`archive_url`. Home Assistant receives safe call metadata plus
`has_preview` / `has_archive` flags while tokenized media URLs remain private
runtime data.

The validation branch also feeds the same confirmed event into the Companion
notification blueprint. Images come from the private HA ImageEntity through
`/api/image_proxy/`, and the door action invokes the selected Home Assistant button
entity rather than embedding a provider endpoint/credential in the notification.

See [../notifications.md](../notifications.md) for the delivery sequence, Android
live-validation, safety model and remaining release gates.