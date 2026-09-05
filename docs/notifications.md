# Home Assistant call notifications

Ufanet Intercom exposes confirmed incoming calls through Home Assistant without publishing the provider's tokenized preview/archive URLs. The notification path uses only Home Assistant entities and the authenticated Companion app connection.

## Recommended blueprint

Import `blueprints/automation/ufanet_intercom/incoming_call_notification.yaml` and select:

- the Ufanet intercom device;
- the Companion app phone;
- the matching **Last call** sensor (recommended, used for manual-test fallback metadata);
- the matching **Last call image** entity;
- optionally, the matching **Live camera** entity;
- optionally, the exact **Open door** button/relay;
- the Home Assistant dashboard URI used as notification/fallback navigation;
- optionally, the Android notification channel name;
- optionally, the image-wait delay and Open door action timeout.

The blueprint keeps the existing `incoming_call` device trigger for compatibility. A native doorbell EventEntity also represents the same confirmed call using Home Assistant's standard `ring` event type.

## Native push content

A real call notification is built only from Home Assistant-safe metadata. The title contains the selected Home Assistant intercom device name. The body can contain:

- address;
- porch;
- flat;
- call time converted to the Home Assistant local timezone.

Missing fields are simply omitted. Manual runs use the same formatting with metadata from the selected **Last call** sensor and are explicitly marked as tests.

The call time is formatted from the confirmed `called_at` timestamp with Home Assistant's local timezone, so it follows the timezone configured for the HA instance rather than displaying provider UTC directly.

## Delivery sequence

1. A new call is confirmed by the integration's call-history coordinator (polling or FCM-assisted refresh).
2. The blueprint sends the text notification immediately. Image generation never delays this first push.
3. The integration privately downloads the provider preview and extracts a JPEG into the **Last call image** entity.
4. If that image becomes ready inside the configured image window, the blueprint replaces the notification using the same `tag` and `/api/image_proxy/image.entity_id`.
5. The raw Ufanet preview/archive URL is never put into automation variables or notification data.

A stable live `tag` is derived from the selected Home Assistant intercom device, so image/status updates replace the same notification. Manual tests use a separate tag and do not replace an active real-call notification.

For Android, the initial push requests `ttl: 0` and `priority: high` for prompt delivery. The configurable `channel` and `importance: high` fields are Android-specific; iOS ignores the Android channel field. Image/status replacements use `alert_once: true` so they update the existing notification without intentionally producing another alert.

## Android and iOS actions

The blueprint uses inline Companion actions matching the shared Android/iOS action schema:

- **Open door** uses a unique Home Assistant-local action ID and never calls a provider API directly;
- **View camera** uses the standard `URI` action. When a matching **Live camera** entity is selected, the blueprint opens that entity directly with Home Assistant's `more-info-entity-id` frontend query parameter; otherwise it falls back to the configured Home Assistant view.

The selected camera is accepted only when it is a `camera.*` entity belonging to the same Home Assistant device as the selected intercom. A Ufanet device can expose both live and archive camera entities, so choose the live camera explicitly in the blueprint selector. The device-membership guard prevents an unrelated camera from becoming the notification target.

The Open door action requests device authentication where supported. During Android live testing the Companion/FCM data channel required action values to be strings, so `authenticationRequired` is encoded as `"true"`; Android Companion parses that value as a boolean. Apple-only `destructive` metadata is deliberately not included in the cross-platform payload.

**Android Companion has been live-tested. iOS action delivery has not been live-tested**; iOS compatibility is documentation/schema-aligned rather than claimed as live-confirmed.

## Actions and safety model

When an **Open door** button is selected, a real incoming-call notification contains a unique action identifier derived from the Home Assistant event context. Provider call UUIDs are not used in the Companion payload.

The door action is enabled only when the selected button belongs to the same Home Assistant device as the selected Ufanet intercom. The same device-membership check is repeated immediately before `button.press`, so a stale or mismatched entity selection cannot be used to open another configured intercom.

The blueprint runs in `restart` mode. A newer call therefore cancels the previous run, invalidates its action listener and replaces the live notification for the same intercom. The previous action ID is not accepted by the new run. Regression tests cover the state machine, but two sequential **real** calls remain a required live gate.

The Open door action is accepted only for the configured timeout. After either a successful `button.press` dispatch or timeout, the notification is replaced without the Open door action. The success message deliberately says that the open command was **sent**; it does not claim that the physical door state was independently verified.

Manual runs deliberately disable the physical door action and use a separate notification tag, so **Run actions** can test delivery without replacing an active real-call notification or creating a door-control path.

No door opening occurs without an explicit user tap on the actionable notification.

## Manual testing

A manual automation run has no real `trigger.event`. The blueprint therefore falls back to the selected **Last call** sensor for safe call metadata and clearly labels the notification as a manual test. It never expects `preview_url` or `archive_url` fields in the event payload.

This is intentional: `ufanet_intercom_call` publishes only sanitized call metadata plus `has_preview` / `has_archive`; temporary provider media URLs remain private runtime data.

## Live validation on the combined validation branch

The following has already been confirmed on a real Home Assistant installation with the Android Companion app:

- manual notification delivery with the cached last-call image;
- synthetic `ufanet_intercom_call` delivery through the integration device trigger;
- Android actionable notification delivery;
- real Ufanet incoming call delivery;
- presence of the Open door action on the real call;
- successful dispatch of the selected Ufanet `button.press` from the notification action and physical door opening;
- **View camera** opens More Info for the selected live `camera.*` entity directly;
- after the action timeout, the existing notification is updated **in place** under the same stable tag, no second notification is created, Open door disappears, and View camera remains.

Android payload issues found during live testing were fixed: bare automation `context.id` was replaced with the actual event context, and action-specific boolean values that the FCM data channel requires as strings were corrected.

## Required live gates before release

Before the combined validation work can be treated as release-ready, real-world testing still needs to confirm:

1. a second real call replaces the first pending notification and the old action is no longer accepted;
2. after a successful **Open door** tap, the same notification is immediately replaced without the door action and shows the command-sent status;
3. a door button from another Ufanet device is never exposed or executed;
4. a fresh real-call notification shows the expected Home Assistant device name, address, porch, flat and local call time;
5. iOS needs a separate real-device test only if it is later going to be described as live-tested; this documentation currently makes no such claim.

These items do not block unrelated development, but they do block final live-validation of the notification feature for release unless explicitly reviewed and waived.

## Troubleshooting

If no notification arrives during a real call:

1. Run the blueprint manually. If that notification arrives, Companion delivery works and the next place to inspect is the automation trace for the real incoming-call trigger.
2. If the immediate text notification arrives but the image does not, inspect the **Last call image** entity and Ufanet diagnostics. JPEG extraction requires a working `ffmpeg` runtime.
3. If the notification arrives but the door button is absent, confirm that an **Open door** entity from the same Ufanet device was selected and that the run was triggered by a real incoming call rather than manually.
4. If **View camera** only opens the dashboard, select the matching live `camera.*` entity in the blueprint inputs. A mismatched camera deliberately falls back to the dashboard URI.
5. The image URL should be `/api/image_proxy/image.entity_id`; do not append the image entity access token yourself.
6. For Android push rejection, enable debug logging for `homeassistant.components.mobile_app.notify`; an FCM error such as `data must only contain string values` points to an invalid actionable-notification payload rather than the Ufanet call trigger.

The integration does not use critical/alarm-stream notifications by default and therefore does not intentionally bypass device Do Not Disturb settings.