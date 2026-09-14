"""Regression coverage for archive camera, datetime and number platform glue."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ufanet_intercom.api import UfanetApiError
from custom_components.ufanet_intercom.button import (
    UfanetArchiveNavigationButton,
    UfanetOpenDoorButton,
    UfanetPhysicalKeyEnrollmentButton,
    _known_key_capable_ids,
    async_setup_entry as async_setup_button_entry,
)
from custom_components.ufanet_intercom.camera import (
    UfanetArchiveCamera,
    UfanetIntercomCamera,
    async_setup_entry as async_setup_camera_entry,
)
from custom_components.ufanet_intercom.const import DOMAIN
from custom_components.ufanet_intercom.datetime import (
    UfanetArchiveDateTime,
    async_setup_entry as async_setup_datetime_entry,
)
from custom_components.ufanet_intercom.number import (
    UfanetArchiveDuration,
    UfanetArchiveStep,
    async_setup_entry as async_setup_number_entry,
)


def _skud(skud_id: int = 7, camera: str | None = "CAM-7") -> dict:
    return {
        "id": skud_id,
        "name": "Entrance",
        "cctv_number": camera,
        "is_blocked": False,
        "open_type": "http",
        "disable_button": False,
    }


def _controller() -> MagicMock:
    controller = MagicMock()
    controller.skud_id = 7
    controller.position = datetime(2026, 9, 9, tzinfo=timezone.utc)
    controller.duration = 300
    controller.step = 60
    controller.timezone_name = "Asia/Vladivostok"
    controller.archive_name = "Video archive"
    controller.dvr_hours = 120
    controller.async_get_stream_url = AsyncMock(return_value="https://archive")
    controller.async_set_position = AsyncMock()
    controller.async_set_duration = AsyncMock()
    controller.async_set_step = AsyncMock()
    controller.async_shift = AsyncMock()
    controller.async_go_latest = AsyncMock()
    controller.async_add_listener.return_value = lambda: None
    return controller


@pytest.mark.asyncio
async def test_platform_entrypoints_keep_intercom_and_private_entities(hass) -> None:
    entry = SimpleNamespace(entry_id="entry")
    controller = _controller()
    coordinator = SimpleNamespace(data={7: _skud(), 8: _skud(8, None)})
    runtime = {
        "coordinator": coordinator,
        "api": MagicMock(),
        "archive_controllers": {7: controller, 99: MagicMock()},
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    camera_batches: list[list] = []
    datetime_batches: list[list] = []
    number_batches: list[list] = []

    with (
        patch(
            "custom_components.ufanet_intercom.camera.async_setup_private_camera_entities",
            AsyncMock(),
        ) as private_camera,
        patch(
            "custom_components.ufanet_intercom.datetime.async_setup_private_datetime_entities",
            AsyncMock(),
        ) as private_datetime,
        patch(
            "custom_components.ufanet_intercom.number.async_setup_private_number_entities",
            AsyncMock(),
        ) as private_number,
    ):
        await async_setup_camera_entry(hass, entry, lambda values: camera_batches.append(list(values)))
        await async_setup_datetime_entry(hass, entry, lambda values: datetime_batches.append(list(values)))
        await async_setup_number_entry(hass, entry, lambda values: number_batches.append(list(values)))

    assert [type(entity) for entity in camera_batches[0]] == [
        UfanetIntercomCamera,
        UfanetArchiveCamera,
    ]
    assert [type(entity) for entity in datetime_batches[0]] == [UfanetArchiveDateTime]
    assert [type(entity) for entity in number_batches[0]] == [
        UfanetArchiveDuration,
        UfanetArchiveStep,
    ]
    private_camera.assert_awaited_once_with(hass, entry, ANY, runtime)
    private_datetime.assert_awaited_once_with(hass, entry, ANY, runtime)
    private_number.assert_awaited_once_with(hass, entry, ANY, runtime)


@pytest.mark.asyncio
async def test_intercom_camera_availability_and_media_errors() -> None:
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {7: _skud()}
    api = MagicMock()
    api.async_get_snapshot = AsyncMock(return_value=b"jpeg")
    api.async_get_hls_url = AsyncMock(return_value="https://live")
    entity = UfanetIntercomCamera(coordinator, api, _skud())

    assert entity.available is True
    assert await entity.async_camera_image(width=600) == b"jpeg"
    api.async_get_snapshot.assert_awaited_once_with("CAM-7", small=True)
    assert await entity.stream_source() == "https://live"

    coordinator.data[7]["is_blocked"] = True
    assert entity.available is False
    coordinator.last_update_success = False
    assert entity.available is False
    api.async_get_snapshot.side_effect = UfanetApiError("bad jpeg")
    api.async_get_hls_url.side_effect = UfanetApiError("bad hls")
    assert await entity.async_camera_image() is None
    assert await entity.stream_source() is None


@pytest.mark.asyncio
async def test_intercom_archive_camera_stream_refresh_and_errors(hass) -> None:
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {7: _skud()}
    controller = _controller()
    entity = UfanetArchiveCamera(coordinator, controller, _skud())
    entity.hass = hass
    entity.stream = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity.async_update_token = MagicMock()

    assert entity.available is True
    assert entity.use_stream_for_stills is True
    assert await entity.stream_source() == "https://archive"
    await entity._async_update_stream_source()  # noqa: SLF001
    entity.stream.update_source.assert_called_once_with("https://archive")

    controller.async_get_stream_url.side_effect = HomeAssistantError("gone")
    assert await entity.stream_source() is None
    entity.stream.update_source.reset_mock()
    await entity._async_update_stream_source()  # noqa: SLF001
    entity.stream.update_source.assert_not_called()


@pytest.mark.asyncio
async def test_button_platform_and_actions_cover_all_intercom_paths(hass) -> None:
    entry = MagicMock()
    entry.entry_id = "buttons"
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        7: {**_skud(), "relays": [{"number": 2, "name": "Gate"}, None]},
        8: {**_skud(8), "relays": []},
        9: {**_skud(9), "disable_button": True},
    }
    api = MagicMock()
    api.async_open_door = AsyncMock()
    controller = _controller()
    key_coordinator = MagicMock()
    key_coordinator.capability_known = True
    key_coordinator.supported_skud_ids = {7}
    key_coordinator.async_add_listener.return_value = lambda: None
    runtime = {
        "entry": entry,
        "coordinator": coordinator,
        "api": api,
        "archive_controllers": {7: controller},
        "key_passage_coordinator": key_coordinator,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    batches: list[list] = []

    with (
        patch(
            "custom_components.ufanet_intercom.button.async_setup_authorized_device_services"
        ) as setup_services,
        patch(
            "custom_components.ufanet_intercom.button.async_setup_private_button_entities",
            AsyncMock(),
        ) as setup_private,
    ):
        await async_setup_button_entry(hass, entry, lambda values: batches.append(list(values)))

    setup_services.assert_called_once_with(hass)
    setup_private.assert_awaited_once()
    entities = [entity for batch in batches for entity in batch]
    assert sum(isinstance(entity, UfanetOpenDoorButton) for entity in entities) == 2
    assert sum(isinstance(entity, UfanetArchiveNavigationButton) for entity in entities) == 3
    assert sum(isinstance(entity, UfanetPhysicalKeyEnrollmentButton) for entity in entities) == 1

    door = next(entity for entity in entities if isinstance(entity, UfanetOpenDoorButton))
    assert door.available is True
    await door.async_press()
    api.async_open_door.assert_awaited_once_with(7, 2)
    api.async_open_door.side_effect = UfanetApiError("offline")
    with pytest.raises(HomeAssistantError, match="failed to open"):
        await door.async_press()

    key = next(
        entity for entity in entities if isinstance(entity, UfanetPhysicalKeyEnrollmentButton)
    )
    assert key.available is True
    assert key.extra_state_attributes["enrollment_window_seconds"] > 0
    with patch(
        "custom_components.ufanet_intercom.button.async_start_physical_key_enrollment",
        AsyncMock(),
    ) as enroll:
        await key.async_press()
        enroll.assert_awaited_once_with(api, 7)
    with patch(
        "custom_components.ufanet_intercom.button.async_start_physical_key_enrollment",
        AsyncMock(side_effect=UfanetApiError("offline")),
    ):
        with pytest.raises(HomeAssistantError, match="physical key"):
            await key.async_press()

    navigation = [
        entity for entity in entities if isinstance(entity, UfanetArchiveNavigationButton)
    ]
    for button in navigation:
        await button.async_press()
    assert [call.args for call in controller.async_shift.await_args_list] == [(-1,), (1,)]
    controller.async_go_latest.assert_awaited_once_with()

    coordinator.last_update_success = False
    assert door.available is False
    assert key.available is False


def test_known_key_capable_ids_supports_known_and_legacy_shapes() -> None:
    assert _known_key_capable_ids(None) == set()
    assert _known_key_capable_ids(
        SimpleNamespace(capability_known=True, supported_skud_ids={"7"})
    ) == {7}
    assert _known_key_capable_ids(SimpleNamespace(data={8: {}})) == {8}
    assert _known_key_capable_ids(SimpleNamespace(data=[])) == set()


@pytest.mark.asyncio
async def test_intercom_archive_controls_delegate_values() -> None:
    controller = _controller()
    date_entity = UfanetArchiveDateTime(controller, _skud())
    duration = UfanetArchiveDuration(controller, _skud())
    step = UfanetArchiveStep(controller, _skud())

    assert date_entity.native_value == controller.position
    assert date_entity.extra_state_attributes["camera_timezone"] == "Asia/Vladivostok"
    position = datetime(2026, 9, 10, tzinfo=timezone.utc)
    await date_entity.async_set_value(position)
    await duration.async_set_native_value(450.7)
    await step.async_set_native_value(90.7)

    controller.async_set_position.assert_awaited_once_with(position)
    controller.async_set_duration.assert_awaited_once_with(450)
    controller.async_set_step.assert_awaited_once_with(90)
    assert duration.native_value == 300.0
    assert step.native_value == 60.0
