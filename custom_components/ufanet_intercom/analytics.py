"""Privacy-minimized UCAMS motion analytics support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UfanetApi, UfanetApiError, UfanetResponseError
from .const import ANALYTICS_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)

_MOTION_TYPE = "motion_alarm"
_MOTION_FIELDS = ["number", "analytics"]
_MOTION_REQUEST_LIMIT = 25
_MOTION_PROCESSING_LIMIT = 60
_MOTION_LOOKBACK = timedelta(hours=24)
_MOTION_SPLIT_MIN_WINDOW = timedelta(seconds=1)
_MOTION_SPLIT_MAX_DEPTH = 16
_MOTION_STORE_VERSION = 1
_SAFE_UPDATE_ERROR = "UCAMS motion analytics update failed"


class MotionAnalyticsEvent(TypedDict):
    """Normalized event retained only until cursor processing completes."""

    cursor_id: int
    occurred_at: datetime


@dataclass(frozen=True)
class _MotionCursor:
    """Latest event timestamp and opaque IDs seen at that timestamp."""

    timestamp: datetime
    ids: frozenset[int]


@dataclass(frozen=True)
class _MotionEventPage:
    """One normalized report page plus whether the queried window is complete."""

    events: tuple[MotionAnalyticsEvent, ...]
    complete: bool


def _iso_utc_request(value: datetime) -> str:
    """Format bounded report query timestamps using the confirmed wire shape."""
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _iso_utc_storage(value: datetime) -> str:
    """Persist the cursor without losing fractional-second precision."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_wire_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise UfanetResponseError("UCAMS motion event has invalid date")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise UfanetResponseError("UCAMS motion event has invalid date") from err
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise UfanetResponseError("UCAMS motion event date is not UTC")
    return parsed.astimezone(timezone.utc)


async def async_get_motion_capabilities(
    api: UfanetApi,
    camera_numbers: list[str],
) -> set[str]:
    """Return only cameras that explicitly advertise live-confirmed motion analytics."""
    if not camera_numbers:
        return set()
    data = await api._async_ucams_json(  # noqa: SLF001 - package-private API boundary
        "POST",
        "/api/v0/cameras/this/",
        json_body={"fields": _MOTION_FIELDS, "numbers": list(camera_numbers)},
    )
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise UfanetResponseError("Unexpected UCAMS analytics capability response")

    requested = set(camera_numbers)
    supported: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            raise UfanetResponseError("Invalid UCAMS analytics capability item")
        number = item.get("number")
        analytics = item.get("analytics")
        if not isinstance(number, (str, int)) or isinstance(number, bool):
            raise UfanetResponseError("Invalid UCAMS analytics camera reference")
        if analytics is None:
            analytics = []
        if not isinstance(analytics, list) or not all(
            isinstance(value, str) for value in analytics
        ):
            raise UfanetResponseError("Invalid UCAMS analytics capability list")
        normalized = str(number)
        if normalized in requested and _MOTION_TYPE in analytics:
            supported.add(normalized)
    return supported


async def async_get_motion_events(
    api: UfanetApi,
    camera_number: str,
    *,
    start: datetime,
    end: datetime,
) -> _MotionEventPage:
    """Return a bounded normalized report page without retaining raw fields."""
    data = await api._async_ucams_json(  # noqa: SLF001 - package-private API boundary
        "POST",
        "/api/v0/analytics/motion_alarm/report/",
        json_body={
            "camera_number": camera_number,
            "start": _iso_utc_request(start),
            "end": _iso_utc_request(end),
            "limit": _MOTION_REQUEST_LIMIT,
            "order_by_date": "desc",
        },
    )
    if not isinstance(data, dict):
        raise UfanetResponseError("Unexpected UCAMS motion analytics response")
    results = data.get("results")
    count = data.get("count")
    page = data.get("page")
    if (
        not isinstance(results, list)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or not isinstance(page, dict)
    ):
        raise UfanetResponseError("Unexpected UCAMS motion analytics response")
    page_all = page.get("all")
    if (
        not isinstance(page_all, int)
        or isinstance(page_all, bool)
        or page_all < 0
    ):
        raise UfanetResponseError("Unexpected UCAMS motion analytics pagination")

    events: list[MotionAnalyticsEvent] = []
    for item in results[:_MOTION_PROCESSING_LIMIT]:
        if not isinstance(item, dict):
            raise UfanetResponseError("Invalid UCAMS motion analytics item")
        cursor_id = item.get("id")
        if not isinstance(cursor_id, int) or isinstance(cursor_id, bool):
            raise UfanetResponseError("UCAMS motion event has invalid cursor")
        events.append(
            {
                "cursor_id": cursor_id,
                "occurred_at": _parse_wire_datetime(item.get("date")),
            }
        )

    normalized = tuple(
        sorted(events, key=lambda item: (item["occurred_at"], item["cursor_id"]))
    )
    complete = (
        len(results) <= _MOTION_PROCESSING_LIMIT
        and count <= len(results)
        and page_all <= 1
    )
    return _MotionEventPage(normalized, complete)


