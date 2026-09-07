# Physical-key passage live-schema validation note — 2026-09-07

This note records privacy-safe live evidence obtained while validating PR #15. It contains no provider key IDs, external IDs, names, passage timestamps, credentials, tokens, or raw response bodies.

## Confirmed live response shape

A supported intercom with one registered physical key returned HTTP 200 for the unfiltered passage-history request. The response envelope contained:

- `count`: integer
- `current_page`: integer
- `page_count`: integer
- `page_size`: integer
- `results`: list

The live page contained passage rows. A row contained exactly the observed fields:

- `key`: **string**
- `key_name`: string
- `time_passage`: integer

This corrects the earlier strict Home Assistant assumption that `key` would always be a JSON integer. The Android DTO declares the field as an integer, but the live API emits a numeric JSON string; the Android Gson path accepts that representation. Validation runtime mirrors this behavior by coercing only decimal numeric strings and integers, rejecting other types.

## Per-key filter reconstruction and live confirmation

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

The corrected privacy-safe probe confirmed that filtering by the private Android `external_id` returns the passage history associated with the selected registered key. The Home Assistant `get_physical_key_passages` path and KEYS-tab click-to-history flow were then exercised end to end. Subsequent history updates continued to correlate to that same physical key.

The validation runtime retains `external_id` only in private in-memory key inventory so it can reproduce the Android request. It is never returned by public services, entity attributes, events, diagnostics, or frontend code. Public selection uses only the opaque `key_ref`.

## Printed physical-key number comparison

A direct comparison against the number printed on the tested physical key showed that the printed marking does **not** match `external_id` or the other candidate identifier values from the tested key-list response. This does not weaken the selected-key correlation because the passage history for `filters.key=<external_id>` is correct and continues to update for that physical key.

Therefore the project treats `external_id` as a confirmed private backend selector, **not** as a printed physical-key number. The former Experimental public `number` candidate has been removed from the validation service/UI.

## Later state-changing validation

After this passage-schema investigation, controlled Home Assistant testing also confirmed the physical-key rename success path through `/api/v4/key/edit/`. Provider inventory read-back was observed to be eventually consistent, so the integration now uses one provider write followed by bounded read-only verification retries; that automatic verification path was live-tested successfully.

This note still does **not** confirm new-key enrollment or a real FCM `reason=key_add` completion. Those remain the active PR #15 functional release gates. Physical-key deletion is destructive, unimplemented, and outside the current release scope.
