"""Integration-style tests for the local archive MP4 export service."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    CONF_EXPORT_AUTO_CLEANUP,
    DOMAIN,
    SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
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
        with pytest.raises(HomeAssistantError, match="decoder failed"):
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