def _merge_motion_events(
    *batches: list[MotionAnalyticsEvent] | tuple[MotionAnalyticsEvent, ...],
) -> list[MotionAnalyticsEvent]:
    """Merge overlapping time windows without replaying boundary rows."""
    unique: dict[tuple[datetime, int], MotionAnalyticsEvent] = {}
    for batch in batches:
        for event in batch:
            unique[(event["occurred_at"], event["cursor_id"])] = event
    return sorted(
        unique.values(),
        key=lambda item: (item["occurred_at"], item["cursor_id"]),
    )


async def _async_collect_motion_events(
    api: UfanetApi,
    camera_number: str,
    *,
    start: datetime,
    end: datetime,
    depth: int = 0,
) -> list[MotionAnalyticsEvent]:
    """Split a confirmed start/end window until no server page is truncated."""
    report = await async_get_motion_events(
        api,
        camera_number,
        start=start,
        end=end,
    )
    if report.complete:
        return list(report.events)

    if depth >= _MOTION_SPLIT_MAX_DEPTH or end - start <= _MOTION_SPLIT_MIN_WINDOW:
        raise UfanetResponseError("UCAMS motion analytics window is too dense")

    midpoint = start + (end - start) / 2
    older = await _async_collect_motion_events(
        api,
        camera_number,
        start=start,
        end=midpoint,
        depth=depth + 1,
    )
    newer = await _async_collect_motion_events(
        api,
        camera_number,
        start=midpoint,
        end=end,
        depth=depth + 1,
    )
    return _merge_motion_events(older, newer)


