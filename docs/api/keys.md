# Physical keys and passage history

[Русская версия](keys_RU.md)

This page documents the read-only physical-key and passage-event API used by the
official Android client and the Home Assistant integration.

## Status

The four read-only request forms below were exercised successfully against a real
account. The account advertised `keys`, one intercom reported
key-recording support, and both the key list and passage history returned valid
empty collections with HTTP 200. The empty-response envelopes and pagination are
therefore **Confirmed**; the fields of a non-empty key or passage item remain
**Observed** from the Android client until a real item is captured. The probe does
not create, rename, or delete keys.

## Account features

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

Confirmed response shape:

```json
{
  "status": "ok",
  "data": {
    "features": ["keys"]
  }
}
```

The live response included `keys`. The client also recognizes `share_access`,
`temporary_access`, `frsi`, and `ble`.

## Per-intercom capability

```http
POST /api/v0/intercoms/
Authorization: JWT <UFANET_ACCESS>
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

Entries in `result.intercoms` carry an `id` and the Boolean
`has_key_recording_support` capability. Both the request and a `true` capability
were live-confirmed. Paging is one-based for this endpoint. The integration does
not poll passage history for an intercom that is absent from the filtered result.

## Physical-key list

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

Confirmed empty envelope; non-empty item shape remains Observed:

```json
{
  "data": {
    "keys": [
      {
        "id": 1,
        "external_id": "<redacted>",
        "name": "<redacted>",
        "create_date": 1700000000,
        "devices": ["<redacted-skud-id>"]
      }
    ]
  }
}
```

`external_id` is treated as a private access identifier. It must not enter Home
Assistant logs, diagnostics, entity states, or events.

## Passage history

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

Minimal request without a per-key filter:

```json
{
  "page": 0,
  "page_size": 5
}
```

Confirmed envelope and pagination; non-empty item shape remains Observed:

```json
{
  "count": 1,
  "current_page": 0,
  "page_count": 1,
  "page_size": 5,
  "results": [
    {
      "key": 1,
      "key_name": "<redacted>",
      "time_passage": 1700000000
    }
  ]
}
```

The Android client interprets `time_passage` as Unix seconds. Paging starts at
page `0`; the client normally requests 25 items.

## Home Assistant model

Version 0.27.0 implements the feature as read-only:

- capability discovery before polling;
- **Physical key count** sensor;
- **Last key passage** timestamp sensor;
- passage `EventEntity`, `ufanet_intercom_key_passage` bus event and device trigger;
- a private reload-safe timestamp/internal-key cursor;
- a dedicated 60-second coordinator.

The first successful poll is a baseline and does not emit historical events. Key
names are present only in an actual transient event. Diagnostics exclude names,
timestamps, internal key IDs, `external_id`, and full history.

Key rename/delete, automatic collection, and BLE keys are outside the first phase.
