"""Shared runtime for account-wide standalone UCAMS cameras."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import hashlib
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .analytics import UfanetMotionAnalyticsCoordinator
from .archive import UfanetArchiveController
from .const import (
    CONF_ARCHIVE_DEFAULT_DURATION,
    CONF_ARCHIVE_DEFAULT_STEP,
    DEFAULT_ARCHIVE_DURATION_SECONDS,
    DEFAULT_ARCHIVE_STEP_SECONDS,
    DOMAIN,
)
from .private_cameras import UcamsPrivateCamera, UfanetPrivateCameraCoordinator

_PRIVATE_RUNTIME_KEY = "private_camera_runtime"
_PRIVATE_RUNTIME_TASK_KEY = "_private_camera_runtime_task"
PrivateCameraListener = Callable[[], None]


def private_camera_ref(camera_number: str) -> str:
    """Return a stable opaque Home Assistant device reference for a UCAMS camera."""
    digest = hashlib.sha256(str(camera_number).encode("utf-8")).hexdigest()[:20]
    return f"ucams_camera_{digest}"


def private_camera_name(camera: UcamsPrivateCamera) -> str:
    """Return the provider title/address without exposing the provider identifier."""
    return camera.get("title") or camera.get("address") or "Ufanet video camera"


def private_camera_device_info(camera: UcamsPrivateCamera) -> DeviceInfo:
    """Build the shared device identity for all entities of one standalone camera."""
    return DeviceInfo(
        identifiers={(DOMAIN, private_camera_ref(camera["number"]))},
        name=private_camera_name(camera),
        manufacturer="Ufanet",
        model="UCAMS video surveillance camera",
    )


def private_camera_supports_archive(camera: UcamsPrivateCamera) -> bool:
    """Return archive capability using tariff plus the official permission threshold."""
    if int(camera.get("dvr_hours") or 0) <= 0:
        return False
    permission = camera.get("permission")
    return permission is None or permission <= 20


def private_camera_supports_motion(camera: UcamsPrivateCamera) -> bool:
    """Return whether the inventory advertises motion analytics."""
    return "motion_alarm" in camera.get("analytics", ())


class UfanetPrivateCameraRuntime:
    """Own shared inventory, archive and motion state for standalone UCAMS cameras."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        runtime: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.runtime = runtime
        self.api = runtime["api"]
        self.skud_coordinator = runtime["coordinator"]
        self.coordinator = UfanetPrivateCameraCoordinator(hass, self.api)
        self.analytics_coordinator = UfanetMotionAnalyticsCoordinator(
            hass,
            self.api,
            f"{entry.entry_id}.private_cameras",
            {},
        )
        self.archive_controllers: dict[str, UfanetArchiveController] = {}
        self._listeners: set[PrivateCameraListener] = set()
        self._remove_inventory_listener: Callable[[], None] | None = None
        self._remove_skud_listener: Callable[[], None] | None = None
        self._sync_task: asyncio.Task[None] | None = None
        self._sync_pending = False
        self._closed = False

        options = runtime.get("options") or {}
        self._default_duration = int(
            options.get(
                CONF_ARCHIVE_DEFAULT_DURATION,
                DEFAULT_ARCHIVE_DURATION_SECONDS,
            )
        )
        self._default_step = int(
            options.get(
                CONF_ARCHIVE_DEFAULT_STEP,
                DEFAULT_ARCHIVE_STEP_SECONDS,
            )
        )

    async def async_initialize(self) -> None:
        """Initialize optional inventory and a separate motion baseline."""
        await self.analytics_coordinator.async_initialize()
        await self.coordinator.async_refresh()
        if self.coordinator.data is None:
            self.coordinator.data = {}

        await self._async_sync_inventory(refresh_analytics=False)
        await self.analytics_coordinator.async_refresh()
        if self.analytics_coordinator.data is None:
            self.analytics_coordinator.data = {}

        self._remove_inventory_listener = self.coordinator.async_add_listener(
            self._handle_source_update
        )
        self._remove_skud_listener = self.skud_coordinator.async_add_listener(
            self._handle_source_update
        )
        self.entry.async_on_unload(self.close)

    def standalone_cameras(self) -> dict[str, UcamsPrivateCamera]:
        """Return current non-intercom cameras keyed only by opaque HA references."""
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        skud_data = (
            self.skud_coordinator.data
            if isinstance(getattr(self.skud_coordinator, "data", None), dict)
            else {}
        )
        intercom_numbers = {
            str(skud["cctv_number"])
            for skud in skud_data.values()
            if isinstance(skud, dict) and skud.get("cctv_number")
        }
        return {
            private_camera_ref(camera["number"]): camera
            for camera in data.values()
            if camera["number"] not in intercom_numbers
        }

    def camera_for_target(self, target_ref: str) -> UcamsPrivateCamera | None:
        """Resolve an opaque runtime target to the current standalone inventory item."""
        return self.standalone_cameras().get(target_ref)

    def camera_available(self, target_ref: str) -> bool:
        """Return whether inventory is healthy and the standalone camera is present."""
        return bool(
            self.coordinator.last_update_success
            and self.camera_for_target(target_ref) is not None
        )

    def archive_available(self, target_ref: str) -> bool:
        """Return whether a standalone camera still advertises archive capability."""
        camera = self.camera_for_target(target_ref)
        return bool(
            self.coordinator.last_update_success
            and camera is not None
            and private_camera_supports_archive(camera)
            and target_ref in self.archive_controllers
        )

    def motion_available(self, target_ref: str) -> bool:
        """Return whether motion polling is healthy for the standalone camera."""
        data = self.analytics_coordinator.data
        return bool(
            self.camera_available(target_ref)
            and self.analytics_coordinator.last_update_success
            and isinstance(data, dict)
            and target_ref in data
        )

    def async_add_listener(self, listener: PrivateCameraListener) -> Callable[[], None]:
        """Subscribe platform entity factories and existing entities to inventory changes."""
        self._listeners.add(listener)

        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def _handle_source_update(self) -> None:
        """Serialize asynchronous inventory reconciliation after coordinator callbacks."""
        if self._closed:
            return
        if self._sync_task is not None and not self._sync_task.done():
            self._sync_pending = True
            return
        self._sync_task = self.hass.async_create_task(self._async_sync_runner())

    async def _async_sync_runner(self) -> None:
        while not self._closed:
            self._sync_pending = False
            await self._async_sync_inventory(refresh_analytics=True)
            if not self._sync_pending:
                break

    async def _async_sync_inventory(self, *, refresh_analytics: bool) -> None:
        """Create stable archive controllers and keep motion targets synchronized."""
        cameras = self.standalone_cameras()
        new_controllers: list[UfanetArchiveController] = []
        for target_ref, camera in cameras.items():
            if (
                not private_camera_supports_archive(camera)
                or target_ref in self.archive_controllers
            ):
                continue

            # UfanetArchiveController is media-oriented internally; the numeric
            # SKUD value is not used by its archive operations. Keep the legacy
            # constructor untouched and never expose this placeholder outside
            # this private-camera runtime.
            controller = UfanetArchiveController(
                self.api,
                {"id": -1, "cctv_number": camera["number"]},
                default_duration=self._default_duration,
                default_step=self._default_step,
            )
            self.archive_controllers[target_ref] = controller
            new_controllers.append(controller)

        if new_controllers:
            await asyncio.gather(
                *(controller.async_initialize() for controller in new_controllers)
            )

        motion_targets = {
            target_ref: camera["number"]
            for target_ref, camera in cameras.items()
            if private_camera_supports_motion(camera)
        }
        motion_changed = motion_targets != self.analytics_coordinator.camera_by_skud
        if motion_changed:
            # The analytics coordinator only depends on hashable target keys at
            # runtime. Standalone cameras use opaque string refs, while the
            # existing intercom coordinator continues using numeric SKUD IDs.
            self.analytics_coordinator.camera_by_skud = motion_targets  # type: ignore[assignment]
            if refresh_analytics:
                await self.analytics_coordinator.async_refresh()
                if self.analytics_coordinator.data is None:
                    self.analytics_coordinator.data = {}

        self._notify()

    def close(self) -> None:
        """Detach private runtime listeners and cancel pending reconciliation."""
        self._closed = True
        if self._remove_inventory_listener is not None:
            self._remove_inventory_listener()
            self._remove_inventory_listener = None
        if self._remove_skud_listener is not None:
            self._remove_skud_listener()
            self._remove_skud_listener = None
        if self._sync_task is not None and not self._sync_task.done():
            self._sync_task.cancel()
        self._listeners.clear()

    def diagnostic_summary(self) -> dict[str, int]:
        """Return aggregate standalone state without provider camera identifiers."""
        cameras = self.standalone_cameras()
        return {
            "standalone_camera_count": len(cameras),
            "archive_camera_count": sum(
                private_camera_supports_archive(camera) for camera in cameras.values()
            ),
            "motion_alarm_camera_count": sum(
                private_camera_supports_motion(camera) for camera in cameras.values()
            ),
            "archive_controller_count": len(self.archive_controllers),
            "motion_supported_count": len(
                self.analytics_coordinator.data
                if isinstance(self.analytics_coordinator.data, dict)
                else {}
            ),
        }


