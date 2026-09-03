"""Integration-style tests for FCM authorized-session security services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    CONF_USERNAME,
    DOMAIN,
    SERVICE_LIST_FCM_SESSIONS,
    SERVICE_REVOKE_FCM_SESSION,
    SERVICE_REVOKE_OTHER_FCM_SESSIONS,
)
from custom_components.ufanet_intercom.services import async_setup_services


def _device_row(device_id: str, title: str, when: str, platform: str = "Android"):
    return {
        "device_id": device_id,
        "title": title,
        "last_update": when,
        "is_call_access": True,
        "os": 0,
        "os_display": platform,
    }


def _install_runtime(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FCM security",
        data={CONF_USERNAME: "ACCOUNT"},
        unique_id="fcm-security",
    )
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "7")},
        name="Door",
    )
    api = MagicMock()
    api.async_get_authorized_fcm_devices = AsyncMock()
    api.async_logout_fcm_device = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "entry": entry,
        "coordinator": SimpleNamespace(data={7: {"id": 7, "cctv_number": "CAM"}}),
        "options": {},
    }
    async_setup_services(hass, MagicMock())
    return device, api


@pytest.mark.asyncio
async def test_list_fcm_sessions_hides_provider_ids_and_marks_ha_owned(hass) -> None:
    device, api = _install_runtime(hass)
    api.async_get_authorized_fcm_devices.return_value = [
        _device_row("ha-private", "Home Assistant", "2026-09-03T01:00:00Z"),
        _device_row("phone-private", "Unknown Phone", "2026-09-02T01:00:00Z", "iOS"),
    ]
    with patch(
        "custom_components.ufanet_intercom.services.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value={"ha-private"}),
    ):
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_LIST_FCM_SESSIONS,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )
    assert result["count"] == 2
    assert result["protected_count"] == 1
    assert result["revocable_count"] == 1
    assert "ha-private" not in str(result)
    assert "phone-private" not in str(result)


@pytest.mark.asyncio
async def test_revoke_fcm_session_rejects_protected_ha_registration(hass) -> None:
    device, api = _install_runtime(hass)
    api.async_get_authorized_fcm_devices.return_value = [
        _device_row("ha-private", "Home Assistant", "2026-09-03T01:00:00Z")
    ]
    with patch(
        "custom_components.ufanet_intercom.services.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value={"ha-private"}),
    ):
        listed = await hass.services.async_call(
            DOMAIN,
            SERVICE_LIST_FCM_SESSIONS,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )
        with pytest.raises(ServiceValidationError, match="protected"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_REVOKE_FCM_SESSION,
                {
                    "device_id": device.id,
                    "session_ref": listed["sessions"][0]["session_ref"],
                    "confirm": True,
                },
                blocking=True,
                return_response=True,
            )
    api.async_logout_fcm_device.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_fcm_session_refetches_and_verifies_disappearance(hass) -> None:
    device, api = _install_runtime(hass)
    target = _device_row("phone-private", "Phone", "2026-09-03T01:00:00Z")
    api.async_get_authorized_fcm_devices.return_value = [target]
    with patch(
        "custom_components.ufanet_intercom.services.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value=set()),
    ):
        listed = await hass.services.async_call(
            DOMAIN,
            SERVICE_LIST_FCM_SESSIONS,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )
        api.async_get_authorized_fcm_devices.side_effect = [[target], []]
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_REVOKE_FCM_SESSION,
            {
                "device_id": device.id,
                "session_ref": listed["sessions"][0]["session_ref"],
                "confirm": True,
            },
            blocking=True,
            return_response=True,
        )
    assert result["revoked"] is True
    assert "phone-private" not in str(result)
    api.async_logout_fcm_device.assert_awaited_once_with(device_id="phone-private")


@pytest.mark.asyncio
async def test_bulk_revoke_aborts_when_expected_count_changed(hass) -> None:
    device, api = _install_runtime(hass)
    api.async_get_authorized_fcm_devices.return_value = [
        _device_row("one", "One", "2026-09-03T01:00:00Z"),
        _device_row("two", "Two", "2026-09-03T00:00:00Z"),
    ]
    with patch(
        "custom_components.ufanet_intercom.services.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value=set()),
    ):
        with pytest.raises(ServiceValidationError, match="count changed"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_REVOKE_OTHER_FCM_SESSIONS,
                {
                    "device_id": device.id,
                    "expected_count": 1,
                    "confirm": True,
                },
                blocking=True,
                return_response=True,
            )
    api.async_logout_fcm_device.assert_not_awaited()
