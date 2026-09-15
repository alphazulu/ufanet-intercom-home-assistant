"""Lifecycle and failure-path coverage for standalone UCAMS runtime."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ufanet_intercom.private_runtime import (
    UfanetPrivateCameraRuntime,
    async_ensure_private_camera_runtime,
    private_camera_device_info,
    private_camera_name,
    private_camera_ref,
)


def _camera(number: str, *, archive: bool = True, motion: bool = True) -> dict:
    return {
        "number": number,
        "title": "Yard camera",
        "address": "Hidden address",
        "timezone": "UTC",
        "streams_count": 1,
        "analytics": ("motion_alarm",) if motion else (),
        "dvr_hours": 120 if archive else 0,
        "permission": 10,
        "is_fav": False,
        "is_public": False,
    }


def _manager(hass, *, cameras: dict | None = None):
    inventory = MagicMock()
    inventory.data = cameras or {}
    inventory.last_update_success = True
    inventory.async_refresh = AsyncMock()
    inventory.async_add_listener.side_effect = lambda listener: MagicMock()

    analytics = MagicMock()
    analytics.data = {}
    analytics.new_events = {}
    analytics.last_update_success = True
    analytics.camera_by_skud = {}
    analytics.async_initialize = AsyncMock()
    analytics.async_refresh = AsyncMock()

    skud = MagicMock()
    skud.data = {}
    skud.async_add_listener.side_effect = lambda listener: MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry"
    runtime = {"api": MagicMock(), "coordinator": skud, "options": {}}

    with (
        patch(
            "custom_components.ufanet_intercom.private_runtime.UfanetPrivateCameraCoordinator",
            return_value=inventory,
        ),
        patch(
            "custom_components.ufanet_intercom.private_runtime.UfanetMotionAnalyticsCoordinator",
            return_value=analytics,
        ),
    ):
        manager = UfanetPrivateCameraRuntime(hass, entry, runtime)
    return manager, entry, runtime, inventory, analytics, skud


def test_private_camera_name_and_device_info_do_not_expose_number() -> None:
    camera = _camera("SECRET-42")
    assert private_camera_name(camera) == "Yard camera"
    assert private_camera_name({**camera, "title": None}) == "Hidden address"
    assert private_camera_name({**camera, "title": None, "address": None}) == (
        "Ufanet video camera"
    )

    info = private_camera_device_info(camera)
    assert info["identifiers"] == {
        ("ufanet_intercom", private_camera_ref("SECRET-42"))
    }
    assert "SECRET-42" not in repr(info)


@pytest.mark.asyncio
async def test_initialize_builds_controllers_and_registers_cleanup(hass) -> None:
    manager, entry, _runtime, inventory, analytics, skud = _manager(
        hass,
        cameras={"CAM-A": _camera("CAM-A")},
    )
    inventory.data = None
    analytics.data = None
    controller = MagicMock()
    controller.async_initialize = AsyncMock()

    async def refresh_inventory() -> None:
        inventory.data = {"CAM-A": _camera("CAM-A")}

    async def refresh_analytics() -> None:
        analytics.data = {private_camera_ref("CAM-A"): {"supported": True}}

    inventory.async_refresh.side_effect = refresh_inventory
    analytics.async_refresh.side_effect = refresh_analytics

    with patch(
        "custom_components.ufanet_intercom.private_runtime.UfanetArchiveController",
        return_value=controller,
    ) as controller_type:
        await manager.async_initialize()

    target = private_camera_ref("CAM-A")
    analytics.async_initialize.assert_awaited_once_with()
    inventory.async_refresh.assert_awaited_once_with()
    controller.async_initialize.assert_awaited_once_with()
    assert manager.archive_controllers[target] is controller
    assert analytics.camera_by_skud == {target: "CAM-A"}
    assert inventory.async_add_listener.call_count == 1
    assert skud.async_add_listener.call_count == 1
    entry.async_on_unload.assert_called_once_with(manager.close)
    assert controller_type.call_args.kwargs["default_duration"] > 0


@pytest.mark.asyncio
async def test_sync_inventory_updates_motion_and_notifies(hass) -> None:
    manager, _entry, _runtime, inventory, analytics, _skud = _manager(
        hass,
        cameras={
            "CAM-A": _camera("CAM-A", archive=False),
            "CAM-B": _camera("CAM-B", archive=False, motion=False),
        },
    )
    listener = MagicMock()
    remove = manager.async_add_listener(listener)

    await manager._async_sync_inventory(refresh_analytics=True)  # noqa: SLF001

    assert analytics.camera_by_skud == {private_camera_ref("CAM-A"): "CAM-A"}
    analytics.async_refresh.assert_awaited_once_with()
    listener.assert_called_once_with()
    remove()
    manager._notify()  # noqa: SLF001
    listener.assert_called_once_with()

    inventory.last_update_success = False
    assert manager.camera_available(private_camera_ref("CAM-A")) is False
    assert manager.archive_available(private_camera_ref("CAM-A")) is False
    assert manager.motion_available(private_camera_ref("CAM-A")) is False


@pytest.mark.asyncio
async def test_source_updates_are_serialized_and_pending_update_repeats(hass) -> None:
    manager, *_ = _manager(hass)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    calls = 0

    async def sync(*, refresh_analytics: bool) -> None:
        nonlocal calls
        assert refresh_analytics is True
        calls += 1
        if calls == 1:
            first_started.set()
            await release_first.wait()

    manager._async_sync_inventory = sync  # type: ignore[method-assign]
    manager._handle_source_update()  # noqa: SLF001
    await first_started.wait()
    manager._handle_source_update()  # noqa: SLF001
    release_first.set()
    await manager._sync_task  # type: ignore[misc]  # noqa: SLF001
    assert calls == 2

    manager.close()
    manager._handle_source_update()  # noqa: SLF001
    assert calls == 2


def test_close_detaches_listeners_cancels_task_and_summarizes(hass) -> None:
    manager, *_ = _manager(
        hass,
        cameras={
            "CAM-A": _camera("CAM-A"),
            "CAM-B": _camera("CAM-B", archive=False, motion=False),
        },
    )
    target = private_camera_ref("CAM-A")
    manager.archive_controllers[target] = MagicMock()
    manager.analytics_coordinator.data = {target: {"supported": True}}
    assert manager.diagnostic_summary() == {
        "standalone_camera_count": 2,
        "archive_camera_count": 1,
        "motion_alarm_camera_count": 1,
        "archive_controller_count": 1,
        "motion_supported_count": 1,
    }

    remove_inventory = MagicMock()
    remove_skud = MagicMock()
    task = MagicMock()
    task.done.return_value = False
    manager._remove_inventory_listener = remove_inventory  # noqa: SLF001
    manager._remove_skud_listener = remove_skud  # noqa: SLF001
    manager._sync_task = task  # type: ignore[assignment]  # noqa: SLF001
    manager.async_add_listener(MagicMock())
    manager.close()

    remove_inventory.assert_called_once_with()
    remove_skud.assert_called_once_with()
    task.cancel.assert_called_once_with()
    assert manager._listeners == set()  # noqa: SLF001


@pytest.mark.asyncio
async def test_ensure_runtime_reuses_concurrent_initialization_and_recovers(hass) -> None:
    manager = object.__new__(UfanetPrivateCameraRuntime)
    started = asyncio.Event()
    release = asyncio.Event()

    async def initialize() -> None:
        started.set()
        await release.wait()

    manager.async_initialize = initialize  # type: ignore[method-assign]
    entry = MagicMock()
    runtime: dict = {}
    with (
        patch.object(UfanetPrivateCameraRuntime, "__new__", return_value=manager),
        patch.object(UfanetPrivateCameraRuntime, "__init__", return_value=None) as init,
    ):
        first = asyncio.create_task(async_ensure_private_camera_runtime(hass, entry, runtime))
        await started.wait()
        second = asyncio.create_task(async_ensure_private_camera_runtime(hass, entry, runtime))
        release.set()
        assert await first is manager
        assert await second is manager
        assert init.call_count == 1
        assert await async_ensure_private_camera_runtime(hass, entry, runtime) is manager

    bad_task = asyncio.create_task(asyncio.sleep(0))
    bad_runtime = {
        "_private_camera_runtime_task": bad_task,
        "private_camera_runtime": object(),
    }
    with pytest.raises(RuntimeError, match="Invalid Ufanet"):
        await async_ensure_private_camera_runtime(hass, entry, bad_runtime)
    await bad_task


@pytest.mark.asyncio
async def test_ensure_runtime_cleans_failed_initialization(hass) -> None:
    manager = object.__new__(UfanetPrivateCameraRuntime)
    manager.async_initialize = AsyncMock(  # type: ignore[method-assign]
        side_effect=ValueError("boom")
    )
    runtime: dict = {}
    with (
        patch.object(UfanetPrivateCameraRuntime, "__new__", return_value=manager),
        patch.object(UfanetPrivateCameraRuntime, "__init__", return_value=None),
    ):
        with pytest.raises(ValueError, match="boom"):
            await async_ensure_private_camera_runtime(hass, MagicMock(), runtime)
    assert "private_camera_runtime" not in runtime
    assert "_private_camera_runtime_task" not in runtime
