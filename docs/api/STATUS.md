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
| FCM | `DELETE /api/v0/fcm/` | **Confirmed** | Probe removed only its own virtual registration with HTTP 200, then restored it with POST HTTP 200 |
| FCM | `POST /api/v4/fcm_device/authorized_devices/` | **Observed** | Android client consumes device list / call-access metadata |
| FCM | `POST /api/v4/fcm_device/logout_device/` | **Observed** | Android client sends `{device_id}` to revoke another device/session |
| Push | `data.reason = "sip"` | **Confirmed** | Real payload carries `username`, `password`, `server`, `skud_id`, `transport`, `contract`, `house_id`, `flat`, `time`, `uuid`; `from=<sender-id>`, priority `normal` |
| SKUD | `GET /api/v0/skud/shared/` | **Confirmed** | Returns tested intercom |
| SKUD | `GET /api/v0/skud/` | **Observed** | Returned `[]` for tested account |
| Capabilities | `GET /api/v4/skud/features/` | **Confirmed** | Live response included the `keys` account feature |
| Intercoms | `POST /api/v0/intercoms/` | **Confirmed** | One-based filtered request returned `has_key_recording_support=true` |
| Keys | `POST /api/v4/key/list/` | **Confirmed** | HTTP 200 and empty `data.keys` confirmed; non-empty item fields remain Observed |
| Passages | `POST /api/v4/key/skud/<id>/key/pass_history/` | **Confirmed** | HTTP 200, zero-based pagination and empty `results` confirmed; item fields remain Observed |
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
- record tested failures as **Not supported** only for the exact request form that was tested;
- do not infer untested pagination/request fields from response metadata;
- avoid publishing account-specific data, credentials, camera/event identifiers, exact event history, or raw private responses.
