"""Date/time platform for Ufanet archive playback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .archive import UfanetArchiveController
from .const import DOMAIN
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up archive date/time controls."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    controllers: dict[int, UfanetArchiveController] = runtime["archive_controllers"]
    coordinator = runtime["coordinator"]

    async_add_entities(
        UfanetArchiveDateTime(controller, coordinator.data[skud_id])
        for skud_id, controller in controllers.items()
        if skud_id in coordinator.data
    )


class UfanetArchiveDateTime(DateTimeEntity):
    """Archive playback start date/time."""

    _attr_has_entity_name = True
    _attr_translation_key = "archive_position"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        controller: UfanetArchiveController,
        skud: dict[str, Any],
    ) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.skud_id}_archive_position"
        self._attr_device_info = device_info(skud)

    @property
    def native_value(self) -> datetime:
        return self.controller.position

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "camera_timezone": self.controller.timezone_name,
            "archive_name": self.controller.archive_name,
            "dvr_hours": self.controller.dvr_hours,
        }

    async def async_set_value(self, value: datetime) -> None:
        await self.controller.async_set_position(value)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.controller.async_add_listener(self.async_write_ha_state)
        )
