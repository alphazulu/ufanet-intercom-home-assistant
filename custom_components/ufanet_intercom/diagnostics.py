"""Diagnostics support for Ufanet Intercom."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .api import UfanetApi
from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .options import effective_options

_ENTRY_REDACT = {CONF_USERNAME, CONF_PASSWORD}


def _hash_identifier(value: Any) -> str | None:
    """Return a stable non-reversible short reference for diagnostics."""
    if value in (None, ""):
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _coordinator_state(coordinator: Any) -> dict[str, Any]:
    """Return coordinator health without embedding API responses/errors."""
    if coordinator is None:
        return {"present": False}

    interval = getattr(coordinator, "update_interval", None)
    seconds = interval.total_seconds() if interval is not None else None
    last_exception = getattr(coordinator, "last_exception", None)

    return {
        "present": True,
        "last_update_success": bool(
            getattr(coordinator, "last_update_success", False)
        ),
        "last_exception_type": (
            type(last_exception).__name__ if last_exception is not None else None
        ),
        "update_interval_seconds": seconds,
    }


def _safe_skud(skud: dict[str, Any]) -> dict[str, Any]:
    """Summarize an intercom without address/account/camera identifiers."""
    return {
        "skud_id": skud.get("id"),
        "role": skud.get("role"),
        "model": skud.get("model"),
        "scope": skud.get("scope"),
        "private_status": skud.get("private_status"),
        "open_type": skud.get("open_type"),
        "open_in_talk": skud.get("open_in_talk"),
        "is_blocked": skud.get("is_blocked"),
        "is_shared_assignment": skud.get("_is_shared"),
        "relay_count": len(skud.get("relays") or []),
        "has_camera": bool(skud.get("cctv_number")),
        "camera_reference": _hash_identifier(skud.get("cctv_number")),
    }


def _safe_camera(camera: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(camera, dict):
        return None
    server = camera.get("server")
    tariff = camera.get("tariff")
    return {
        "timezone_present": bool(camera.get("timezone")),
        "is_llhls_enabled": camera.get("is_llhls_enabled"),
        "streams_count": camera.get("streams_count"),
        "server": {
            "vendor_name": server.get("vendor_name"),
            "domain": server.get("domain"),
            "screenshot_domain": server.get("screenshot_domain"),
        } if isinstance(server, dict) else None,
        "tariff": {
            "name": tariff.get("name"),
            "dvr_hours": tariff.get("dvr_hours"),
        } if isinstance(tariff, dict) else None,
        "live_token_present": bool(camera.get("token_l")),
        "archive_token_present": bool(camera.get("token_r")),
    }


def _export_stats(hass: HomeAssistant, camera_number: str | None) -> dict[str, Any]:
    """Return counts/bytes only; never expose filenames or local paths."""
    if not camera_number or not hass.config.media_dirs:
        return {"count": 0, "total_bytes": 0}

    media_root = Path(
        hass.config.media_dirs.get("local")
        or next(iter(hass.config.media_dirs.values()))
    )
    export_dir = media_root / "ufanet_intercom"
    if not export_dir.exists():
        return {"count": 0, "total_bytes": 0}

    safe_camera = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in str(camera_number)
    )
    prefix = f"ufanet_{safe_camera}_"

    count = 0
    total = 0
    try:
        for path in export_dir.iterdir():
            if (
                path.is_file()
                and path.name.startswith(prefix)
                and path.name.endswith(".mp4")
                and not path.name.startswith(".")
            ):
                count += 1
                total += path.stat().st_size
    except OSError:
        return {"count": None, "total_bytes": None, "read_error": True}

    return {"count": count, "total_bytes": total}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return privacy-preserving diagnostics for one config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not isinstance(runtime, dict):
        runtime = {}

    api: UfanetApi | None = runtime.get("api")
    coordinator = runtime.get("coordinator")
    call_coordinator = runtime.get("call_coordinator")
    controllers = runtime.get("archive_controllers") or {}
    auto_save_manager = runtime.get("auto_save_manager")

    skuds = []
    if coordinator is not None and isinstance(coordinator.data, dict):
        skuds = [_safe_skud(item) for item in coordinator.data.values()]

    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), _ENTRY_REDACT),
            "options": effective_options(entry),
        },
        "api_auth": api.diagnostic_auth_state() if api is not None else None,
        "coordinator": {
            **_coordinator_state(coordinator),
            "intercom_count": len(skuds),
        },
        "call_coordinator": {
            **_coordinator_state(call_coordinator),
            "camera_with_latest_call_count": (
                len(call_coordinator.data)
                if call_coordinator is not None
                and isinstance(call_coordinator.data, dict)
                else 0
            ),
            "new_call_batch_count": len(
                getattr(call_coordinator, "new_calls", []) or []
            ),
        },
        "archive_controller_count": len(controllers),
        "auto_save": (
            auto_save_manager.status(include_details=False)
            if auto_save_manager is not None
            else None
        ),
        "intercoms": skuds,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: DeviceEntry,
) -> dict[str, Any]:
    """Return technical diagnostics for one Ufanet intercom device."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not isinstance(runtime, dict):
        return {"loaded": False}

    coordinator = runtime.get("coordinator")
    call_coordinator = runtime.get("call_coordinator")
    api: UfanetApi | None = runtime.get("api")
    controllers = runtime.get("archive_controllers") or {}
    auto_save_manager = runtime.get("auto_save_manager")

    skud = None
    if coordinator is not None and isinstance(coordinator.data, dict):
        for domain, identifier in device.identifiers:
            if domain != DOMAIN:
                continue
            try:
                skud = coordinator.data.get(int(identifier))
            except (TypeError, ValueError):
                continue
            if skud is not None:
                break

    if not isinstance(skud, dict):
        return {
            "loaded": True,
            "device_found_in_coordinator": False,
            "coordinator": _coordinator_state(coordinator),
        }

    camera_number = (
        str(skud["cctv_number"]) if skud.get("cctv_number") else None
    )
    camera = None
    camera_error_type = None
    if api is not None and camera_number:
        try:
            camera = await api.async_get_camera(camera_number)
        except Exception as err:  # diagnostics must not fail on cloud outage
            camera_error_type = type(err).__name__

    controller = controllers.get(int(skud["id"]))
    controller_state = None
    if controller is not None:
        controller_state = {
            "ready": bool(controller.ready),
            "timezone_present": bool(controller.timezone_name),
            "archive_name": controller.archive_name,
            "dvr_hours": controller.dvr_hours,
            "duration_seconds": controller.duration,
            "step_seconds": controller.step,
            "last_archive_loaded": bool(controller.last_archive),
        }

    latest_call_present = False
    if call_coordinator is not None and camera_number:
        latest_call_present = bool(
            isinstance(call_coordinator.data, dict)
            and call_coordinator.data.get(camera_number)
        )

    return {
        "loaded": True,
        "options": effective_options(entry),
        "intercom": _safe_skud(skud),
        "camera": _safe_camera(camera),
        "camera_fetch_error_type": camera_error_type,
        "api_auth": api.diagnostic_auth_state() if api is not None else None,
        "coordinator": _coordinator_state(coordinator),
        "call_coordinator": {
            **_coordinator_state(call_coordinator),
            "latest_call_present": latest_call_present,
        },
        "archive_controller": controller_state,
        "auto_save": (
            auto_save_manager.status(include_details=False)
            if auto_save_manager is not None
            else None
        ),
        "exports": await hass.async_add_executor_job(
            _export_stats,
            hass,
            camera_number,
        ),
    }
