"""Image platform for Ufanet Intercom."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UfanetApi
from .const import DOMAIN
from .coordinator import UfanetCallCoordinator, UfanetCoordinator
from .entity import device_info

_LOGGER = logging.getLogger(__name__)

PREVIEW_FRAME_TIMEOUT_SECONDS = 45
PREVIEW_FRAME_RETRY_SECONDS = 300
PREVIEW_FRAME_MAX_BYTES = 8 * 1024 * 1024


class UfanetPreviewFrameError(Exception):
    """Raised when a JPEG frame cannot be extracted from a call preview."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up last-call image entities."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]
    call_coordinator: UfanetCallCoordinator = runtime["call_coordinator"]
    api: UfanetApi = runtime["api"]

    async_add_entities(
        UfanetLastCallImage(hass, call_coordinator, api, skud)
        for skud in coordinator.data.values()
        if skud.get("cctv_number")
    )


class UfanetLastCallImage(ImageEntity):
    """JPEG frame extracted privately from the latest confirmed call preview."""

    _attr_content_type = "image/jpeg"
    _attr_has_entity_name = True
    _attr_translation_key = "last_call"

    def __init__(
        self,
        hass: HomeAssistant,
        call_coordinator: UfanetCallCoordinator,
        api: UfanetApi,
        skud: dict[str, Any],
    ) -> None:
        super().__init__(hass)
        self.call_coordinator = call_coordinator
        self.api = api
        self.skud_id = int(skud["id"])
        self.camera_number = str(skud["cctv_number"])
        self._attr_unique_id = f"{self.skud_id}_last_call_image"
        self._attr_device_info = device_info(skud)

        self._image_bytes: bytes | None = None
        self._loaded_uuid: str | None = None
        self._loading_uuid: str | None = None
        self._last_attempted_uuid: str | None = None
        self._last_attempt_at = 0.0
        self._load_task: asyncio.Task[None] | None = None

    @property
    def available(self) -> bool:
        """Return call-history coordinator availability."""
        return self.call_coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """Subscribe to call-history updates and load the current latest call."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.call_coordinator.async_add_listener(self._handle_call_update)
        )
        self.async_on_remove(self._cancel_load_task)
        self._handle_call_update()

    async def async_image(self) -> bytes | None:
        """Return only the cached JPEG; tokenized media URLs remain private."""
        return self._image_bytes

    @callback
    def _handle_call_update(self) -> None:
        """Schedule frame extraction when the latest confirmed call changes."""
        event = self.call_coordinator.data.get(self.camera_number)
        if not event:
            self.async_write_ha_state()
            return

        uuid = str(event.get("uuid") or "")
        preview_url = event.get("preview_url")
        if not uuid or not isinstance(preview_url, str) or not preview_url:
            self.async_write_ha_state()
            return
        if uuid == self._loaded_uuid or uuid == self._loading_uuid:
            self.async_write_ha_state()
            return

        now = time.monotonic()
        if (
            uuid == self._last_attempted_uuid
            and now - self._last_attempt_at < PREVIEW_FRAME_RETRY_SECONDS
        ):
            self.async_write_ha_state()
            return

        self._cancel_load_task()
        self._loading_uuid = uuid
        self._last_attempted_uuid = uuid
        self._last_attempt_at = now
        self._load_task = self.hass.async_create_task(
            self._async_refresh_image(
                uuid,
                preview_url,
                event.get("called_at"),
            ),
            f"{DOMAIN}_last_call_image_{self.skud_id}",
        )
        self.async_write_ha_state()

    async def _async_refresh_image(
        self,
        uuid: str,
        preview_url: str,
        called_at: Any,
    ) -> None:
        """Download the preview and atomically replace the cached JPEG frame."""
        current_task = asyncio.current_task()
        try:
            preview = await self.api.async_get_call_preview(preview_url)
            image = await _async_extract_preview_frame(preview)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - isolate this optional background task
            _LOGGER.warning(
                "Unable to generate Ufanet last-call image (%s)",
                type(err).__name__,
            )
            return
        finally:
            if self._loading_uuid == uuid:
                self._loading_uuid = None
            if self._load_task is current_task:
                self._load_task = None

        current = self.call_coordinator.data.get(self.camera_number)
        if not current or str(current.get("uuid") or "") != uuid:
            return

        self._image_bytes = image
        self._loaded_uuid = uuid
        self._attr_image_last_updated = _call_timestamp(called_at)
        self.async_update_token()
        self.async_write_ha_state()

    @callback
    def _cancel_load_task(self) -> None:
        """Cancel an obsolete or unloading frame-extraction task."""
        if self._load_task is not None:
            self._load_task.cancel()
            self._load_task = None


async def _async_extract_preview_frame(preview: bytes) -> bytes:
    """Extract one JPEG frame without passing a tokenized URL to ffmpeg."""
    command = (
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ss",
        "1",
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "pipe:1",
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as err:
        raise UfanetPreviewFrameError("ffmpeg executable is unavailable") from err

    try:
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(input=preview),
            timeout=PREVIEW_FRAME_TIMEOUT_SECONDS,
        )
    except TimeoutError as err:
        process.kill()
        await process.communicate()
        raise UfanetPreviewFrameError("ffmpeg frame extraction timed out") from err

    if process.returncode != 0:
        raise UfanetPreviewFrameError("ffmpeg could not decode the call preview")
    if not stdout.startswith(b"\xff\xd8"):
        raise UfanetPreviewFrameError("ffmpeg did not return a JPEG frame")
    if len(stdout) > PREVIEW_FRAME_MAX_BYTES:
        raise UfanetPreviewFrameError("JPEG frame exceeds the in-memory size limit")
    return stdout


def _call_timestamp(value: Any) -> datetime:
    """Return an aware timestamp describing the cached call image."""
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)
