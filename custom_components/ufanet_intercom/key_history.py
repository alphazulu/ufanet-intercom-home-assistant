"""Privacy-safe per-key passage history and validation frontend setup."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import UfanetApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_GET_PHYSICAL_KEY_PASSAGES = "get_physical_key_passages"
KEY_HISTORY_PAGE_SIZE = 25
MAX_KEY_HISTORY_PAGE = 1000
KEY_REF_PATTERN = r"^[0-9a-f]{24}$"

_FRONTEND_PATH = Path(__file__).parent / "frontend" / "ufanet-key-history-card.js"
_FRONTEND_URL = "/ufanet_intercom/ufanet-key-history-card.js"
_FRONTEND_MODULE_URL = f"{_FRONTEND_URL}?v=0.30.0"
_FRONTEND_SETUP_KEY = f"{DOMAIN}_key_history_frontend_setup"

GET_PHYSICAL_KEY_PASSAGES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("key_ref"): vol.All(cv.string, vol.Match(KEY_REF_PATTERN)),
        vol.Optional("page", default=0): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_KEY_HISTORY_PAGE),
        ),
    }
)


def _coerce_nonnegative_int(value: Any) -> int | None:
    """Return a non-negative integer without accepting booleans."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed >= 0 else None
    return None


def _coerce_positive_timestamp(value: Any) -> int | None:
    """Return a provider Unix timestamp in seconds when safely parseable."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        return None
    if parsed <= 0 or parsed > 253_402_300_799:
        return None
    return parsed


def _parse_filtered_passage_response(
    payload: Any,
    *,
    expected_key_id: int,
    requested_page: int,
    page_size: int = KEY_HISTORY_PAGE_SIZE,
) -> dict[str, Any]:
    """Normalize one key-filtered page without exposing provider identifiers.

    The official Android client models ``key``, ``key_name`` and ``time_passage``.
    HA deliberately ignores the provider key name in passage rows because the
    selected key was already resolved from a fresh inventory snapshot. The raw
    ``key`` field is used only to verify that the provider respected the filter.
    """
    if not isinstance(payload, dict):
        raise ValueError("unexpected response envelope")

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("response has no results list")

    passages: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            raise ValueError("response contains an invalid passage item")

        raw_key_id = _coerce_nonnegative_int(item.get("key"))
        if raw_key_id is None or raw_key_id != int(expected_key_id):
            raise ValueError("provider key filter was not respected")

        timestamp = _coerce_positive_timestamp(item.get("time_passage"))
        if timestamp is None:
            raise ValueError("passage contains an invalid timestamp")

        passages.append(
            {
                "occurred_at": datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                ).isoformat()
            }
        )

    current_page = _coerce_nonnegative_int(payload.get("current_page"))
    if current_page is None:
        current_page = int(requested_page)

    returned_page_size = _coerce_nonnegative_int(payload.get("page_size"))
    if returned_page_size is None or returned_page_size < 1:
        returned_page_size = int(page_size)

    total = _coerce_nonnegative_int(payload.get("count"))
    page_count = _coerce_nonnegative_int(payload.get("page_count"))
    has_more = (
        current_page < page_count
        if page_count is not None
        else len(passages) >= int(page_size)
    )

    return {
        "page": current_page,
        "page_size": returned_page_size,
        "total": total,
        "has_more": bool(has_more),
        "passages": passages,
    }


async def _async_fetch_filtered_passages(
    api: Any,
    *,
    skud_id: int,
    key_id: int,
    page: int,
) -> dict[str, Any]:
    """Fetch one Android-observed key-filtered passage page."""
    payload = await api._async_ufanet_json(  # noqa: SLF001 - package-internal transport
        "POST",
        f"/api/v4/key/skud/{int(skud_id)}/key/pass_history/",
        json_body={
            "page": int(page),
            "page_size": KEY_HISTORY_PAGE_SIZE,
            "filters": {"key": str(int(key_id))},
        },
    )
    return _parse_filtered_passage_response(
        payload,
        expected_key_id=int(key_id),
        requested_page=int(page),
    )


async def _async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve and register the validation-only history frontend extension."""
    try:
        exists = await hass.async_add_executor_job(_FRONTEND_PATH.is_file)
        if not exists:
            _LOGGER.warning("Ufanet key-history frontend was not found at %s", _FRONTEND_PATH)
            return

        await hass.http.async_register_static_paths(
            [StaticPathConfig(_FRONTEND_URL, str(_FRONTEND_PATH), False)]
        )

        # Reuse the same race-safe Lovelace resource registration helper as the
        # main card. Import locally to avoid an import cycle during module load.
        from . import _async_ensure_lovelace_module  # noqa: PLC0415

        registered = await _async_ensure_lovelace_module(
            hass,
            _FRONTEND_MODULE_URL,
        )
        if not registered:
            frontend.add_extra_js_url(hass, _FRONTEND_MODULE_URL)
    except Exception as err:  # noqa: BLE001 - frontend must not break integration setup
        _LOGGER.warning(
            "Could not set up Ufanet key-history frontend: %s",
            type(err).__name__,
        )


def async_setup_key_history(hass: HomeAssistant) -> None:
    """Register per-key read-only history service and its Lovelace extension."""
    # Import locally because key_management calls this function after its own
    # helpers are defined. This preserves a single key_ref implementation.
    from .key_management import (  # noqa: PLC0415
        _async_fresh_key_inventory,
        resolve_physical_key,
    )

    async def async_get_physical_key_passages(
        call: ServiceCall,
    ) -> ServiceResponse:
        requested_ref = str(call.data["key_ref"])
        requested_page = int(call.data["page"])

        _runtime, entry, skud_id, api, _coordinator, inventory = (
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

        try:
            normalized = await _async_fetch_filtered_passages(
                api,
                skud_id=skud_id,
                key_id=int(target["key_id"]),
                page=requested_page,
            )
        except UfanetApiError as err:
            raise HomeAssistantError("Ufanet physical-key passage request failed") from err
        except (TypeError, ValueError, OverflowError, OSError) as err:
            raise HomeAssistantError(
                "Ufanet physical-key passage response has an unexpected schema"
            ) from err

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "key_ref": requested_ref,
            "name": target["name"],
            **normalized,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_GET_PHYSICAL_KEY_PASSAGES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PHYSICAL_KEY_PASSAGES,
            async_get_physical_key_passages,
            schema=GET_PHYSICAL_KEY_PASSAGES_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.data.get(_FRONTEND_SETUP_KEY):
        hass.data[_FRONTEND_SETUP_KEY] = True
        hass.async_create_task(_async_setup_frontend(hass))
