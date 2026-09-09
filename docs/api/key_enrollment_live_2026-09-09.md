# Physical-key enrollment live evidence — 2026-09-09

> Validation evidence only. Account-specific identifiers, provider key IDs, raw FCM payloads, credentials, and private location data are intentionally omitted.

## Scope

This document records the first end-to-end live validation of the physical-key enrollment path implemented for v0.31.0 before publication.

## Successful enrollment

A genuinely unregistered physical key was enrolled through the Home Assistant **Add physical key** flow.

Observed sequence:

1. Home Assistant invoked the Android-observed enrollment endpoint:
   `POST /api/v4/key/skud/<id>/auto_collect/enable/`.
2. The intercom entered the expected 60-second enrollment window.
3. A previously unregistered physical key was presented to the reader and was successfully added.
4. The active headless FCM listener received real `reason=key_add` completion pushes.
5. Diagnostics after the live test showed:
   - `received_push_count = 2`;
   - `received_key_add_push_count = 2`;
   - `last_key_add_result = success`;
   - FCM transport active and listener running;
   - fallback polling inactive;
   - physical-key coordinator healthy;
   - registered-key inventory present after enrollment.
6. Runtime success classification therefore matched the Android-observed contract used by the integration: `key_status == 0` with a parseable `key_id`.

The integration intentionally does not retain or publish the provider `key_id`, raw push body, notification title/body, or other private provider identifiers.

## Timeout / no-key behavior

A separate live test armed the same 60-second enrollment window and deliberately presented no key.

After the full window elapsed:

- no additional `reason=key_add` completion push was received;
- `received_key_add_push_count` remained unchanged;
- `last_key_add_result` remained the prior successful result;
- no separate FCM error completion was observed.

Therefore the tested timeout behavior is:

```text
arm enrollment
→ wait 60 seconds without presenting a key
→ enrollment window expires
→ no key_add completion push observed
```

No HTTP 400, `key_status != 0`, or other provider error payload was observed in this timeout case, so the project does not claim such semantics.

## Evidence disposition

The following are now live-confirmed for the tested account/intercom:

- `POST /api/v4/key/skud/<id>/auto_collect/enable/` actually arms physical-key enrollment;
- the 60-second enrollment window is operational;
- a genuinely unregistered key can be registered through this flow;
- real `reason=key_add` completion is delivered through the headless FCM listener;
- the integration's success classification matches the real successful completion;
- Home Assistant's physical-key inventory is healthy and contains the registered key after enrollment;
- a no-key timeout produces no observed completion push.

The absence of an error push during timeout is itself the live result; unobserved provider error semantics remain undocumented rather than inferred.
