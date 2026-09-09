"""Authorized-device and advanced FCM registration service actions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import UfanetApi, UfanetApiError, UfanetResponseError
from .const import (
    CONF_USERNAME,
    DOMAIN,
    SERVICE_LIST_AUTHORIZED_DEVICES,
    SERVICE_LIST_FCM_REGISTRATIONS,
    SERVICE_REVOKE_AUTHORIZED_DEVICE,
    SERVICE_REVOKE_OTHER_AUTHORIZED_DEVICES,
    SERVICE_UNREGISTER_FCM_REGISTRATION,
    SERVICE_UNREGISTER_OTHER_FCM_REGISTRATIONS,
)
from .fcm_sessions import (
    FcmSessionProtectionError,
    async_owned_fcm_device_ids_for_account,
    build_authorized_session_inventory,
    resolve_authorized_session,
)

_LOGGER = logging.getLogger(__name__)
_AUTHORIZED_DEVICES_CARD_PATH = (
    Path(__file__).parent / "frontend" / "ufanet-authorized-devices-card.js"
)
_AUTHORIZED_DEVICES_CARD_URL = "/ufanet_intercom/ufanet-authorized-devices-card.js"
_AUTHORIZED_DEVICES_CARD_MODULE_URL = f"{_AUTHORIZED_DEVICES_CARD_URL}?v=0.31.0"
_FRONTEND_SETUP_GUARD = f"_{DOMAIN}_authorized_devices_frontend_setup"

_REF = vol.All(cv.string, vol.Match(r"^[0-9a-f]{24}$"))
LIST_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})
REVOKE_AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("authorization_ref"): _REF,
        vol.Required("confirm"): vol.In([True]),
    }
)
REVOKE_OTHER_AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("expected_count"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Required("confirm"): vol.In([True]),
    }
)
UNREGISTER_FCM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("fcm_ref"): _REF,
        vol.Required("confirm"): vol.In([True]),
    }
)
UNREGISTER_OTHER_FCM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("expected_count"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Required("confirm"): vol.In([True]),
    }
)


async def _async_setup_authorized_devices_frontend(hass: HomeAssistant) -> None:
    """Expose and inject the optional device-management extension after its path exists."""
    try:
        exists = await hass.async_add_executor_job(
            _AUTHORIZED_DEVICES_CARD_PATH.is_file
        )
        if not exists:
            _LOGGER.warning(
                "Ufanet authorized-device frontend extension was not found at %s",
                _AUTHORIZED_DEVICES_CARD_PATH,
            )
            return
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    _AUTHORIZED_DEVICES_CARD_URL,
                    str(_AUTHORIZED_DEVICES_CARD_PATH),
                    False,
                )
            ]
        )
        # This extension waits for the main custom element with whenDefined(), so
        # extra-JS injection is safe even if the base Lovelace module loads first.
        frontend.add_extra_js_url(hass, _AUTHORIZED_DEVICES_CARD_MODULE_URL)
        _LOGGER.info(
            "Ufanet authorized-device frontend extension URL: %s",
            _AUTHORIZED_DEVICES_CARD_MODULE_URL,
        )
    except Exception as err:  # noqa: BLE001 - UI extension must not break core setup
        _LOGGER.warning(
            "Could not register Ufanet authorized-device frontend extension: %s",
            type(err).__name__,
        )


def _schedule_authorized_devices_frontend(hass: HomeAssistant) -> None:
    """Schedule the extension exactly once without changing service setup semantics."""
    if hass.data.get(_FRONTEND_SETUP_GUARD):
        return
    if getattr(hass, "http", None) is None:
        return
    if not callable(getattr(hass, "async_create_task", None)):
        return
    hass.data[_FRONTEND_SETUP_GUARD] = True
    hass.async_create_task(
        _async_setup_authorized_devices_frontend(hass),
        "Ufanet authorized-device frontend setup",
    )


def _runtime_for_device(hass: HomeAssistant, device_id: str) -> dict[str, Any]:
    """Resolve one integration runtime from a Home Assistant device ID."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError("Selected Home Assistant device was not found")

    runtimes = hass.data.get(DOMAIN, {})
    if not isinstance(runtimes, dict):
        raise ServiceValidationError("Ufanet integration runtime is unavailable")

    matches = [
        runtimes[entry_id]
        for entry_id in device.config_entries
        if entry_id in runtimes and isinstance(runtimes[entry_id], dict)
    ]
    if len(matches) != 1:
        raise ServiceValidationError(
            "Selected device does not resolve to exactly one Ufanet config entry"
        )
    return matches[0]


