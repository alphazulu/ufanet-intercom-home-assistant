# Physical keys and passage history

[Русская версия](keys_RU.md)

This page documents the physical-key and passage-event API used by the official Android client and the Home Assistant integration.

## Status

The read-only physical-key and passage-history contracts have been exercised against a real non-empty account. Confirmed behavior includes:

- account feature `keys`;
- `has_key_recording_support=true` for a real intercom;
- non-empty `/api/v4/key/list/` with one registered key;
- non-empty `/api/v4/key/skud/<id>/key/pass_history/` with two passages;
- live passage-item schema `key:str`, `key_name:str`, `time_passage:int`;
- filtering one key's passage history through `filters.key=<external_id>`;
- Home Assistant/Lovelace rendering one key and loading two passage timestamps when that row is selected;
- controlled rename through `/api/v4/key/edit/`, including eventual-consistent read-back and automatic post-write verification retries.

A direct physical comparison was also completed on 2026-09-07. The number printed on the tested key did **not** match the candidate identifier values returned by the key-list response. At the same time, using that key's `external_id` continued to return the correct, updating passage history. Therefore:

- `external_id` is **Confirmed** as a backend per-key identifier used for passage-history filtering;
- `external_id` is **not** the number printed on the tested physical key;
- the previously experimental public `number` field was removed from the validation branch rather than shipping a misleading interpretation.

New-key enrollment and the real `reason=key_add` completion remain **Observed** until their state-changing live tests are completed. Physical-key rename is now **Confirmed** for the tested success path.

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

Both provider `id` and `external_id` remain implementation-only. The live comparison showed that the printed physical-key number is not represented by the tested identifier values returned by this response.

`external_id` still has an important confirmed runtime role: the official Android client uses it as the identifier in `filters.key` when requesting passage history for one selected key, and live testing confirmed that the resulting history belongs to the expected physical key and updates correctly.

## Read-only inventory in Home Assistant

The **Physical keys** sensor remains numeric. Its `keys` attribute stays minimal:

```yaml
keys:
  - name: "Dad"
    created_at: "2025-06-27T06:03:36+00:00"
```

Rows are filtered by `devices`, sorted newest first, and contain no provider identifiers. Both the empty (`0`, `[]`) path and a non-empty live path with one real key have been validated.

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
    name: "Dad"
    created_at: "<UTC ISO-8601>"
```

No provider `id`, `external_id`, or guessed physical-key number is returned.

`key_ref` is a local opaque reference scoped to the ConfigEntry, selected SKUD, and internal provider ID. A ref from another intercom does not resolve for the selected device.

Both the empty service path (`count: 0`, `keys: []`) and the non-empty inventory path have been exercised live.

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

with the internal provider identifier plus the requested name. **Confirmed for the tested success path.** A controlled Home Assistant live test verified that the selected physical key's name actually changes on the provider side.

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

Safety and verification flow:

1. refresh inventory before mutation;
2. resolve `key_ref` only within the selected intercom;
3. reject blank names/control characters and apply a conservative local 128-character bound (not a claimed provider limit);
4. send the provider edit request exactly once with the resolved internal provider ID;
5. perform bounded read-only inventory refresh retries after the POST because provider read-back is eventually consistent;
6. report success only when the same key is observed with the requested new name;
7. skip the provider POST when the normalized name is already unchanged.

Live testing showed that the first immediate read-back can still contain the previous name while a later refresh returns the new name. The automatic retry-based verification path was then exercised successfully without requiring a manual refresh. The implementation never retries the state-changing POST automatically.

The internal provider ID is never accepted or returned by the service. If the POST may have changed remote state but verification cannot be completed within the bounded read-only retries, Home Assistant reports an indeterminate result instead of falsely claiming success. Provider-specific failure semantics for invalid/stale IDs, duplicate names, or server-side length limits are still not claimed without direct evidence.

## Lovelace KEYS tab

The validation branch automatically loads the packaged physical-key extensions and adds **KEYS / КЛЮЧИ** to the existing card.

Each physical-key row shows only:

- user-facing name;
- creation date;
- **Rename** action.

Provider IDs and the disproven physical-key-number candidate are not rendered. Opaque `key_ref` is used only for Home Assistant service calls and is not shown to the user.

**Add key** requires confirmation, shows the 60-second countdown, and refreshes inventory afterward. **Rename** requires confirmation and reports success only after backend `verified: true`. There is no delete action.

Selecting a key row loads the **Passage history** section below the key list for that selected key.

The non-empty list, selected-key passage history, backend-verified rename, repeated dashboard switching, normal reloads, and hard refreshes have all been live-tested on the validation branch without reproducing the former Lovelace **Configuration error**.

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

The live API confirmed that `filters.key=<external_id>` returns the passages associated with the selected physical key. The frontend path was also exercised end to end: selecting the real key rendered its passage times below the key list, and subsequent history updates continued to correlate to that same key.

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

Important difference from the decompiled Android DTO: the DTO declares `key` as an integer, while the real backend returns a JSON string. Gson accepts a numeric string for an integer field; Home Assistant mirrors that coercion explicitly.

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
- `list_physical_keys` with only `key_ref`, `name`, `created_at`;
- live-confirmed `rename_physical_key` with fresh resolution, one provider write and bounded post-write read-only verification;
- `get_physical_key_passages` with per-key filtering through private `external_id`;
- validation-branch **KEYS** Lovelace tab with selected-key passage history, live-confirmed rename and no delete action.

Diagnostics exclude key names, provider identifiers, passage timestamps, and full history.

## Required live validation before release

The read-only key/history path, negative printed-number comparison, physical-key rename success path, notification block, and Lovelace resource-load regression are resolved. The Android notification block has no remaining hard release gate; the unavailable second-Ufanet-device live test was explicitly waived after targeted security review without waiving the cross-device safety invariant.

The remaining hard functional release gates are exclusively the new physical-key enrollment path:

1. arm auto-collection from HA/card and verify the provider really enables enrollment mode;
2. present a new unregistered key within 60 seconds;
3. capture the real `reason=key_add` wire shape using sanitized schema/status evidence only;
4. verify the new key is actually registered and the numeric **Physical keys** sensor refreshes promptly after the FCM-triggered inventory update;
5. verify the new key appears across the privacy-safe read-only surfaces without provider identifiers;
6. verify the privacy-safe `ufanet_intercom_key_enrollment` success/error result;
7. inspect real enrollment error behavior, including any observed HTTP 400/status semantics.

Delete and BLE keys remain outside the current release scope. iOS notification actions remain not live-tested and are not claimed as Confirmed.
