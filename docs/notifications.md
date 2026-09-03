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

The blueprint keeps the existing `incoming_call` device trigger for compatibility. A new native doorbell EventEntity also represents the same confirmed call using Home Assistant's standard `ring` event type.

## Delivery sequence

1. A new call is confirmed by the integration's call-history coordinator (polling or FCM-assisted refresh).
2. The blueprint sends a text notification immediately. Image generation never delays this first push.
3. The integration privately downloads the provider preview and extracts a JPEG into the **Last call image** entity.
4. The blueprint waits up to the configured image timeout for that image entity to represent the same call timestamp.
5. If ready, the blueprint sends a replacement notification with the same `tag` and `/api/image_proxy/image.entity_id`. The raw Ufanet preview/archive URL is never put into automation variables or notification data.

For Android, the initial push requests `ttl: 0` and `priority: high` for prompt delivery. The image replacement uses the same notification tag and `alert_once: true` so it updates the existing notification without intentionally producing another alert.

## Actions

When an **Open door** button is selected, real incoming-call notifications contain a unique action identifier derived from the automation run context. The blueprint accepts that action only for the configured timeout and then presses the explicitly selected Ufanet button entity.

The action requests device authentication where supported. Manual runs of the automation deliberately disable the door action, so **Run actions** can be used to test delivery without creating a physical door-control path.

The second action opens the configured Home Assistant dashboard URI.

## Manual testing

A manual automation run has no real `trigger.event`. The blueprint therefore falls back to the selected **Last call** sensor for safe call metadata and clearly labels the notification as a manual test. It never expects `preview_url` or `archive_url` fields in the event payload.

This is intentional: `ufanet_intercom_call` publishes only sanitized call metadata plus `has_preview` / `has_archive`; temporary provider media URLs remain private runtime data.

## Troubleshooting

If no notification arrives during a real call:

1. Run the blueprint manually. If that notification arrives, Companion delivery works and the next place to inspect is the automation trace for the real incoming-call trigger.
2. If the immediate text notification arrives but the image does not, inspect the **Last call image** entity and Ufanet diagnostics. JPEG extraction requires a working `ffmpeg` runtime.
3. If the notification arrives but the door button is absent, confirm that an **Open door** entity was selected and that the run was triggered by a real incoming call rather than manually.
4. The image URL should be `/api/image_proxy/image.entity_id`; do not append the image entity access token yourself.

The integration does not use critical/alarm-stream notifications by default and therefore does not intentionally bypass device Do Not Disturb settings.
