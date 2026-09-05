"""Tests for privacy-safe physical-key listing and rename services."""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    DOMAIN,
    SERVICE_LIST_PHYSICAL_KEYS,
    SERVICE_RENAME_PHYSICAL_KEY,
)
from custom_components.ufanet_intercom.key_management import (
    async_setup_key_services,
    physical_key_ref,
)

SKUD_ID = 154273


def _key(key_id: int, name: str, devices=(SKUD_ID,), created_at: int = 1_700_000_000):
    return {
        "key_id": key_id,
        "name": name,
        "created_at": created_at,
        "devices": tuple(devices),
    }


def _install_runtime(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Physical keys",
        data={"username": "ACCOUNT"},
        unique_id="physical-keys",
    )
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(SKUD_ID))},
        name="Door",
    )

    api = MagicMock()
    api._async_ufanet_json = AsyncMock()
    api.physical_key_inventory = ()

    key_coordinator = SimpleNamespace(
        data={SKUD_ID: {"key_count": 0, "last_passage_at": None}},
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "entry": entry,
        "coordinator": SimpleNamespace(
            data={SKUD_ID: {"id": SKUD_ID, "cctv_number": "CAM"}}
        ),
        "key_passage_coordinator": key_coordinator,
        "options": {},
    }
    async_setup_key_services(hass)
    return entry, device, api, key_coordinator


def test_physical_key_ref_is_stable_scoped_and_opaque() -> None:
    first = physical_key_ref("entry-a", SKUD_ID, 41)
    assert first == physical_key_ref("entry-a", SKUD_ID, 41)
    assert re.fullmatch(r"[0-9a-f]{24}", first)
    assert first != physical_key_ref("entry-b", SKUD_ID, 41)
    assert first != physical_key_ref("entry-a", SKUD_ID + 1, 41)
    assert first != physical_key_ref("entry-a", SKUD_ID, 42)
    assert "41" not in first


@pytest.mark.asyncio
async def test_list_physical_keys_hides_provider_ids_and_filters_intercom(hass) -> None:
    _entry, device, api, coordinator = _install_runtime(hass)
    api.physical_key_inventory = (
        _key(41, "Front door", created_at=1_700_000_100),
        _key(42, "Other door", devices=(999999,), created_at=1_700_000_200),
    )

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_LIST_PHYSICAL_KEYS,
        {"device_id": device.id},
        blocking=True,
        return_response=True,
    )

    assert result["count"] == 1
    assert result["keys"][0]["name"] == "Front door"
    assert result["keys"][0]["created_at"] == "2023-11-14T22:15:00+00:00"
    assert re.fullmatch(r"[0-9a-f]{24}", result["keys"][0]["key_ref"])
    assert "key_id" not in str(result)
    assert "external_id" not in str(result)
    assert "41" not in result["keys"][0]["key_ref"]
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_rename_physical_key_uses_native_contract_and_verifies_refresh(hass) -> None:
    entry, device, api, coordinator = _install_runtime(hass)
    before = _key(41, "Old name")
    after = _key(41, "New name")
    api.physical_key_inventory = (before,)
    calls = 0

    async def refresh():
        nonlocal calls
        calls += 1
        if calls == 2:
            api.physical_key_inventory = (after,)

    coordinator.async_request_refresh.side_effect = refresh
    key_ref = physical_key_ref(entry.entry_id, SKUD_ID, 41)

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_RENAME_PHYSICAL_KEY,
        {
            "device_id": device.id,
            "key_ref": key_ref,
            "new_name": "  New name  ",
        },
        blocking=True,
        return_response=True,
    )

    api._async_ufanet_json.assert_awaited_once_with(
        "POST",
        "/api/v4/key/edit/",
        json_body={"key_id": 41, "name": "New name"},
    )
    assert coordinator.async_request_refresh.await_count == 2
    assert result == {
        "device_id": device.id,
        "key_ref": key_ref,
        "name": "New name",
        "renamed": True,
        "verified": True,
        "unchanged": False,
    }
    assert "key_id" not in str(result)


@pytest.mark.asyncio
async def test_rename_rejects_stale_or_wrong_intercom_ref_without_post(hass) -> None:
    entry, device, api, _coordinator = _install_runtime(hass)
    api.physical_key_inventory = (_key(41, "Old name"),)
    wrong_ref = physical_key_ref(entry.entry_id, 999999, 41)

    with pytest.raises(ServiceValidationError, match="no longer present"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RENAME_PHYSICAL_KEY,
            {
                "device_id": device.id,
                "key_ref": wrong_ref,
                "new_name": "New name",
            },
            blocking=True,
            return_response=True,
        )
    api._async_ufanet_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_rejects_blank_name_without_provider_call(hass) -> None:
    entry, device, api, _coordinator = _install_runtime(hass)
    api.physical_key_inventory = (_key(41, "Old name"),)
    key_ref = physical_key_ref(entry.entry_id, SKUD_ID, 41)

    with pytest.raises(ServiceValidationError, match="must not be blank"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RENAME_PHYSICAL_KEY,
            {
                "device_id": device.id,
                "key_ref": key_ref,
                "new_name": "   ",
            },
            blocking=True,
            return_response=True,
        )
    api._async_ufanet_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_same_name_is_noop(hass) -> None:
    entry, device, api, coordinator = _install_runtime(hass)
    api.physical_key_inventory = (_key(41, "Same name"),)
    key_ref = physical_key_ref(entry.entry_id, SKUD_ID, 41)

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_RENAME_PHYSICAL_KEY,
        {
            "device_id": device.id,
            "key_ref": key_ref,
            "new_name": "Same name",
        },
        blocking=True,
        return_response=True,
    )

    api._async_ufanet_json.assert_not_awaited()
    coordinator.async_request_refresh.assert_awaited_once()
    assert result["renamed"] is False
    assert result["verified"] is True
    assert result["unchanged"] is True


@pytest.mark.asyncio
async def test_rename_requires_post_write_inventory_confirmation(hass) -> None:
    entry, device, api, coordinator = _install_runtime(hass)
    api.physical_key_inventory = (_key(41, "Old name"),)
    key_ref = physical_key_ref(entry.entry_id, SKUD_ID, 41)

    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RENAME_PHYSICAL_KEY,
            {
                "device_id": device.id,
                "key_ref": key_ref,
                "new_name": "New name",
            },
            blocking=True,
            return_response=True,
        )

    api._async_ufanet_json.assert_awaited_once()
    assert coordinator.async_request_refresh.await_count == 2
