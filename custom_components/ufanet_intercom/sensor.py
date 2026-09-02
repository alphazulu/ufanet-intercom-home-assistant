"""Sensor platform for Ufanet Intercom."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import (
    UfanetCallCoordinator,
    UfanetCoordinator,
    UfanetKeyPassageCoordinator,
)
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

    passage_coordinator: UfanetKeyPassageCoordinator = runtime[
        "key_passage_coordinator"
    ]

    entities: list[SensorEntity] = [
        UfanetLastCallSensor(call_coordinator, skud)
        for skud in coordinator.data.values()
        if skud.get("cctv_number")
    ]
    for skud_id in passage_coordinator.data:
        if (skud := coordinator.data.get(skud_id)) is None:
            continue
        entities.extend(
            (
                UfanetPhysicalKeyCountSensor(passage_coordinator, skud),
                UfanetLastKeyPassageSensor(passage_coordinator, skud),
            )
        )
    async_add_entities(entities)


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
        """Return useful metadata without tokenized media URLs."""
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
            "has_preview": bool(event.get("preview_url")),
            "has_archive": bool(event.get("archive_url")),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to call coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.call_coordinator.async_add_listener(self.async_write_ha_state)
        )


class _UfanetKeyPassageSensor(SensorEntity):
    """Base sensor backed by the physical-key passage coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UfanetKeyPassageCoordinator,
        skud: dict[str, Any],
        suffix: str,
    ) -> None:
        self.coordinator = coordinator
        self.skud_id = int(skud["id"])
        self._attr_unique_id = f"{self.skud_id}_{suffix}"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        """Return whether passage polling is healthy for this intercom."""
        return (
            self.coordinator.last_update_success
            and self.skud_id in self.coordinator.data
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to physical-key coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class UfanetPhysicalKeyCountSensor(_UfanetKeyPassageSensor):
    """Number of registered physical keys linked to one intercom."""

    _attr_translation_key = "physical_key_count"
    _attr_icon = "mdi:key-chain-variant"

    def __init__(
        self,
        coordinator: UfanetKeyPassageCoordinator,
        skud: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, skud, "physical_key_count")

    @property
    def native_value(self) -> int | None:
        """Return the number of keys linked to this intercom."""
        state = self.coordinator.data.get(self.skud_id)
        if state is None:
            return None
        value = state.get("key_count")
        return int(value) if value is not None else None


class UfanetLastKeyPassageSensor(_UfanetKeyPassageSensor):
    """Timestamp of the latest physical-key passage."""

    _attr_translation_key = "last_key_passage"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:door-open"

    def __init__(
        self,
        coordinator: UfanetKeyPassageCoordinator,
        skud: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, skud, "last_key_passage")

    @property
    def native_value(self) -> datetime | None:
        """Return the latest passage time in UTC."""
        state = self.coordinator.data.get(self.skud_id)
        if state is None:
            return None
        value = state.get("last_passage_at")
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (OSError, OverflowError, TypeError, ValueError):
            return None
