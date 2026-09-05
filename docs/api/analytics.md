# UCAMS camera analytics

[Русская версия](analytics_RU.md)

This page records the read-only UCAMS camera-analytics contract observed in the
official Android client, the parts verified against the live UCAMS service, and
the privacy-safe production behavior implemented by Ufanet Intercom v0.28.0.

> The current combined notification/physical-key validation branch does not change
> the `motion_alarm` contract, its evidence status, or production model. This page
> was re-audited during the documentation refresh and preserves the existing
> confirmed details without expanding its claims.

## Camera capability metadata

**Status: Confirmed for `motion_alarm`; Observed for `perimeter_security`**

`POST /api/v0/cameras/this/` can include the `analytics` field. The live-tested
camera advertised `motion_alarm`. The Android client also knows about
`perimeter_security`, but the tested tariff did not advertise that capability,
so its event endpoint was not called and production runtime does not use it.

For production capability discovery v0.28.0 requests only the minimum required
fields:

```json
{
  "fields": ["number", "analytics"],
  "numbers": ["<CAMERA_NUMBER>"]
}
```

The research probe may request additional non-media metadata such as `tariff` to
classify what was observed, but production discovery does not need tariff,
timezone, live/archive tokens, screenshots, or recognition data.

## Motion event report

**Status: Confirmed for `motion_alarm`**

The live-confirmed endpoint is:

```http
POST https://cloud.ucams.ru/api/v0/analytics/motion_alarm/report/
Authorization: Bearer <UCAMS_TOKEN>
Content-Type: application/json
```

Confirmed request fields:

```json
{
  "camera_number": "<CAMERA_NUMBER>",
  "start": "<ISO-8601 UTC>",
  "end": "<ISO-8601 UTC>",
  "limit": 25,
  "order_by_date": "desc"
}
```

`limit` is advisory only: the server did not obey a smaller tested value, so
clients must validate the returned envelope rather than assuming the requested
row count is enforced.

The live response is a dictionary containing `count`, `page`, and `results`.
Each confirmed `motion_alarm` result contains:

| Field | Confirmed meaning |
|---|---|
| `id` | opaque numeric event identifier; private replay cursor only |
| `date` | authoritative ISO-8601 UTC event time |
| `length` | event length reported by UCAMS |

The Android DTO contains a field named `time`, but the live wire schema uses
`date`. Runtime code therefore treats `date` as authoritative and never applies
the archive playback-before-event offset to the event timestamp.

## Pagination and oversized windows

The confirmed `page` object contains `current`, `next`, `previous`, `all`, and
`page_size`. In the live test the server returned a page size of 60 even though
a smaller `limit` was requested.

No pagination request field such as `page` or `offset` has been live-confirmed
for this report endpoint, so v0.28.0 intentionally does **not** invent one.
Instead production runtime:

1. checks `count`/`page` to determine whether the returned time window is
   complete;
2. accepts and immediately normalizes complete windows;
3. if a post-baseline window is incomplete, recursively splits only the already
   confirmed `start`/`end` time interval and queries the smaller windows;
4. refuses to advance the cursor if a window remains too dense to resolve
   safely.

This makes overflow fail closed: a temporary analytics update can fail, but
unseen events are not silently skipped by advancing the cursor past an
unprocessed gap.

## Replay cursor and first-poll baseline

The provider `id` is never published as Home Assistant event data. Production
stores only a private per-camera replay cursor containing the latest exact UTC
`date` plus the set of IDs seen at that same timestamp.

Important v0.28.0 behavior:

- fractional timestamp precision is preserved in private storage, so a reload
  cannot move the cursor backwards and replay an already processed event;
- same-timestamp IDs are retained for deterministic deduplication;
- the first successful poll establishes a baseline and does not replay existing
  history;
- if that first poll is empty, the baseline is the poll time rather than Unix
  epoch;
- subsequent queries use a small overlap around the private cursor and rely on
  the cursor to suppress duplicates;
- the analytics lookback is bounded rather than allowing an unbounded history
  replay.

Cursor updates are transactional across cameras. If any camera request or the
private storage write fails, transient events are cleared and cursor state is
rolled back for the whole poll.

## Home Assistant surface in v0.28.0

For an intercom whose camera advertises `motion_alarm`, the integration exposes:

- a **Motion detected** Home Assistant `EventEntity`;
- the `ufanet_intercom_motion` Home Assistant bus event;
- the **Motion detected** device trigger (`motion_detected`) for the visual automation editor.

The EventEntity exposes only `occurred_at`. Internal bus routing can include the
intercom/Home Assistant device reference needed to match an automation, but it
does not expose the UCAMS camera number, provider event/cursor ID, `length`, raw
history, media, screenshots, recognition output, or arbitrary response fields.

Motion entity discovery is recoverable: if UCAMS analytics is unavailable during
initial setup, a later successful capability refresh can add the **Motion detected**
entity without reloading the ConfigEntry.

The analytics coordinator normally polls at low frequency (60 seconds). It is an
event source for automation, not an instantaneous security-alarm transport.

## Archive timeline model observed in the Android client

**Status: Observed**

The decompiled Android client maintains a separate point-event list for its archive timebar. Each `EventDataExistTimeSegment` stores an event timestamp, color, and type; the timebar draws that timestamp as a narrow overlay on the recorded-data bar. The player requests analytics for the currently available archive interval and keeps event timestamps separate from recording ranges.

The same client also contains `POST /api/v0/analytics/archive_events/` for an all-analytics archive query. That endpoint is **Observed only**: it has not been live-confirmed by this project and production Home Assistant code does not call it. Archive motion markers instead reuse the already Confirmed `POST /api/v0/analytics/motion_alarm/report/` endpoint with bounded `start`/`end` windows.

The official client uses an 18-second playback-before-event offset when opening an analytics event. The event timestamp itself is not shifted. The Home Assistant archive timeline follows that UI behavior: the point marker stays at the authoritative `date`, while clicking it seeks to approximately 18 seconds before the event when recording is available.

The authenticated `get_motion_events` Home Assistant response service returns only the selected camera-local date, support flag, count, and normalized event times needed by the Lovelace timeline. UCAMS camera numbers, provider event IDs, `length`, raw results, media, screenshots, and recognition data are not returned.

## Errors, diagnostics, and privacy boundary

Production support is intentionally limited to `motion_alarm`. The project does
not request face recognition, license plates, thermal data, crowd analysis,
helmet detection, screenshots, free text, or analytics media URLs.

The research probe reports only status codes, counts, capability presence,
envelope shape, known field names, and pagination behavior. It never prints
camera numbers, event IDs/timestamps, tokens, media URLs, images, recognition
results, or raw JSON.

At the production boundary, raw result objects are immediately reduced to the
private cursor ID and authoritative `date`; extra response fields are discarded.
UCAMS API failures are mapped to a fixed safe coordinator error rather than
surfacing response-body text. Diagnostics expose aggregate counts/health and the
exception type only, not the exception message, raw events, camera identifiers,
or cursor values.
