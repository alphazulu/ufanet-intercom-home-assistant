"""Integration-style tests for the local archive MP4 export service."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.api import UfanetResponseError
from custom_components.ufanet_intercom.const import (
    CONF_EXPORT_AUTO_CLEANUP,
    DOMAIN,
    SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
    SERVICE_GET_LAST_CALL_PREVIEW_URL,
    SERVICE_GET_RUNTIME_STATUS,
)
from custom_components.ufanet_intercom.services import async_setup_services


def _install_runtime(hass, tmp_path: Path):
    hass.config.media_dirs = {"local": str(tmp_path)}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Export test",
        data={},
        unique_id="export-test",
    )
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "7")},
        name="Door",
    )

    api = MagicMock()
    api.async_get_camera = AsyncMock(return_value={"timezone": "UTC"})
    api.async_get_archive_url = AsyncMock(
        return_value={
            "url": "https://media.invalid/archive.m3u8?token=hidden",
            "start": 1_777_000_000,
            "duration": 30,
            "requested_duration": 30,
            "range_from": 1_776_999_900,
            "range_duration": 300,
        }
    )
    coordinator = SimpleNamespace(
        data={7: {"id": 7, "cctv_number": "CAM/1"}},
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "options": {CONF_EXPORT_AUTO_CLEANUP: False},
    }
    async_setup_services(hass, MagicMock())
    return device, api


@pytest.mark.asyncio
async def test_archive_download_service_exports_atomic_mp4_and_deduplicates_call(
    hass,
    tmp_path: Path,
) -> None:
    device, api = _install_runtime(hass, tmp_path)

    async def fake_exec(*args, **kwargs):
        temporary_path = Path(args[-1])
        assert temporary_path.name.startswith(".ufanet_CAM_1_")
        temporary_path.write_bytes(b"mp4-data")
        process = MagicMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        process.kill = MagicMock()
        return process

    event_id = "call-uuid-1"
    with patch(
        "custom_components.ufanet_intercom.services.asyncio.create_subprocess_exec",
        side_effect=fake_exec,
    ) as exec_mock:
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
            {
                "device_id": device.id,
                "start": datetime.fromtimestamp(1_777_000_000, tz=timezone.utc),
                "duration": 30,
                "source": "call",
                "event_id": event_id,
            },
            blocking=True,
            return_response=True,
        )

    event_ref = hashlib.sha256(event_id.encode()).hexdigest()[:12]
    assert result["existing"] is False
    assert result["source"] == "call"
    assert result["event_ref"] == event_ref
    assert result["filename"].endswith(f"_call_{event_ref}.mp4")
    assert result["content_length"] == len(b"mp4-data")
    assert result["media_content_id"].startswith("media-source://media_source/local/")
    assert (tmp_path / "ufanet_intercom" / result["filename"]).read_bytes() == b"mp4-data"
    assert not list((tmp_path / "ufanet_intercom").glob(".*.part.mp4"))
    exec_mock.assert_awaited_once()
    api.async_get_archive_url.assert_awaited_once()

    with patch(
        "custom_components.ufanet_intercom.services.asyncio.create_subprocess_exec",
        side_effect=AssertionError("ffmpeg must not run for an existing call export"),
    ) as second_exec:
        existing = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
            {
                "device_id": device.id,
                "start": datetime.fromtimestamp(1_777_000_000, tz=timezone.utc),
                "duration": 30,
                "source": "call",
                "event_id": event_id,
            },
            blocking=True,
            return_response=True,
        )

    assert existing["existing"] is True
    assert existing["filename"] == result["filename"]
    second_exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_status_includes_only_safe_image_health(
    hass,
    tmp_path: Path,
) -> None:
    device, api = _install_runtime(hass, tmp_path)
    api.diagnostic_auth_state.return_value = {"ufanet_access_present": True}
    image_status = MagicMock()
    image_status.status.return_value = {
        "configured": True,
        "ffmpeg_available": True,
        "ready": True,
        "loading": False,
        "preview_available": True,
        "preview_https_upgraded": True,
        "success_count": 1,
        "failure_count": 0,
        "consecutive_failures": 0,
        "last_success_at": "2026-08-31T01:00:00+00:00",
        "last_error_at": None,
        "last_error_code": None,
        "last_error_type": None,
        "repair_issue_active": False,
    }
    runtime = next(iter(hass.data[DOMAIN].values()))
    runtime["image_status_manager"] = image_status

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_RUNTIME_STATUS,
        {"device_id": device.id},
        blocking=True,
        return_response=True,
    )
    serialized = json.dumps(result)

    assert result["last_call_image"]["ready"] is True
    assert result["last_call_image"]["ffmpeg_available"] is True
    assert result["last_call_image"]["preview_https_upgraded"] is True
    assert "preview_url" not in serialized
    assert "archive_url" not in serialized
    assert "token=" not in serialized
    image_status.status.assert_called_once_with(7)


@pytest.mark.asyncio
async def test_preview_url_is_returned_only_by_explicit_response_service(
    hass,
    tmp_path: Path,
) -> None:
    device, api = _install_runtime(hass, tmp_path)
    preview_url = "http://media.invalid/call.mp4?token=EXPLICIT-SECRET"
    api.async_get_call_media = AsyncMock(return_value={"preview": preview_url})
    runtime = next(iter(hass.data[DOMAIN].values()))
    runtime["call_coordinator"] = SimpleNamespace(
        data={
            "CAM/1": {
                "uuid": "call-1",
                "called_at": "2026-08-31T11:22:33+10:00",
            }
        }
    )

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_LAST_CALL_PREVIEW_URL,
        {"device_id": device.id},
        blocking=True,
        return_response=True,
    )

    assert result["url"] == preview_url.replace("http://", "https://", 1)
    assert result["https_upgraded"] is True
    assert result["called_at"] == "2026-08-31T11:22:33+10:00"
    api.async_get_call_media.assert_awaited_once_with("call-1")


@pytest.mark.asyncio
async def test_preview_service_does_not_expose_private_api_error_text(
    hass,
    tmp_path: Path,
) -> None:
    device, api = _install_runtime(hass, tmp_path)
    api.async_get_call_media = AsyncMock(
        side_effect=UfanetResponseError(
            "https://media.invalid/call.mp4?token=PRIVATE-ERROR-TOKEN"
        )
    )
    runtime = next(iter(hass.data[DOMAIN].values()))
    runtime["call_coordinator"] = SimpleNamespace(
        data={"CAM/1": {"uuid": "call-1"}}
    )

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_LAST_CALL_PREVIEW_URL,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )

    message = str(err.value)
    assert "PRIVATE-ERROR-TOKEN" not in message
    assert "media.invalid" not in message


@pytest.mark.asyncio
async def test_preview_service_returns_only_safe_url_validation_code(
    hass,
    tmp_path: Path,
) -> None:
    device, api = _install_runtime(hass, tmp_path)
    api.async_get_call_media = AsyncMock(
        return_value={
            "preview": "ftp://media.invalid/call.mp4?token=PRIVATE-URL-TOKEN"
        }
    )
    runtime = next(iter(hass.data[DOMAIN].values()))
    runtime["call_coordinator"] = SimpleNamespace(
        data={"CAM/1": {"uuid": "call-1"}}
    )

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_LAST_CALL_PREVIEW_URL,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )

    message = str(err.value)
    assert "unsupported_scheme" in message
    assert "PRIVATE-URL-TOKEN" not in message
    assert "media.invalid" not in message


@pytest.mark.asyncio
async def test_archive_download_service_reports_ffmpeg_failure_and_cleans_partial(
    hass,
    tmp_path: Path,
) -> None:
    device, _ = _install_runtime(hass, tmp_path)

    async def fake_exec(*args, **kwargs):
        temporary_path = Path(args[-1])
        temporary_path.write_bytes(b"partial")
        process = MagicMock()
        process.returncode = 1
        process.communicate = AsyncMock(return_value=(b"", b"decoder failed"))
        process.kill = MagicMock()
        return process

    with patch(
        "custom_components.ufanet_intercom.services.asyncio.create_subprocess_exec",
        side_effect=fake_exec,
    ):
        with pytest.raises(HomeAssistantError, match="could not export") as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
                {
                    "device_id": device.id,
                    "start": datetime.fromtimestamp(1_777_000_000, tz=timezone.utc),
                    "duration": 30,
                },
                blocking=True,
                return_response=True,
            )

    assert "decoder failed" not in str(err.value)

    export_dir = tmp_path / "ufanet_intercom"
    assert not list(export_dir.glob(".*.part.mp4"))
    assert not list(export_dir.glob("*.mp4"))


@pytest.mark.asyncio
async def test_archive_download_service_maps_missing_ffmpeg_to_validation_error(
    hass,
    tmp_path: Path,
) -> None:
    device, _ = _install_runtime(hass, tmp_path)

    with patch(
        "custom_components.ufanet_intercom.services.asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError,
    ):
        with pytest.raises(ServiceValidationError, match="ffmpeg executable"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
                {
                    "device_id": device.id,
                    "start": datetime.fromtimestamp(1_777_000_000, tz=timezone.utc),
                    "duration": 30,
                },
                blocking=True,
                return_response=True,
            )
