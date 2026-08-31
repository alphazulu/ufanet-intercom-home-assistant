"""Tests for the latest confirmed call image entity."""

from __future__ import annotations

from datetime import datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import DOMAIN
from custom_components.ufanet_intercom.image import (
    UfanetLastCallImage,
    UfanetPreviewFrameError,
    _async_extract_preview_frame,
    async_setup_entry,
)


@pytest.fixture(autouse=True)
def mock_unused_image_http_client():
    """Avoid the base ImageEntity HTTP client; this entity serves cached bytes."""
    with patch(
        "homeassistant.components.image.get_async_client",
        return_value=MagicMock(),
    ):
        yield


def _skud(skud_id: int = 7) -> dict:
    return {
        "id": skud_id,
        "cctv_number": f"CAM-{skud_id}",
        "custom_name": "Front door",
        "role": {"name": "Intercom"},
        "model": 39,
    }


def _call(uuid: str = "call-1") -> dict:
    return {
        "uuid": uuid,
        "camera_number": "CAM-7",
        "called_at": "2026-08-31T11:22:33+10:00",
        "preview_url": "https://media.example/private-preview.mp4?token=secret",
    }


@pytest.mark.asyncio
async def test_setup_creates_image_only_for_intercoms_with_camera(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.data = {
        7: _skud(),
        8: {"id": 8, "custom_name": "No camera"},
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": MagicMock(),
        "coordinator": coordinator,
        "call_coordinator": MagicMock(),
        "image_status_manager": MagicMock(),
    }
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    entities = list(async_add_entities.call_args.args[0])
    assert len(entities) == 1
    assert entities[0].unique_id == "7_last_call_image"
    assert entities[0].content_type == "image/jpeg"


@pytest.mark.asyncio
async def test_refresh_caches_only_jpeg_and_rotates_proxy_token(hass) -> None:
    event = _call()
    call_coordinator = MagicMock()
    call_coordinator.data = {"CAM-7": event}
    call_coordinator.last_update_success = True
    api = MagicMock()
    api.async_get_call_preview = AsyncMock(return_value=b"private-mp4")
    status_manager = MagicMock()
    entity = UfanetLastCallImage(
        hass,
        call_coordinator,
        api,
        status_manager,
        _skud(),
    )
    entity.async_write_ha_state = MagicMock()
    previous_token = entity.access_tokens[-1]
    jpeg = b"\xff\xd8jpeg\xff\xd9"

    with patch(
        "custom_components.ufanet_intercom.image._async_extract_preview_frame",
        AsyncMock(return_value=jpeg),
    ):
        await entity._async_refresh_image(  # noqa: SLF001
            event["uuid"],
            event["preview_url"],
            event["called_at"],
        )

    assert await entity.async_image() == jpeg
    assert entity.image_last_updated == datetime.fromisoformat(event["called_at"])
    assert entity.access_tokens[-1] != previous_token
    assert "private-preview" not in repr(entity.state_attributes)
    assert "secret" not in repr(entity.state_attributes)
    api.async_get_call_preview.assert_awaited_once_with(event["preview_url"])
    status_manager.mark_success.assert_called_once_with(7)
    entity.async_write_ha_state.assert_called_once_with()


@pytest.mark.asyncio
async def test_refresh_discards_frame_if_latest_call_changed(hass) -> None:
    old = _call("old-call")
    call_coordinator = MagicMock()
    call_coordinator.data = {"CAM-7": _call("new-call")}
    api = MagicMock()
    api.async_get_call_preview = AsyncMock(return_value=b"private-mp4")
    status_manager = MagicMock()
    entity = UfanetLastCallImage(
        hass,
        call_coordinator,
        api,
        status_manager,
        _skud(),
    )
    entity.async_write_ha_state = MagicMock()

    with patch(
        "custom_components.ufanet_intercom.image._async_extract_preview_frame",
        AsyncMock(return_value=b"\xff\xd8jpeg\xff\xd9"),
    ):
        await entity._async_refresh_image(  # noqa: SLF001
            old["uuid"],
            old["preview_url"],
            old["called_at"],
        )

    assert await entity.async_image() is None
    status_manager.mark_cancelled.assert_called_once_with(7)
    entity.async_write_ha_state.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_failure_logs_only_safe_exception_type(hass, caplog) -> None:
    event = _call()
    call_coordinator = MagicMock()
    call_coordinator.data = {"CAM-7": event}
    api = MagicMock()
    api.async_get_call_preview = AsyncMock(
        side_effect=RuntimeError(
            "https://media.example/private.mp4?token=VERY-SECRET"
        )
    )
    status_manager = MagicMock()
    entity = UfanetLastCallImage(
        hass,
        call_coordinator,
        api,
        status_manager,
        _skud(),
    )

    with caplog.at_level(
        logging.WARNING,
        logger="custom_components.ufanet_intercom.image",
    ):
        await entity._async_refresh_image(  # noqa: SLF001
            event["uuid"],
            event["preview_url"],
            event["called_at"],
        )

    assert "RuntimeError" in caplog.text
    assert "VERY-SECRET" not in caplog.text
    assert "media.example" not in caplog.text
    status_manager.mark_failure.assert_called_once_with(7, "RuntimeError")


@pytest.mark.asyncio
async def test_ffmpeg_extracts_one_jpeg_from_private_stdin() -> None:
    jpeg = b"\xff\xd8jpeg\xff\xd9"
    process = MagicMock()
    process.returncode = 0
    process.communicate = AsyncMock(return_value=(jpeg, b""))

    with patch(
        "custom_components.ufanet_intercom.image.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ) as create_process:
        assert await _async_extract_preview_frame(b"private-mp4") == jpeg

    args = create_process.await_args.args
    assert "pipe:0" in args
    assert "pipe:1" in args
    assert not any("http" in str(value) for value in args)
    process.communicate.assert_awaited_once_with(input=b"private-mp4")


@pytest.mark.asyncio
async def test_ffmpeg_failure_does_not_include_private_media_data() -> None:
    process = MagicMock()
    process.returncode = 1
    process.communicate = AsyncMock(
        return_value=(b"", b"https://media.example/video.mp4?token=secret")
    )

    with patch(
        "custom_components.ufanet_intercom.image.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        with pytest.raises(UfanetPreviewFrameError) as err:
            await _async_extract_preview_frame(b"private-mp4")

    assert "secret" not in str(err.value)
    assert "media.example" not in str(err.value)
