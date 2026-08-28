"""Shared archive playback state for Ufanet Intercom."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .api import UfanetApi, UfanetApiError, UfanetResponseError
from .const import (
    DEFAULT_ARCHIVE_DURATION_SECONDS,
    DEFAULT_ARCHIVE_STEP_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

ArchiveListener = Callable[[], None]


class UfanetArchiveController:
    """Keep archive playback controls synchronized across HA entities."""

    def __init__(
        self,
        api: UfanetApi,
        skud: dict[str, Any],
        *,
        default_duration: int = DEFAULT_ARCHIVE_DURATION_SECONDS,
        default_step: int = DEFAULT_ARCHIVE_STEP_SECONDS,
    ) -> None:
        self.api = api
        self.skud_id = int(skud["id"])
        self.camera_number = str(skud["cctv_number"])

        # UTC internally; Home Assistant renders aware datetimes in the UI time zone.
        self.position = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.duration = int(default_duration)
        self.step = int(default_step)

        self.timezone_name = "UTC"
        self.archive_name: str | None = None
        self.dvr_hours: int | None = None
        self.ready = False

        self.last_archive: dict[str, Any] | None = None
        self._listeners: set[ArchiveListener] = set()

    async def async_initialize(self) -> None:
        """Load camera metadata and start at the newest recorded archive."""
        try:
            camera = await self.api.async_get_camera(self.camera_number)
            self._update_camera_metadata(camera)
            ranges = await self.api.async_get_archive_ranges(self.camera_number)
            if ranges:
                newest = max(
                    ranges,
                    key=lambda item: int(item["from"]) + int(item["duration"]),
                )
                start = int(newest["from"])
                end = start + int(newest["duration"])
                initial = max(start, end - self.duration)
                self.position = datetime.fromtimestamp(initial, tz=timezone.utc)
            self.ready = True
        except UfanetApiError as err:
            # Archive is an optional extension; it must not break the main intercom.
            _LOGGER.warning(
                "Unable to initialize archive for camera %s: %s",
                self.camera_number,
                err,
            )

    def async_add_listener(self, listener: ArchiveListener) -> Callable[[], None]:
        """Subscribe an entity to archive control changes."""
        self._listeners.add(listener)

        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def _invalidate(self) -> None:
        self.last_archive = None
        self._notify()

    async def async_set_position(self, value: datetime) -> None:
        """Set playback position after verifying recording exists."""
        if value.tzinfo is None:
            raise HomeAssistantError("Archive position must contain timezone information")

        target = int(value.timestamp())
        ranges = await self._get_ranges()
        if not self._contains(ranges, target):
            raise HomeAssistantError("No Ufanet archive recording exists at selected time")

        self.position = datetime.fromtimestamp(target, tz=timezone.utc)
        self._invalidate()

    async def async_set_duration(self, value: int) -> None:
        """Set requested playback clip duration."""
        self.duration = int(value)
        self._invalidate()

    async def async_set_step(self, value: int) -> None:
        """Set rewind/forward step."""
        self.step = int(value)
        self._notify()

    async def async_shift(self, direction: int) -> None:
        """Move backward/forward and automatically skip recording gaps."""
        direction = -1 if direction < 0 else 1
        ranges = await self._get_ranges()
        if not ranges:
            raise HomeAssistantError("No Ufanet archive ranges are available")

        current = int(self.position.timestamp())
        target = current + direction * self.step
        resolved = self._resolve_target(ranges, target, direction)

        if resolved is None:
            raise HomeAssistantError(
                "There is no older archive recording"
                if direction < 0
                else "There is no newer archive recording"
            )

        self.position = datetime.fromtimestamp(resolved, tz=timezone.utc)
        self._invalidate()

    async def async_go_latest(self) -> None:
        """Jump to the newest useful point of the latest recorded range."""
        ranges = await self._get_ranges()
        if not ranges:
            raise HomeAssistantError("No Ufanet archive ranges are available")

        newest = max(
            ranges,
            key=lambda item: int(item["from"]) + int(item["duration"]),
        )
        start = int(newest["from"])
        end = start + int(newest["duration"])
        target = max(start, end - self.duration)
        self.position = datetime.fromtimestamp(target, tz=timezone.utc)
        self._invalidate()

    async def async_get_stream_url(self) -> str:
        """Return a validated archive HLS URL for the selected position."""
        try:
            archive = await self.api.async_get_archive_url(
                self.camera_number,
                int(self.position.timestamp()),
                self.duration,
            )
        except UfanetResponseError as err:
            raise HomeAssistantError(str(err)) from err
        except UfanetApiError as err:
            raise HomeAssistantError(f"Unable to load Ufanet archive: {err}") from err

        self.last_archive = archive
        return str(archive["url"])

    async def _get_ranges(self) -> list[dict[str, int]]:
        try:
            camera = await self.api.async_get_camera(self.camera_number)
            self._update_camera_metadata(camera)
            ranges = await self.api.async_get_archive_ranges(self.camera_number)
        except UfanetApiError as err:
            raise HomeAssistantError(f"Unable to load Ufanet archive ranges: {err}") from err
        self.ready = True
        return sorted(ranges, key=lambda item: int(item["from"]))

    def _update_camera_metadata(self, camera: dict[str, Any]) -> None:
        self.timezone_name = str(camera.get("timezone") or "UTC")
        tariff = camera.get("tariff")
        if isinstance(tariff, dict):
            self.archive_name = tariff.get("name")
            dvr_hours = tariff.get("dvr_hours")
            try:
                self.dvr_hours = int(dvr_hours) if dvr_hours is not None else None
            except (TypeError, ValueError):
                self.dvr_hours = None

    @staticmethod
    def _contains(ranges: list[dict[str, int]], timestamp: int) -> bool:
        return any(
            int(item["from"])
            <= timestamp
            < int(item["from"]) + int(item["duration"])
            for item in ranges
        )

    @staticmethod
    def _resolve_target(
        ranges: list[dict[str, int]],
        target: int,
        direction: int,
    ) -> int | None:
        """Resolve a target inside recording, skipping gaps in movement direction."""
        for item in ranges:
            start = int(item["from"])
            end = start + int(item["duration"])
            if start <= target < end:
                return target

        if direction > 0:
            for item in ranges:
                start = int(item["from"])
                if start > target:
                    return start
            return None

        for item in reversed(ranges):
            start = int(item["from"])
            end = start + int(item["duration"])
            if end <= target:
                return max(start, end - 1)
        return None