class UfanetMotionAnalyticsCoordinator(
    DataUpdateCoordinator[dict[int, dict[str, Any]]]
):
    """Poll motion events at low frequency with a private replay cursor."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UfanetApi,
        entry_id: str,
        camera_by_skud: dict[int, str],
        *,
        scan_interval_seconds: int = ANALYTICS_SCAN_INTERVAL_SECONDS,
    ) -> None:
        self.api = api
        self.camera_by_skud = dict(camera_by_skud)
        self.new_events: dict[int, list[dict[str, str]]] = {}
        self._cursors: dict[str, _MotionCursor] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass,
            _MOTION_STORE_VERSION,
            f"{DOMAIN}.motion_analytics.{entry_id}",
            private=True,
            atomic_writes=True,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_motion_analytics",
            update_interval=timedelta(seconds=int(scan_interval_seconds)),
        )

    async def async_initialize(self) -> None:
        """Load private cursors before the first cloud refresh."""
        try:
            self._cursors = _parse_cursors(await self._store.async_load())
        except Exception:  # noqa: BLE001 - corrupt private state must rebuild baseline
            self._cursors = {}

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        self.new_events = {}
        if not self.camera_by_skud:
            return {}

        previous_cursors = dict(self._cursors)
        try:
            supported_cameras = await async_get_motion_capabilities(
                self.api,
                list(dict.fromkeys(self.camera_by_skud.values())),
            )
            now = datetime.now(timezone.utc)
            data: dict[int, dict[str, Any]] = {}
            for skud_id, camera_number in sorted(self.camera_by_skud.items()):
                if camera_number not in supported_cameras:
                    continue
                cursor = self._cursors.get(camera_number)
                start = (
                    max(cursor.timestamp - timedelta(minutes=1), now - _MOTION_LOOKBACK)
                    if cursor is not None
                    else now - _MOTION_LOOKBACK
                )
                if cursor is None:
                    report = await async_get_motion_events(
                        self.api,
                        camera_number,
                        start=start,
                        end=now,
                    )
                    events = list(report.events)
                else:
                    events = await _async_collect_motion_events(
                        self.api,
                        camera_number,
                        start=start,
                        end=now,
                    )

                next_cursor, unseen = _advance_cursor(
                    cursor,
                    events,
                    baseline_at=now,
                )
                self._cursors[camera_number] = next_cursor
                if unseen:
                    self.new_events[skud_id] = [
                        {"occurred_at": event["occurred_at"].isoformat()}
                        for event in unseen
                    ]
                data[skud_id] = {
                    "supported": True,
                    "last_event_at": (
                        events[-1]["occurred_at"].isoformat() if events else None
                    ),
                }

            if self._cursors != previous_cursors:
                try:
                    await self._store.async_save(_serialize_cursors(self._cursors))
                except Exception as err:
                    self.new_events = {}
                    self._cursors = previous_cursors
                    raise UpdateFailed("Unable to save motion analytics cursor state") from err
            return data
        except UfanetApiError:
            self.new_events = {}
            self._cursors = previous_cursors
            raise UpdateFailed(_SAFE_UPDATE_ERROR) from None

    def diagnostic_summary(self) -> dict[str, int]:
        """Return aggregate analytics state without camera/cursor identifiers."""
        data = self.data if isinstance(self.data, dict) else {}
        return {
            "supported_intercom_count": len(data),
            "new_event_batch_count": sum(len(items) for items in self.new_events.values()),
            "stored_cursor_count": len(self._cursors),
        }


def _advance_cursor(
    cursor: _MotionCursor | None,
    events: list[MotionAnalyticsEvent],
    *,
    baseline_at: datetime | None = None,
) -> tuple[_MotionCursor, list[MotionAnalyticsEvent]]:
    """Build baseline or return only events beyond the private cursor."""
    if not events:
        if cursor is not None:
            return cursor, []
        if baseline_at is None:
            raise ValueError("baseline_at is required for an empty initial motion page")
        return _MotionCursor(
            baseline_at.astimezone(timezone.utc),
            frozenset(),
        ), []

    latest_time = events[-1]["occurred_at"]
    latest_ids = frozenset(
        event["cursor_id"] for event in events if event["occurred_at"] == latest_time
    )
    if cursor is None:
        return _MotionCursor(latest_time, latest_ids), []

    unseen = [
        event
        for event in events
        if event["occurred_at"] > cursor.timestamp
        or (
            event["occurred_at"] == cursor.timestamp
            and event["cursor_id"] not in cursor.ids
        )
    ]
    if latest_time < cursor.timestamp:
        return cursor, unseen
    if latest_time == cursor.timestamp:
        latest_ids = frozenset(set(latest_ids) | set(cursor.ids))
    return _MotionCursor(latest_time, latest_ids), unseen


def _parse_cursors(data: Any) -> dict[str, _MotionCursor]:
    if data is None:
        return {}
    raw = data.get("cameras") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        raise TypeError("invalid motion analytics cursor schema")
    cursors: dict[str, _MotionCursor] = {}
    for camera_ref, item in raw.items():
        if not isinstance(camera_ref, str) or not isinstance(item, dict):
            raise TypeError("invalid motion analytics cursor item")
        timestamp = _parse_wire_datetime(item.get("date"))
        ids = item.get("ids")
        if not isinstance(ids, list) or not all(
            isinstance(value, int) and not isinstance(value, bool) for value in ids
        ):
            raise ValueError("invalid motion analytics cursor IDs")
        cursors[camera_ref] = _MotionCursor(timestamp, frozenset(ids))
    return cursors


def _serialize_cursors(cursors: dict[str, _MotionCursor]) -> dict[str, Any]:
    return {
        "cameras": {
            camera_ref: {
                "date": _iso_utc_storage(cursor.timestamp),
                "ids": sorted(cursor.ids),
            }
            for camera_ref, cursor in sorted(cursors.items())
        }
    }
