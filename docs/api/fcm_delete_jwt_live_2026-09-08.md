# Live validation: `DELETE /api/v0/fcm/` vs JWT authorization — 2026-09-08

## Result

Controlled live testing established that Ufanet `DELETE /api/v0/fcm/` is not a push-only side effect.

The test used a disposable probe-owned virtual device and two ordinary Ufanet JWT logins:

- **subject** — the JWT pair used to register the disposable FCM device;
- **observer** — an independent JWT session used to inspect the account and perform the FCM DELETE.

The probe did not call `logout_device`, did not accept an arbitrary provider `device_id`, did not start MCS, and did not expose JWTs, FCM tokens or provider IDs.

## Observed sequence

1. Subject JWT registered the probe-owned device through `POST /api/v0/fcm/`.
2. Observer confirmed the row was present in `POST /api/v4/fcm_device/authorized_devices/`.
3. Subject access JWT was valid before deletion.
4. Observer called only `DELETE /api/v0/fcm/` for the probe-owned device.
5. The row disappeared from `authorized_devices`.
6. The already-issued subject access JWT remained valid (`HTTP 200`).
7. The subject refresh JWT was rejected (`HTTP 401`).
8. The independent observer access JWT remained valid (`HTTP 200`).
9. The probe-owned registration was restored with a fresh login.

## Interpretation

`DELETE /api/v0/fcm/` has two live-confirmed effects for the tested device:

- removes the FCM/device registration row;
- invalidates the refresh authorization chain associated with the JWT session that registered that device.

An already-issued access JWT can continue to work after the deletion, so the effect is not immediate access-token revocation.

This is the same authorization pattern previously observed for `POST /api/v4/fcm_device/logout_device/`: the device row disappears, an already-issued access JWT may survive, and refresh is invalidated.

The two endpoints remain distinct contracts and should remain separately addressable in Home Assistant:

- `logout_device` is the official authorized-device/session logout action;
- `DELETE /api/v0/fcm/` is the FCM/device unregister action, but it must be treated as authorization-destructive because it also invalidates the tested refresh chain.

## Consequence for `authorized_devices`

Because a row disappears after FCM DELETE even without `logout_device`, `authorized_devices` must not be described as an independent exhaustive inventory of all JWTs. It is the provider's authorized-device/registration inventory used by the official device UI and is coupled to device/FCM registration state.

## Production safety rule

The integration must continue to protect its own `Home Assistant_<UUID>` registration from generic targeted or bulk destructive actions. Normal cleanup of the integration-owned registration should continue through the controlled FCM-disable/config-entry-removal lifecycle.
