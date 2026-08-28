"""Tests for archive controller state and gap navigation."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ufanet_intercom.api import (
    UfanetConnectionError,
    UfanetResponseError,
)
from custom_components.ufanet_intercom.archive import UfanetArchiveController


def _controller() -> tuple[UfanetArchiveController, MagicMock]:
    api = MagicMock()
    api.async_get_camera = AsyncMock(
        return_value={
            "timezone": "Asia/Vladivostok",
            "tariff": {"name": "Archive 5", "dvr_hours": "120"},
        }
    )
    api.async_get_archive_ranges = AsyncMock(
        return_value=[
            {"from": 1000, "duration": 100},
            {"from": 1200, "duration": 200},
        ]
    )
    api.async_get_archive_url = AsyncMock(
        return_value={"url": "https://archive.invalid/master.m3u8"}
    )
    controller = UfanetArchiveController(
        api,
        {"id": 7, "cctv_number": "CAM"},
        default_duration=60,
        default_step=30,
    )
    return controller, api


@pytest.mark.asyncio
async def test_initialize_uses_newest_range_and_camera_metadata() -> None:
    controller, _ = _controller()

    await controller.async_initialize()

    assert controller.ready is True
    assert controller.timezone_name == "Asia/Vladivostok"
    assert controller.archive_name == "Archive 5"
    assert controller.dvr_hours == 120
    assert int(controller.position.timestamp()) == 1340


@pytest.mark.asyncio
async def test_initialize_failure_is_optional() -> None:
    controller, api = _controller()
    api.async_get_camera.side_effect = UfanetConnectionError("offline")

    await controller.async_initialize()

    assert controller.ready is False


@pytest.mark.asyncio
async def test_set_position_requires_timezone_and_recording() -> None:
    controller, _ = _controller()

    with pytest.raises(HomeAssistantError, match="timezone"):
        await controller.async_set_position(datetime(2026, 1, 1))

    with pytest.raises(HomeAssistantError, match="No Ufanet archive"):
        await controller.async_set_position(
            datetime.fromtimestamp(1150, tz=timezone.utc)
        )

    await controller.async_set_position(datetime.fromtimestamp(1210, tz=timezone.utc))
    assert int(controller.position.timestamp()) == 1210


@pytest.mark.asyncio
async def test_listeners_are_notified_and_removable() -> None:
    controller, _ = _controller()
    listener = MagicMock()
    remove = controller.async_add_listener(listener)

    await controller.async_set_duration(90)
    await controller.async_set_step(60)

    assert controller.duration == 90
    assert controller.step == 60
    assert listener.call_count == 2

    remove()
    await controller.async_set_duration(120)
    assert listener.call_count == 2


@pytest.mark.asyncio
async def test_shift_skips_gaps_in_both_directions() -> None:
    controller, _ = _controller()
    controller.position = datetime.fromtimestamp(1090, tz=timezone.utc)
    controller.step = 30

    await controller.async_shift(1)
    assert int(controller.position.timestamp()) == 1200

    controller.position = datetime.fromtimestamp(1210, tz=timezone.utc)
    await controller.async_shift(-1)
    assert int(controller.position.timestamp()) == 1099


@pytest.mark.asyncio
async def test_shift_reports_boundaries_and_empty_archive() -> None:
    controller, api = _controller()
    api.async_get_archive_ranges.return_value = []

    with pytest.raises(HomeAssistantError, match="No Ufanet archive ranges"):
        await controller.async_shift(1)

    api.async_get_archive_ranges.return_value = [{"from": 1000, "duration": 100}]
    controller.position = datetime.fromtimestamp(1090, tz=timezone.utc)
    controller.step = 100

    with pytest.raises(HomeAssistantError, match="no newer"):
        await controller.async_shift(1)

    controller.position = datetime.fromtimestamp(1000, tz=timezone.utc)
    with pytest.raises(HomeAssistantError, match="no older"):
        await controller.async_shift(-1)


@pytest.mark.asyncio
async def test_go_latest_respects_duration() -> None:
    controller, _ = _controller()
    controller.duration = 90

    await controller.async_go_latest()

    assert int(controller.position.timestamp()) == 1310


@pytest.mark.asyncio
async def test_stream_url_and_error_mapping() -> None:
    controller, api = _controller()
    controller.position = datetime.fromtimestamp(1200, tz=timezone.utc)

    assert await controller.async_get_stream_url() == "https://archive.invalid/master.m3u8"
    assert controller.last_archive == {"url": "https://archive.invalid/master.m3u8"}

    api.async_get_archive_url.side_effect = UfanetResponseError("outside")
    with pytest.raises(HomeAssistantError, match="outside"):
        await controller.async_get_stream_url()

    api.async_get_archive_url.side_effect = UfanetConnectionError("offline")
    with pytest.raises(HomeAssistantError, match="Unable to load"):
        await controller.async_get_stream_url()


@pytest.mark.asyncio
async def test_range_fetch_maps_api_errors() -> None:
    controller, api = _controller()
    api.async_get_camera.side_effect = UfanetConnectionError("offline")

    with pytest.raises(HomeAssistantError, match="ranges"):
        await controller.async_go_latest()


def test_metadata_tolerates_invalid_tariff_values() -> None:
    controller, _ = _controller()

    controller._update_camera_metadata(  # noqa: SLF001
        {
            "timezone": "",
            "tariff": {"name": "Archive", "dvr_hours": "bad"},
        }
    )

    assert controller.timezone_name == "UTC"
    assert controller.archive_name == "Archive"
    assert controller.dvr_hours is None


def test_resolve_target_and_contains_boundaries() -> None:
    ranges = [{"from": 100, "duration": 10}, {"from": 120, "duration": 10}]
    assert UfanetArchiveController._contains(ranges, 100) is True  # noqa: SLF001
    assert UfanetArchiveController._contains(ranges, 110) is False  # noqa: SLF001
    assert UfanetArchiveController._resolve_target(ranges, 105, 1) == 105  # noqa: SLF001
    assert UfanetArchiveController._resolve_target(ranges, 111, 1) == 120  # noqa: SLF001
    assert UfanetArchiveController._resolve_target(ranges, 119, -1) == 109  # noqa: SLF001
