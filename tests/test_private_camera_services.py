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
    SERVICE_PRIVATE_CLEANUP_ARCHIVE_EXPORTS,
    SERVICE_PRIVATE_DELETE_ARCHIVE_EXPORT,
    SERVICE_PRIVATE_GET_ARCHIVE_DOWNLOAD_URL,
    SERVICE_PRIVATE_GET_ARCHIVE_RANGES,
    SERVICE_PRIVATE_GET_ARCHIVE_URL,
    SERVICE_PRIVATE_GET_CALL_EVENTS,
    SERVICE_PRIVATE_GET_MOTION_EVENTS,
    SERVICE_PRIVATE_GET_SETTINGS,
    SERVICE_PRIVATE_LIST_ARCHIVE_EXPORTS,
    _resolve_private_target,
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


@pytest.mark.asyncio
async def test_private_settings_and_duplicate_registration(hass) -> None:
    device, _api, _manager, target_ref = _install_runtime(hass)
    async_setup_private_camera_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_PRIVATE_GET_SETTINGS,
        {"device_id": device.id},
        blocking=True,
        return_response=True,
    )

    assert response["camera_ref"] == target_ref
    assert response["archive_default_duration_seconds"] > 0
    assert response["archive_default_step_seconds"] > 0
    assert response["export_default_duration_seconds"] > 0
    assert isinstance(response["export_auto_cleanup"], bool)


def test_private_target_validation_rejects_unknown_or_wrong_devices(hass) -> None:
    with pytest.raises(Exception, match="was not found"):
        _resolve_private_target(hass, "missing")

    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="wrong-device")
    entry.add_to_hass(hass)
    wrong = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "not-a-camera")},
        name="Wrong",
    )
    with pytest.raises(Exception, match="not a standalone"):
        _resolve_private_target(hass, wrong.id)

    orphan = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, private_camera_ref("ORPHAN"))},
        name="Orphan",
    )
    hass.data.setdefault(DOMAIN, {})["noise"] = object()
    hass.data[DOMAIN]["invalid-manager"] = {"private_camera_runtime": object()}
    with pytest.raises(Exception, match="runtime is not available"):
        _resolve_private_target(hass, orphan.id)


@pytest.mark.asyncio
async def test_private_ranges_and_url_translate_provider_errors(hass) -> None:
    device, api, manager, _target_ref = _install_runtime(hass)
    with patch.object(manager, "archive_available", return_value=False):
        with pytest.raises(Exception, match="Archive is not available"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_PRIVATE_GET_ARCHIVE_RANGES,
                {"device_id": device.id},
                blocking=True,
                return_response=True,
            )

    api.async_get_camera = AsyncMock(side_effect=Exception("network"))
    # Only Ufanet errors are intentionally translated; avoid hiding programming bugs.
    with pytest.raises(Exception, match="network"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_ARCHIVE_RANGES,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )

    from custom_components.ufanet_intercom.api import UfanetApiError, UfanetResponseError

    api.async_get_camera.side_effect = UfanetApiError("offline")
    with pytest.raises(Exception, match="Unable to load standalone"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_ARCHIVE_RANGES,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )

    api.async_get_camera = AsyncMock(return_value={"timezone": "Invalid/Zone"})
    api.async_get_archive_url = AsyncMock(side_effect=UfanetResponseError("gap"))
    with pytest.raises(Exception, match="interval is unavailable"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_ARCHIVE_URL,
            {"device_id": device.id, "start": datetime(2026, 9, 9), "duration": 60},
            blocking=True,
            return_response=True,
        )

    api.async_get_archive_url.side_effect = UfanetApiError("offline")
    with pytest.raises(Exception, match="Unable to load standalone"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_ARCHIVE_URL,
            {"device_id": device.id, "start": datetime(2026, 9, 9), "duration": 60},
            blocking=True,
            return_response=True,
        )


@pytest.mark.asyncio
async def test_motion_fallback_capability_timezone_filtering_and_errors(hass) -> None:
    hass.config.time_zone = "UTC"
    device, api, manager, target_ref = _install_runtime(hass)
    manager.analytics_coordinator.last_update_success = False
    manager.analytics_coordinator.data = None
    manager.archive_controllers = {}
    manager.coordinator.data[_PROVIDER_CAMERA]["timezone"] = "Invalid/Zone"
    requested = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)

    with (
        patch(
            "custom_components.ufanet_intercom.private_services.async_get_motion_capabilities",
            AsyncMock(return_value={_PROVIDER_CAMERA: {"supported": True}}),
        ),
        patch(
            "custom_components.ufanet_intercom.private_services.async_get_motion_timeline_events",
            AsyncMock(
                return_value=[
                    requested.replace(day=10),
                    requested.replace(hour=13),
                    requested.replace(hour=11),
                ]
            ),
        ),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_MOTION_EVENTS,
            {"device_id": device.id, "date": "2026-09-09"},
            blocking=True,
            return_response=True,
        )
    assert response["camera_ref"] == target_ref
    assert response["timezone"] != "Invalid/Zone"
    assert response["count"] == 2
    assert [event["timestamp"] for event in response["events"]] == sorted(
        event["timestamp"] for event in response["events"]
    )

    from custom_components.ufanet_intercom.api import UfanetApiError

    with patch(
        "custom_components.ufanet_intercom.private_services.async_get_motion_capabilities",
        AsyncMock(return_value={}),
    ):
        unsupported = await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_MOTION_EVENTS,
            {"device_id": device.id, "date": "2026-09-09"},
            blocking=True,
            return_response=True,
        )
    assert unsupported["supported"] is False
    assert unsupported["events"] == []

    with patch(
        "custom_components.ufanet_intercom.private_services.async_get_motion_capabilities",
        AsyncMock(side_effect=UfanetApiError("offline")),
    ):
        with pytest.raises(Exception, match="motion capabilities"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_PRIVATE_GET_MOTION_EVENTS,
                {"device_id": device.id, "date": "2026-09-09"},
                blocking=True,
                return_response=True,
            )


