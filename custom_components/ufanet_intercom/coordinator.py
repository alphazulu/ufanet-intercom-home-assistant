"""Data coordinators for Ufanet Intercom."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KeyPassage, UfanetApi, UfanetApiError, UfanetAuthError
from .const import (
    CALL_SCAN_INTERVAL_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    KEY_PASSAGE_SCAN_INTERVAL_SECONDS,
    MEDIA_REFRESH_SECONDS,
)

_LOGGER = logging.getLogger(__name__)
_PASSAGE_STORE_VERSION = 1


@dataclass(frozen=True)
class _PassageCursor:
    """Last processed second and the keys seen at that second."""

    timestamp: int
    key_ids: frozenset[int]


class UfanetCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Refresh the list and metadata of available intercom/SKUD objects."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UfanetApi,
        *,
        scan_interval_seconds: int = DEFAULT_SCAN_INTERVAL_SECONDS,
    ) -> None:
        self.api = api
        self.scan_interval_seconds = int(scan_interval_seconds)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval_seconds),
        )

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        try:
            items = await self.api.async_get_skuds()
        except UfanetAuthError as err:
            raise ConfigEntryAuthFailed from err
        except UfanetApiError as err:
            raise UpdateFailed(str(err)) from err
        return {int(item["id"]): item for item in items}


class UfanetKeyPassageCoordinator(
    DataUpdateCoordinator[dict[int, dict[str, int | None]]]
):
    """Poll physical keys and passages without retaining full history."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UfanetApi,
        entry_id: str,
        skud_ids: set[int],
        *,
        scan_interval_seconds: int = KEY_PASSAGE_SCAN_INTERVAL_SECONDS,
    ) -> None:
        self.api = api
        self.skud_ids = set(skud_ids)
        self.scan_interval_seconds = int(scan_interval_seconds)
        self.new_passages: dict[int, list[dict[str, str]]] = {}
        self._cursors: dict[int, _PassageCursor] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass,
            _PASSAGE_STORE_VERSION,
            f"{DOMAIN}.key_passages.{entry_id}",
            private=True,
            atomic_writes=True,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_key_passages",
            update_interval=timedelta(seconds=self.scan_interval_seconds),
        )

    async def async_initialize(self) -> None:
        """Load private cursors before the first cloud refresh."""
        try:
            self._cursors = _parse_passage_cursors(await self._store.async_load())
        except Exception as err:  # noqa: BLE001 - storage must not block setup
            self._cursors = {}
            _LOGGER.warning(
                "Unable to load key-passage cursor state (%s); rebuilding baseline",
                type(err).__name__,
            )

    async def _async_update_data(self) -> dict[int, dict[str, int | None]]:
        # A failed refresh must never replay the previous successful batch.
        self.new_passages = {}
        try:
            supported_ids = (
                await self.api.async_get_key_recording_intercom_ids()
            ) & self.skud_ids
            if not supported_ids:
                return {}

            ordered_ids = sorted(supported_ids)
            keys_result, *history_results = await asyncio.gather(
                self.api.async_get_physical_keys(),
                *(
                    self.api.async_get_key_passage_history(skud_id)
                    for skud_id in ordered_ids
                ),
            )
        except UfanetAuthError as err:
            raise ConfigEntryAuthFailed from err
        except UfanetApiError as err:
            raise UpdateFailed(str(err)) from err

        key_counts = dict.fromkeys(ordered_ids, 0)
        for key in keys_result:
            for skud_id in set(key["devices"]):
                if skud_id in key_counts:
                    key_counts[skud_id] += 1

        previous_cursors = dict(self._cursors)
        data: dict[int, dict[str, int | None]] = {}
        for skud_id, page in zip(ordered_ids, history_results, strict=True):
            passages = page["results"]
            cursor, new_passages = _advance_passage_cursor(
                self._cursors.get(skud_id),
                passages,
            )
            self._cursors[skud_id] = cursor
            if new_passages:
                self.new_passages[skud_id] = [
                    {
                        "key_name": passage["key_name"],
                        "occurred_at": datetime.fromtimestamp(
                            passage["timestamp"],
                            tz=timezone.utc,
                        ).isoformat(),
                    }
                    for passage in new_passages
                ]
            data[skud_id] = {
                "key_count": key_counts[skud_id],
                "last_passage_at": max(
                    (passage["timestamp"] for passage in passages),
                    default=None,
                ),
            }

        if self._cursors != previous_cursors:
            try:
                await self._store.async_save(_serialize_passage_cursors(self._cursors))
            except Exception as err:
                self.new_passages = {}
                self._cursors = previous_cursors
                raise UpdateFailed("Unable to save key-passage cursor state") from err

        return data

    def diagnostic_summary(self) -> dict[str, int]:
        """Return privacy-safe aggregate state for diagnostics."""
        data = self.data if isinstance(self.data, dict) else {}
        return {
            "supported_intercom_count": len(data),
            "registered_key_link_count": sum(
                int(item.get("key_count") or 0) for item in data.values()
            ),
            "intercom_with_history_count": sum(
                item.get("last_passage_at") is not None for item in data.values()
            ),
            "new_passage_batch_count": sum(
                len(items) for items in self.new_passages.values()
            ),
            "stored_cursor_count": len(self._cursors),
        }


