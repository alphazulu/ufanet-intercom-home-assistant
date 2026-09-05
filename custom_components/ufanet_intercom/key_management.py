"""Privacy-safe physical-key listing and rename services."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import UfanetApi, UfanetApiError
from .const import DOMAIN, SERVICE_LIST_PHYSICAL_KEYS, SERVICE_RENAME_PHYSICAL_KEY
from .key_inventory import PhysicalKeyInventoryItem
from .services import _resolve_device_runtime

KEY_REF_LENGTH = 24
MAX_KEY_NAME_LENGTH = 128

LIST_PHYSICAL_KEYS_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)
RENAME_PHYSICAL_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("key_ref"): vol.All(
            cv.string,
            vol.Match(r"^[0-9a-f]{24}$"),
        ),
        vol.Required("new_name"): cv.string,
    }
)


def physical_key_ref(entry_id: str, skud_id: int, key_id: int) -> str:
    """Return a stable intercom-scoped opaque key reference."""
    raw = f"{entry_id}\0{int(skud_id)}\0{int(key_id)}".encode(
        "utf-8",
        errors="strict",
    )
    return hashlib.sha256(raw).hexdigest()[:KEY_REF_LENGTH]


def _normalize_new_name(value: Any) -> str:
    """Normalize a user-facing key name using a conservative local safety bound."""
    if not isinstance(value, str):
        raise ServiceValidationError("Physical-key name must be text")
    name = value.strip()
    if not name:
        raise ServiceValidationError("Physical-key name must not be blank")
    if len(name) > MAX_KEY_NAME_LENGTH:
        raise ServiceValidationError(
            f"Physical-key name must not exceed {MAX_KEY_NAME_LENGTH} characters"
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ServiceValidationError("Physical-key name contains control characters")
    return name


def _key_created_at_iso(value: int) -> str:
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()


def public_physical_keys(
    entry_id: str,
    skud_id: int,
    inventory: tuple[PhysicalKeyInventoryItem, ...] | list[PhysicalKeyInventoryItem],
) -> list[dict[str, Any]]:
    """Return one intercom's key inventory without provider key IDs."""
    rows: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for item in inventory:
        if int(skud_id) not in item["devices"]:
            continue
        ref = physical_key_ref(entry_id, skud_id, int(item["key_id"]))
        if ref in seen_refs:
            raise ValueError("physical-key reference collision")
        seen_refs.add(ref)
        rows.append(
            {
                "key_ref": ref,
                "name": item["name"],
                "created_at": _key_created_at_iso(int(item["created_at"])),
            }
        )
    rows.sort(key=lambda item: item["created_at"], reverse=True)
    return rows


def resolve_physical_key(
    entry_id: str,
    skud_id: int,
    inventory: tuple[PhysicalKeyInventoryItem, ...] | list[PhysicalKeyInventoryItem],
    key_ref: str,
) -> PhysicalKeyInventoryItem | None:
    """Resolve exactly one intercom-scoped opaque key reference."""
    matches = [
        item
        for item in inventory
        if int(skud_id) in item["devices"]
        and physical_key_ref(entry_id, skud_id, int(item["key_id"])) == key_ref
    ]
    if len(matches) > 1:
        raise ValueError("physical-key reference is ambiguous")
    return matches[0] if matches else None


async def async_rename_physical_key(
    api: UfanetApi,
    key_id: int,
    new_name: str,
) -> None:
    """Rename one key using the endpoint observed in the official Android client."""
    await api._async_ufanet_json(  # noqa: SLF001 - package-internal transport wrapper
        "POST",
        "/api/v4/key/edit/",
        json_body={"key_id": int(key_id), "name": new_name},
    )


