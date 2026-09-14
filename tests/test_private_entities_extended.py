"""Behavioral coverage for standalone UCAMS entity platforms."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ufanet_intercom.api import UfanetApiError
from custom_components.ufanet_intercom.private_entities import (
    UfanetStandaloneArchiveCamera,
    UfanetStandaloneArchiveDateTime,
    UfanetStandaloneArchiveDuration,
    UfanetStandaloneArchiveNavigationButton,
    UfanetStandaloneArchiveStep,
    UfanetStandaloneCamera,
    UfanetStandaloneMotionEvent,
    async_setup_private_button_entities,
    async_setup_private_camera_entities,
    async_setup_private_datetime_entities,
    async_setup_private_event_entities,
    async_setup_private_number_entities,
)
from custom_components.ufanet_intercom.private_runtime import private_camera_ref


def _camera(number: str = "PRIVATE-42") -> dict:
    return {
        "number": number,
        "title": "Garage",
        "address": None,
        "timezone": "UTC",
        "streams_count": 1,
        "analytics": ("motion_alarm",),
        "dvr_hours": 120,
        "permission": 10,
        "is_fav": False,
        "is_public": False,
    }


def _controller() -> MagicMock:
    controller = MagicMock()
    controller.position = datetime(2026, 9, 9, tzinfo=timezone.utc)
    controller.duration = 300
    controller.step = 60
    controller.timezone_name = "UTC"
    controller.archive_name = "Archive 5 days"
    controller.dvr_hours = 120
    controller.async_get_stream_url = AsyncMock(return_value="https://media/archive.m3u8")
    controller.async_set_position = AsyncMock()
    controller.async_set_duration = AsyncMock()
    controller.async_set_step = AsyncMock()
    controller.async_shift = AsyncMock()
    controller.async_go_latest = AsyncMock()
    controller.async_add_listener.return_value = lambda: None
    return controller


def _manager(camera: dict | None = None):
    camera = camera or _camera()
    target = private_camera_ref(camera["number"])
    controller = _controller()
    analytics = MagicMock()
    analytics.data = {target: {"supported": True}}
    analytics.new_events = {}
    analytics.async_add_listener.return_value = lambda: None
    manager = MagicMock()
    manager.api = MagicMock()
    manager.api.async_get_snapshot = AsyncMock(return_value=b"jpeg")
    manager.api.async_get_hls_url = AsyncMock(return_value="https://media/live.m3u8")
    manager.analytics_coordinator = analytics
    manager.archive_controllers = {target: controller}
    manager.standalone_cameras.return_value = {target: camera}
    manager.camera_for_target.side_effect = lambda ref: camera if ref == target else None
    manager.camera_available.return_value = True
    manager.archive_available.return_value = True
    manager.motion_available.return_value = True
    manager.async_add_listener.return_value = lambda: None
    return manager, target, camera, controller


@pytest.mark.asyncio
async def test_entity_factories_add_each_capability_once(hass) -> None:
    manager, target, camera, controller = _manager()
    entry = MagicMock()
    runtime = {"api": object(), "coordinator": MagicMock()}
    runtime["coordinator"].async_add_listener = MagicMock()
    batches: list[list] = []

    def add_entities(entities) -> None:
        batches.append(list(entities))

    setup_functions = (
        async_setup_private_camera_entities,
        async_setup_private_datetime_entities,
        async_setup_private_number_entities,
        async_setup_private_button_entities,
        async_setup_private_event_entities,
    )
    with patch(
        "custom_components.ufanet_intercom.private_entities.async_ensure_private_camera_runtime",
        AsyncMock(return_value=manager),
    ):
        for setup in setup_functions:
            await setup(hass, entry, add_entities, runtime)

    assert sum(len(batch) for batch in batches) == 9
    assert sum(isinstance(item, UfanetStandaloneCamera) for batch in batches for item in batch) == 1
    assert sum(isinstance(item, UfanetStandaloneArchiveCamera) for batch in batches for item in batch) == 1
    assert sum(isinstance(item, UfanetStandaloneArchiveDateTime) for batch in batches for item in batch) == 1
    assert sum(isinstance(item, UfanetStandaloneArchiveDuration) for batch in batches for item in batch) == 1
    assert sum(isinstance(item, UfanetStandaloneArchiveStep) for batch in batches for item in batch) == 1
    assert sum(isinstance(item, UfanetStandaloneArchiveNavigationButton) for batch in batches for item in batch) == 3
    assert sum(isinstance(item, UfanetStandaloneMotionEvent) for batch in batches for item in batch) == 1

    # Every factory subscribed a callback. Replaying them must not duplicate entities.
    callbacks = [call.args[0] for call in manager.async_add_listener.call_args_list]
    callbacks += [call.args[0] for call in manager.analytics_coordinator.async_add_listener.call_args_list]
    before = sum(len(batch) for batch in batches)
    for callback in callbacks:
        callback()
    assert sum(len(batch) for batch in batches) == before
    assert target in manager.archive_controllers
    assert controller is manager.archive_controllers[target]


@pytest.mark.asyncio
async def test_entity_factories_ignore_stubs_and_missing_capabilities(hass) -> None:
    add = MagicMock()
    entry = MagicMock()
    for setup in (
        async_setup_private_camera_entities,
        async_setup_private_datetime_entities,
        async_setup_private_number_entities,
        async_setup_private_button_entities,
        async_setup_private_event_entities,
    ):
        await setup(hass, entry, add, {"api": object(), "coordinator": object()})
    add.assert_not_called()

    manager, target, _camera_item, _controller_item = _manager()
    manager.archive_controllers = {}
    manager.analytics_coordinator.data = None
    runtime = {"api": object(), "coordinator": MagicMock()}
    with patch(
        "custom_components.ufanet_intercom.private_entities.async_ensure_private_camera_runtime",
        AsyncMock(return_value=manager),
    ):
        await async_setup_private_datetime_entities(hass, entry, add, runtime)
        await async_setup_private_number_entities(hass, entry, add, runtime)
        await async_setup_private_button_entities(hass, entry, add, runtime)
        await async_setup_private_event_entities(hass, entry, add, runtime)
    add.assert_not_called()
    assert target not in manager.archive_controllers


@pytest.mark.asyncio
async def test_live_camera_media_success_and_provider_failures() -> None:
    manager, target, camera, _controller_item = _manager()
    entity = UfanetStandaloneCamera(manager, target, camera)

    assert entity.available is True
    assert await entity.async_camera_image(width=320) == b"jpeg"
    manager.api.async_get_snapshot.assert_awaited_once_with(camera["number"], small=True)
    assert await entity.stream_source() == "https://media/live.m3u8"

    manager.api.async_get_snapshot.side_effect = UfanetApiError("snapshot failed")
    manager.api.async_get_hls_url.side_effect = UfanetApiError("stream failed")
    assert await entity.async_camera_image(width=1000) is None
    assert await entity.stream_source() is None


@pytest.mark.asyncio
async def test_archive_camera_refreshes_open_stream_and_handles_errors(hass) -> None:
    manager, target, camera, controller = _manager()
    entity = UfanetStandaloneArchiveCamera(manager, target, camera, controller)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    entity.async_update_token = MagicMock()
    entity.stream = MagicMock()

    assert entity.available is True
    assert entity.use_stream_for_stills is True
    assert await entity.stream_source() == "https://media/archive.m3u8"
    await entity._async_update_stream_source()  # noqa: SLF001
    entity.stream.update_source.assert_called_once_with("https://media/archive.m3u8")
    entity.async_update_token.assert_called_once_with()

    controller.async_get_stream_url.side_effect = HomeAssistantError("expired")
    assert await entity.stream_source() is None
    entity.stream.update_source.reset_mock()
    await entity._async_update_stream_source()  # noqa: SLF001
    entity.stream.update_source.assert_not_called()


@pytest.mark.asyncio
async def test_archive_controls_delegate_and_publish_metadata() -> None:
    manager, target, camera, controller = _manager()
    date_entity = UfanetStandaloneArchiveDateTime(manager, target, camera, controller)
    duration = UfanetStandaloneArchiveDuration(manager, target, camera, controller)
    step = UfanetStandaloneArchiveStep(manager, target, camera, controller)

    assert date_entity.available is True
    assert date_entity.native_value == controller.position
    assert date_entity.extra_state_attributes == {
        "camera_timezone": "UTC",
        "archive_name": "Archive 5 days",
        "dvr_hours": 120,
    }
    new_position = datetime(2026, 9, 10, tzinfo=timezone.utc)
    await date_entity.async_set_value(new_position)
    controller.async_set_position.assert_awaited_once_with(new_position)

    assert duration.native_value == 300.0
    assert step.native_value == 60.0
    await duration.async_set_native_value(450.9)
    await step.async_set_native_value(90.9)
    controller.async_set_duration.assert_awaited_once_with(450)
    controller.async_set_step.assert_awaited_once_with(90)

    for action in ("previous", "next", "latest"):
        button = UfanetStandaloneArchiveNavigationButton(
            manager, target, camera, controller, action
        )
        assert button.available is True
        await button.async_press()
    assert [call.args for call in controller.async_shift.await_args_list] == [(-1,), (1,)]
    controller.async_go_latest.assert_awaited_once_with()


def test_motion_entity_availability_and_event_without_provider_metadata() -> None:
    manager, target, camera, _controller_item = _manager()
    entity = UfanetStandaloneMotionEvent(manager, target, camera)
    entity.async_write_ha_state = MagicMock()
    entity._trigger_event = MagicMock()
    manager.analytics_coordinator.new_events = {
        target: [{"occurred_at": "2026-09-09T00:00:00Z"}, {"cursor_id": 99}]
    }

    assert entity.available is True
    entity._handle_motion_update()  # noqa: SLF001
    assert entity._trigger_event.call_args_list[0].args == (
        "motion",
        {"occurred_at": "2026-09-09T00:00:00Z"},
    )
    assert entity._trigger_event.call_args_list[1].args == ("motion", {})
    entity.async_write_ha_state.assert_called_once_with()
