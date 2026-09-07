"""Sensor platform for Ufanet Intercom."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UfanetCallCoordinator, UfanetCoordinator
from .entity import device_info
from .key_coordinator import UfanetKeyPassageCoordinator


def _known_key_capable_ids(coordinator: Any) -> set[int]:
    if bool(getattr(coordinator, "capability_known", False)):
        return {int(value) for value in getattr(coordinator, "supported_skud_ids", set())}
    data = getattr(coordinator, "data", None)
    return {int(value) for value in data} if isinstance(data, dict) else set()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up last-call and physical-key sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]
    call_coordinator: UfanetCallCoordinator = runtime["call_coordinator"]
    passage_coordinator: UfanetKeyPassageCoordinator = runtime[
        "key_passage_coordinator"
    ]

    async_add_entities(
        [
            UfanetLastCallSensor(call_coordinator, skud)
            for skud in coordinator.data.values()
            if skud.get("cctv_number")
        ]
    )

    added_key_ids: set[int] = set()

    @callback
    def _add_supported_key_sensors() -> None:
        new_ids = [
            skud_id
            for skud_id in sorted(_known_key_capable_ids(passage_coordinator))
            if skud_id in coordinator.data and skud_id not in added_key_ids
        ]
        if not new_ids:
            return
        added_key_ids.update(new_ids)
        entities: list[SensorEntity] = []
        for skud_id in new_ids:
            skud = coordinator.data[skud_id]
            entities.extend(
                (
                    UfanetPhysicalKeyCountSensor(passage_coordinator, skud),
                    UfanetLastKeyPassageSensor(passage_coordinator, skud),
                )
            )
        async_add_entities(entities)

    _add_supported_key_sensors()
    entry.async_on_unload(
        passage_coordinator.async_add_listener(_add_supported_key_sensors)
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
        """Return whether key inventory is healthy for this intercom."""
        supports_skud = getattr(self.coordinator, "supports_skud", None)
        supported = (
            supports_skud(self.skud_id)
            if callable(supports_skud)
            else self.skud_id in self.coordinator.data
        )
        return (
            self.coordinator.last_update_success
            and supported
            and self.skud_id in self.coordinator.data
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to physical-key coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class UfanetPhysicalKeyCountSensor(_UfanetKeyPassageSensor):
    """Number and read-only inventory of physical keys linked to one intercom."""

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose key names/dates without provider key or external IDs."""
        api = getattr(self.coordinator, "api", None)
        inventory = getattr(api, "physical_key_inventory", ())
        visible: list[tuple[int, int, dict[str, str | None]]] = []

        for key in inventory:
            if not isinstance(key, dict):
                continue
            devices = key.get("devices") or ()
            if self.skud_id not in devices:
                continue
            name = key.get("name")
            created_at = key.get("created_at")
            key_id = key.get("key_id")
            if not isinstance(name, str):
                continue

            created_iso: str | None = None
            if isinstance(created_at, int) and not isinstance(created_at, bool):
                try:
                    created_iso = datetime.fromtimestamp(
                        created_at,
                        tz=timezone.utc,
                    ).isoformat()
                except (OSError, OverflowError, ValueError):
                    created_iso = None

            sort_key_id = (
                key_id
                if isinstance(key_id, int) and not isinstance(key_id, bool)
                else 0
            )
            sort_created = (
                created_at
                if isinstance(created_at, int) and not isinstance(created_at, bool)
                else 0
            )
            visible.append(
                (
                    sort_created,
                    sort_key_id,
                    {"name": name, "created_at": created_iso},
                )
            )

        visible.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return {"keys": [item[2] for item in visible]}


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
    def available(self) -> bool:
        """Return whether passage history itself is healthy."""
        if not super().available:
            return False
        state = self.coordinator.data.get(self.skud_id) or {}
        return bool(state.get("history_healthy", True))

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