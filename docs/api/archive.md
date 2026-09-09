# Archive

[Русская версия](archive_RU.md)

> The combined notification/physical-key validation branch does not change the
> archive API or its evidence status. This page was re-audited during the
> documentation refresh; the existing Confirmed/Observed claims remain unchanged.

## Recording ranges

**Status: Confirmed**

Archive availability is queried from the camera media server using `token_r`:

```text
https://<MEDIA_SERVER>/<CAMERA_NUMBER>/recording_status.json?from=0&request=ranges&token=<TOKEN_R>
```

Observed response contains recording intervals shaped like:

```json
{
  "from": 1700000000,
  "duration": 3600
}
```

`from` is a Unix timestamp and `duration` is expressed in seconds.

The tested camera returned multiple such ranges. Clients should not assume continuous recording: request ranges first and validate that the requested interval is covered.

## Archive HLS

**Status: Confirmed**

Tested archive playlist form:

```text
https://<MEDIA_SERVER>/<CAMERA_NUMBER>/archive-<START_UNIX>-<DURATION>.m3u8?token=<TOKEN_R>
```

The tested request returned HTTP 200.

- `<START_UNIX>` — requested start time as Unix timestamp.
- `<DURATION>` — clip duration in seconds.

## Arbitrary direct MP4

**Status: Not supported in the tested form**

The following form was explicitly tested:

```text
https://<MEDIA_SERVER>/<CAMERA_NUMBER>/archive-<START_UNIX>-<DURATION>.mp4?token=<TOKEN_R>
```

The tested server returned **HTTP 403**.

Do not document or implement this URL as a generally working archive-download endpoint unless new tests prove otherwise.

## Working MP4 export strategy

**Status: Confirmed in this project**

The Home Assistant integration exports MP4 by:

1. validating the requested time window against archive ranges;
2. opening the archive HLS playlist;
3. using ffmpeg stream copy (`-c copy`) to remux the media into MP4;
4. storing the resulting file in Home Assistant Media.

This avoids transcoding when the source codecs are MP4-compatible.

## Archive depth

Camera metadata can expose tariff/archive information such as `dvr_hours`. The tested camera reported a five-day archive depth (120 hours).

**Status: Observed; tariff and archive depth are account/camera dependent.**

## Time handling

Use timezone-aware datetimes at API/application boundaries. Convert to Unix timestamps only for media-server requests that explicitly require Unix time. Do not silently reinterpret a timestamp by replacing its timezone.