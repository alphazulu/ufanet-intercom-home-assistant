# Observed data models

[Русская версия](models_RU.md)

This page records fields that have been observed in API responses or the official client and are used/researched by the integration. It is **not** a formal vendor schema.

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

**Status: empty list envelope Confirmed; non-empty item fields Observed**

The Android model and expected non-empty `/api/v4/key/list/` item contain:

```text
id
external_id
name
create_date
devices[]
```

Observed semantics:

| Field | Meaning |
|---|---|
| `id` | internal provider key ID used by operations targeting a specific key |
| `external_id` | private access-medium identifier; never exposed by Home Assistant |
| `name` | user-visible physical-key name |
| `create_date` | key creation Unix timestamp in seconds |
| `devices[]` | SKUD/intercom references associated with the key |

The production/validation runtime discards `external_id` at the normalization
boundary. `id` is retained only in memory for potential future key-management
operations. The public sensor attribute contains only `name` and `created_at`, and
intercom association is derived from `devices`.

The following public state has been live-validated on a Home Assistant instance
with an empty provider inventory:

```yaml
state: 0
attributes:
  keys: []
```

A non-empty item is not yet live-confirmed.

## Physical-key FCM completion

**Status: Observed in the Android client**

Observed minimum completion-push data model:

```text
reason = key_add
key_status
key_id
```

The Android client treats the operation as successful only when `key_status == 0`
and a valid `key_id` is present. The observed `key_add` flow does not provide a
`skud_id`, so Home Assistant does not attach the FCM event itself to a specific
intercom and instead reloads the physical-key inventory after the push.

Provider `key_id`, notification `title`/`body`, and the raw payload are not exposed
through `ufanet_intercom_key_enrollment` or diagnostics.

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

Only add a field to this document when it was actually observed in a response or client code. Mark uncertain semantics explicitly instead of guessing. Never publish real account-specific camera/event/key identifiers, `external_id`, or raw event history as documentation samples.