def _archive_result(start: datetime) -> dict:
    return {
        "start": int(start.timestamp()),
        "duration": 60,
        "requested_duration": 60,
        "range_from": int(start.timestamp()) - 10,
        "range_duration": 120,
        "url": "https://media.invalid/archive.m3u8?token=secret",
        "vendor": "UMS",
        "token_expires_at": None,
    }


@pytest.mark.asyncio
async def test_private_export_success_list_delete_and_cleanup(hass, tmp_path) -> None:
    device, api, _manager, target_ref = _install_runtime(hass)
    start = datetime(2026, 9, 9, 1, 2, 3, tzinfo=timezone.utc)
    api.async_get_camera = AsyncMock(return_value={"timezone": "UTC"})
    api.async_get_archive_url = AsyncMock(return_value=_archive_result(start))

    process = MagicMock()
    process.returncode = 0
    process.communicate = AsyncMock(return_value=(b"", b""))

    async def create_process(*command, **kwargs):
        del kwargs
        from pathlib import Path

        Path(command[-1]).write_bytes(b"valid mp4")
        return process

    with (
        patch(
            "custom_components.ufanet_intercom.private_services._async_archive_export_location",
            AsyncMock(return_value=("media", tmp_path)),
        ),
        patch(
            "custom_components.ufanet_intercom.private_services.asyncio.create_subprocess_exec",
            side_effect=create_process,
        ),
    ):
        exported = await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_ARCHIVE_DOWNLOAD_URL,
            {"device_id": device.id, "start": start, "duration": 60},
            blocking=True,
            return_response=True,
        )
        listed = await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_LIST_ARCHIVE_EXPORTS,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )
        deleted = await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_DELETE_ARCHIVE_EXPORT,
            {"device_id": device.id, "filename": exported["filename"]},
            blocking=True,
            return_response=True,
        )
        cleanup = await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_CLEANUP_ARCHIVE_EXPORTS,
            {"device_id": device.id, "retention_days": 1, "max_total_mb": 1},
            blocking=True,
            return_response=True,
        )

    assert exported["camera_ref"] == target_ref
    assert exported["content_length"] == 9
    assert _PROVIDER_CAMERA not in json.dumps(exported)
    assert listed["count"] == 1
    assert deleted["deleted"] is True
    assert cleanup["retention_days"] == 1
    assert cleanup["max_total_mb"] == 1


@pytest.mark.asyncio
async def test_private_export_ffmpeg_failure_paths(hass, tmp_path) -> None:
    device, api, _manager, _target_ref = _install_runtime(hass)
    start = datetime(2026, 9, 9, tzinfo=timezone.utc)
    api.async_get_camera = AsyncMock(return_value={"timezone": "UTC"})
    api.async_get_archive_url = AsyncMock(return_value=_archive_result(start))

    async def call_export():
        return await hass.services.async_call(
            DOMAIN,
            SERVICE_PRIVATE_GET_ARCHIVE_DOWNLOAD_URL,
            {"device_id": device.id, "start": start, "duration": 60},
            blocking=True,
            return_response=True,
        )

    location = patch(
        "custom_components.ufanet_intercom.private_services._async_archive_export_location",
        AsyncMock(return_value=("media", tmp_path)),
    )
    with location, patch(
        "custom_components.ufanet_intercom.private_services.asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError,
    ):
        with pytest.raises(Exception, match="ffmpeg executable"):
            await call_export()

    process = MagicMock(returncode=1)
    process.communicate = AsyncMock(return_value=(b"", b"error"))
    with location, patch(
        "custom_components.ufanet_intercom.private_services.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        with pytest.raises(Exception, match="ffmpeg could not export"):
            await call_export()

    process.returncode = 0
    with location, patch(
        "custom_components.ufanet_intercom.private_services.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        with pytest.raises(Exception, match="valid standalone archive MP4"):
            await call_export()

    timeout_process = MagicMock()
    timeout_process.communicate = AsyncMock(return_value=(b"", b""))

    async def timeout(awaitable, *, timeout):
        del timeout
        awaitable.close()
        raise TimeoutError

    with (
        location,
        patch(
            "custom_components.ufanet_intercom.private_services.asyncio.create_subprocess_exec",
            AsyncMock(return_value=timeout_process),
        ),
        patch(
            "custom_components.ufanet_intercom.private_services.asyncio.wait_for",
            side_effect=timeout,
        ),
    ):
        with pytest.raises(Exception, match="timed out"):
            await call_export()
    timeout_process.kill.assert_called_once_with()
    timeout_process.communicate.assert_awaited()


@pytest.mark.asyncio
async def test_private_delete_missing_export_is_rejected(hass, tmp_path) -> None:
    device, _api, _manager, target_ref = _install_runtime(hass)
    with patch(
        "custom_components.ufanet_intercom.private_services._async_archive_export_location",
        AsyncMock(return_value=("media", tmp_path)),
    ):
        with pytest.raises(Exception, match="was not found"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_PRIVATE_DELETE_ARCHIVE_EXPORT,
                {
                    "device_id": device.id,
                    "filename": f"ufanet_{target_ref}_missing.mp4",
                },
                blocking=True,
                return_response=True,
            )
