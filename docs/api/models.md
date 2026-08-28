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

## UCAMS camera metadata

**Status: Observed**

Fields requested by this project include:

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

Observed nested server/tariff data can include media-server domain/vendor, screenshot domain and archive depth (`dvr_hours`). Exact nesting should be treated as implementation detail until broader samples are collected.

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
- preserve unknown fields when useful for diagnostics, while redacting sensitive values.

## Schema contribution rule

Only add a field to this document when it was actually observed in a response or client code. Mark uncertain semantics explicitly instead of guessing.