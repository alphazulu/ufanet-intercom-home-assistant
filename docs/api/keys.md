# Physical keys and passage history

[Русская версия](keys_RU.md)

This page documents the physical-key and passage-event API used by the official Android client and the Home Assistant integration.

## Status

The read-only physical-key and passage-history contracts have now been exercised against a real non-empty account. Confirmed behavior includes:

- account feature `keys`;
- `has_key_recording_support=true` for a real intercom;
- non-empty `/api/v4/key/list/` with one registered key;
- non-empty `/api/v4/key/skud/<id>/key/pass_history/` with two passages;
- live passage-item schema `key:str`, `key_name:str`, `time_passage:int`;
- filtering one key's passage history through `filters.key=<external_id>`;
- Home Assistant/Lovelace rendering one key and loading two passage timestamps when that row is selected.

The validation branch contains:

- native 60-second physical-key enrollment;
- FCM `reason=key_add` completion handling;
- read-only key inventory;
- `list_physical_keys`, `rename_physical_key`, and `get_physical_key_passages` services;
- a validation-only **KEYS / КЛЮЧИ** Lovelace tab with an experimental key-number field, rename, and selected-key passage history.

New-key enrollment, `reason=key_add`, and rename remain **Observed** until their state-changing live tests are completed. Non-empty read-only inventory and passage history are now **Confirmed**. The interpretation of `external_id` as the number printed on a physical key is **Experimental** until it is visually matched against a known key.

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

**Confirmed.** `result.intercoms` contains `id` and live-confirmed `has_key_recording_support=true`. Paging is one-based. Enrollment/key-management surfaces are not exposed for an intercom absent from this capability result.

## Physical-key list

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed on a non-empty live response.** Each key item contains:

- internal provider `id`;
- string `external_id`;
- `name`;
- `create_date`;
- `devices`.

The internal provider `id` remains implementation-only and is not published through entity state, events, diagnostics, or public service responses.

`external_id` has a confirmed runtime role: the official Android client uses it as the identifier in `filters.key` when requesting passage history for one selected key. The validation branch also exposes its **value** as an experimental user-facing field `number`. This is intentionally provisional: the project has not yet established that `external_id` equals the digits printed on the physical key. The raw wire field name `external_id` is not exposed through the public service/UI.

## Read-only inventory in Home Assistant

The **Physical keys** sensor remains numeric. Its existing `keys` attribute stays minimal:

```yaml
keys:
  - name: "Dad"
    created_at: "2025-06-27T06:03:36+00:00"
```

Rows are filtered by `devices`, sorted newest first, and contain no internal provider ID. Both the empty (`0`, `[]`) path and a non-empty live path with one real key have been validated.

## List surface used by Lovelace and management actions

The validation branch exposes:

```text
ufanet_intercom.list_physical_keys
```

It refreshes the key coordinator/inventory first and returns, for the selected intercom:

```yaml
count: 1
keys:
  - key_ref: "<24-hex-opaque-ref>"
    number: "<experimental key identifier>"
    name: "Dad"
    created_at: "<UTC ISO-8601>"
```

`number` is currently the experimental user-facing representation of the provider `external_id` value. Do not interpret it as the printed key number until that mapping is live-confirmed. The internal provider `id` is neither accepted nor returned.

`key_ref` is a local opaque reference scoped to the ConfigEntry, selected SKUD, and internal provider ID. A ref from another intercom does not resolve for the selected device.

Both the empty service path (`count: 0`, `keys: []`) and the non-empty inventory path have been exercised live. The remaining visual gate is to compare the displayed experimental `number` with the marking on a known physical key.

## Starting physical-key enrollment

The official Android client arms automatic collection with:

```http
POST /api/v4/key/skud/<skud_id>/auto_collect/enable/
Authorization: JWT <UFANET_ACCESS>
```

**Observed in the Android client; state-changing live validation pending.** A successful response opens a **60-second** window for presenting a new key. HTTP success proves only that enrollment mode was armed, not that a key was registered.

Home Assistant exposes **Add physical key** (`mdi:key-plus`) only for capability-supported intercoms and publishes `enrollment_window_seconds: 60`. The button is unavailable for a blocked/unhealthy target.

## Asynchronous enrollment completion through FCM

The Android client recognizes `reason=key_add` plus status and an internal key identifier. **Observed; live validation pending.** Native success semantics require status `0` and a parseable key identifier.

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

The observed completion payload does not carry `skud_id`, so the integration does not invent one. `/api/v4/key/list/` plus `devices` establishes actual intercom association.

