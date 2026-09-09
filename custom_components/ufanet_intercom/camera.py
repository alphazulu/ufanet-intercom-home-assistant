"""Camera platform for Ufanet Intercom."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UfanetApi, UfanetApiError
from .archive import UfanetArchiveController
from .const import DOMAIN
from .coordinator import UfanetCoordinator
from .entity import device_info
from .private_cameras import UcamsPrivateCamera, UfanetPrivateCameraCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ufanet/UCAMS cameras."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]
    api: UfanetApi = runtime["api"]

    controllers: dict[int, UfanetArchiveController] = runtime["archive_controllers"]

    intercom_numbers = {
        str(skud["cctv_number"])
        for skud in coordinator.data.values()
        if skud.get("cctv_number")
    }
    private_camera_coordinator = UfanetPrivateCameraCoordinator(hass, api)
    runtime["private_camera_coordinator"] = private_camera_coordinator

    # Account-wide video surveillance is optional. Failure of this independent
    # endpoint must not block the already supported intercom cameras.
    await private_camera_coordinator.async_refresh()
    if private_camera_coordinator.data is None:
        private_camera_coordinator.data = {}

    entities: list[Camera] = []
    for skud in coordinator.data.values():
        if not skud.get("cctv_number"):
            continue
        entities.append(UfanetIntercomCamera(coordinator, api, skud))
        controller = controllers.get(int(skud["id"]))
        if controller is not None:
            entities.append(UfanetArchiveCamera(coordinator, controller, skud))

    added_private_numbers: set[str] = set()
    for camera in private_camera_coordinator.data.values():
        number = camera["number"]
        if number in intercom_numbers:
            continue
        added_private_numbers.add(number)
        entities.append(UfanetPrivateCamera(private_camera_coordinator, api, camera))

    async_add_entities(entities)

    def _handle_private_camera_update() -> None:
        """Add newly discovered standalone cameras without duplicating intercom cameras."""
        new_entities: list[Camera] = []
        data = private_camera_coordinator.data or {}
        for camera in data.values():
            number = camera["number"]
            if number in intercom_numbers or number in added_private_numbers:
                continue
            added_private_numbers.add(number)
            new_entities.append(
                UfanetPrivateCamera(private_camera_coordinator, api, camera)
            )
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        private_camera_coordinator.async_add_listener(_handle_private_camera_update)
    )


class UfanetIntercomCamera(Camera):
    """UCAMS-backed live camera associated with a Ufanet intercom."""

    _attr_has_entity_name = True
    _attr_translation_key = "camera"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: UfanetCoordinator,
        api: UfanetApi,
        skud: dict[str, Any],
    ) -> None:
        super().__init__()
        self.coordinator = coordinator
        self.api = api
        self.skud_id = int(skud["id"])
        self.camera_number = str(skud["cctv_number"])
        self._attr_unique_id = f"{self.skud_id}_camera_{self.camera_number}"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        """Return whether the parent intercom is currently available to the account."""
        if not self.coordinator.last_update_success:
            return False
        skud = self.coordinator.data.get(self.skud_id)
        return bool(
            skud
            and skud.get("cctv_number") == self.camera_number
            and not skud.get("is_blocked")
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        """Return a current JPEG snapshot."""
        try:
            # UCAMS supports a ~600 variant; use it only for small requests.
            small = bool(width is not None and width <= 600)
            return await self.api.async_get_snapshot(self.camera_number, small=small)
        except UfanetApiError as err:
            _LOGGER.warning(
                "Unable to fetch Ufanet snapshot for %s: %s",
                self.camera_number,
                err,
            )
            return None

    async def stream_source(self) -> str | None:
        """Return a fresh HLS live-stream URL usable by Home Assistant stream/ffmpeg."""
        try:
            return await self.api.async_get_hls_url(
                self.camera_number,
                stream_number=1,
            )
        except UfanetApiError as err:
            _LOGGER.warning(
                "Unable to obtain Ufanet HLS stream for %s: %s",
                self.camera_number,
                err,
            )
            return None


class UfanetPrivateCamera(Camera):
    """Account-wide UCAMS video-surveillance camera not tied to an intercom."""

    _attr_has_entity_name = True
    _attr_translation_key = "camera"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: UfanetPrivateCameraCoordinator,
        api: UfanetApi,
        camera: UcamsPrivateCamera,
    ) -> None:
        super().__init__()
        self.coordinator = coordinator
        self.api = api
        self.camera_number = camera["number"]
        camera_ref = hashlib.sha256(self.camera_number.encode("utf-8")).hexdigest()[:20]
        self._attr_unique_id = f"ucams_private_camera_{camera_ref}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"ucams_camera_{camera_ref}")},
            name=_private_camera_name(camera),
            manufacturer="Ufanet",
            model="UCAMS video surveillance camera",
        )

    @property
    def available(self) -> bool:
        """Return whether this camera is still present in the private inventory."""
        return bool(
            self.coordinator.last_update_success
            and self.camera_number in (self.coordinator.data or {})
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to account-wide camera inventory updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        """Return a current JPEG snapshot through the existing UCAMS media path."""
        try:
            small = bool(width is not None and width <= 600)
            return await self.api.async_get_snapshot(self.camera_number, small=small)
        except UfanetApiError as err:
            _LOGGER.warning(
                "Unable to fetch UCAMS private camera snapshot: %s",
                err,
            )
            return None

    async def stream_source(self) -> str | None:
        """Return a fresh HLS URL through the existing UCAMS media path."""
        try:
            return await self.api.async_get_hls_url(
                self.camera_number,
                stream_number=1,
            )
        except UfanetApiError as err:
            _LOGGER.warning(
                "Unable to obtain UCAMS private camera HLS stream: %s",
                err,
            )
            return None


def _private_camera_name(camera: UcamsPrivateCamera) -> str:
    """Return the official camera title, falling back to address without IDs."""
    return camera.get("title") or camera.get("address") or "Ufanet video camera"


class UfanetArchiveCamera(Camera):
    """Virtual camera that plays the selected UCAMS archive interval."""

    _attr_has_entity_name = True
    _attr_translation_key = "archive_camera"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: UfanetCoordinator,
        controller: UfanetArchiveController,
        skud: dict[str, Any],
    ) -> None:
        super().__init__()
        self.coordinator = coordinator
        self.controller = controller
        self.skud_id = int(skud["id"])
        self.camera_number = str(skud["cctv_number"])
        self._attr_unique_id = f"{self.skud_id}_archive_camera_{self.camera_number}"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        skud = self.coordinator.data.get(self.skud_id)
        return bool(
            skud
            and skud.get("cctv_number") == self.camera_number
            and not skud.get("is_blocked")
        )

    @property
    def use_stream_for_stills(self) -> bool:
        """Let HA extract the archive keyframe for the entity picture."""
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        self.async_on_remove(
            self.controller.async_add_listener(self._handle_archive_change)
        )

    def _handle_archive_change(self) -> None:
        """Refresh state and, if open, restart the existing HA stream source."""
        self.async_write_ha_state()
        if self.stream is not None:
            self.hass.async_create_task(self._async_update_stream_source())

    async def _async_update_stream_source(self) -> None:
        try:
            new_source = await self.controller.async_get_stream_url()
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Unable to switch Ufanet archive stream for %s: %s",
                self.camera_number,
                err,
            )
            return
        if self.stream is not None:
            self.stream.update_source(new_source)
        self.async_update_token()
        self.async_write_ha_state()

    async def stream_source(self) -> str | None:
        try:
            return await self.controller.async_get_stream_url()
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Unable to obtain Ufanet archive stream for %s: %s",
                self.camera_number,
                err,
            )
            return None
