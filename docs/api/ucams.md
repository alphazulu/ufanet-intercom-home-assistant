# UCAMS camera control and live video

[Русская версия](ucams_RU.md)

UCAMS is the video platform used by the tested Ufanet intercom account.

> The combined notification/physical-key validation branch does not change the
> UCAMS authentication/live/archive-token contract. This page was re-audited
> during the documentation refresh and keeps the existing evidence statuses.

## Get camera metadata

**Status: Confirmed**

After exchanging the Ufanet JWT for a UCAMS bearer token, request camera information:

```http
POST https://cloud.ucams.ru/api/v0/cameras/this/
Authorization: Bearer <UCAMS_JWT>
Content-Type: application/json
```

Tested request body:

```json
{
  "fields": [
    "number",
    "token_l",
    "token_r",
    "is_llhls_enabled",
    "permission",
    "address",
    "title",
    "timezone",
    "is_fav",
    "is_public",
    "inactivity_period",
    "server",
    "analytics",
    "tariff",
    "is_sounding",
    "streams_count"
  ],
  "token_l_ttl": 20800,
  "token_r_ttl": 20800,
  "numbers": ["<CAMERA_NUMBER>"]
}
```

Observed response data includes:

- camera `number`;
- `token_l` — live/media token;
- `token_r` — archive token;
- timezone;
- LL-HLS capability;
- stream count;
- media server domain/vendor;
- screenshot service domain;
- advertised `analytics` capabilities; `motion_alarm` is live-confirmed on the tested camera, while `perimeter_security` remains Observed only;
- tariff metadata including archive depth (`dvr_hours`).

The exact response nesting is intentionally not presented as a complete stable schema because it is private API behavior and may vary.

Production analytics capability discovery does not need the full media metadata request above. Ufanet Intercom v0.28.0 uses a separate minimal `cameras/this/` request containing only `number` and `analytics`. See [UCAMS camera analytics](analytics.md) for the confirmed `motion_alarm` report contract and its privacy boundary.

## Live HLS

**Status: Confirmed**

```text
https://<MEDIA_SERVER>/<CAMERA_NUMBER>/index.m3u8?token=<TOKEN_L>&tracks=v1a1
```

The tested URL returned HTTP 200 and HLS media.

`tracks=v1a1` requests the tested video/audio track combination. Other track selectors have not been systematically documented.

## Screenshot

**Status: Confirmed**

```text
https://<SCREENSHOT_DOMAIN>/api/v0/screenshots/<CAMERA_NUMBER>.jpg?token=<TOKEN_L>
```

The screenshot domain should come from camera/server metadata rather than being hard-coded when possible.

## Token roles

Observed behavior:

| Token | Purpose |
|---|---|
| Ufanet access JWT | Ufanet API and UCAMS auth exchange |
| UCAMS JWT | UCAMS control API (`Bearer`), including camera metadata and analytics reports |
| `token_l` | live HLS and screenshot access |
| `token_r` | archive/range access |

**Status: Confirmed for the operations documented above.**

## Codec/stream observations

The tested camera exposed H.264 video and AAC audio at 1920×1080.

**Status: Observed; do not assume these codecs/resolution for every camera.**