async def _authorized_inventory(
    hass: HomeAssistant,
    call: ServiceCall,
) -> tuple[UfanetApi, Any, list[dict[str, Any]]]:
    """Fetch fresh provider device inventory with HA-owned rows protected."""
    runtime = _runtime_for_device(hass, str(call.data[ATTR_DEVICE_ID]))
    api: UfanetApi = runtime["api"]
    entry = runtime.get("entry")
    if entry is None:
        raise ServiceValidationError("Ufanet config entry is unavailable")

    username = entry.data.get(CONF_USERNAME)
    if not isinstance(username, str) or not username.strip():
        raise ServiceValidationError("Ufanet account identity is unavailable")

    try:
        protected_ids = await async_owned_fcm_device_ids_for_account(hass, username)
        # Historical API method name retained for compatibility. Live tests proved
        # this endpoint is the official device/registration inventory. It can be
        # read by a plain JWT controller, but rows are coupled to FCM registration
        # state and must not be treated as an exhaustive independent JWT inventory.
        devices = await api.async_get_authorized_fcm_devices()
        inventory = build_authorized_session_inventory(
            entry.entry_id,
            devices,
            protected_ids,
        )
    except FcmSessionProtectionError as err:
        raise HomeAssistantError(
            "Unable to verify Home Assistant-owned device registrations; no destructive action was attempted"
        ) from err
    except (UfanetResponseError, ValueError) as err:
        raise ServiceValidationError(str(err)) from err
    return api, entry, inventory


def _authorization_public(row: dict[str, Any]) -> dict[str, Any]:
    public = dict(row["public"])
    public["authorization_ref"] = public.pop("session_ref")
    return public


def _fcm_public(row: dict[str, Any]) -> dict[str, Any]:
    public = dict(row["public"])
    public["fcm_ref"] = public.pop("session_ref")
    return public


def _counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    protected = sum(1 for row in rows if row["public"]["protected"])
    return protected, len(rows) - protected


