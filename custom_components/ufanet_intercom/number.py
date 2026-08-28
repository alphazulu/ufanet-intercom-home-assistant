"""Number platform for Ufanet archive playback."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
    """Set up archive duration and navigation step."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    controllers: dict[int, UfanetArchiveController] = runtime["archive_controllers"]
    coordinator = runtime["coordinator"]

    entities: list[NumberEntity] = []
    for skud_id, controller in controllers.items():
        skud = coordinator.data.get(skud_id)
        if skud is None:
            continue
        entities.append(UfanetArchiveDuration(controller, skud))
        entities.append(UfanetArchiveStep(controller, skud))
    async_add_entities(entities)


class _UfanetArchiveNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        controller: UfanetArchiveController,
        skud: dict[str, Any],
    ) -> None:
        self.controller = controller
        self._attr_device_info = device_info(skud)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.controller.async_add_listener(self.async_write_ha_state)
        )


class UfanetArchiveDuration(_UfanetArchiveNumber):
    """Requested archive clip duration."""

    _attr_translation_key = "archive_duration"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 30
    _attr_native_max_value = 3600
    _attr_native_step = 30

    def __init__(self, controller: UfanetArchiveController, skud: dict[str, Any]) -> None:
        super().__init__(controller, skud)
        self._attr_unique_id = f"{controller.skud_id}_archive_duration"

    @property
    def native_value(self) -> float:
        return float(self.controller.duration)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_duration(int(value))


class UfanetArchiveStep(_UfanetArchiveNumber):
    """Backward/forward navigation step."""

    _attr_translation_key = "archive_step"
    _attr_icon = "mdi:ray-start-arrow"
    _attr_native_min_value = 10
    _attr_native_max_value = 3600
    _attr_native_step = 10

    def __init__(self, controller: UfanetArchiveController, skud: dict[str, Any]) -> None:
        super().__init__(controller, skud)
        self._attr_unique_id = f"{controller.skud_id}_archive_step"

    @property
    def native_value(self) -> float:
        return float(self.controller.step)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_step(int(value))
