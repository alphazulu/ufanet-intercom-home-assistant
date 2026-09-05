# Physical keys and passage history

[Русская версия](keys_RU.md)

This page documents the physical-key and passage-event API used by the official
Android client and the Home Assistant integration.

## Status

The read-only request forms were exercised successfully against a real account.
The account advertised `keys`, one intercom reported key-recording support, and
both the key list and passage history returned valid empty collections with HTTP
200. The empty-response envelopes and pagination are therefore **Confirmed**;
fields of a non-empty key or passage item remain **Observed** from the Android
client until a real new key is captured.

The validation branch also contains the native 60-second physical-key enrollment
start and asynchronous `reason=key_add` completion handling. Those paths are not
considered live-confirmed until a new physical key can be tested end to end.

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

`external_id` is treated as a private access identifier and is discarded at the
response-normalization boundary. It is not retained in the runtime inventory and
must not enter Home Assistant logs, diagnostics, entity states, or events.

The provider key `id` is retained only in integration memory because future
rename/delete operations require it. It is not published in entity state or
diagnostics.

## Read-only inventory in Home Assistant

The **Physical keys** sensor keeps its numeric state: the number of keys linked to
the specific intercom. On the validation branch, the same sensor also has a
read-only `keys` attribute:

```yaml
state: 2
attributes:
  keys:
    - name: "Dad"
      created_at: "2025-06-27T06:03:36+00:00"
    - name: "Spare"
      created_at: "2025-06-20T10:11:12+00:00"
```

Each visible item contains only:

- `name` — the Ufanet key name;
- `created_at` — `create_date` converted to an ISO UTC timestamp.

The list is filtered by `devices`, so one intercom does not expose keys associated
only with another intercom. Items are sorted newest first. Provider `key_id` and
`external_id` are not exposed through the `keys` attribute.

After a `reason=key_add` push, the FCM handler immediately requests a refresh of
the key coordinator. That same refresh reloads `/api/v4/key/list/`, so a newly
registered key is expected to appear together with the updated numeric sensor
state. This still requires live validation with a new unregistered key.

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

The current validation branch includes:

- capability discovery before polling;
- **Physical keys** sensor: count plus read-only `keys` inventory;
- **Last key passage** timestamp sensor;
- passage `EventEntity`, `ufanet_intercom_key_passage` bus event and device trigger;
- a private reload-safe timestamp/internal-key cursor;
- a dedicated 60-second coordinator;
- an **Add physical key** button that arms native 60-second auto-collection;
- `reason=key_add` FCM completion handling with an immediate key-list refresh.

The first successful history poll is a baseline and does not emit historical
events. Diagnostics exclude key names, passage timestamps, internal key IDs,
`external_id`, and full history.

Key rename/delete is not implemented yet. BLE keys are also outside the current
phase. Release of this block remains gated on a real physical-key registration and
validation of the non-empty API response.