FCM diagnostics retain only `received_key_add_push_count`, `last_key_add_push_at`, and `last_key_add_result`; provider identifiers, title/body, and raw push data are not retained.

## Physical-key rename

The official Android client uses:

```http
POST /api/v4/key/edit/
```

with the internal provider identifier plus the requested name. **Observed in the Android client; the state-changing endpoint is not yet live-confirmed.**

The validation branch exposes:

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
4. call the observed edit endpoint internally with the resolved internal provider ID;
5. refresh inventory again after POST;
6. report success only if the same key is observed with the requested new name;
7. skip provider POST when the normalized name is already unchanged.

The internal provider ID is never accepted or returned by the service. If POST may have changed remote state but the verification refresh fails, Home Assistant reports an indeterminate result instead of falsely claiming success.

## Lovelace KEYS tab

The validation branch automatically loads the packaged `ufanet-physical-keys-card.js` extension and adds **KEYS / КЛЮЧИ** to the existing card.

Each physical-key row now shows:

- user-facing name;
- **experimental key number** (`number`, sourced from provider `external_id` but not yet proven to match the printed marking);
- creation date;
- **Rename** action.

The internal provider ID is never rendered. Opaque `key_ref` is used only for Home Assistant service calls and is not shown to the user.

**Add key** requires confirmation, shows the 60-second countdown, and refreshes inventory afterward. **Rename** requires confirmation and reports success only after backend `verified: true`. There is no delete action.

Selecting a key row loads the **Passage history** section below the key list for that selected key.

## Per-key passage-history service

The validation branch exposes:

```text
ufanet_intercom.get_physical_key_passages
```

Public input contains only HA `device_id`, opaque `key_ref`, and page. The service refreshes inventory, resolves the selected key within the selected intercom, then internally uses its `external_id`:

```json
{
  "page": 0,
  "page_size": 25,
  "filters": {
    "key": "<private external_id>"
  }
}
```

Only normalized passage times are returned:

```yaml
page: 0
page_size: 25
total: 2
has_more: false
passages:
  - occurred_at: "<UTC ISO-8601>"
  - occurred_at: "<UTC ISO-8601>"
```

The live API confirmed that `filters.key=<external_id>` returns the two passages associated with the selected key. The frontend path was also exercised end to end: selecting the real key rendered its two passage times below the key list.

## Passage-history wire contract

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

Minimal request:

```json
{"page": 0, "page_size": 5}
```

**Confirmed on a non-empty live response.** Envelope:

```text
count: int
current_page: int
page_count: int
page_size: int
results: list
```

Live passage item:

```text
key: str
key_name: str
time_passage: int
```

Important difference from the decompiled Android DTO: the DTO declares `key` as an integer, while the real backend returns a JSON string. Gson accepts a numeric string for an integer field; Home Assistant now mirrors that coercion explicitly.

The first successful coordinator poll establishes a baseline and does not replay historical passages. A private cursor prevents duplicates after reload/restart. Public passage events do not expose provider IDs.

## Delete key

The Android client also contains a destructive delete request for a selected physical key. **Observed.** Deletion is **not implemented** in the current runtime and remains outside release scope until separately designed, guarded, and live-tested.

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
- `list_physical_keys` with `key_ref`, experimental `number`, `name`, `created_at`;
- validation-only `rename_physical_key` with fresh resolution and post-write verification;
- `get_physical_key_passages` with per-key filtering through private `external_id`;
- validation-only **KEYS** Lovelace tab with experimental number and passage history, with no delete action.

Diagnostics exclude key names, key numbers/`external_id` values, passage timestamps, internal provider IDs, and full history.

## Required live validation before release

The read-only key/history path is now live-confirmed. Release remains blocked by state-changing and safety tests, including:

1. compare the experimental **Key number** field against the marking on a known physical key and either confirm the mapping or rename/remove the field before release;
2. arm auto-collection from HA/card;
3. present a new unregistered key within 60 seconds;
4. capture the real `reason=key_add` wire shape;
5. verify prompt numeric Physical keys refresh after FCM completion;
6. verify the newly registered key appears across all read-only surfaces;
7. verify privacy-safe `ufanet_intercom_key_enrollment` result;
8. live-test `rename_physical_key` plus post-write verification;
9. inspect enrollment/rename error behavior;
10. complete the remaining notification safety gates tracked in PR #15.

Delete and BLE keys remain outside the current release scope.
