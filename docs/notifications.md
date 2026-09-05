# Home Assistant call notifications

Ufanet Intercom exposes confirmed incoming calls through Home Assistant without publishing the provider's tokenized preview/archive URLs. The notification path uses only Home Assistant entities and the authenticated Companion app connection.

## Recommended blueprint

Import `blueprints/automation/ufanet_intercom/incoming_call_notification.yaml` and select:

- the Ufanet intercom device;
- the Companion app phone;
- the matching **Last call** sensor (recommended, used for manual-test fallback metadata);
- the matching **Last call image** entity;
- optionally, the exact **Open door** button/relay;
- the Home Assistant dashboard URI to open from the notification.

The blueprint keeps the existing `incoming_call` device trigger for compatibility. A native doorbell EventEntity also represents the same confirmed call using Home Assistant's standard `ring` event type.

## Delivery sequence

1. A new call is confirmed by the integration's call-history coordinator (polling or FCM-assisted refresh).
2. The blueprint sends a text notification immediately. Image generation never delays this first push.
3. The integration privately downloads the provider preview and extracts a JPEG into the **Last call image** entity.
4. If that image becomes ready inside the configured image window, the blueprint replaces the notification using the same `tag` and `/api/image_proxy/image.entity_id`.
5. The raw Ufanet preview/archive URL is never put into automation variables or notification data.

For Android, the initial push requests `ttl: 0` and `priority: high` for prompt delivery. The image replacement uses the same notification tag and `alert_once: true` so it updates the existing notification without intentionally producing another alert.

## Actions and safety model

When an **Open door** button is selected, a real incoming-call notification contains a unique action identifier derived from the Home Assistant event context. Provider call UUIDs are not used in the Companion payload.

The door action is enabled only when the selected button belongs to the same Home Assistant device as the selected Ufanet intercom. The same device-membership check is repeated immediately before `button.press`, so a stale or mismatched entity selection cannot be used to open another configured intercom.

The blueprint runs in `restart` mode. A newer call therefore cancels the previous run, invalidates its action listener and replaces the live notification for the same intercom. The previous action ID is not accepted by the new run.

The Open door action is accepted only for the configured timeout. After either a successful `button.press` dispatch or timeout, the notification is replaced without the Open door action. The success message deliberately says that the open command was **sent**; it does not claim that the physical door state was independently verified.

The action requests device authentication where supported. For Android Companion/FCM compatibility the `authenticationRequired` action property is encoded as the string `"true"`, which the Android app parses as a boolean.

Manual runs deliberately disable the physical door action and use a separate notification tag, so **Run actions** can test delivery without replacing an active real-call notification or creating a door-control path.

The second action opens the configured Home Assistant dashboard URI.

## Manual testing

A manual automation run has no real `trigger.event`. The blueprint therefore falls back to the selected **Last call** sensor for safe call metadata and clearly labels the notification as a manual test. It never expects `preview_url` or `archive_url` fields in the event payload.

This is intentional: `ufanet_intercom_call` publishes only sanitized call metadata plus `has_preview` / `has_archive`; temporary provider media URLs remain private runtime data.

## Live validation completed during v0.31.0 development

The notification flow was smoke-tested on a real Home Assistant installation with the Android Companion app:

- manual notification delivery with the cached last-call image;
- synthetic `ufanet_intercom_call` delivery through the integration device trigger;
- Android actionable notification delivery;
- real Ufanet incoming call delivery;
- presence of the Open door action on the real call;
- successful dispatch of the selected Ufanet `button.press` from the notification action.

Two Android payload issues found during live testing were fixed: bare automation `context.id` was replaced with the actual event context, and action-specific boolean values that the FCM data channel requires as strings were corrected.

## Troubleshooting

If no notification arrives during a real call:

1. Run the blueprint manually. If that notification arrives, Companion delivery works and the next place to inspect is the automation trace for the real incoming-call trigger.
2. If the immediate text notification arrives but the image does not, inspect the **Last call image** entity and Ufanet diagnostics. JPEG extraction requires a working `ffmpeg` runtime.
3. If the notification arrives but the door button is absent, confirm that an **Open door** entity from the same Ufanet device was selected and that the run was triggered by a real incoming call rather than manually.
4. The image URL should be `/api/image_proxy/image.entity_id`; do not append the image entity access token yourself.
5. For Android push rejection, enable debug logging for `homeassistant.components.mobile_app.notify`; an FCM error such as `data must only contain string values` points to an invalid actionable-notification payload rather than the Ufanet call trigger.

The integration does not use critical/alarm-stream notifications by default and therefore does not intentionally bypass device Do Not Disturb settings.
