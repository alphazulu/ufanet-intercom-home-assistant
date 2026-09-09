# Observed data models

[Русская версия](models_RU.md)

This page records fields that have been observed and are used by the integration. It is **not** a formal vendor schema.

## SKUD/intercom object

**Status: Observed / partially Confirmed**

Relevant fields:

| Field | Observed meaning |
|---|---|
| `id` | SKUD/intercom identifier |
| `role` | device role, e.g. `Домофон` |
| `model` | numeric model identifier |
| `camera` | may be `null` on the tested device |
| `cctv_number` | UCAMS camera identifier used by the integration |
| `open_in_talk` | observed opening mode, e.g. `http` |
| `open_type` | observed opening mode, e.g. `http` |
| `relays` | relay metadata; empty on the tested device |
| `private_status` | numeric status; semantics not fully characterized |
| `scope` | access scope, e.g. `owner` |
| address/custom-name fields | human-readable location/name; exact field set may vary |

Do not hard-code `model == 39` or assume `camera == null` for all devices.

## Physical key

**Status: non-empty live model Confirmed**

A live non-empty `/api/v4/key/list/` response confirmed these item fields:

```text
id
external_id
name
create_date
devices
```

Confirmed runtime roles:

- `id` — internal provider key identifier; required only for private runtime mutation verification and never exposed through public key-management surfaces;
- `external_id` — string per-key identifier used by the official Android client for `filters.key` when requesting one selected key's passage history;
- `name` — user-facing key name;
- `create_date` — key creation/registration timestamp;
- `devices` — relationship used to associate the account-level key with a specific intercom.

A direct live comparison on 2026-09-07 showed that the number printed on the tested physical key did **not** match the candidate identifier values returned by the key-list response. At the same time, `filters.key=<external_id>` continued to return the correct updating history for that physical key. Therefore `external_id` is a confirmed backend selector, not a printed-key-number field for the tested key.

The sensor `keys` attribute intentionally remains minimal and contains only `name` and normalized UTC `created_at`.

Validation management surfaces expose a local opaque `key_ref` rather than any provider identifier. `list_physical_keys` returns only `key_ref`, `name`, and `created_at`; the previously experimental public `number` field was removed after the live comparison disproved that interpretation.

Both provider `id` and `external_id` remain private runtime data. They are excluded from diagnostics, logs, events, public support bundles and repository examples.

## Physical-key passage item

**Status: Confirmed**

A live non-empty `/api/v4/key/skud/<id>/key/pass_history/` response confirmed:

```text
key: str
key_name: str
time_passage: int
```

The live backend returns `key` as a numeric JSON string even though the decompiled Android DTO models it as an integer. Gson accepts that numeric-string representation; Home Assistant mirrors the coercion explicitly.

For selected-key history, the official Android flow uses:

```text
filters.key = <physical-key external_id>
```

This filtering contract was live-confirmed with a real registered key and its updating passage history.

## UCAMS camera metadata

**Status: Observed; `motion_alarm` capability Confirmed on the live-tested camera**

Fields requested by the broader camera/media flow include:

```text
number
token_l
token_r
is_llhls_enabled
permission
address
title
timezone
is_fav
is_public
inactivity_period
server
analytics
tariff
is_sounding
streams_count
```

`analytics` is a capability list. `motion_alarm` was returned by the live-tested camera and is Confirmed; `perimeter_security` is known from the Android client but was not advertised by the tested tariff and remains Observed.

Production v0.28.0 analytics discovery requests only `number` and `analytics`. Observed nested server/tariff data in the broader media request can include media-server domain/vendor, screenshot domain and archive depth (`dvr_hours`). Exact nesting should be treated as implementation detail until broader samples are collected.

## UCAMS `motion_alarm` report

**Status: Confirmed**

The confirmed response is an object with this structural model:

```text
count
page
  current
  next
  previous
  all
  page_size
results[]
  id
  date
  length
```

Confirmed result semantics:

| Field | Meaning |
|---|---|
| `id` | opaque numeric provider event identifier; private cursor/deduplication only |
| `date` | authoritative ISO-8601 UTC event timestamp |
| `length` | event length reported by UCAMS |

The Android DTO field `time` is not used as the live wire timestamp; `date` is authoritative. The server may return a `page_size` larger than the requested `limit`; the live test returned 60 despite a smaller requested value.

This is a **private wire model**, not the Home Assistant event schema. Production immediately discards unrelated/unknown result fields, stores cursor identifiers only in private Home Assistant storage, and exposes only coarse `occurred_at` through the Motion detected EventEntity. See [analytics.md](analytics.md).

## Archive range

**Status: Confirmed**

```json
{
  "from": 1700000000,
  "duration": 3600
}
```

- `from`: Unix timestamp in seconds.
- `duration`: seconds.

## Call history item

**Status: Observed / Confirmed for fields used**

Relevant fields:

```text
uuid
called_at
timezone
camera_number
address
porch
flat
```

`called_at` is offset-aware and must be treated as the authoritative instant.

## Nullability and optional fields

Private API responses may differ across accounts, cities, tariffs, firmware and intercom models. Code should:

- tolerate absent optional fields;
- tolerate explicit `null`;
- avoid assuming all enum values are already known;
- validate confirmed fields before use;
- discard or redact unknown/private fields instead of exposing raw responses through public diagnostics.

## Schema contribution rule

Only add a field to this document when it was actually observed in a response or client code. Mark uncertain semantics explicitly instead of guessing. Never publish real provider key IDs or `external_id` values, raw account-specific camera/event identifiers, or event history as documentation samples.
