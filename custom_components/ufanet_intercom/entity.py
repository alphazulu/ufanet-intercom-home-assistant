"""Shared entity helpers for Ufanet Intercom."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def device_name(skud: dict[str, Any]) -> str:
    """Return the best human-readable device name from the API object."""
    return (
        skud.get("custom_name")
        or skud.get("string_view")
        or f"Ufanet intercom {skud.get('id', 'unknown')}"
    )


def device_info(skud: dict[str, Any]) -> DeviceInfo:
    """Build Home Assistant device information."""
    role = skud.get("role") or {}
    role_name = role.get("name") or "Intercom"
    model_number = skud.get("model")
    model = f"{role_name} (model {model_number})" if model_number is not None else role_name
    return DeviceInfo(
        identifiers={(DOMAIN, str(skud["id"]))},
        name=device_name(skud),
        manufacturer="Ufanet SmartHome",
        model=model,
    )
