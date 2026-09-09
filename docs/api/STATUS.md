# API verification matrix

[Русская версия](STATUS_RU.md)

This table is a compact index of what has actually been tested by the project. The detailed pages remain authoritative for caveats.

| Area | Method / endpoint | Status | Notes |
|---|---|---|---|
| Auth | `POST /api/v1/auth/auth_by_contract/` | **Confirmed** | Contract/password -> access + refresh JWT |
| Auth | `POST /api/v1/auth/refresh/` | **Confirmed** | Refresh flow |
| Auth | `POST cloud.ucams.ru/api/v0/auth/?ttl=20800` | **Confirmed** | Ufanet JWT -> UCAMS token |
| Account | `GET /api/v0/contract/` | **Confirmed** | Reachability confirmed; schema not documented |
| Account | `GET /api/v0/object/` | **Confirmed** | Reachability confirmed; schema not documented |
| FCM | `POST /api/v0/fcm/` | **Confirmed** | Android 4.0.14 registration body successfully used by headless Windows/Python client |
| FCM | Headless FIS/GCM/MCS receive | **Confirmed** | Real Ufanet push received through `mtalk.google.com:5228` without Android/Google Play Services |
| FCM/Auth | `DELETE /api/v0/fcm/` | **Confirmed** | Controlled target row disappeared without `logout_device`; its issued access JWT remained accepted while its refresh JWT was rejected with HTTP 401. Independent observer authorization survived. The registration was then restored with a fresh JWT login. |
| Device/Auth | `POST /api/v4/fcm_device/authorized_devices/` | **Confirmed** | A plain JWT controller with no FCM registration can query it. Live rows include `device_id`, `title`, `last_update`, `is_call_access`, plus `os`/`os_display`; rows are coupled to FCM/device-registration state and are not an exhaustive independent list of all JWTs. `devices_num_permission` is observed but exact business semantics remain unconfirmed. |
| Device/Auth | `POST /api/v4/fcm_device/logout_device/` | **Confirmed** | A plain-JWT controller successfully revoked a different test device. The target row disappeared; the target issued access JWT remained accepted while its refresh JWT was rejected with HTTP 401. Independent observer authorization survived. Targeted Home Assistant UI revoke was also live-tested. |
| Push | `data.reason = "sip"` | **Confirmed** | Real payload carries `username`, `password`, `server`, `skud_id`, `transport`, `contract`, `house_id`, `flat`, `time`, `uuid`; `from=<sender-id>`, priority `normal` |
| Push | `data.reason = "key_add"` | **Confirmed** | Real completion pushes were received after enrolling a genuinely unregistered key through Home Assistant. The tested success path matched `key_status == 0` plus a parseable `key_id`; a separate no-key 60-second timeout produced no additional completion push. |
| SKUD | `GET /api/v0/skud/shared/` | **Confirmed** | Returns tested intercom |
| SKUD | `GET /api/v0/skud/` | **Observed** | Returned `[]` for tested account |
| Capabilities | `GET /api/v4/skud/features/` | **Confirmed** | Live response included the `keys` account feature |
| Intercoms | `POST /api/v0/intercoms/` | **Confirmed** | One-based filtered request returned `has_key_recording_support=true` |
| Keys | `POST /api/v4/key/list/` | **Confirmed** | Both empty and non-empty live responses were exercised. Confirmed item fields: `id`, `external_id`, `name`, `create_date`, `devices`. HA empty and non-empty inventory paths were also live-validated. |
| Keys | `external_id` selected-key semantics | **Confirmed** | Android uses `external_id` for `filters.key`; live history for the tested physical key updates correctly. Direct comparison also confirmed that `external_id`/other candidate server identifiers do **not** match the number printed on that tested key, so no public key-number field is exposed. |
| Keys | `POST /api/v4/key/skud/<id>/auto_collect/enable/` | **Confirmed** | Home Assistant live-tested the real 60-second enrollment window with a genuinely unregistered key; the key was physically registered and completion arrived through `reason=key_add`. HTTP success alone is still not treated as proof of registration. |
| Keys | `POST /api/v4/key/edit/` | **Confirmed** | Controlled Home Assistant live rename changed the selected key name. Provider inventory is eventually consistent, so runtime sends one write and performs bounded read-only refresh retries; automatic post-write verification was live-confirmed and no automatic write retry occurs. |
| Keys | `POST /api/v4/key/skud/<id>/delete/key/` | **Observed** | Android deletes a key with `{key_id}`; destructive flow is neither implemented nor live-validated. |
| Passages | `POST /api/v4/key/skud/<id>/key/pass_history/` | **Confirmed** | Empty and non-empty responses confirmed. Live item fields are `key:str`, `key_name:str`, `time_passage:int`; zero-based pagination confirmed. |
| Passages | `filters.key=<external_id>` | **Confirmed** | Privacy-safe live probe and Home Assistant selected-key flow returned the passages associated with the real registered key; subsequent history updates continued to correlate to that same physical key. |
| Door | `GET /api/v0/skud/shared/<id>/open/?door=1` | **Confirmed** | Physical side effect; successful `{"result":true}` |
| UCAMS | `POST /api/v0/cameras/this/` | **Confirmed** | Camera/server/token metadata; `analytics` capability metadata also live-confirmed |
| Analytics | `analytics` in camera metadata: `motion_alarm` | **Confirmed** | Live-tested camera advertises motion analytics; used by production v0.28.0 |
| Analytics | `analytics` in camera metadata: `perimeter_security` | **Observed** | Android capability exists; not advertised by the tested tariff and not used by production runtime |
| Analytics | `POST /api/v0/analytics/motion_alarm/report/` | **Confirmed** | HTTP 200; envelope `count/page/results`; result fields `id/date/length`; `date` is authoritative and `id` is a private opaque cursor |
| Analytics | `POST /api/v0/analytics/archive_events/` | **Observed** | Decompiled Android archive player can request all analytics for an archive interval; not live-confirmed and not used by production runtime |
| Analytics | motion report pagination | **Confirmed** | `page` has `current/next/previous/all/page_size`; server returned page size 60 despite a smaller requested `limit`. No pagination request field is yet live-confirmed, so v0.28.0 resolves incomplete reports by splitting only the confirmed `start`/`end` window and never advances the cursor past an unresolved gap |
| Live | `.../<camera>/index.m3u8?...` | **Confirmed** | HTTP 200 |
| Snapshot | `/api/v0/screenshots/<camera>.jpg?...` | **Confirmed** | Working snapshot |
| Archive | `recording_status.json?...request=ranges...` | **Confirmed** | `{from,duration}` ranges |
| Archive | `archive-<start>-<duration>.m3u8` | **Confirmed** | HTTP 200 |
| Archive | `archive-<start>-<duration>.mp4` with `token_r` | **Not supported** | HTTP 403 in tested form |
| Calls | `GET /api/v1/skuds/call-history/` | **Confirmed** | Call list with offset-aware `called_at` |
| Calls | `POST /api/v1/cctv/history/` | **Confirmed** | Tokenized preview/archive MP4 URLs |
| Shared access | `GET /api/v4/token/shared/users/` | **Confirmed** | Accepted users |
| Shared access | `POST /api/v4/token/shared/create_token/` | **Confirmed** | Creates invitation token |
| Shared access | `POST /api/v4/token/shared_device/` | **Confirmed** | Recipient accepts token |
| Shared access | `POST /api/v4/token/delete/` | **Confirmed** | Revokes accepted access |
| Temporary guest | `GET /api/v1/skuds/skud_share_open/` | **Confirmed** | Lists links |
| Temporary guest | `POST /api/v1/skuds/skud_share_open/` | **Confirmed** | `time` is minutes; 3h tested |
| Temporary guest | `DELETE /api/v1/skuds/skud_share_open/` | **Confirmed** | Revocation tested |

## Update policy

When adding a new finding:

- update this matrix and the detailed page in the same commit;
- do not mark a behavior **Confirmed** based only on decompiled client code;
- use **Experimental** for a user-facing interpretation that is intentionally exposed for validation but whose semantic mapping is not yet proven;
- record tested failures as **Not supported** only for the exact request form that was tested;
- do not infer untested pagination/request fields from response metadata;
- for state-changing operations, record separately whether the physical/account side effect was actually verified rather than only the HTTP response;
- avoid publishing account-specific data, credentials, camera/event/key identifiers, exact event history, or raw private responses.
