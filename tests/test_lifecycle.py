"""Tests for integration setup, unload and event serialization lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom import (
    _call_event_data,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ufanet_intercom.api import (
    UfanetAuthError,
    UfanetConnectionError,
)
from custom_components.ufanet_intercom.const import CONF_PASSWORD, CONF_USERNAME, DOMAIN


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        options={},
        unique_id="ab123",
    )


def test_call_event_data_keeps_only_present_serializable_fields() -> None:
    result = _call_event_data(
        {
            "uuid": "u1",
            "called_at": "2026-08-28T10:00:00+10:00",
            "timezone": None,
            "camera_number": "CAM",
            "address": "Street",
            "porch": None,
            "flat": "10",
            "preview_url": None,
            "archive_url": "https://archive.invalid/x.mp4",
            "ignored": "value",
        }
    )

    assert result == {
        "type": "call",
        "uuid": "u1",
        "called_at": "2026-08-28T10:00:00+10:00",
        "camera_number": "CAM",
        "address": "Street",
        "flat": "10",
        "archive_url": "https://archive.invalid/x.mp4",
    }


@pytest.mark.asyncio
async def test_setup_entry_maps_auth_failure(hass) -> None:
    entry = _entry()

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi") as api_cls,
    ):
        api_cls.return_value.async_login = AsyncMock(
            side_effect=UfanetAuthError("bad credentials")
        )
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_setup_entry_maps_connection_failure_to_not_ready(hass) -> None:
    entry = _entry()

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi") as api_cls,
    ):
        api_cls.return_value.async_login = AsyncMock(
            side_effect=UfanetConnectionError("offline")
        )
        with pytest.raises(ConfigEntryNotReady, match="offline"):
            await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_setup_entry_builds_runtime_and_optional_archive(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    skud = {"id": 7, "cctv_number": "CAM", "custom_name": "Door"}
    api = MagicMock()
    api.async_login = AsyncMock(return_value=None)

    coordinator = MagicMock()
    coordinator.data = {7: skud}
    coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)

    call_coordinator = MagicMock()
    call_coordinator.data = None
    call_coordinator.new_calls = []
    call_coordinator.async_refresh = AsyncMock(return_value=None)
    call_coordinator.async_add_listener.return_value = lambda: None

    controller = MagicMock()
    controller.async_initialize = AsyncMock(return_value=None)

    auto_manager = MagicMock()
    auto_manager.enabled = False

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi", return_value=api),
        patch("custom_components.ufanet_intercom.UfanetCoordinator", return_value=coordinator),
        patch(
            "custom_components.ufanet_intercom.UfanetCallCoordinator",
            return_value=call_coordinator,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetArchiveController",
            return_value=controller,
        ) as archive_cls,
        patch(
            "custom_components.ufanet_intercom.UfanetCallAutoSaveManager",
            return_value=auto_manager,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(return_value=None),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry) is True

    runtime = hass.data[DOMAIN][entry.entry_id]
    assert runtime["api"] is api
    assert runtime["coordinator"] is coordinator
    assert runtime["call_coordinator"] is call_coordinator
    assert runtime["archive_controllers"] == {7: controller}
    assert call_coordinator.data == {}
    controller.async_initialize.assert_awaited_once()
    archive_cls.assert_called_once()
    forward.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_removes_runtime_only_after_platform_success(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"sentinel": True}

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=False),
    ):
        assert await async_unload_entry(hass, entry) is False
    assert entry.entry_id in hass.data[DOMAIN]

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        assert await async_unload_entry(hass, entry) is True
    assert entry.entry_id not in hass.data[DOMAIN]
