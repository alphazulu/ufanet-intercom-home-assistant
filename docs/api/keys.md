# Physical keys and passage history

[Русская версия](keys_RU.md)

This page documents the physical-key and passage-event API used by the official Android client and the Home Assistant integration.

## Status

The read-only request forms were exercised successfully against a real account. The account advertised `keys`, one intercom reported key-recording support, and both the key list and passage history returned valid empty collections with HTTP 200. Empty-response envelopes and pagination are therefore **Confirmed**; fields of a non-empty key or passage item remain **Observed** from the Android client until a real new key is captured.

The validation branch now contains:

- native 60-second physical-key enrollment;
- FCM `reason=key_add` completion handling;
- read-only key inventory;
- privacy-safe `list_physical_keys` and `rename_physical_key` services;
- a validation-only Lovelace **KEYS** tab built on those Home Assistant surfaces.

Enrollment, `key_add`, non-empty key-item, and rename wire contracts remain **Observed** until a real unregistered key is tested end to end. The empty Home Assistant paths are live-confirmed: **Physical keys** reports numeric `0` and `keys: []`, and `ufanet_intercom.list_physical_keys` returned `count: 0`, `keys: []`.

## Account features

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed.** The live response included the account feature `keys`.

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
  "filters": {"has_key_recording_support": true}
}
```

**Confirmed.** `result.intercoms` contains `id` and the live-confirmed `has_key_recording_support=true`. Paging is one-based. Enrollment/key-management surfaces are not exposed for an intercom absent from this capability result.

## Physical-key list

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed for the empty envelope; non-empty item fields remain Observed.** Android-observed item shape:

```json
{
  "id": 1,
  "external_id": "<redacted>",
  "name": "<redacted>",
  "create_date": 1700000000,
  "devices": ["<redacted-skud-id>"]
}
```

`external_id` is treated as a private access identifier and discarded at response normalization. Provider `id` is retained only in private runtime memory because operations on one key require it. Neither value is published through entity state, events, diagnostics, or public service responses.

## Read-only inventory in Home Assistant

The **Physical keys** sensor remains numeric. Its `keys` attribute contains only:

```yaml
keys:
  - name: "Dad"
    created_at: "2025-06-27T06:03:36+00:00"
```

Rows are filtered by `devices`, sorted newest first, and contain no provider IDs. The live-tested empty state is:

```yaml
state: 0
attributes:
  keys: []
```

A non-empty inventory still requires a real key.

## Privacy-safe list for key-management operations

The validation branch also exposes the response service:

```text
ufanet_intercom.list_physical_keys
```

It first refreshes the key coordinator/inventory and returns, for the selected intercom, only:

```yaml
count: 1
keys:
  - key_ref: "<24-hex-opaque-ref>"
    name: "Dad"
    created_at: "<UTC ISO-8601>"
```

`key_ref` is a local opaque reference scoped to the ConfigEntry, selected SKUD, and internal provider key ID. Raw `key_id` is neither accepted nor returned, and a reference from another intercom does not resolve for the selected device.

The empty service response is live-confirmed (`count: 0`, `keys: []`). A non-empty response remains pending live validation.

## Starting physical-key enrollment

The official Android client arms automatic collection with:

```http
POST /api/v4/key/skud/<skud_id>/auto_collect/enable/
Authorization: JWT <UFANET_ACCESS>
```

**Observed in the Android client; live validation pending.** A successful response opens a **60-second** window for presenting a new key. HTTP success proves only that enrollment mode was armed.

Home Assistant exposes **Add physical key** (`mdi:key-plus`) only for capability-supported intercoms and publishes `enrollment_window_seconds: 60`. The button is unavailable for a blocked/unhealthy target.

## Asynchronous enrollment completion through FCM

The Android client recognizes:

```text
data.reason = key_add
data.key_status
data.key_id
```

**Observed; live validation pending.** Native success semantics require `key_status == 0` and a parseable integer `key_id`.

The validation runtime refreshes the key coordinator immediately and fires only the privacy-minimized account-level event:

```yaml
event_type: ufanet_intercom_key_enrollment
data:
  type: key_enrollment
  source: fcm
  result: success
  received_at: "<UTC ISO-8601>"
  inventory_refresh_succeeded: true
