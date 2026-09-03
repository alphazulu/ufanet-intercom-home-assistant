"""Privacy-safe authorized FCM session inventory and ownership protection."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_USERNAME, DOMAIN
from .fcm import _fcm_store, _owned_device_id

SESSION_REF_LENGTH = 24
MAX_SESSION_TITLE_LENGTH = 128
MAX_OS_DISPLAY_LENGTH = 64


class FcmSessionProtectionError(RuntimeError):
    """Raised when Home Assistant-owned FCM registrations cannot be protected."""


def _normalized_username(value: Any) -> str:
    return str(value or "").strip().upper()


def authorized_session_ref(entry_id: str, device_id: str) -> str:
    """Return a stable opaque reference without exposing the provider device ID."""
    raw = f"{entry_id}\0{device_id}".encode("utf-8", errors="strict")
    return hashlib.sha256(raw).hexdigest()[:SESSION_REF_LENGTH]


def _safe_title(value: Any) -> str:
    if not isinstance(value, str):
        return "Unknown device"
    title = value.strip()
    if (
        not title
        or len(title) > MAX_SESSION_TITLE_LENGTH
        or any(ord(char) < 32 or ord(char) == 127 for char in title)
    ):
        return "Unknown device"
    return title


def _normalized_last_update(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid authorized-device timestamp")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("authorized-device timestamp has no timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _platform_category(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    display = value.strip()
    if (
        not display
        or len(display) > MAX_OS_DISPLAY_LENGTH
        or any(ord(char) < 32 or ord(char) == 127 for char in display)
    ):
        return "unknown"
    normalized = display.casefold()
    if "android" in normalized:
        return "android"
    if (
        normalized == "ios"
        or normalized.startswith("ios ")
        or "iphone" in normalized
        or "ipad" in normalized
    ):
        return "ios"
    if "harmony" in normalized:
        return "harmonyos"
    return "other"


def build_authorized_session_inventory(
    entry_id: str,
    devices: list[dict[str, Any]],
    protected_device_ids: set[str],
) -> list[dict[str, Any]]:
    """Build private inventory rows containing a public-safe view plus raw ID."""
    inventory: list[dict[str, Any]] = []
    seen_device_ids: set[str] = set()
    seen_refs: set[str] = set()

    for item in devices:
        if not isinstance(item, dict):
            raise ValueError("authorized-device list contains invalid item")
        device_id = item.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            raise ValueError("authorized-device list contains invalid device ID")
        if device_id in seen_device_ids:
            raise ValueError("authorized-device list contains duplicate device ID")
        seen_device_ids.add(device_id)

        call_access = item.get("is_call_access")
        if not isinstance(call_access, bool):
            raise ValueError("authorized-device list contains invalid call-access field")

        ref = authorized_session_ref(entry_id, device_id)
        if ref in seen_refs:
            raise ValueError("authorized-device session reference collision")
        seen_refs.add(ref)

        public = {
            "session_ref": ref,
            "title": _safe_title(item.get("title")),
            "last_update": _normalized_last_update(item.get("last_update")),
            "is_call_access": call_access,
            "platform": _platform_category(item.get("os_display")),
            "protected": device_id in protected_device_ids,
            "protected_reason": (
                "home_assistant" if device_id in protected_device_ids else None
            ),
        }
        inventory.append({"device_id": device_id, "public": public})

    inventory.sort(key=lambda row: row["public"]["last_update"], reverse=True)
    return inventory


def public_authorized_sessions(
    inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop all provider IDs from an inventory before returning it to Home Assistant."""
    return [dict(row["public"]) for row in inventory]


def resolve_authorized_session(
    inventory: list[dict[str, Any]],
    session_ref: str,
) -> dict[str, Any] | None:
    matches = [row for row in inventory if row["public"]["session_ref"] == session_ref]
    if len(matches) > 1:
        raise ValueError("authorized-device session reference is ambiguous")
    return matches[0] if matches else None


async def async_owned_fcm_device_ids_for_account(
    hass: HomeAssistant,
    username: str,
) -> set[str]:
    """Return all locally provable HA-owned registrations for one Ufanet account."""
    target = _normalized_username(username)
    if not target:
        raise FcmSessionProtectionError("Ufanet account identity is unavailable")

    result: set[str] = set()
    runtimes = hass.data.get(DOMAIN, {})

    for entry in hass.config_entries.async_entries(DOMAIN):
        if _normalized_username(entry.data.get(CONF_USERNAME)) != target:
            continue

        runtime = runtimes.get(entry.entry_id) if isinstance(runtimes, dict) else None
        manager = runtime.get("fcm_manager") if isinstance(runtime, dict) else None
        if manager is not None:
            owned = getattr(manager, "owned_device_id", None)
            if isinstance(owned, str) and owned:
                result.add(owned)
                continue

        try:
            stored = await _fcm_store(hass, entry.entry_id).async_load()
        except Exception as err:
            raise FcmSessionProtectionError(
                "Unable to verify Home Assistant FCM ownership"
            ) from err
        owned = _owned_device_id(stored)
        if owned is not None:
            result.add(owned)

    return result
