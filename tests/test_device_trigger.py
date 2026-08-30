"""Tests for the visual incoming-call device trigger."""

from __future__ import annotations

import pytest
from homeassistant.components.device_automation import DeviceNotFound
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    DOMAIN,
    EVENT_INTERCOM_CALL,
    TRIGGER_INCOMING_CALL,
)
from custom_components.ufanet_intercom.device_trigger import (
    async_attach_trigger,
    async_get_triggers,
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Device trigger test",
        data={},
        unique_id="device-trigger-test",
    )


@pytest.mark.asyncio
async def test_get_triggers_lists_only_ufanet_devices(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "7")},
        name="Front door",
    )
    unrelated = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_domain", "7")},
        name="Other device",
    )

    assert await async_get_triggers(hass, device.id) == [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device.id,
            CONF_TYPE: TRIGGER_INCOMING_CALL,
        }
    ]
    assert await async_get_triggers(hass, unrelated.id) == []

    with pytest.raises(DeviceNotFound):
        await async_get_triggers(hass, "missing-device")


@pytest.mark.asyncio
async def test_incoming_call_trigger_filters_device_and_preserves_event(hass) -> None:
    device_id = "ufanet-device-id"
    calls = []

    async def action(variables, _context) -> None:
        calls.append(variables)

    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_INCOMING_CALL,
        },
        action,
        {
            "trigger_data": {"id": "incoming-call-test"},
            "variables": {},
        },
    )

    hass.bus.async_fire(EVENT_INTERCOM_CALL, {CONF_DEVICE_ID: "other-device"})
    await hass.async_block_till_done()
    assert calls == []

    event_data = {
        CONF_DEVICE_ID: device_id,
        "skud_id": 7,
        "device_name": "Front door",
    }
    hass.bus.async_fire(EVENT_INTERCOM_CALL, event_data)
    await hass.async_block_till_done()

    assert len(calls) == 1
    trigger = calls[0]["trigger"]
    assert trigger["platform"] == "device"
    assert trigger["event"].event_type == EVENT_INTERCOM_CALL
    assert trigger["event"].data == event_data

    remove()
    hass.bus.async_fire(EVENT_INTERCOM_CALL, event_data)
    await hass.async_block_till_done()
    assert len(calls) == 1
