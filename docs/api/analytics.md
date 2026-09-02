# UCAMS camera analytics

[Русская версия](analytics_RU.md)

This page records read-only camera analytics contracts observed in the official
Android client. They are not enabled in the Home Assistant runtime until a live
account confirms the request and response behavior.

## Camera capability metadata

**Status: Observed; camera metadata endpoint itself is Confirmed**

The existing `POST /api/v0/cameras/this/` request can include the `analytics`
field. The Android client treats it as a list of analytics type strings.

The research probe requests only:

```json
{
  "fields": ["number", "analytics", "tariff", "timezone"],
  "numbers": ["<CAMERA_NUMBER>"]
}
```

No live, archive, or screenshot token is requested for capability discovery.

## Type-filtered archive events

**Status: Observed**

The Android client reads one analytics type with:

```http
POST https://cloud.ucams.ru/api/v0/analytics/<type>/report/
Authorization: Bearer <UCAMS_TOKEN>
Content-Type: application/json
```

Observed request fields:

```json
{
  "camera_number": "<CAMERA_NUMBER>",
  "start": "<ISO-8601>",
  "end": "<ISO-8601>",
  "limit": 5,
  "order_by_date": "desc"
}
```

The first probe stage is deliberately limited to `motion_alarm` and
`perimeter_security`. Face recognition, license plates, thermal data, crowd
analysis, helmet detection, screenshots, free text, and media URLs are outside
the integration scope.

Observed event model field names include `id`, `time`, `type`, `camera_number`,
`duration`, `full_screenshot_url`, `protocol`, `text`, and motion-specific
`length`. Their live presence and exact envelope remain unconfirmed.

## Privacy boundary

The probe reports only status codes, counts, the presence of safe capability
types, envelope shape, and known field names. It never prints camera numbers,
event IDs/timestamps, text, tokens, media URLs, images, or recognition results.

Production support must retain only a private replay cursor plus the coarse
event type/time required by Home Assistant. It must not expose or diagnose raw
event history or media/recognition content.