def _advance_passage_cursor(
    cursor: _PassageCursor | None,
    passages: list[KeyPassage],
) -> tuple[_PassageCursor, list[KeyPassage]]:
    """Advance one cursor and return only unseen passages in time order."""
    ordered = sorted(
        passages,
        key=lambda passage: (passage["timestamp"], passage["key_id"]),
    )
    if cursor is None:
        if not ordered:
            return _PassageCursor(0, frozenset()), []
        latest = ordered[-1]["timestamp"]
        return (
            _PassageCursor(
                latest,
                frozenset(
                    passage["key_id"]
                    for passage in ordered
                    if passage["timestamp"] == latest
                ),
            ),
            [],
        )

    unseen = [
        passage
        for passage in ordered
        if passage["timestamp"] > cursor.timestamp
        or (
            passage["timestamp"] == cursor.timestamp
            and passage["key_id"] not in cursor.key_ids
        )
    ]
    if not ordered or ordered[-1]["timestamp"] < cursor.timestamp:
        return cursor, unseen

    latest = ordered[-1]["timestamp"]
    latest_ids = {
        passage["key_id"]
        for passage in ordered
        if passage["timestamp"] == latest
    }
    if latest == cursor.timestamp:
        latest_ids.update(cursor.key_ids)
    return _PassageCursor(latest, frozenset(latest_ids)), unseen


def _parse_passage_cursors(data: Any) -> dict[int, _PassageCursor]:
    """Validate private cursor storage without retaining unknown fields."""
    if data is None:
        return {}
    raw_cursors = data.get("intercoms") if isinstance(data, dict) else None
    if not isinstance(raw_cursors, dict):
        raise TypeError("invalid key-passage cursor schema")

    cursors: dict[int, _PassageCursor] = {}
    for raw_skud_id, raw_cursor in raw_cursors.items():
        if not isinstance(raw_cursor, dict):
            raise TypeError("invalid key-passage cursor item")
        try:
            skud_id = int(raw_skud_id)
        except (TypeError, ValueError) as err:
            raise ValueError("invalid key-passage cursor intercom") from err
        timestamp = raw_cursor.get("timestamp")
        raw_key_ids = raw_cursor.get("key_ids")
        if (
            not isinstance(timestamp, int)
            or isinstance(timestamp, bool)
            or timestamp < 0
            or not isinstance(raw_key_ids, list)
            or not all(
                isinstance(key_id, int) and not isinstance(key_id, bool)
                for key_id in raw_key_ids
            )
        ):
            raise ValueError("invalid key-passage cursor fields")
        cursors[skud_id] = _PassageCursor(timestamp, frozenset(raw_key_ids))
    return cursors


def _serialize_passage_cursors(
    cursors: dict[int, _PassageCursor],
) -> dict[str, Any]:
    """Serialize only the private fields required for deduplication."""
    return {
        "intercoms": {
            str(skud_id): {
                "timestamp": cursor.timestamp,
                "key_ids": sorted(cursor.key_ids),
            }
            for skud_id, cursor in sorted(cursors.items())
        }
    }


class UfanetCallCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Poll intercom call history and expose the latest call per camera."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UfanetApi,
        *,
        scan_interval_seconds: int = CALL_SCAN_INTERVAL_SECONDS,
        media_refresh_seconds: int = MEDIA_REFRESH_SECONDS,
    ) -> None:
        self.api = api
        self.scan_interval_seconds = int(scan_interval_seconds)
        self.media_refresh_seconds = int(media_refresh_seconds)
        self.new_calls: list[dict[str, Any]] = []
        self._initialized = False
        self._seen_uuids: set[str] = set()
        self._media_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_calls",
            update_interval=timedelta(seconds=self.scan_interval_seconds),
        )

    @callback
    def async_set_scan_interval(self, scan_interval_seconds: int) -> None:
        """Change call polling interval and reschedule an active coordinator."""
        scan_interval_seconds = int(scan_interval_seconds)
        if scan_interval_seconds == self.scan_interval_seconds:
            return
        self.scan_interval_seconds = scan_interval_seconds
        self.update_interval = timedelta(seconds=scan_interval_seconds)
        if self._listeners:
            self._schedule_refresh()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        # Clear the transient batch before every poll so a failed refresh can
        # never replay calls detected during the previous successful refresh.
        self.new_calls = []
        try:
            events = await self.api.async_get_call_history(page=1, page_size=25)
        except UfanetAuthError as err:
            raise ConfigEntryAuthFailed from err
        except UfanetApiError as err:
            raise UpdateFailed(str(err)) from err

        valid_events = [
            dict(event)
            for event in events
            if isinstance(event, dict) and event.get("uuid")
        ]

        current_uuids = {str(event["uuid"]) for event in valid_events}
        if not self._initialized:
            # Existing history is baseline state, not a new Home Assistant event.
            self._seen_uuids.update(current_uuids)
            self.new_calls = []
            self._initialized = True
        else:
            self.new_calls = [
                event
                for event in valid_events
                if str(event["uuid"]) not in self._seen_uuids
            ]
            self._seen_uuids.update(current_uuids)

        # Keep memory bounded while retaining enough recent UUIDs to suppress
        # duplicates if the server reorders the first history page.
        if len(self._seen_uuids) > 250:
            recent = [str(event["uuid"]) for event in valid_events]
            self._seen_uuids = set(recent[-100:]) | current_uuids

        latest_by_camera: dict[str, dict[str, Any]] = {}
        for event in valid_events:
            camera = event.get("camera_number")
            if not camera:
                continue
            camera = str(camera)
            previous = latest_by_camera.get(camera)
            if previous is None or _event_timestamp(event) > _event_timestamp(previous):
                latest_by_camera[camera] = event

        # Always enrich latest sensor values. Media URLs are cached for a while
        # and refreshed before their short-lived tokens become stale.
        for camera, event in list(latest_by_camera.items()):
            latest_by_camera[camera] = await self._async_enrich_media(event)

        # New events need media even if they are not the latest event for a camera
        # (for example, multiple calls arrive between polls).
        enriched_new: list[dict[str, Any]] = []
        for event in self.new_calls:
            enriched_new.append(await self._async_enrich_media(event))
        self.new_calls = sorted(enriched_new, key=_event_timestamp)

        return latest_by_camera

    async def _async_enrich_media(self, event: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(event)
        uuid = str(enriched.get("uuid") or "")
        if not uuid:
            return enriched

        cached = self._media_cache.get(uuid)
        now = time.monotonic()
        if cached and now - cached[0] < self.media_refresh_seconds:
            media = cached[1]
        else:
            try:
                media = await self.api.async_get_call_media(uuid)
            except UfanetApiError as err:
                _LOGGER.debug(
                    "Unable to obtain call media for %s (%s)",
                    uuid,
                    type(err).__name__,
                )
                return enriched
            self._media_cache[uuid] = (now, media)

        preview = media.get("preview")
        archive = media.get("url")
        if preview:
            enriched["preview_url"] = preview
        if archive:
            enriched["archive_url"] = archive
        return enriched


def _event_timestamp(event: dict[str, Any]) -> datetime:
    """Return an aware timestamp for stable call ordering."""
    value = event.get("called_at")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)
