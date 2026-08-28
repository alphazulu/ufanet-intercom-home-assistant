"""Data coordinators for Ufanet Intercom."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UfanetApi, UfanetApiError, UfanetAuthError
from .const import (
    CALL_SCAN_INTERVAL_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    MEDIA_REFRESH_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


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
                _LOGGER.debug("Unable to obtain call media for %s: %s", uuid, err)
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
