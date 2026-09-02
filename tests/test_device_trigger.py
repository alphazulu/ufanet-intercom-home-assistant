"""Tests for Ufanet visual device triggers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.components.device_automation import DeviceNotFound
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    DOMAIN,
    EVENT_INTERCOM_CALL,
    EVENT_KEY_PASSAGE,
    EVENT_MOTION_ANALYTICS,
    TRIGGER_INCOMING_CALL,
    TRIGGER_KEY_PASSAGE,
    TRIGGER_MOTION_ANALYTICS,
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


@pytest.mark.asyncio
async def test_supported_device_exposes_and_attaches_key_passage_trigger(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "7")},
        name="Front door",
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "key_passage_coordinator": SimpleNamespace(data={7: {}})
    }

    triggers = await async_get_triggers(hass, device.id)
    assert [item[CONF_TYPE] for item in triggers] == [
        TRIGGER_INCOMING_CALL,
        TRIGGER_KEY_PASSAGE,
    ]

    calls = []

    async def action(variables, _context) -> None:
        calls.append(variables)

    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device.id,
            CONF_TYPE: TRIGGER_KEY_PASSAGE,
        },
        action,
        {"trigger_data": {"id": "key-passage-test"}, "variables": {}},
    )

    event_data = {
        CONF_DEVICE_ID: device.id,
        "skud_id": 7,
        "key_name": "Family key",
        "occurred_at": "2026-09-01T00:00:00+00:00",
    }
    hass.bus.async_fire(EVENT_KEY_PASSAGE, event_data)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0]["trigger"]["event"].data == event_data
    remove()


@pytest.mark.asyncio
async def test_supported_device_exposes_and_attaches_motion_trigger(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "7")},
        name="Front door",
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "key_passage_coordinator": SimpleNamespace(data={}),
        "analytics_coordinator": SimpleNamespace(data={7: {"supported": True}}),
    }

    triggers = await async_get_triggers(hass, device.id)
    assert [item[CONF_TYPE] for item in triggers] == [
        TRIGGER_INCOMING_CALL,
        TRIGGER_MOTION_ANALYTICS,
    ]

    calls = []

    async def action(variables, _context) -> None:
        calls.append(variables)

    remove = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device.id,
            CONF_TYPE: TRIGGER_MOTION_ANALYTICS,
        },
        action,
        {"trigger_data": {"id": "motion-test"}, "variables": {}},
    )

    hass.bus.async_fire(
        EVENT_MOTION_ANALYTICS,
        {
            CONF_DEVICE_ID: "other-device",
            "skud_id": 7,
            "occurred_at": "private-other-time",
        },
    )
    await hass.async_block_till_done()
    assert calls == []

    event_data = {
        CONF_DEVICE_ID: device.id,
        "skud_id": 7,
        "device_name": "Front door",
        "occurred_at": "2026-09-02T10:00:34.793780+00:00",
    }
    hass.bus.async_fire(EVENT_MOTION_ANALYTICS, event_data)
    await hass.async_block_till_done()

    assert len(calls) == 1
    trigger = calls[0]["trigger"]
    assert trigger["event"].event_type == EVENT_MOTION_ANALYTICS
    assert trigger["event"].data == event_data

    remove()
