"""Sensor platform for Ufanet Intercom."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UfanetCallCoordinator, UfanetCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up last-call sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]
    call_coordinator: UfanetCallCoordinator = runtime["call_coordinator"]

    async_add_entities(
        UfanetLastCallSensor(call_coordinator, skud)
        for skud in coordinator.data.values()
        if skud.get("cctv_number")
    )


class UfanetLastCallSensor(SensorEntity):
    """Timestamp sensor representing the latest intercom call."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_call"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:phone-incoming"

    def __init__(
        self,
        call_coordinator: UfanetCallCoordinator,
        skud: dict[str, Any],
    ) -> None:
        self.call_coordinator = call_coordinator
        self.skud_id = int(skud["id"])
        self.camera_number = str(skud["cctv_number"])
        self._attr_unique_id = f"{self.skud_id}_last_call"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        """Return coordinator availability."""
        return self.call_coordinator.last_update_success

    @property
    def native_value(self) -> datetime | None:
        """Return the absolute timestamp encoded by called_at."""
        event = self.call_coordinator.data.get(self.camera_number)
        if not event:
            return None
        value = event.get("called_at")
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return useful metadata and short-lived media URLs for the call."""
        event = self.call_coordinator.data.get(self.camera_number)
        if not event:
            return None
        return {
            "uuid": event.get("uuid"),
            "camera_number": event.get("camera_number"),
            "timezone": event.get("timezone"),
            "address": event.get("address"),
            "porch": event.get("porch"),
            "flat": event.get("flat"),
            "preview_url": event.get("preview_url"),
            "archive_url": event.get("archive_url"),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to call coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.call_coordinator.async_add_listener(self.async_write_ha_state)
        )
