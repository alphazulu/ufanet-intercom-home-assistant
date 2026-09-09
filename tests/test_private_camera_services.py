"""Tests for standalone UCAMS response services and privacy boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import DOMAIN
from custom_components.ufanet_intercom.private_runtime import (
    UfanetPrivateCameraRuntime,
    private_camera_ref,
)
from custom_components.ufanet_intercom.private_services import (
    SERVICE_PRIVATE_GET_ARCHIVE_RANGES,
    SERVICE_PRIVATE_GET_ARCHIVE_URL,
    SERVICE_PRIVATE_GET_CALL_EVENTS,
    SERVICE_PRIVATE_GET_MOTION_EVENTS,
    async_setup_private_camera_services,
)

_PROVIDER_CAMERA = "PRIVATE-PROVIDER-CAMERA-42"


def _install_runtime(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Standalone camera services",
        data={},
        unique_id="standalone-camera-services",
    )
    entry.add_to_hass(hass)

    target_ref = private_camera_ref(_PROVIDER_CAMERA)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, target_ref)},
        name="Standalone camera",
    )

    api = MagicMock()
    runtime = {
        "api": api,
        "coordinator": SimpleNamespace(data={}),
        "options": {},
    }
    manager = UfanetPrivateCameraRuntime(hass, entry, runtime)
    manager.coordinator.data = {
        _PROVIDER_CAMERA: {
            "number": _PROVIDER_CAMERA,
            "title": "Test camera",
            "address": None,
            "timezone": "UTC",
            "streams_count": 1,
            "analytics": ("motion_alarm",),
            "dvr_hours": 120,
            "permission": 10,
            "is_fav": False,
            "is_public": False,
        }
    }
    manager.coordinator.last_update_success = True
    manager.archive_controllers[target_ref] = SimpleNamespace(timezone_name="UTC")
    manager.analytics_coordinator.data = {target_ref: {"supported": True}}
    manager.analytics_coordinator.last_update_success = True
    runtime["private_camera_runtime"] = manager
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    async_setup_private_camera_services(hass)
    return device, api, manager, target_ref


@pytest.mark.asyncio
async def test_private_archive_ranges_use_provider_number_only_inside_api(hass) -> None:
    device, api, _manager, target_ref = _install_runtime(hass)
    api.async_get_camera = AsyncMock(
        return_value={
            "timezone": "UTC",
            "tariff": {"name": "Video archive", "dvr_hours": 120},
        }
    )
    api.async_get_archive_ranges = AsyncMock(
        return_value=[{"from": 1_780_000_000, "duration": 3600}]
    )

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_PRIVATE_GET_ARCHIVE_RANGES,
        {"device_id": device.id},
        blocking=True,
        return_response=True,
    )

    api.async_get_camera.assert_awaited_once_with(_PROVIDER_CAMERA)
    api.async_get_archive_ranges.assert_awaited_once_with(_PROVIDER_CAMERA)
    assert response["camera_ref"] == target_ref
    assert response["count"] == 1
    serialized = json.dumps(response, default=str)
    assert _PROVIDER_CAMERA not in serialized
    assert "camera_number" not in serialized
    assert "skud_id" not in serialized


@pytest.mark.asyncio
async def test_private_archive_url_returns_safe_target_reference(hass) -> None:
    device, api, _manager, target_ref = _install_runtime(hass)
    start = datetime(2026, 9, 9, 1, 2, 3, tzinfo=timezone.utc)
    api.async_get_camera = AsyncMock(return_value={"timezone": "UTC"})
    api.async_get_archive_url = AsyncMock(
        return_value={
            "start": int(start.timestamp()),
            "duration": 300,
            "requested_duration": 300,
            "range_from": int(start.timestamp()) - 60,
            "range_duration": 600,
            "url": "https://media.invalid/archive.m3u8?token=temporary",
            "vendor": "UMS",
            "token_expires_at": None,
        }
    )

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_PRIVATE_GET_ARCHIVE_URL,
        {"device_id": device.id, "start": start, "duration": 300},
        blocking=True,
        return_response=True,
    )

    api.async_get_archive_url.assert_awaited_once_with(
        _PROVIDER_CAMERA,
        int(start.timestamp()),
        300,
    )
    assert response["camera_ref"] == target_ref
    assert response["duration"] == 300
    assert _PROVIDER_CAMERA not in json.dumps(response, default=str)


@pytest.mark.asyncio
async def test_private_motion_timeline_publishes_only_normalized_times(hass) -> None:
    device, _api, _manager, target_ref = _install_runtime(hass)
    event_time = datetime(2026, 9, 9, 10, 0, 34, 793780, tzinfo=timezone.utc)

    with patch(
        "custom_components.ufanet_intercom.private_services.async_get_motion_timeline_events",
        AsyncMock(return_value=[event_time]),
    ) as loader:
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_MOTION_EVENTS,
            {"device_id": device.id, "date": "2026-09-09"},
            blocking=True,
            return_response=True,
        )

    loader.assert_awaited_once()
    assert response["camera_ref"] == target_ref
    assert response["supported"] is True
    assert response["count"] == 1
    assert response["events"][0]["local_time"] == "10:00:34.79378"
    assert response["events"][0]["second_of_day"] == pytest.approx(36034.79378)
    serialized = json.dumps(response, default=str)
    assert _PROVIDER_CAMERA not in serialized
    assert "cursor" not in serialized.lower()
    assert "event_id" not in serialized.lower()


@pytest.mark.asyncio
async def test_private_call_timeline_is_intentionally_empty(hass) -> None:
    device, _api, _manager, target_ref = _install_runtime(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_PRIVATE_GET_CALL_EVENTS,
        {"device_id": device.id, "date": "2026-09-09"},
        blocking=True,
        return_response=True,
    )
    assert response == {
        "device_id": device.id,
        "camera_ref": target_ref,
        "timezone": "UTC",
        "date": "2026-09-09",
        "count": 0,
        "events": [],
    }
