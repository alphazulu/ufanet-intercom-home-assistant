# Physical keys and passage history

[Русская версия](keys_RU.md)

This page documents the read-only physical-key and passage-event API observed in
the official Android client.

## Status

Every contract below is currently **Observed**: the HTTP methods, paths, request
bodies and DTOs are present in client code, but have not yet been exercised against
a real account. `tools/research/key_passage_probe_py/probe.py` performs the live
check without mutating keys.

## Account features

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

Observed response shape:

```json
{
  "status": "ok",
  "data": {
    "features": ["keys"]
  }
}
```

The client recognizes `share_access`, `temporary_access`, `keys`, `frsi`, and
`ble`.

## Per-intercom capability

```http
POST /api/v0/intercoms/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "page": 0,
  "page_size": 100,
  "filters": {}
}
```

Entries in `result.intercoms` carry an `id` and the Boolean
`has_key_recording_support` capability. The integration should not poll passage
history for an intercom that explicitly reports `false`.

## Physical-key list

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

Observed shape:

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

Observed response model:

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

## Planned Home Assistant model

After live confirmation, the first implementation remains read-only:

- capability discovery before enabling polling;
- physical-key count sensor;
- latest-passage timestamp sensor;
- passage `EventEntity` for automations;
- reload-safe event deduplication;
- a dedicated coordinator with a bounded polling interval.

Key rename/delete, automatic collection, and BLE keys are outside the first phase.
