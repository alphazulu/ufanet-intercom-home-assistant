# Cross-device notification security review — 2026-09-07

## Scope

This review covers the remaining notification release gate in PR #15:

> A door button from another Ufanet device must never be exposed or executed by the incoming-call Companion notification workflow.

The review is specifically about **cross-device relay selection/execution after a call has been associated with a Home Assistant Ufanet device**. It does not claim a live multi-device test, does not claim iOS live validation, and does not change the trust model for a Home Assistant administrator who can intentionally edit automations/entity-registry state.

## Reviewed code paths

The review covered:

- `custom_components/ufanet_intercom/device_trigger.py`;
- `custom_components/ufanet_intercom/__init__.py` call-event publication;
- `custom_components/ufanet_intercom/entity.py` device identity;
- `custom_components/ufanet_intercom/button.py` open-door entity binding/press behavior;
- `blueprints/automation/ufanet_intercom/incoming_call_notification.yaml`;
- `tests/test_device_trigger.py`;
- `tests/test_blueprint.py`;
- `tests/test_event.py`.

## Security invariants found

### 1. The incoming-call trigger is device-scoped

`device_trigger.async_attach_trigger()` subscribes to `ufanet_intercom_call` with an exact `event_data.device_id` match taken from the selected Home Assistant device.

A call event carrying another device ID does not trigger the automation. This is covered by `test_incoming_call_trigger_filters_device_and_preserves_event`.

If an event has no matching `device_id`, this device trigger does not match it.

### 2. Ufanet entities are bound to one Home Assistant device through SKUD identity

`device_info(skud)` registers the device identifier as `(DOMAIN, skud_id)`.

`UfanetOpenDoorButton` uses the same `device_info(skud)`, stores its own `skud_id`, and `async_press()` opens only that button entity's own `(skud_id, door)` pair.

Therefore the notification blueprint never sends a provider SKUD/door identifier supplied by the phone; it can only invoke the already-registered Home Assistant button entity.

### 3. The blueprint selector is narrowed to Ufanet button entities

The `open_door_button` input selector filters to:

- domain `button`;
- integration `ufanet_intercom`.

This prevents normal UI configuration from offering unrelated button entities.

The selector is only the first layer; the runtime checks below remain authoritative even if configuration is edited manually.

### 4. Cross-device membership is checked before the action is exposed

`can_open_door` is true only when all of the following hold:

- this is a real triggered call, not a manual run;
- a `button.*` entity was configured;
- that exact entity is present in `device_entities(intercom_device_id)`.

If a Ufanet door button belongs to another Home Assistant device, the **Open door** notification action is not included.

### 5. Membership is revalidated immediately before `button.press`

The same `button.*` plus `device_entities(intercom_device_id)` membership test is repeated immediately before physical execution.

This revalidation exists in both action paths:

- when the user taps before an image update;
- when the notification image has already been refreshed and the user taps afterward.

If the entity no longer belongs to the selected device, the blueprint sends a notification that the action is no longer available and stops without calling `button.press`.

This makes stale/moved entity configuration fail closed at execution time.

### 6. Old-call actions are isolated from new calls

Each real call gets a unique action ID based on the Home Assistant event context. The blueprint uses `mode: restart`, so a newer call cancels the previous wait/listener. The old action ID is not accepted by the new run.

This was additionally live-confirmed with two sequential real calls.

### 7. Manual runs cannot create a physical door path

A manual blueprint run has no real event trigger. `can_open_door` is false, the notification is marked as a manual test, and no **Open door** action is rendered.

### 8. Door actions expire and are removed after use

The door action has a bounded timeout. After timeout or successful command dispatch, the same notification is replaced without the door action.

Both timeout replacement and post-open replacement were live-confirmed on Android.

## Existing automated evidence

The current test suite covers the relevant structure and routing:

- another `device_id` does not fire the selected incoming-call device trigger;
- the blueprint trigger is a Ufanet `incoming_call` device trigger;
- the blueprint requires same-device membership for the selected door button;
- the same membership test appears again immediately before the press path;
- unique per-run action IDs are used;
- `mode: restart` invalidates the old listener;
- manual runs do not expose the door action.

The exact branch head used for this review must still pass the repository's normal **Tests**, **HACS and Hassfest validation**, and **Release self-check** before release-candidate promotion.

## Live evidence already available

Although no second Ufanet device is available for a true cross-device live test, the following surrounding behavior has been live-confirmed on Android:

- real-call notification delivery;
- selected Ufanet door button physically opens the configured door;
- post-open notification replacement removes the door action;
- action timeout removes the stale door action;
- a second real call supersedes the first pending action/listener;
- real-call device/location/time metadata is correct.

## Residual risk / limits of this waiver

The only missing evidence for this gate is a **real second Ufanet device** used to demonstrate the negative path end to end.

This waiver does **not** claim that test happened. It records that the negative path is enforced by independent Home Assistant device-ID filtering, same-device entity membership at notification construction, and a second membership check immediately before physical execution.

The review assumes the normal trusted-Home-Assistant-administrator model. An administrator who intentionally rewrites automation inputs or entity-registry state is already authorized to call Home Assistant services directly and is outside the untrusted-notification threat model.

Call-history rows observed in the supported provider flow include `camera_number`, which the integration uses to associate calls with Ufanet devices. This review does not promote malformed/ambiguous provider call-routing behavior to live-confirmed multi-device semantics; the waiver is narrowly for **cross-device door-button selection/execution** once Home Assistant has associated the call with a device.

## Waiver rationale

**Recommended disposition: WAIVE THE LIVE MULTI-DEVICE TEST ONLY. Do not waive the safety invariant.**

Reasoning:

1. The missing test requires hardware/account topology that is not currently available.
2. Cross-device isolation is implemented in multiple independent layers rather than one UI-only selector.
3. The final physical action is revalidated at execution time.
4. Existing automated tests prove exact device-trigger filtering and guard structure.
5. Adjacent real-world action lifecycle behavior has already been exercised successfully.
6. No provider identifier from the phone is accepted as the physical-action target.

With this waiver recorded, the notification block can be considered sufficiently validated for the planned 0.31.0 candidate **without claiming a live second-device test**. The remaining hard release blockers are the new physical-key enrollment / real `reason=key_add` validation gates tracked in PR #15.
