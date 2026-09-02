# UCAMS camera analytics

[Русская версия](analytics_RU.md)

This page records read-only camera analytics contracts observed in the official
Android client and verified against the live UCAMS service where noted.

## Camera capability metadata

**Status: Confirmed for `motion_alarm`; Observed for `perimeter_security`**

The existing `POST /api/v0/cameras/this/` request can include the `analytics`
field. The live-tested camera returned `motion_alarm`. The same Android contract
also exposes `perimeter_security`, but the tested tariff did not advertise that
capability, so the event endpoint was not called for it.

The research probe requests only:

```json
{
  "fields": ["number", "analytics", "tariff", "timezone"],
  "numbers": ["<CAMERA_NUMBER>"]
}
```

No live, archive, or screenshot token is requested for capability discovery.

## Motion event report

**Status: Confirmed for `motion_alarm`**

The live-confirmed request is:

```http
POST https://cloud.ucams.ru/api/v0/analytics/motion_alarm/report/
Authorization: Bearer <UCAMS_TOKEN>
Content-Type: application/json
```

Request fields:

```json
{
  "camera_number": "<CAMERA_NUMBER>",
  "start": "<ISO-8601 UTC>",
  "end": "<ISO-8601 UTC>",
  "limit": 5,
  "order_by_date": "desc"
}
```

The live response uses a dictionary envelope containing `count`, `page` and
`results`. Each confirmed `motion_alarm` result contains an opaque numeric `id`,
an ISO-8601 UTC `date`, and `length`.

The Android DTO contains a field named `time`, but the live wire schema uses
`date`. Runtime code must therefore treat `date` as authoritative and must not
apply any archive playback offset to it.

The `id` is not user-facing event data. It is treated only as a private opaque
cursor for deduplication.

## Pagination and limits

The confirmed `page` object contains `current`, `next`, `previous`, `all`, and
`page_size`. In the live test the server returned a page size of 60 even though
a smaller `limit` was requested. Clients must not assume that the server obeys
the requested row limit and must cap local processing themselves.

## Scope and privacy boundary

Production support is intentionally limited to `motion_alarm`. The project does
not request face recognition, license plates, thermal data, crowd analysis,
helmet detection, screenshots, free text, or media URLs.

The probe reports only status codes, counts, capability presence, envelope
shape, known field names, and pagination behavior. It never prints camera
numbers, event IDs/timestamps, text, tokens, media URLs, images, recognition
results, or raw JSON.

Production support may retain only the private cursor required for replay
suppression plus coarse event time required by Home Assistant. Raw event history,
media, recognition data, camera identifiers and cursor values must not be
exposed through entities, logs or diagnostics.
