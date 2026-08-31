"""Tests for privacy-safe last-call image health supervision."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import DOMAIN
from custom_components.ufanet_intercom.image_status import (
    IMAGE_FAILURES_BEFORE_REPAIR,
    UfanetLastCallImageStatusManager,
    async_check_ffmpeg,
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Private contract",
        data={},
        unique_id="private-contract",
    )


def _skuds() -> list[dict]:
    return [
        {"id": 7, "cctv_number": "CAMERA-SECRET"},
        {"id": 8},
    ]


@pytest.mark.asyncio
async def test_ffmpeg_probe_reports_success_without_capturing_output() -> None:
    process = MagicMock()
    process.returncode = 0
    process.wait = AsyncMock()

    with patch(
        "custom_components.ufanet_intercom.image_status.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ) as create_process:
        assert await async_check_ffmpeg() is True

    assert create_process.await_args.args == ("ffmpeg", "-version")
    assert create_process.await_args.kwargs["stdout"] != -1
    assert create_process.await_args.kwargs["stderr"] != -1


@pytest.mark.asyncio
async def test_missing_ffmpeg_opens_issue_and_success_closes_it(hass) -> None:
    entry = _entry()
    manager = UfanetLastCallImageStatusManager(hass, entry, _skuds())

    with patch(
        "custom_components.ufanet_intercom.image_status.async_check_ffmpeg",
        AsyncMock(return_value=False),
    ):
        await manager.async_initialize()

    issue_id = f"last_call_image_unavailable_{entry.entry_id}"
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, issue_id) is not None
    assert manager.status(7)["ffmpeg_available"] is False
    assert manager.status(8)["configured"] is False

    manager.mark_success(7)

    assert registry.async_get_issue(DOMAIN, issue_id) is None
    assert manager.status(7)["ffmpeg_available"] is True
    assert manager.status(7)["ready"] is True


@pytest.mark.asyncio
async def test_repeated_safe_failures_open_issue_and_recovery_closes_it(hass) -> None:
    entry = _entry()
    manager = UfanetLastCallImageStatusManager(hass, entry, _skuds())

    with patch(
        "custom_components.ufanet_intercom.image_status.async_check_ffmpeg",
        AsyncMock(return_value=True),
    ):
        await manager.async_initialize()

    issue_id = f"last_call_image_unavailable_{entry.entry_id}"
    registry = ir.async_get(hass)
    for _ in range(IMAGE_FAILURES_BEFORE_REPAIR):
        manager.mark_failure(
            7,
            "UfanetPreviewFrameError",
            error_code="decode_error",
            ffmpeg_available=True,
        )

    status = manager.status(7)
    serialized = json.dumps(status)
    assert registry.async_get_issue(DOMAIN, issue_id) is not None
    assert status["consecutive_failures"] == IMAGE_FAILURES_BEFORE_REPAIR
    assert status["last_error_code"] == "decode_error"
    assert status["last_error_type"] == "UfanetPreviewFrameError"
    assert "CAMERA-SECRET" not in serialized
    assert "token" not in serialized.lower()

    manager.mark_success(7)

    assert registry.async_get_issue(DOMAIN, issue_id) is None
    assert manager.summary()["consecutive_failures"] == 0
    assert manager.summary()["success_count"] == 1
    assert manager.summary()["last_error_code"] is None
