# Physical-key passage live-schema validation note — 2026-09-07

This note records privacy-safe live evidence obtained while validating PR #15. It contains no provider key IDs, external IDs, names, passage timestamps, credentials, tokens, or raw response bodies.

## Confirmed live response shape

A supported intercom with one registered physical key returned HTTP 200 for the unfiltered passage-history request. The response envelope contained:

- `count`: integer
- `current_page`: integer
- `page_count`: integer
- `page_size`: integer
- `results`: list

The live page contained two passage rows. A row contained exactly the observed fields:

- `key`: **string**
- `key_name`: string
- `time_passage`: integer

This corrects the earlier strict Home Assistant assumption that `key` would always be a JSON integer. The Android DTO declares the field as an integer, but the live API emits a numeric JSON string; the Android Gson path accepts that representation. Validation runtime now mirrors this behavior by coercing only decimal numeric strings and integers, rejecting other types.

## Per-key filter reconstruction

Re-inspection of the official Android client showed that passage-history filtering is built from `SkudKey.getExternalID()` and sent as:

```json
{
  "page": 0,
  "page_size": 25,
  "filters": {
    "key": "<private external_id>"
  }
}
```

The first schema-probe version incorrectly filtered using the internal key `id`; its live filtered response was therefore empty and is not evidence that the provider filter is broken.

The validation runtime now retains `external_id` only in private in-memory key inventory so it can reproduce the Android request. It is never returned by public services, entity attributes, events, diagnostics, or frontend code. Public selection continues to use the opaque `key_ref`.

## Remaining live gate

The updated privacy-safe schema probe must be rerun to confirm that filtering by the private Android `external_id` returns the expected passage row(s). After that, the Home Assistant `get_physical_key_passages` service and the KEYS-tab click-to-history flow must be live-tested.

This note does not confirm enrollment, FCM `key_add`, rename, or delete behavior.
