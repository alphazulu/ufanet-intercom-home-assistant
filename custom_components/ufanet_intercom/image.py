"""Image platform for Ufanet Intercom."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    UfanetApi,
    UfanetAuthError,
    UfanetCallPreviewError,
    UfanetConnectionError,
    normalize_call_preview_url,
)
from .const import DOMAIN
from .coordinator import UfanetCallCoordinator, UfanetCoordinator
from .entity import device_info
from .image_status import UfanetLastCallImageStatusManager

_LOGGER = logging.getLogger(__name__)

PREVIEW_FRAME_TIMEOUT_SECONDS = 45
PREVIEW_FRAME_RETRY_SECONDS = 300
PREVIEW_FRAME_MAX_BYTES = 8 * 1024 * 1024


class UfanetPreviewFrameError(Exception):
    """Raised when a JPEG frame cannot be extracted from a call preview."""


class UfanetFfmpegUnavailableError(UfanetPreviewFrameError):
    """Raised when the local ffmpeg executable cannot be started."""


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
    status_manager: UfanetLastCallImageStatusManager = runtime["image_status_manager"]

    async_add_entities(
        UfanetLastCallImage(hass, call_coordinator, api, status_manager, skud)
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
        status_manager: UfanetLastCallImageStatusManager,
        skud: dict[str, Any],
    ) -> None:
        super().__init__(hass)
        self.call_coordinator = call_coordinator
        self.api = api
        self.status_manager = status_manager
        self.skud_id = int(skud["id"])
        self.camera_number = str(skud["cctv_number"])
        self._attr_unique_id = f"{self.skud_id}_last_call_image"
        self._attr_device_info = device_info(skud)

        self._image_bytes: bytes | None = None
        self._loaded_uuid: str | None = None
        self._loading_uuid: str | None = None
        self._last_attempted_uuid: str | None = None
        self._terminal_failure_uuid: str | None = None
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
            self.status_manager.set_preview_available(self.skud_id, False)
            self.async_write_ha_state()
            return

        uuid = str(event.get("uuid") or "")
        preview_url = event.get("preview_url")
        self.status_manager.set_preview_available(
            self.skud_id,
            isinstance(preview_url, str) and bool(preview_url),
        )
        if not uuid or not isinstance(preview_url, str) or not preview_url:
            self.async_write_ha_state()
            return
        if uuid == self._loaded_uuid or uuid == self._loading_uuid:
            self.async_write_ha_state()
            return
        if uuid == self._terminal_failure_uuid:
            self.status_manager.set_retry_suppressed(self.skud_id, True)
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
        self.status_manager.set_preview_payload_kind(self.skud_id, None)
        self.status_manager.set_retry_suppressed(self.skud_id, False)
        self.status_manager.mark_loading(self.skud_id)
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
            try:
                self.status_manager.set_preview_https_upgraded(
                    self.skud_id,
                    False,
                )
                normalized_url, upgraded = normalize_call_preview_url(preview_url)
                self.status_manager.set_preview_https_upgraded(
                    self.skud_id,
                    upgraded,
                )
                preview = await self.api.async_get_call_preview(normalized_url)
                self.status_manager.set_preview_payload_kind(
                    self.skud_id,
                    _preview_payload_kind(preview),
                )
            except asyncio.CancelledError:
                self.status_manager.mark_cancelled(self.skud_id)
                raise
            except Exception as err:  # noqa: BLE001 - isolate optional download
                error_code = _preview_download_error_code(err)
                if isinstance(err, UfanetCallPreviewError):
                    self._terminal_failure_uuid = uuid
                    self.status_manager.set_retry_suppressed(self.skud_id, True)
                self.status_manager.mark_failure(
                    self.skud_id,
                    type(err).__name__,
                    error_code=error_code,
                )
                _LOGGER.warning(
                    "Unable to generate Ufanet last-call image (%s, reason=%s)",
                    type(err).__name__,
                    error_code,
                )
                return

            try:
                image = await _async_extract_preview_frame(preview)
            except asyncio.CancelledError:
                self.status_manager.mark_cancelled(self.skud_id)
                raise
            except Exception as err:  # noqa: BLE001 - isolate optional ffmpeg
                error_code = _preview_extract_error_code(err)
                if isinstance(err, UfanetPreviewFrameError) and not isinstance(
                    err,
                    UfanetFfmpegUnavailableError,
                ):
                    self._terminal_failure_uuid = uuid
                    self.status_manager.set_retry_suppressed(self.skud_id, True)
                self.status_manager.mark_failure(
                    self.skud_id,
                    type(err).__name__,
                    error_code=error_code,
                    ffmpeg_available=(
                        False
                        if isinstance(err, UfanetFfmpegUnavailableError)
                        else (
                            True if isinstance(err, UfanetPreviewFrameError) else None
                        )
                    ),
                )
                _LOGGER.warning(
                    "Unable to generate Ufanet last-call image (%s, reason=%s)",
                    type(err).__name__,
                    error_code,
                )
                return

            current = self.call_coordinator.data.get(self.camera_number)
            if not current or str(current.get("uuid") or "") != uuid:
                self.status_manager.mark_cancelled(self.skud_id)
                return

            self._image_bytes = image
            self._loaded_uuid = uuid
            self._terminal_failure_uuid = None
            self.status_manager.set_retry_suppressed(self.skud_id, False)
            self._attr_image_last_updated = _call_timestamp(called_at)
            self.async_update_token()
            self.status_manager.mark_success(self.skud_id)
            self.async_write_ha_state()
        finally:
            if self._loading_uuid == uuid:
                self._loading_uuid = None
            if self._load_task is current_task:
                self._load_task = None

    @callback
    def _cancel_load_task(self) -> None:
        """Cancel an obsolete or unloading frame-extraction task."""
        if self._load_task is not None:
            self._load_task.cancel()
            self._load_task = None
        self.status_manager.mark_cancelled(self.skud_id)


def _preview_download_error_code(err: Exception) -> str:
    """Map preview download failures to a fixed, credential-free reason code."""
    if isinstance(err, UfanetCallPreviewError):
        return err.code
    if isinstance(err, (UfanetAuthError, UfanetConnectionError)):
        return "download_error"
    return "unexpected_error"


def _preview_extract_error_code(err: Exception) -> str:
    """Map local extraction failures to a fixed, credential-free reason code."""
    if isinstance(err, UfanetFfmpegUnavailableError):
        return "ffmpeg_unavailable"
    if isinstance(err, UfanetPreviewFrameError):
        return "decode_error"
    return "unexpected_error"


def _preview_payload_kind(preview: bytes) -> str:
    """Return a fixed, privacy-safe media signature classification."""
    if preview.startswith(b"\xff\xd8"):
        return "jpeg"
    if preview.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if preview.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if preview.startswith(b"\x1aE\xdf\xa3"):
        return "webm"
    if len(preview) >= 12 and preview[4:8] == b"ftyp":
        return "mp4"
    if (
        len(preview) >= 377
        and preview[0] == 0x47
        and preview[188] == 0x47
        and preview[376] == 0x47
    ):
        return "mpeg_ts"
    return "unknown"


async def _async_extract_preview_frame(preview: bytes) -> bytes:
    """Extract a JPEG from an anonymous seekable in-memory MP4 source."""
    try:
        preview_fd = await asyncio.to_thread(_create_preview_memfd_sync, preview)
    except OSError as err:
        raise UfanetPreviewFrameError(
            "seekable in-memory preview storage is unavailable"
        ) from err

    try:
        try:
            return await _async_run_preview_ffmpeg(
                preview_fd,
                seek_seconds=1,
            )
        except UfanetFfmpegUnavailableError:
            raise
        except UfanetPreviewFrameError:
            return await _async_run_preview_ffmpeg(
                preview_fd,
                seek_seconds=None,
            )
    finally:
        os.close(preview_fd)


def _create_preview_memfd_sync(preview: bytes) -> int:
    """Copy private media into an anonymous seekable memory file."""
    if not hasattr(os, "memfd_create"):
        raise OSError("memfd is unavailable")

    fd = os.memfd_create("ufanet-call-preview", flags=os.MFD_CLOEXEC)
    try:
        remaining = memoryview(preview)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("unable to populate preview memfd")
            remaining = remaining[written:]
        os.lseek(fd, 0, os.SEEK_SET)
        return fd
    except Exception:
        os.close(fd)
        raise


async def _async_run_preview_ffmpeg(
    preview_fd: int,
    *,
    seek_seconds: int | None,
) -> bytes:
    """Run one private byte-stream extraction attempt."""
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        f"/proc/self/fd/{preview_fd}",
    ]
    if seek_seconds is not None:
        command.extend(("-ss", str(seek_seconds)))
    command.extend(
        (
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        )
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            pass_fds=(preview_fd,),
        )
    except OSError as err:
        raise UfanetFfmpegUnavailableError("ffmpeg executable is unavailable") from err

    try:
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(),
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
