"""Button platform for Ufanet Intercom."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UfanetApi, UfanetApiError
from .archive import UfanetArchiveController
from .const import DOMAIN
from .coordinator import UfanetCoordinator
from .entity import device_info
from .key_enrollment import (
    KEY_ENROLLMENT_WINDOW_SECONDS,
    async_start_physical_key_enrollment,
)
from .key_management import async_setup_key_services


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up intercom buttons."""
    async_setup_key_services(hass)

    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: UfanetCoordinator = runtime["coordinator"]
    api: UfanetApi = runtime["api"]

    entities: list[ButtonEntity] = []
    for skud in coordinator.data.values():
        if skud.get("disable_button") or skud.get("open_type") != "http":
            continue
        relays = skud.get("relays") or []
        if relays:
            for relay in relays:
                if not isinstance(relay, dict) or "number" not in relay:
                    continue
                entities.append(
                    UfanetOpenDoorButton(
                        coordinator,
                        api,
                        skud,
                        int(relay["number"]),
                        relay.get("name"),
                    )
                )
        else:
            # The Android app/API uses door=1 for the primary relay even when
            # the relays array is empty (validated with a real intercom).
            entities.append(UfanetOpenDoorButton(coordinator, api, skud, 1, None))

    # The key-passage coordinator contains only intercom IDs for which Ufanet
    # advertised physical-key recording support during its successful refresh.
    # Do not expose enrollment on unknown/unsupported intercoms.
    key_passage_coordinator = runtime.get("key_passage_coordinator")
    key_data = getattr(key_passage_coordinator, "data", None)
    if isinstance(key_data, dict):
        for skud_id in sorted(key_data):
            skud = coordinator.data.get(int(skud_id))
            if skud is not None:
                entities.append(UfanetPhysicalKeyEnrollmentButton(coordinator, api, skud))

    controllers: dict[int, UfanetArchiveController] = runtime["archive_controllers"]
    for skud_id, controller in controllers.items():
        skud = coordinator.data.get(skud_id)
        if skud is None:
            continue
        entities.extend(
            (
                UfanetArchiveNavigationButton(controller, skud, "previous"),
                UfanetArchiveNavigationButton(controller, skud, "next"),
                UfanetArchiveNavigationButton(controller, skud, "latest"),
            )
        )

    async_add_entities(entities)


class UfanetOpenDoorButton(ButtonEntity):
    """Momentary button that opens an intercom/SKUD relay."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:door-open"

    def __init__(
        self,
        coordinator: UfanetCoordinator,
        api: UfanetApi,
        skud: dict[str, Any],
        door: int,
        relay_name: str | None,
    ) -> None:
        self.coordinator = coordinator
        self.api = api
        self.skud_id = int(skud["id"])
        self.door = door
        self._attr_unique_id = f"{self.skud_id}_open_door_{door}"
        self._attr_device_info = device_info(skud)
        if relay_name:
            self._attr_name = relay_name
        else:
            self._attr_translation_key = "open_door"

    @property
    def available(self) -> bool:
        """Return availability based on coordinator state and current device flags."""
        if not self.coordinator.last_update_success:
            return False
        skud = self.coordinator.data.get(self.skud_id)
        return bool(skud and not skud.get("disable_button") and not skud.get("is_blocked"))

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    async def async_press(self) -> None:
        """Open the configured door/relay."""
        try:
            await self.api.async_open_door(self.skud_id, self.door)
        except UfanetApiError as err:
            raise HomeAssistantError(f"Ufanet failed to open the door: {err}") from err


class UfanetPhysicalKeyEnrollmentButton(ButtonEntity):
    """Arm an intercom for physical-key auto-collection."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:key-plus"
    _attr_translation_key = "add_physical_key"

    def __init__(
        self,
        coordinator: UfanetCoordinator,
        api: UfanetApi,
        skud: dict[str, Any],
    ) -> None:
        self.coordinator = coordinator
        self.api = api
        self.skud_id = int(skud["id"])
        self._attr_unique_id = f"{self.skud_id}_add_physical_key"
        self._attr_device_info = device_info(skud)

    @property
    def available(self) -> bool:
        """Return whether the target intercom is currently usable."""
        if not self.coordinator.last_update_success:
            return False
        skud = self.coordinator.data.get(self.skud_id)
        return bool(skud and not skud.get("is_blocked"))

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Expose the enrollment window documented by the Android application."""
        return {"enrollment_window_seconds": KEY_ENROLLMENT_WINDOW_SECONDS}

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    async def async_press(self) -> None:
        """Start the server-side physical-key enrollment window."""
        try:
            await async_start_physical_key_enrollment(self.api, self.skud_id)
        except UfanetApiError as err:
            raise HomeAssistantError(
                f"Ufanet failed to start physical key enrollment: {err}"
            ) from err


class UfanetArchiveNavigationButton(ButtonEntity):
    """Move the virtual archive camera backward/forward/latest."""

    _attr_has_entity_name = True

    def __init__(
        self,
        controller: UfanetArchiveController,
        skud: dict[str, Any],
        action: str,
    ) -> None:
        self.controller = controller
        self.action = action
        self._attr_unique_id = f"{controller.skud_id}_archive_{action}"
        self._attr_device_info = device_info(skud)

        if action == "previous":
            self._attr_translation_key = "archive_previous"
            self._attr_icon = "mdi:rewind"
        elif action == "next":
            self._attr_translation_key = "archive_next"
            self._attr_icon = "mdi:fast-forward"
        else:
            self._attr_translation_key = "archive_latest"
            self._attr_icon = "mdi:clock-end"

    async def async_press(self) -> None:
        if self.action == "previous":
            await self.controller.async_shift(-1)
        elif self.action == "next":
            await self.controller.async_shift(1)
        else:
            await self.controller.async_go_latest()
