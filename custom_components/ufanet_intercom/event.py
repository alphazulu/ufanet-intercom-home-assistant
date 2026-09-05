"""Event platform for Ufanet calls, physical-key passages and motion analytics."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.event import DoorbellEventType, EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .analytics import UfanetMotionAnalyticsCoordinator
from .const import (
    DOMAIN,
    EVENT_INTERCOM_CALL,
    EVENT_KEY_PASSAGE,
    EVENT_MOTION_ANALYTICS,
)
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
    """Set up call, passage and motion event entities."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]
    call_coordinator: UfanetCallCoordinator = runtime["call_coordinator"]
    passage_coordinator: UfanetKeyPassageCoordinator = runtime[
        "key_passage_coordinator"
    ]
    analytics_coordinator: UfanetMotionAnalyticsCoordinator | None = runtime.get(
        "analytics_coordinator"
    )

    call_entities: list[EventEntity] = [
        UfanetIncomingCallEvent(call_coordinator, skud)
        for skud in coordinator.data.values()
        if skud.get("cctv_number")
    ]
    passage_entities: list[EventEntity] = [
        UfanetKeyPassageEvent(passage_coordinator, coordinator.data[skud_id])
        for skud_id in passage_coordinator.data
        if skud_id in coordinator.data
    ]
    async_add_entities([*call_entities, *passage_entities])

    if analytics_coordinator is None:
        return

    added_motion_ids: set[int] = set()

    @callback
    def _add_supported_motion_entities() -> None:
        """Add newly discovered motion entities after coordinator recovery."""
        data = analytics_coordinator.data
        if not isinstance(data, dict):
            return
        new_ids = [
            skud_id
            for skud_id in data
            if skud_id in coordinator.data and skud_id not in added_motion_ids
        ]
        if not new_ids:
            return
        added_motion_ids.update(new_ids)
        async_add_entities(
            [
                UfanetMotionAnalyticsEvent(
                    analytics_coordinator,
                    coordinator.data[skud_id],
                )
                for skud_id in new_ids
            ]
        )

    _add_supported_motion_entities()
    entry.async_on_unload(
        analytics_coordinator.async_add_listener(_add_supported_motion_entities)
    )


class UfanetIncomingCallEvent(EventEntity):
    """Represent a confirmed Ufanet intercom call as a standard doorbell event."""

    _attr_has_entity_name = True
    _attr_translation_key = "incoming_call_event"
    _attr_icon = "mdi:doorbell-video"
    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types: ClassVar[list[str]] = [DoorbellEventType.RING]

    def __init__(
        self,
        coordinator: UfanetCallCoordinator,
        skud: dict[str, Any],
    ) -> None:
        self.coordinator = coordinator
        self.skud_id = int(skud["id"])
        self._attr_unique_id = f"{self.skud_id}_incoming_call_event"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        """Return whether call-history updates are healthy."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """Subscribe to privacy-safe incoming-call events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_INTERCOM_CALL,
                self._async_handle_call,
            )
        )

    @callback
    def _async_handle_call(self, event: Event) -> None:
        """Publish a standard ring event for this intercom only."""
        if event.data.get("skud_id") != self.skud_id:
            return
        attributes = {
            field: event.data[field]
            for field in (
                "uuid",
                "called_at",
                "address",
                "porch",
                "flat",
                "has_preview",
                "has_archive",
            )
            if field in event.data
        }
        self._trigger_event(DoorbellEventType.RING, attributes)
        self.async_write_ha_state()


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


class UfanetMotionAnalyticsEvent(EventEntity):
    """Represent privacy-minimized UCAMS motion events for one intercom."""

    _attr_has_entity_name = True
    _attr_translation_key = "motion_analytics"
    _attr_icon = "mdi:motion-sensor"
    _attr_event_types: ClassVar[list[str]] = ["motion"]

    def __init__(
        self,
        coordinator: UfanetMotionAnalyticsCoordinator,
        skud: dict[str, Any],
    ) -> None:
        self.coordinator = coordinator
        self.skud_id = int(skud["id"])
        self._attr_unique_id = f"{self.skud_id}_motion_analytics"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        """Return whether motion polling is healthy for this intercom."""
        return (
            self.coordinator.last_update_success
            and isinstance(self.coordinator.data, dict)
            and self.skud_id in self.coordinator.data
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to coarse motion events only."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_MOTION_ANALYTICS,
                self._async_handle_motion,
            )
        )

    @callback
    def _async_handle_motion(self, event: Event) -> None:
        if event.data.get("skud_id") != self.skud_id:
            return
        attributes = (
            {"occurred_at": event.data["occurred_at"]}
            if "occurred_at" in event.data
            else {}
        )
        self._trigger_event("motion", attributes)
        self.async_write_ha_state()
