"""Home Assistant entities for standalone UCAMS cameras."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, ClassVar

from homeassistant.components.button import ButtonEntity
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.event import EventEntity
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UfanetApiError
from .archive import UfanetArchiveController
from .private_runtime import (
    UfanetPrivateCameraRuntime,
    async_ensure_private_camera_runtime,
    private_camera_device_info,
    private_camera_supports_archive,
)

_LOGGER = logging.getLogger(__name__)


def _camera_suffix(target_ref: str) -> str:
    """Return the opaque digest part used in stable entity unique IDs."""
    return target_ref.removeprefix("ucams_camera_")


def _supports_private_runtime(runtime: dict[str, Any]) -> bool:
    """Return whether this is a full integration runtime rather than a unit-test stub."""
    coordinator = runtime.get("coordinator")
    return bool(
        runtime.get("api") is not None
        and callable(getattr(coordinator, "async_add_listener", None))
    )


async def async_setup_private_camera_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    runtime: dict[str, Any],
) -> None:
    """Add live and virtual archive cameras for standalone UCAMS devices."""
    if not _supports_private_runtime(runtime):
        return
    manager = await async_ensure_private_camera_runtime(hass, entry, runtime)
    added_live: set[str] = set()
    added_archive: set[str] = set()

    @callback
    def add_entities() -> None:
        entities: list[Camera] = []
        for target_ref, camera in manager.standalone_cameras().items():
            if target_ref not in added_live:
                added_live.add(target_ref)
                entities.append(UfanetStandaloneCamera(manager, target_ref, camera))

            controller = manager.archive_controllers.get(target_ref)
            if (
                controller is not None
                and private_camera_supports_archive(camera)
                and target_ref not in added_archive
            ):
                added_archive.add(target_ref)
                entities.append(
                    UfanetStandaloneArchiveCamera(
                        manager,
                        target_ref,
                        camera,
                        controller,
                    )
                )
        if entities:
            async_add_entities(entities)

    add_entities()
    entry.async_on_unload(manager.async_add_listener(add_entities))


async def async_setup_private_datetime_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    runtime: dict[str, Any],
) -> None:
    """Add archive position controls for standalone cameras."""
    if not _supports_private_runtime(runtime):
        return
    manager = await async_ensure_private_camera_runtime(hass, entry, runtime)
    added: set[str] = set()

    @callback
    def add_entities() -> None:
        entities: list[DateTimeEntity] = []
        for target_ref, camera in manager.standalone_cameras().items():
            controller = manager.archive_controllers.get(target_ref)
            if controller is None or target_ref in added:
                continue
            added.add(target_ref)
            entities.append(
                UfanetStandaloneArchiveDateTime(
                    manager,
                    target_ref,
                    camera,
                    controller,
                )
            )
        if entities:
            async_add_entities(entities)

    add_entities()
    entry.async_on_unload(manager.async_add_listener(add_entities))


async def async_setup_private_number_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    runtime: dict[str, Any],
) -> None:
    """Add archive duration and navigation-step controls for standalone cameras."""
    if not _supports_private_runtime(runtime):
        return
    manager = await async_ensure_private_camera_runtime(hass, entry, runtime)
    added: set[str] = set()

    @callback
    def add_entities() -> None:
        entities: list[NumberEntity] = []
        for target_ref, camera in manager.standalone_cameras().items():
            controller = manager.archive_controllers.get(target_ref)
            if controller is None or target_ref in added:
                continue
            added.add(target_ref)
            entities.extend(
                (
                    UfanetStandaloneArchiveDuration(
                        manager,
                        target_ref,
                        camera,
                        controller,
                    ),
                    UfanetStandaloneArchiveStep(
                        manager,
                        target_ref,
                        camera,
                        controller,
                    ),
                )
            )
        if entities:
            async_add_entities(entities)

    add_entities()
    entry.async_on_unload(manager.async_add_listener(add_entities))


async def async_setup_private_button_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    runtime: dict[str, Any],
) -> None:
    """Add archive previous/next/latest buttons for standalone cameras."""
    if not _supports_private_runtime(runtime):
        return
    manager = await async_ensure_private_camera_runtime(hass, entry, runtime)
    added: set[str] = set()

    @callback
    def add_entities() -> None:
        entities: list[ButtonEntity] = []
        for target_ref, camera in manager.standalone_cameras().items():
            controller = manager.archive_controllers.get(target_ref)
            if controller is None or target_ref in added:
                continue
            added.add(target_ref)
            entities.extend(
                UfanetStandaloneArchiveNavigationButton(
                    manager,
                    target_ref,
                    camera,
                    controller,
                    action,
                )
                for action in ("previous", "next", "latest")
            )
        if entities:
            async_add_entities(entities)

    add_entities()
    entry.async_on_unload(manager.async_add_listener(add_entities))


async def async_setup_private_event_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    runtime: dict[str, Any],
) -> None:
    """Add motion EventEntity objects after the private analytics baseline is ready."""
    if not _supports_private_runtime(runtime):
        return
    manager = await async_ensure_private_camera_runtime(hass, entry, runtime)
    coordinator = manager.analytics_coordinator
    added: set[str] = set()

    @callback
    def add_entities() -> None:
        data = coordinator.data
        if not isinstance(data, dict):
            return
        entities: list[EventEntity] = []
        for target_ref in data:
            if target_ref in added:
                continue
            camera = manager.camera_for_target(target_ref)
            if camera is None:
                continue
            added.add(target_ref)
            entities.append(
                UfanetStandaloneMotionEvent(
                    manager,
                    target_ref,
                    camera,
                )
            )
        if entities:
            async_add_entities(entities)

    add_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_entities))


class _StandaloneEntityMixin:
    """Shared private-camera identity and availability helpers."""

    manager: UfanetPrivateCameraRuntime
    target_ref: str
    camera_number: str

    def _init_private_identity(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
    ) -> None:
        self.manager = manager
        self.target_ref = target_ref
        self.camera_number = str(camera["number"])
        self._attr_device_info = private_camera_device_info(camera)  # type: ignore[arg-type]

    async def _async_subscribe_private_runtime(self) -> None:
        self.async_on_remove(  # type: ignore[attr-defined]
            self.manager.async_add_listener(self.async_write_ha_state)  # type: ignore[attr-defined]
        )


class UfanetStandaloneCamera(_StandaloneEntityMixin, Camera):
    """Account-wide UCAMS live camera not tied to an intercom."""

    _attr_has_entity_name = True
    _attr_translation_key = "camera"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
    ) -> None:
        super().__init__()
        self._init_private_identity(manager, target_ref, camera)
        self._attr_unique_id = f"ucams_private_camera_{_camera_suffix(target_ref)}"

    @property
    def available(self) -> bool:
        return self.manager.camera_available(self.target_ref)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_subscribe_private_runtime()

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        try:
            small = bool(width is not None and width <= 600)
            return await self.manager.api.async_get_snapshot(
                self.camera_number,
                small=small,
            )
        except UfanetApiError as err:
            _LOGGER.warning("Unable to fetch UCAMS private camera snapshot: %s", err)
            return None

    async def stream_source(self) -> str | None:
        try:
            return await self.manager.api.async_get_hls_url(
                self.camera_number,
                stream_number=1,
            )
        except UfanetApiError as err:
            _LOGGER.warning("Unable to obtain UCAMS private camera HLS stream: %s", err)
            return None


class UfanetStandaloneArchiveCamera(_StandaloneEntityMixin, Camera):
    """Virtual archive camera for one standalone UCAMS device."""

    _attr_has_entity_name = True
    _attr_translation_key = "archive_camera"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
        controller: UfanetArchiveController,
    ) -> None:
        super().__init__()
        self._init_private_identity(manager, target_ref, camera)
        self.controller = controller
        self._attr_unique_id = (
            f"ucams_private_archive_camera_{_camera_suffix(target_ref)}"
        )

    @property
    def available(self) -> bool:
        return self.manager.archive_available(self.target_ref)

    @property
    def use_stream_for_stills(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_subscribe_private_runtime()
        self.async_on_remove(
            self.controller.async_add_listener(self._handle_archive_change)
        )

    def _handle_archive_change(self) -> None:
        self.async_write_ha_state()
        if self.stream is not None:
            self.hass.async_create_task(self._async_update_stream_source())

    async def _async_update_stream_source(self) -> None:
        try:
            new_source = await self.controller.async_get_stream_url()
        except HomeAssistantError as err:
            _LOGGER.warning("Unable to switch standalone UCAMS archive stream: %s", err)
            return
        if self.stream is not None:
            self.stream.update_source(new_source)
        self.async_update_token()
        self.async_write_ha_state()

    async def stream_source(self) -> str | None:
        try:
            return await self.controller.async_get_stream_url()
        except HomeAssistantError as err:
            _LOGGER.warning("Unable to obtain standalone UCAMS archive stream: %s", err)
            return None


class UfanetStandaloneArchiveDateTime(_StandaloneEntityMixin, DateTimeEntity):
    """Archive playback position for a standalone UCAMS camera."""

    _attr_has_entity_name = True
    _attr_translation_key = "archive_position"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
        controller: UfanetArchiveController,
    ) -> None:
        self._init_private_identity(manager, target_ref, camera)
        self.controller = controller
        self._attr_unique_id = f"{target_ref}_archive_position"

    @property
    def available(self) -> bool:
        return self.manager.archive_available(self.target_ref)

    @property
    def native_value(self) -> datetime:
        return self.controller.position

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "camera_timezone": self.controller.timezone_name,
            "archive_name": self.controller.archive_name,
            "dvr_hours": self.controller.dvr_hours,
        }

    async def async_set_value(self, value: datetime) -> None:
        await self.controller.async_set_position(value)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_subscribe_private_runtime()
        self.async_on_remove(
            self.controller.async_add_listener(self.async_write_ha_state)
        )


class _StandaloneArchiveNumber(_StandaloneEntityMixin, NumberEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
        controller: UfanetArchiveController,
    ) -> None:
        self._init_private_identity(manager, target_ref, camera)
        self.controller = controller

    @property
    def available(self) -> bool:
        return self.manager.archive_available(self.target_ref)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_subscribe_private_runtime()
        self.async_on_remove(
            self.controller.async_add_listener(self.async_write_ha_state)
        )


class UfanetStandaloneArchiveDuration(_StandaloneArchiveNumber):
    """Requested archive clip duration for a standalone camera."""

    _attr_translation_key = "archive_duration"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 30
    _attr_native_max_value = 3600
    _attr_native_step = 30

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
        controller: UfanetArchiveController,
    ) -> None:
        super().__init__(manager, target_ref, camera, controller)
        self._attr_unique_id = f"{target_ref}_archive_duration"

    @property
    def native_value(self) -> float:
        return float(self.controller.duration)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_duration(int(value))


class UfanetStandaloneArchiveStep(_StandaloneArchiveNumber):
    """Archive navigation step for a standalone camera."""

    _attr_translation_key = "archive_step"
    _attr_icon = "mdi:ray-start-arrow"
    _attr_native_min_value = 10
    _attr_native_max_value = 3600
    _attr_native_step = 10

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
        controller: UfanetArchiveController,
    ) -> None:
        super().__init__(manager, target_ref, camera, controller)
        self._attr_unique_id = f"{target_ref}_archive_step"

    @property
    def native_value(self) -> float:
        return float(self.controller.step)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_step(int(value))


class UfanetStandaloneArchiveNavigationButton(_StandaloneEntityMixin, ButtonEntity):
    """Move a standalone archive camera backward/forward/latest."""

    _attr_has_entity_name = True

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
        controller: UfanetArchiveController,
        action: str,
    ) -> None:
        self._init_private_identity(manager, target_ref, camera)
        self.controller = controller
        self.action = action
        self._attr_unique_id = f"{target_ref}_archive_{action}"

        if action == "previous":
            self._attr_translation_key = "archive_previous"
            self._attr_icon = "mdi:rewind"
        elif action == "next":
            self._attr_translation_key = "archive_next"
            self._attr_icon = "mdi:fast-forward"
        else:
            self._attr_translation_key = "archive_latest"
            self._attr_icon = "mdi:clock-end"

    @property
    def available(self) -> bool:
        return self.manager.archive_available(self.target_ref)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_subscribe_private_runtime()
        self.async_on_remove(
            self.controller.async_add_listener(self.async_write_ha_state)
        )

    async def async_press(self) -> None:
        if self.action == "previous":
            await self.controller.async_shift(-1)
        elif self.action == "next":
            await self.controller.async_shift(1)
        else:
            await self.controller.async_go_latest()


class UfanetStandaloneMotionEvent(_StandaloneEntityMixin, EventEntity):
    """Privacy-minimized motion event stream for a standalone UCAMS camera."""

    _attr_has_entity_name = True
    _attr_translation_key = "motion_analytics"
    _attr_icon = "mdi:motion-sensor"
    _attr_event_types: ClassVar[list[str]] = ["motion"]

    def __init__(
        self,
        manager: UfanetPrivateCameraRuntime,
        target_ref: str,
        camera: dict[str, Any],
    ) -> None:
        self._init_private_identity(manager, target_ref, camera)
        self.coordinator = manager.analytics_coordinator
        self._attr_unique_id = f"{target_ref}_motion_analytics"

    @property
    def available(self) -> bool:
        return self.manager.motion_available(self.target_ref)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_subscribe_private_runtime()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_motion_update)
        )

    @callback
    def _handle_motion_update(self) -> None:
        for event in self.coordinator.new_events.get(self.target_ref, []):
            attributes = (
                {"occurred_at": event["occurred_at"]}
                if "occurred_at" in event
                else {}
            )
            self._trigger_event("motion", attributes)
        self.async_write_ha_state()