async def async_ensure_private_camera_runtime(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: dict[str, Any],
) -> UfanetPrivateCameraRuntime:
    """Create one shared standalone-camera runtime across concurrently loaded platforms."""
    existing = runtime.get(_PRIVATE_RUNTIME_KEY)
    task = runtime.get(_PRIVATE_RUNTIME_TASK_KEY)
    if isinstance(existing, UfanetPrivateCameraRuntime) and task is None:
        return existing

    if task is None:
        manager = UfanetPrivateCameraRuntime(hass, entry, runtime)
        runtime[_PRIVATE_RUNTIME_KEY] = manager
        task = hass.async_create_task(manager.async_initialize())
        runtime[_PRIVATE_RUNTIME_TASK_KEY] = task
    else:
        manager = runtime.get(_PRIVATE_RUNTIME_KEY)
        if not isinstance(manager, UfanetPrivateCameraRuntime):
            raise RuntimeError("Invalid Ufanet private camera runtime state")

    try:
        await task
    except Exception:
        if runtime.get(_PRIVATE_RUNTIME_KEY) is manager:
            runtime.pop(_PRIVATE_RUNTIME_KEY, None)
        if runtime.get(_PRIVATE_RUNTIME_TASK_KEY) is task:
            runtime.pop(_PRIVATE_RUNTIME_TASK_KEY, None)
        raise
    else:
        if runtime.get(_PRIVATE_RUNTIME_TASK_KEY) is task:
            runtime.pop(_PRIVATE_RUNTIME_TASK_KEY, None)
        return manager
