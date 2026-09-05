"""Tests for physical-key enrollment support."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ufanet_intercom.api import UfanetApiError
from custom_components.ufanet_intercom.button import (
    UfanetPhysicalKeyEnrollmentButton,
    async_setup_entry,
)
from custom_components.ufanet_intercom.const import DOMAIN
from custom_components.ufanet_intercom.key_enrollment import (
    KEY_ENROLLMENT_WINDOW_SECONDS,
    async_start_physical_key_enrollment,
)


def _skud(skud_id: int = 7, *, blocked: bool = False) -> dict:
    return {
        "id": skud_id,
        "cctv_number": f"CAM-{skud_id}",
        "custom_name": "Front door",
        "role": {"name": "Intercom"},
        "model": 39,
        "open_type": "http",
        "disable_button": False,
        "is_blocked": blocked,
        "relays": [],
    }


@pytest.mark.asyncio
async def test_enrollment_helper_uses_native_auto_collect_endpoint() -> None:
    api = SimpleNamespace(_async_ufanet_json=AsyncMock(return_value={"status": "ok"}))

    await async_start_physical_key_enrollment(api, 154273)

    api._async_ufanet_json.assert_awaited_once_with(
        "POST",
        "/api/v4/key/skud/154273/auto_collect/enable/",
    )


@pytest.mark.asyncio
async def test_button_is_exposed_only_for_key_recording_capable_intercoms() -> None:
    supported = _skud(7)
    unsupported = _skud(8)
    coordinator = SimpleNamespace(
        data={7: supported, 8: unsupported},
        last_update_success=True,
        async_add_listener=MagicMock(return_value=lambda: None),
    )
    key_coordinator = SimpleNamespace(data={7: {"key_count": 0, "last_passage_at": None}})
    runtime = {
        "coordinator": coordinator,
        "api": SimpleNamespace(),
        "key_passage_coordinator": key_coordinator,
        "archive_controllers": {},
    }
    hass = SimpleNamespace(data={DOMAIN: {"entry": runtime}})
    entry = SimpleNamespace(entry_id="entry")
    added: list = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    enrollment = [
        entity for entity in added if isinstance(entity, UfanetPhysicalKeyEnrollmentButton)
    ]
    assert len(enrollment) == 1
    assert enrollment[0].skud_id == 7


@pytest.mark.asyncio
async def test_enrollment_button_properties_and_press(monkeypatch) -> None:
    coordinator = SimpleNamespace(
        data={7: _skud(7)},
        last_update_success=True,
    )
    api = SimpleNamespace()
    start = AsyncMock()
    monkeypatch.setattr(
        "custom_components.ufanet_intercom.button.async_start_physical_key_enrollment",
        start,
    )
    entity = UfanetPhysicalKeyEnrollmentButton(coordinator, api, _skud(7))

    assert entity.unique_id == "7_add_physical_key"
    assert entity.translation_key == "add_physical_key"
    assert entity.icon == "mdi:key-plus"
    assert entity.available is True
    assert entity.extra_state_attributes == {
        "enrollment_window_seconds": KEY_ENROLLMENT_WINDOW_SECONDS
    }

    await entity.async_press()
    start.assert_awaited_once_with(api, 7)


@pytest.mark.asyncio
async def test_enrollment_button_unavailable_when_intercom_is_blocked() -> None:
    coordinator = SimpleNamespace(
        data={7: _skud(7, blocked=True)},
        last_update_success=True,
    )
    entity = UfanetPhysicalKeyEnrollmentButton(
        coordinator,
        SimpleNamespace(),
        _skud(7, blocked=True),
    )

    assert entity.available is False


@pytest.mark.asyncio
async def test_enrollment_button_wraps_api_error(monkeypatch) -> None:
    coordinator = SimpleNamespace(
        data={7: _skud(7)},
        last_update_success=True,
    )
    start = AsyncMock(side_effect=UfanetApiError("HTTP 400"))
    monkeypatch.setattr(
        "custom_components.ufanet_intercom.button.async_start_physical_key_enrollment",
        start,
    )
    entity = UfanetPhysicalKeyEnrollmentButton(
        coordinator,
        SimpleNamespace(),
        _skud(7),
    )

    with pytest.raises(HomeAssistantError, match="failed to start physical key enrollment"):
        await entity.async_press()
