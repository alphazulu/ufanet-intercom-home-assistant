"""Tests for the incoming-call binary sensor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.binary_sensor import (
    UfanetIncomingCallBinarySensor,
    async_setup_entry,
)
from custom_components.ufanet_intercom.const import (
    DOMAIN,
    EVENT_INTERCOM_CALL,
    INCOMING_CALL_STATE_SECONDS,
)


def _skud(skud_id: int = 7) -> dict:
    return {
        "id": skud_id,
        "cctv_number": f"camera-{skud_id}",
        "custom_name": "Front door",
        "role": {"name": "Intercom"},
        "model": 39,
    }


@pytest.mark.asyncio
async def test_setup_creates_sensor_only_for_intercoms_with_camera(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.data = {
        7: _skud(),
        8: {"id": 8, "custom_name": "No camera"},
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
    }
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    entities = list(async_add_entities.call_args.args[0])
    assert len(entities) == 1
    assert entities[0].unique_id == "7_incoming_call"
    assert entities[0].is_on is False


@pytest.mark.asyncio
async def test_confirmed_call_turns_sensor_on_and_scheduled_reset_turns_it_off(
    hass,
) -> None:
    sensor = UfanetIncomingCallBinarySensor(_skud())
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()
    cancel_turn_off = MagicMock()

    with patch(
        "custom_components.ufanet_intercom.binary_sensor.async_call_later",
        return_value=cancel_turn_off,
    ) as call_later:
        await sensor.async_added_to_hass()

        hass.bus.async_fire(EVENT_INTERCOM_CALL, {"skud_id": 99})
        await hass.async_block_till_done()
        assert sensor.is_on is False
        call_later.assert_not_called()

        hass.bus.async_fire(EVENT_INTERCOM_CALL, {"skud_id": 7})
        await hass.async_block_till_done()

        assert sensor.is_on is True
        call_later.assert_called_once()
        assert call_later.call_args.args[:2] == (
            hass,
            INCOMING_CALL_STATE_SECONDS,
        )
        clear_state = call_later.call_args.args[2]
        clear_state(None)

        assert sensor.is_on is False
        assert sensor.async_write_ha_state.call_count == 2


@pytest.mark.asyncio
async def test_repeated_call_restarts_state_timer(hass) -> None:
    sensor = UfanetIncomingCallBinarySensor(_skud())
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()
    first_cancel = MagicMock()
    second_cancel = MagicMock()

    with patch(
        "custom_components.ufanet_intercom.binary_sensor.async_call_later",
        side_effect=[first_cancel, second_cancel],
    ) as call_later:
        await sensor.async_added_to_hass()

        hass.bus.async_fire(EVENT_INTERCOM_CALL, {"skud_id": 7})
        await hass.async_block_till_done()
        hass.bus.async_fire(EVENT_INTERCOM_CALL, {"skud_id": 7})
        await hass.async_block_till_done()

        assert sensor.is_on is True
        assert call_later.call_count == 2
        first_cancel.assert_called_once_with()
        second_cancel.assert_not_called()