```

The observed `key_add` payload does not carry `skud_id`, so the integration does not invent one. `/api/v4/key/list/` plus `devices` establishes actual intercom association.

FCM diagnostics retain only `received_key_add_push_count`, `last_key_add_push_at`, and `last_key_add_result`; provider key ID, title/body, and raw push data are not retained.

## Physical-key rename

The official Android client uses:

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

**Observed in the Android client; the real endpoint is not live-confirmed yet.**

The validation branch implements this through:

```text
ufanet_intercom.rename_physical_key
```

Public input:

```yaml
device_id: <HA device id>
key_ref: <opaque ref from list_physical_keys>
new_name: "New name"
```

Safety flow:

1. refresh inventory before mutation;
2. resolve `key_ref` only within the selected intercom;
3. reject blank names/control characters and apply a conservative local 128-character bound (not a claimed provider limit);
4. call `/api/v4/key/edit/` internally with the resolved provider key ID;
5. refresh inventory again after POST;
6. report success only if the same key is observed with the requested new name;
7. skip provider POST when the normalized name is already unchanged.

Provider key ID is never accepted or returned by the service. If the POST may have changed remote state but the verification refresh fails, Home Assistant reports an indeterminate result instead of falsely claiming success.

Until a real key exists, this path is **validation-only** and the endpoint remains **Observed**.

## Lovelace KEYS tab

The validation branch automatically loads the packaged `ufanet-physical-keys-card.js` extension. It waits for `custom:ufanet-intercom-card` and adds **KEYS / КЛЮЧИ** without changing the main card source.

The browser workflow uses only `list_physical_keys`, `rename_physical_key`, and the same-device Home Assistant enrollment button. Rows render only the key name and created time; the opaque `key_ref` is passed back to Home Assistant but is not shown to the user. **Add key** requires confirmation, shows the 60-second countdown, and refreshes the list afterward. **Rename** requires confirmation and reports success only after the backend returns `verified: true`. No delete action exists.

Provider key IDs and `external_id` are not referenced by the extension. Its zero-key layout and actual integration with the development dashboard remain a live visual gate before release.

## Delete key

The Android client also contains:

```http
POST /api/v4/key/skud/<skud_id>/delete/key/
Content-Type: application/json

{"key_id": 1}
```

**Observed.** Deletion is destructive and is **not implemented** in the current runtime. It remains outside release scope until separately designed, guarded, and live-tested.

## Passage history

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

Minimal request:

```json
{"page": 0, "page_size": 5}
```

**Confirmed for envelope/pagination; non-empty item fields remain Observed.** Android-observed results contain `key`, `key_name`, and `time_passage`; `time_passage` is interpreted as Unix seconds. Paging starts at `0`; the Android client normally requests 25 rows.

The first successful poll establishes a baseline and does not replay historical passages. A private cursor prevents duplicates after reload/restart. Public passage events do not expose provider IDs.

## Home Assistant model on the validation branch

Current validation functionality includes:

- capability discovery;
- **Physical keys** count + read-only `keys`;
- **Last key passage**;
- passage EventEntity / `ufanet_intercom_key_passage` / device trigger;
- 60-second key coordinator;
- **Add physical key**;
- FCM `key_add` + immediate inventory refresh;
- `ufanet_intercom_key_enrollment`;
- `list_physical_keys` with opaque `key_ref`;
- validation-only `rename_physical_key` with fresh resolution and post-write verification;
- validation-only **KEYS** Lovelace tab with no delete action.

Diagnostics exclude key names, passage timestamps, provider key IDs, `external_id`, and full history.

## Required live validation before release

Release remains blocked until these are confirmed:

1. the **KEYS** tab loads in the existing Lovelace card and shows the correct zero-key empty state without errors;
2. HA/card can arm auto-collection;
3. the new key can be presented within 60 seconds;
4. the real `reason=key_add` wire shape;
5. prompt numeric Physical keys update;
6. non-empty `keys` with expected `name`/`created_at`;
7. no provider `key_id`/`external_id` on public surfaces;
8. correct `ufanet_intercom_key_enrollment` result;
9. `list_physical_keys` returns an opaque `key_ref` without provider IDs;
10. `rename_physical_key` really changes the name through `/api/v4/key/edit/`, the post-write refresh confirms it, and the **KEYS** tab renders the updated value.

Delete and BLE keys remain outside the current release scope.
