"""Tests for separated Ufanet authorization and advanced FCM actions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.authorized_devices import (
    async_setup_authorized_device_services,
)
from custom_components.ufanet_intercom.const import (
    CONF_USERNAME,
    DOMAIN,
    SERVICE_LIST_AUTHORIZED_DEVICES,
    SERVICE_LIST_FCM_REGISTRATIONS,
    SERVICE_REVOKE_AUTHORIZED_DEVICE,
    SERVICE_UNREGISTER_FCM_REGISTRATION,
)


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
        title="Authorization test",
        data={CONF_USERNAME: "ACCOUNT"},
        unique_id="authorization-test",
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
    api.async_unregister_fcm_device = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "entry": entry,
        "coordinator": SimpleNamespace(data={7: {"id": 7}}),
        "options": {},
    }
    async_setup_authorized_device_services(hass)
    return device, api


@pytest.mark.asyncio
async def test_list_authorized_devices_uses_authorization_semantics(hass) -> None:
    device, api = _install_runtime(hass)
    api.async_get_authorized_fcm_devices.return_value = [
        _device_row("phone-private", "Phone", "2026-09-08T01:00:00Z")
    ]
    with patch(
        "custom_components.ufanet_intercom.authorized_devices.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value=set()),
    ):
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_LIST_AUTHORIZED_DEVICES,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )

    assert result["count"] == 1
    assert result["authorizations"][0]["title"] == "Phone"
    assert "authorization_ref" in result["authorizations"][0]
    assert "session_ref" not in result["authorizations"][0]
    assert "phone-private" not in str(result)


@pytest.mark.asyncio
async def test_revoke_authorized_device_uses_logout_not_fcm_delete(hass) -> None:
    device, api = _install_runtime(hass)
    target = _device_row("phone-private", "Phone", "2026-09-08T01:00:00Z")
    api.async_get_authorized_fcm_devices.return_value = [target]
    with patch(
        "custom_components.ufanet_intercom.authorized_devices.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value=set()),
    ):
        listed = await hass.services.async_call(
            DOMAIN,
            SERVICE_LIST_AUTHORIZED_DEVICES,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )
        api.async_get_authorized_fcm_devices.side_effect = [[target], []]
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_REVOKE_AUTHORIZED_DEVICE,
            {
                "device_id": device.id,
                "authorization_ref": listed["authorizations"][0]["authorization_ref"],
                "confirm": True,
            },
            blocking=True,
            return_response=True,
        )

    assert result["revoked"] is True
    api.async_logout_fcm_device.assert_awaited_once_with(device_id="phone-private")
    api.async_unregister_fcm_device.assert_not_awaited()


@pytest.mark.asyncio
async def test_unregister_fcm_registration_uses_delete_not_logout(hass) -> None:
    device, api = _install_runtime(hass)
    target = _device_row("phone-private", "Phone", "2026-09-08T01:00:00Z")
    api.async_get_authorized_fcm_devices.return_value = [target]
    with patch(
        "custom_components.ufanet_intercom.authorized_devices.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value=set()),
    ):
        listed = await hass.services.async_call(
            DOMAIN,
            SERVICE_LIST_FCM_REGISTRATIONS,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )
        api.async_get_authorized_fcm_devices.side_effect = [[target], [target]]
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_UNREGISTER_FCM_REGISTRATION,
            {
                "device_id": device.id,
                "fcm_ref": listed["registrations"][0]["fcm_ref"],
                "confirm": True,
            },
            blocking=True,
            return_response=True,
        )

    assert result["unregistered"] is True
    assert result["authorized_device_still_visible"] is True
    api.async_unregister_fcm_device.assert_awaited_once_with(device_id="phone-private")
    api.async_logout_fcm_device.assert_not_awaited()


@pytest.mark.asyncio
async def test_unregister_fcm_registration_protects_ha_owned_device(hass) -> None:
    device, api = _install_runtime(hass)
    target = _device_row("ha-private", "Home Assistant", "2026-09-08T01:00:00Z")
    api.async_get_authorized_fcm_devices.return_value = [target]
    with patch(
        "custom_components.ufanet_intercom.authorized_devices.async_owned_fcm_device_ids_for_account",
        AsyncMock(return_value={"ha-private"}),
    ):
        listed = await hass.services.async_call(
            DOMAIN,
            SERVICE_LIST_FCM_REGISTRATIONS,
            {"device_id": device.id},
            blocking=True,
            return_response=True,
        )
        with pytest.raises(ServiceValidationError, match="protected"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_UNREGISTER_FCM_REGISTRATION,
                {
                    "device_id": device.id,
                    "fcm_ref": listed["registrations"][0]["fcm_ref"],
                    "confirm": True,
                },
                blocking=True,
                return_response=True,
            )

    api.async_unregister_fcm_device.assert_not_awaited()
    api.async_logout_fcm_device.assert_not_awaited()