async def _async_fresh_key_inventory(
    hass: HomeAssistant,
    device_id: str,
) -> tuple[
    dict[str, Any],
    Any,
    int,
    UfanetApi,
    Any,
    tuple[PhysicalKeyInventoryItem, ...],
]:
    """Resolve a key-capable intercom and refresh its account-level key inventory."""
    runtime, skud = _resolve_device_runtime(hass, device_id)
    entry = runtime.get("entry")
    if entry is None:
        raise ServiceValidationError("Ufanet config entry is unavailable")

    skud_id = int(skud["id"])
    coordinator = runtime.get("key_passage_coordinator")
    supported = getattr(coordinator, "data", None)
    if coordinator is None or not isinstance(supported, dict) or skud_id not in supported:
        raise ServiceValidationError(
            "Selected intercom does not advertise physical-key recording support"
        )

    try:
        await coordinator.async_request_refresh()
    except Exception as err:  # noqa: BLE001 - normalize coordinator failures for service UI
        raise HomeAssistantError(
            "Unable to refresh the physical-key inventory"
        ) from err
    if not bool(getattr(coordinator, "last_update_success", False)):
        raise HomeAssistantError("Unable to refresh the physical-key inventory")

    api: UfanetApi = runtime["api"]
    inventory = getattr(api, "physical_key_inventory", None)
    if not isinstance(inventory, (tuple, list)):
        raise HomeAssistantError("Physical-key inventory is unavailable")

    return runtime, entry, skud_id, api, coordinator, tuple(inventory)


def async_setup_key_services(hass: HomeAssistant) -> None:
    """Register physical-key services once after a key-capable platform loads."""

    async def async_list_physical_keys(call: ServiceCall) -> ServiceResponse:
        """Return a fresh, provider-ID-free key inventory for one intercom."""
        _runtime, entry, skud_id, _api, _coordinator, inventory = (
            await _async_fresh_key_inventory(hass, call.data[ATTR_DEVICE_ID])
        )
        try:
            keys = public_physical_keys(entry.entry_id, skud_id, inventory)
        except (KeyError, TypeError, ValueError) as err:
            raise HomeAssistantError("Physical-key inventory is invalid") from err
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "count": len(keys),
            "keys": keys,
        }

    async def async_rename_key(call: ServiceCall) -> ServiceResponse:
        """Rename one freshly resolved physical key and verify the refreshed name."""
        requested_ref = str(call.data["key_ref"])
        new_name = _normalize_new_name(call.data["new_name"])
        _runtime, entry, skud_id, api, coordinator, inventory = (
            await _async_fresh_key_inventory(hass, call.data[ATTR_DEVICE_ID])
        )
        try:
            target = resolve_physical_key(
                entry.entry_id,
                skud_id,
                inventory,
                requested_ref,
            )
        except (KeyError, TypeError, ValueError) as err:
            raise ServiceValidationError("Physical-key reference is invalid") from err
        if target is None:
            raise ServiceValidationError(
                "Physical key is no longer present for the selected intercom; refresh the key list"
            )

        previous_name = target["name"]
        if previous_name == new_name:
            return {
                "device_id": call.data[ATTR_DEVICE_ID],
                "key_ref": requested_ref,
                "name": new_name,
                "renamed": False,
                "verified": True,
                "unchanged": True,
            }

        try:
            await async_rename_physical_key(api, int(target["key_id"]), new_name)
        except UfanetApiError as err:
            raise HomeAssistantError("Ufanet physical-key rename request failed") from err

        try:
            await coordinator.async_request_refresh()
        except Exception as err:  # noqa: BLE001 - state may have changed remotely
            raise HomeAssistantError(
                "Physical key may have been renamed, but inventory refresh failed"
            ) from err
        if not bool(getattr(coordinator, "last_update_success", False)):
            raise HomeAssistantError(
                "Physical key may have been renamed, but inventory refresh failed"
            )

        refreshed_inventory = getattr(api, "physical_key_inventory", None)
        if not isinstance(refreshed_inventory, (tuple, list)):
            raise HomeAssistantError(
                "Physical key may have been renamed, but refreshed inventory is unavailable"
            )
        try:
            refreshed = resolve_physical_key(
                entry.entry_id,
                skud_id,
                refreshed_inventory,
                requested_ref,
            )
        except (KeyError, TypeError, ValueError) as err:
            raise HomeAssistantError(
                "Physical key may have been renamed, but refreshed inventory is invalid"
            ) from err
        if refreshed is None or refreshed["name"] != new_name:
            raise HomeAssistantError(
                "Ufanet returned from key rename, but the refreshed inventory did not confirm the new name"
            )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "key_ref": requested_ref,
            "name": new_name,
            "renamed": True,
            "verified": True,
            "unchanged": False,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_LIST_PHYSICAL_KEYS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LIST_PHYSICAL_KEYS,
            async_list_physical_keys,
            schema=LIST_PHYSICAL_KEYS_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RENAME_PHYSICAL_KEY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RENAME_PHYSICAL_KEY,
            async_rename_key,
            schema=RENAME_PHYSICAL_KEY_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
