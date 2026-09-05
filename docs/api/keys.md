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
start and asynchronous `reason=key_add` completion handling. Their wire contracts
were reconstructed from the official Android client and remain **Observed** until
an end-to-end test can be completed with a new unregistered physical key.

The empty Home Assistant inventory state has already been live-validated: the
**Physical keys** sensor reports numeric state `0` and its read-only attribute
returns `keys: []`.

## Account features

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed**

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

**Confirmed**

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
not create the enrollment button or poll passage history for an intercom that is
absent from the filtered result.

## Physical-key list

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed for the empty envelope; non-empty item fields remain Observed**

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

The provider key `id` is retained only in integration memory because it may be
needed for future rename/delete operations. It is not published in entity state,
events, or diagnostics.

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

The following empty state has been live-validated on the test Home Assistant
installation:

```yaml
state: 0
attributes:
  keys: []
```

A non-empty `keys` list still requires validation after a real new key is
registered.

## Starting physical-key enrollment

The official Android client arms server-side automatic collection with:

```http
POST /api/v4/key/skud/<skud_id>/auto_collect/enable/
Authorization: JWT <UFANET_ACCESS>
```

**Observed in the Android client; live validation pending**

After a successful response the application opens a **60-second** window during
which the new physical key must be presented to the intercom reader. A successful
HTTP response means only that enrollment mode was armed; it does not prove that a
key was presented or persisted.

Home Assistant exposes this flow through the **Add physical key** button
(`mdi:key-plus`). The button is created only for an intercom with confirmed
`has_key_recording_support` and exposes:

```yaml
enrollment_window_seconds: 60
```

The button is unavailable when the main coordinator is unhealthy or the intercom
is marked `is_blocked`. Ufanet errors are converted to Home Assistant action
errors; pressing the button is never treated as proof of successful enrollment.

## Asynchronous enrollment completion through FCM

The official Android client recognizes a push carrying:

```text
data.reason = key_add
data.key_status
data.key_id
```

**Observed in the Android client; live validation pending**

Native success semantics are:

```text
key_status == 0
AND
key_id is present and parseable as an integer
```

A missing or invalid `key_status` is treated as an error. The Home Assistant
validation branch mirrors this logic without publishing the provider `key_id`,
`title`, or `body`.

After `reason=key_add`, the integration immediately requests a key-coordinator
refresh. The same refresh reloads `/api/v4/key/list/`, so a newly enrolled key is
expected to appear together with the updated numeric sensor state.

Home Assistant fires only this privacy-minimized account-level event:

```yaml
event_type: ufanet_intercom_key_enrollment
data:
  type: key_enrollment
  source: fcm
  result: success
  received_at: "<UTC ISO-8601>"
  inventory_refresh_succeeded: true
```

The observed Android `key_add` payload does not contain `skud_id`, so the
integration deliberately does not guess a target intercom in this event. The
subsequent `/api/v4/key/list/` response associates the key with intercoms through
its `devices` field.

FCM diagnostics retain only:

```text
received_key_add_push_count
last_key_add_push_at
last_key_add_result
```

Provider `key_id`, `title`, `body`, and the raw push payload are not retained.

## Passage history

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

**Confirmed for envelope/pagination; non-empty item fields remain Observed**

Minimal request without a per-key filter:

```json
{
  "page": 0,
  "page_size": 5
}
```

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

The first successful history poll establishes a baseline and does not emit old
passages. A private cursor prevents duplicate passage delivery after Home
Assistant/integration reloads.

## Observed key-management operations

The official Android client also contains the following state-changing operations.
They are **not implemented** by the current Home Assistant runtime and must not be
considered live-confirmed.

### Rename

**Observed**

```http
POST /api/v4/key/edit/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "key_id": 1,
  "name": "<new-name>"
}
```

### Delete

**Observed**

```http
POST /api/v4/key/skud/<skud_id>/delete/key/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "key_id": 1
}
```

Deletion is destructive and must not be added to a production UI without a
separate endpoint validation, a guard against selecting the wrong intercom/key,
and an explicit user confirmation.

## Home Assistant model on the validation branch

The current validation branch includes:

- capability discovery before polling;
- **Physical keys** sensor: count plus read-only `keys` inventory;
- **Last key passage** timestamp sensor;
- passage `EventEntity`, `ufanet_intercom_key_passage` bus event and device trigger;
- a private reload-safe timestamp/internal-key cursor;
- a dedicated 60-second coordinator;
- an **Add physical key** button that arms native 60-second auto-collection;
- `reason=key_add` FCM completion handling with an immediate key-list refresh;
- the privacy-safe `ufanet_intercom_key_enrollment` event and aggregate FCM
  diagnostics.

Diagnostics exclude key names, passage timestamps, internal key IDs,
`external_id`, and full history.

## Required live validation before release

Release of this block remains gated until a real new key confirms:

1. auto-collection can be armed from the Home Assistant button;
2. the new key can be presented to the selected intercom within 60 seconds;
3. the real `reason=key_add` wire shape matches the observed Android contract;
4. the numeric **Physical keys** state updates promptly after the FCM-triggered
   refresh;
5. the new item appears in `keys` with the expected `name` and `created_at`;
6. `key_id`/`external_id` remain absent from public state/events/diagnostics;
7. `ufanet_intercom_key_enrollment` reports the correct result.

Rename, delete, and BLE keys remain outside the current release scope.