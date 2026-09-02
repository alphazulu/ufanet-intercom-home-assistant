"""Event platform for Ufanet physical-key passages."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_KEY_PASSAGE
from .coordinator import UfanetCoordinator, UfanetKeyPassageCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up physical-key passage event entities."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]
    passage_coordinator: UfanetKeyPassageCoordinator = runtime[
        "key_passage_coordinator"
    ]

    async_add_entities(
        UfanetKeyPassageEvent(passage_coordinator, coordinator.data[skud_id])
        for skud_id in passage_coordinator.data
        if skud_id in coordinator.data
    )


class UfanetKeyPassageEvent(EventEntity):
    """Represent the latest physical-key passage for one intercom."""

    _attr_has_entity_name = True
    _attr_translation_key = "key_passage"
    _attr_icon = "mdi:key-chain-variant"
    _attr_event_types: ClassVar[list[str]] = ["passage"]

    def __init__(
        self,
        coordinator: UfanetKeyPassageCoordinator,
        skud: dict[str, Any],
    ) -> None:
        self.coordinator = coordinator
        self.skud_id = int(skud["id"])
        self._attr_unique_id = f"{self.skud_id}_key_passage"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        """Return whether passage polling is healthy for this intercom."""
        return (
            self.coordinator.last_update_success
            and self.skud_id in self.coordinator.data
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to sanitized key-passage events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_KEY_PASSAGE,
                self._async_handle_passage,
            )
        )

    @callback
    def _async_handle_passage(self, event: Event) -> None:
        """Update the entity for a passage belonging to this intercom."""
        if event.data.get("skud_id") != self.skud_id:
            return
        attributes = {
            field: event.data[field]
            for field in ("key_name", "occurred_at")
            if field in event.data
        }
        self._trigger_event("passage", attributes)
        self.async_write_ha_state()
