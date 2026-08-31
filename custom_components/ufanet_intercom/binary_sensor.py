"""Binary sensor platform for Ufanet Intercom."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, EVENT_INTERCOM_CALL, INCOMING_CALL_STATE_SECONDS
from .coordinator import UfanetCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up incoming-call binary sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]

    async_add_entities(
        UfanetIncomingCallBinarySensor(skud)
        for skud in coordinator.data.values()
        if skud.get("cctv_number")
    )


class UfanetIncomingCallBinarySensor(BinarySensorEntity):
    """Represent a recently confirmed incoming intercom call."""

    _attr_has_entity_name = True
    _attr_translation_key = "incoming_call"
    _attr_icon = "mdi:bell-ring"
    _attr_is_on = False

    def __init__(self, skud: dict[str, Any]) -> None:
        self.skud_id = int(skud["id"])
        self._attr_unique_id = f"{self.skud_id}_incoming_call"
        self._attr_device_info = device_info(skud)
        self._cancel_turn_off: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to confirmed intercom-call events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_INTERCOM_CALL,
                self._async_handle_call,
            )
        )
        self.async_on_remove(self._async_cancel_turn_off)

    @callback
    def _async_handle_call(self, event: Event) -> None:
        """Turn on for a confirmed call belonging to this intercom."""
        if event.data.get("skud_id") != self.skud_id:
            return

        self._async_cancel_turn_off()
        self._attr_is_on = True
        self._cancel_turn_off = async_call_later(
            self.hass,
            INCOMING_CALL_STATE_SECONDS,
            self._async_turn_off,
        )
        self.async_write_ha_state()

    @callback
    def _async_turn_off(self, _now: datetime) -> None:
        """Clear the transient ringing state."""
        self._cancel_turn_off = None
        if not self._attr_is_on:
            return
        self._attr_is_on = False
        self.async_write_ha_state()

    @callback
    def _async_cancel_turn_off(self) -> None:
        """Cancel a pending state reset."""
        if self._cancel_turn_off is not None:
            self._cancel_turn_off()
            self._cancel_turn_off = None