def async_setup_authorized_device_services(hass: HomeAssistant) -> None:
    """Register canonical authorization actions and advanced FCM actions once."""
    _schedule_authorized_devices_frontend(hass)

    async def async_list_authorized_devices(call: ServiceCall) -> ServiceResponse:
        _api, _entry, inventory = await _authorized_inventory(hass, call)
        protected_count, revocable_count = _counts(inventory)
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "count": len(inventory),
            "protected_count": protected_count,
            "revocable_count": revocable_count,
            "authorizations": [_authorization_public(row) for row in inventory],
        }

    async def async_revoke_authorized_device(call: ServiceCall) -> ServiceResponse:
        api, _entry, inventory = await _authorized_inventory(hass, call)
        requested_ref = str(call.data["authorization_ref"])
        try:
            target = resolve_authorized_session(inventory, requested_ref)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        if target is None:
            raise ServiceValidationError(
                "Authorized device is no longer present; refresh the device list"
            )
        if target["public"]["protected"]:
            raise ServiceValidationError(
                "Home Assistant-owned authorization is protected from this service"
            )

        target_device_id = target["device_id"]
        try:
            # logout_device is live-confirmed to revoke another Ufanet authorized
            # device when called from an ordinary JWT session without any FCM setup.
            await api.async_logout_fcm_device(device_id=target_device_id)
            after = await api.async_get_authorized_fcm_devices()
        except UfanetApiError as err:
            raise HomeAssistantError("Ufanet authorized-device revoke request failed") from err
        if any(item["device_id"] == target_device_id for item in after):
            raise HomeAssistantError(
                "Ufanet returned from logout_device, but the authorization is still present"
            )
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "authorization_ref": requested_ref,
            "revoked": True,
        }

    async def async_revoke_other_authorized_devices(
        call: ServiceCall,
    ) -> ServiceResponse:
        api, entry, inventory = await _authorized_inventory(hass, call)
        targets = [row for row in inventory if not row["public"]["protected"]]
        expected_count = int(call.data["expected_count"])
        if len(targets) != expected_count:
            raise ServiceValidationError(
                "Revocable authorized-device count changed; refresh the list and confirm again"
            )

        target_ids = {row["device_id"] for row in targets}
        revoked_count = 0
        try:
            for row in targets:
                await api.async_logout_fcm_device(device_id=row["device_id"])
                revoked_count += 1
            after = await api.async_get_authorized_fcm_devices()
        except UfanetApiError as err:
            raise HomeAssistantError(
                f"Ufanet authorization revoke failed after {revoked_count} successful revocations"
            ) from err

        remaining = sum(1 for item in after if item["device_id"] in target_ids)
        if remaining:
            raise HomeAssistantError(
                "Ufanet logout_device verification failed for one or more authorizations"
            )

        try:
            protected_after = await async_owned_fcm_device_ids_for_account(
                hass,
                str(entry.data[CONF_USERNAME]),
            )
            after_inventory = build_authorized_session_inventory(
                entry.entry_id,
                after,
                protected_after,
            )
        except (FcmSessionProtectionError, ValueError) as err:
            raise HomeAssistantError(
                "Authorizations were revoked, but refreshed ownership verification failed"
            ) from err

        protected_count, revocable_count = _counts(after_inventory)
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "revoked_count": revoked_count,
            "remaining_revocable_count": revocable_count,
            "protected_count": protected_count,
        }

    async def async_list_fcm_registrations(call: ServiceCall) -> ServiceResponse:
        _api, _entry, inventory = await _authorized_inventory(hass, call)
        protected_count, removable_count = _counts(inventory)
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "count": len(inventory),
            "protected_count": protected_count,
            "removable_count": removable_count,
            "inventory_source": "authorized_devices",
            "registrations": [_fcm_public(row) for row in inventory],
        }

    async def async_unregister_fcm_registration(call: ServiceCall) -> ServiceResponse:
        api, _entry, inventory = await _authorized_inventory(hass, call)
        requested_ref = str(call.data["fcm_ref"])
        try:
            target = resolve_authorized_session(inventory, requested_ref)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        if target is None:
            raise ServiceValidationError(
                "FCM registration is no longer present in the device inventory; refresh the list"
            )
        if target["public"]["protected"]:
            raise ServiceValidationError(
                "Home Assistant-owned FCM registration is protected; disable FCM mode or remove the config entry to clean it up safely"
            )

        target_device_id = target["device_id"]
        try:
            # This is deliberately NOT logout_device. Live testing on 2026-09-08
            # confirmed that DELETE /api/v0/fcm/ removes the selected row and
            # invalidates its refresh JWT chain while an issued access JWT can
            # remain usable until expiry.
            await api.async_unregister_fcm_device(device_id=target_device_id)
            after = await api.async_get_authorized_fcm_devices()
        except UfanetApiError as err:
            raise HomeAssistantError("Ufanet FCM unregistration request failed") from err
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "fcm_ref": requested_ref,
            "unregistered": True,
            "authorized_device_still_visible": any(
                item["device_id"] == target_device_id for item in after
            ),
        }

    async def async_unregister_other_fcm_registrations(
        call: ServiceCall,
    ) -> ServiceResponse:
        api, _entry, inventory = await _authorized_inventory(hass, call)
        targets = [row for row in inventory if not row["public"]["protected"]]
        expected_count = int(call.data["expected_count"])
        if len(targets) != expected_count:
            raise ServiceValidationError(
                "Removable FCM registration count changed; refresh the list and confirm again"
            )

        target_ids = {row["device_id"] for row in targets}
        removed_count = 0
        try:
            for row in targets:
                await api.async_unregister_fcm_device(device_id=row["device_id"])
                removed_count += 1
            after = await api.async_get_authorized_fcm_devices()
        except UfanetApiError as err:
            raise HomeAssistantError(
                f"Ufanet FCM unregistration failed after {removed_count} successful removals"
            ) from err

        still_visible_count = sum(
            1 for item in after if item["device_id"] in target_ids
        )
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "unregistered_count": removed_count,
            "authorized_device_still_visible_count": still_visible_count,
        }

    registrations = (
        (
            SERVICE_LIST_AUTHORIZED_DEVICES,
            async_list_authorized_devices,
            LIST_SCHEMA,
        ),
        (
            SERVICE_REVOKE_AUTHORIZED_DEVICE,
            async_revoke_authorized_device,
            REVOKE_AUTH_SCHEMA,
        ),
        (
            SERVICE_REVOKE_OTHER_AUTHORIZED_DEVICES,
            async_revoke_other_authorized_devices,
            REVOKE_OTHER_AUTH_SCHEMA,
        ),
        (
            SERVICE_LIST_FCM_REGISTRATIONS,
            async_list_fcm_registrations,
            LIST_SCHEMA,
        ),
        (
            SERVICE_UNREGISTER_FCM_REGISTRATION,
            async_unregister_fcm_registration,
            UNREGISTER_FCM_SCHEMA,
        ),
        (
            SERVICE_UNREGISTER_OTHER_FCM_REGISTRATIONS,
            async_unregister_other_fcm_registrations,
            UNREGISTER_OTHER_FCM_SCHEMA,
        ),
    )
    for service, handler, schema in registrations:
        if hass.services.has_service(DOMAIN, service):
            continue
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schema,
            supports_response=SupportsResponse.ONLY,
        )
