"""Service actions for Ufanet Intercom."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import voluptuous as vol

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .api import UfanetApi, UfanetApiError, UfanetResponseError
from .guest_store import UfanetGuestInviteStore
from .const import (
    DEFAULT_ARCHIVE_DURATION_SECONDS,
    DEFAULT_ARCHIVE_STEP_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    CALL_SCAN_INTERVAL_SECONDS,
    MEDIA_REFRESH_SECONDS,
    CONF_ARCHIVE_DEFAULT_DURATION,
    CONF_ARCHIVE_DEFAULT_STEP,
    CONF_CALL_LEAD_SECONDS,
    CONF_CALL_AUTOSAVE_ENABLED,
    CONF_CALL_AUTOSAVE_AFTER_SECONDS,
    CONF_CALL_SCAN_INTERVAL,
    CONF_CALL_UPDATE_MODE,
    CONF_EXPORT_AUTO_CLEANUP,
    CONF_EXPORT_DEFAULT_DURATION,
    CONF_EXPORT_MAX_TOTAL_MB,
    CONF_EXPORT_RETENTION_DAYS,
    CONF_MEDIA_REFRESH_INTERVAL,
    CONF_SKUD_SCAN_INTERVAL,
    DOMAIN,
    MAX_ARCHIVE_DURATION_SECONDS,
    SERVICE_GET_SETTINGS,
    SERVICE_GET_RUNTIME_STATUS,
    SERVICE_GET_ARCHIVE_RANGES,
    SERVICE_GET_ARCHIVE_URL,
    SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
    SERVICE_LIST_ARCHIVE_EXPORTS,
    SERVICE_DELETE_ARCHIVE_EXPORT,
    SERVICE_CLEANUP_ARCHIVE_EXPORTS,
    SERVICE_GET_CALL_EVENTS,
    SERVICE_GET_LAST_CALL_PREVIEW_URL,
    SERVICE_GET_GUEST_ACCESS,
    SERVICE_CREATE_GUEST_INVITE,
    SERVICE_FORGET_GUEST_INVITE,
    SERVICE_REVOKE_SHARED_ACCESS,
    SERVICE_CREATE_TEMPORARY_GUEST_LINK,
    SERVICE_REVOKE_TEMPORARY_GUEST_LINK,
    DEFAULT_EXPORT_RETENTION_DAYS,
    DEFAULT_EXPORT_AUTO_CLEANUP,
    DEFAULT_EXPORT_DEFAULT_DURATION_SECONDS,
    DEFAULT_CALL_LEAD_SECONDS,
    DEFAULT_CALL_AUTOSAVE_ENABLED,
    DEFAULT_CALL_AUTOSAVE_AFTER_SECONDS,
    INTEGRATION_VERSION,
    DEFAULT_EXPORT_MAX_TOTAL_MB,
    MAX_EXPORT_RETENTION_DAYS,
    MAX_EXPORT_TOTAL_MB,
)

GET_SETTINGS_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)

GET_RUNTIME_STATUS_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)

GET_LAST_CALL_PREVIEW_URL_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)

GET_ARCHIVE_RANGES_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)

GET_ARCHIVE_URL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("start"): cv.datetime,
        vol.Optional("duration", default=DEFAULT_ARCHIVE_DURATION_SECONDS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_ARCHIVE_DURATION_SECONDS)
        ),
    }
)

GET_ARCHIVE_DOWNLOAD_URL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("start"): cv.datetime,
        vol.Optional("duration", default=DEFAULT_ARCHIVE_DURATION_SECONDS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_ARCHIVE_DURATION_SECONDS)
        ),
        vol.Optional(
            "retention_days",
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_RETENTION_DAYS),
        ),
        vol.Optional(
            "max_total_mb",
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_TOTAL_MB),
        ),
        vol.Optional("source", default="manual"): vol.In(["manual", "call"]),
        vol.Optional("event_id"): cv.string,
    }
)

LIST_ARCHIVE_EXPORTS_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)

DELETE_ARCHIVE_EXPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("filename"): cv.string,
    }
)

CLEANUP_ARCHIVE_EXPORTS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(
            "retention_days",
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_RETENTION_DAYS),
        ),
        vol.Optional(
            "max_total_mb",
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_TOTAL_MB),
        ),
    }
)

GET_CALL_EVENTS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("date"): cv.date,
    }
)

GET_GUEST_ACCESS_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)

CREATE_GUEST_INVITE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}
)

FORGET_GUEST_INVITE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("invite_id"): cv.string,
    }
)

REVOKE_SHARED_ACCESS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("access_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)


CREATE_TEMPORARY_GUEST_LINK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("duration_minutes"): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=10080),
        ),
    }
)

REVOKE_TEMPORARY_GUEST_LINK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("token"): cv.string,
    }
)


def async_setup_services(
    hass: HomeAssistant,
    guest_invite_store: UfanetGuestInviteStore,
) -> None:
    """Register Ufanet archive service actions."""

    async def async_get_settings(call: ServiceCall) -> ServiceResponse:
        """Return effective ConfigEntry options for the selected Ufanet device."""
        runtime, skud = _resolve_device_runtime(hass, call.data[ATTR_DEVICE_ID])
        options = runtime.get("options") or {}
        fcm_manager = runtime.get("fcm_manager")
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "skud_scan_interval_seconds": int(
                options.get(CONF_SKUD_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
            ),
            "call_scan_interval_seconds": int(
                options.get(CONF_CALL_SCAN_INTERVAL, CALL_SCAN_INTERVAL_SECONDS)
            ),
            "call_update_mode": options.get(CONF_CALL_UPDATE_MODE),
            "fcm_configured": bool(fcm_manager is not None),
            "call_media_refresh_seconds": int(
                options.get(CONF_MEDIA_REFRESH_INTERVAL, MEDIA_REFRESH_SECONDS)
            ),
            "call_lead_seconds": int(
                options.get(CONF_CALL_LEAD_SECONDS, DEFAULT_CALL_LEAD_SECONDS)
            ),
            "call_autosave_enabled": bool(
                options.get(
                    CONF_CALL_AUTOSAVE_ENABLED,
                    DEFAULT_CALL_AUTOSAVE_ENABLED,
                )
            ),
            "call_autosave_after_seconds": int(
                options.get(
                    CONF_CALL_AUTOSAVE_AFTER_SECONDS,
                    DEFAULT_CALL_AUTOSAVE_AFTER_SECONDS,
                )
            ),
            "archive_default_duration_seconds": int(
                options.get(CONF_ARCHIVE_DEFAULT_DURATION, DEFAULT_ARCHIVE_DURATION_SECONDS)
            ),
            "archive_default_step_seconds": int(
                options.get(CONF_ARCHIVE_DEFAULT_STEP, DEFAULT_ARCHIVE_STEP_SECONDS)
            ),
            "export_default_duration_seconds": int(
                options.get(CONF_EXPORT_DEFAULT_DURATION, DEFAULT_EXPORT_DEFAULT_DURATION_SECONDS)
            ),
            "export_retention_days": int(
                options.get(CONF_EXPORT_RETENTION_DAYS, DEFAULT_EXPORT_RETENTION_DAYS)
            ),
            "export_max_total_mb": int(
                options.get(CONF_EXPORT_MAX_TOTAL_MB, DEFAULT_EXPORT_MAX_TOTAL_MB)
            ),
            "export_auto_cleanup": bool(
                options.get(CONF_EXPORT_AUTO_CLEANUP, DEFAULT_EXPORT_AUTO_CLEANUP)
            ),
        }

    async def async_get_runtime_status(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Return token-free technical runtime state for the selected device."""
        runtime, skud = _resolve_device_runtime(hass, call.data[ATTR_DEVICE_ID])
        api: UfanetApi = runtime["api"]
        coordinator = runtime.get("coordinator")
        call_coordinator = runtime.get("call_coordinator")
        controllers = runtime.get("archive_controllers") or {}
        options = runtime.get("options") or {}
        auto_manager = runtime.get("auto_save_manager")
        fcm_manager = runtime.get("fcm_manager")
        image_status_manager = runtime.get("image_status_manager")

        camera_number = _camera_number(skud)
        camera: dict[str, Any] | None = None
        camera_error_type: str | None = None
        try:
            camera = await api.async_get_camera(camera_number)
        except Exception as err:  # diagnostic panel must survive cloud outages
            camera_error_type = type(err).__name__

        controller = controllers.get(int(skud["id"]))
        controller_state = None
        if controller is not None:
            controller_state = {
                "ready": bool(controller.ready),
                "timezone": controller.timezone_name,
                "archive_name": controller.archive_name,
                "dvr_hours": controller.dvr_hours,
                "duration_seconds": controller.duration,
                "step_seconds": controller.step,
                "last_archive_loaded": bool(controller.last_archive),
            }

        camera_state = None
        if isinstance(camera, dict):
            server = camera.get("server")
            tariff = camera.get("tariff")
            camera_state = {
                "number": camera_number,
                "timezone": camera.get("timezone"),
                "is_llhls_enabled": camera.get("is_llhls_enabled"),
                "streams_count": camera.get("streams_count"),
                "server_vendor": (
                    server.get("vendor_name")
                    if isinstance(server, dict)
                    else None
                ),
                "server_domain": (
                    server.get("domain")
                    if isinstance(server, dict)
                    else None
                ),
                "tariff_name": (
                    tariff.get("name")
                    if isinstance(tariff, dict)
                    else None
                ),
                "dvr_hours": (
                    tariff.get("dvr_hours")
                    if isinstance(tariff, dict)
                    else None
                ),
            }

        media_key, export_dir = _archive_export_location(hass)
        items = await hass.async_add_executor_job(
            _list_export_files_sync,
            export_dir,
            _camera_export_prefix(camera_number),
            media_key,
        )

        def coordinator_state(value: Any) -> dict[str, Any]:
            if value is None:
                return {"present": False}
            interval = getattr(value, "update_interval", None)
            last_exception = getattr(value, "last_exception", None)
            return {
                "present": True,
                "last_update_success": bool(
                    getattr(value, "last_update_success", False)
                ),
                "update_interval_seconds": (
                    interval.total_seconds() if interval is not None else None
                ),
                "last_exception_type": (
                    type(last_exception).__name__
                    if last_exception is not None
                    else None
                ),
            }

        return {
            "version": INTEGRATION_VERSION,
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud": {
                "id": int(skud["id"]),
                "role": skud.get("role"),
                "model": skud.get("model"),
                "scope": skud.get("scope"),
                "open_type": skud.get("open_type"),
                "open_in_talk": skud.get("open_in_talk"),
                "private_status": skud.get("private_status"),
            },
            "camera": camera_state,
            "camera_error_type": camera_error_type,
            "auth": api.diagnostic_auth_state(),
            "coordinator": coordinator_state(coordinator),
            "call_coordinator": {
                **coordinator_state(call_coordinator),
                "latest_call_present": bool(
                    isinstance(getattr(call_coordinator, "data", None), dict)
                    and call_coordinator.data.get(camera_number)
                ),
            },
            "call_update_mode": runtime.get("call_update_mode"),
            "last_call_image": (
                image_status_manager.status(int(skud["id"]))
                if image_status_manager is not None
                else {
                    "configured": False,
                    "ffmpeg_available": None,
                    "ready": False,
                    "loading": False,
                    "preview_available": False,
                    "success_count": 0,
                    "failure_count": 0,
                    "consecutive_failures": 0,
                    "last_success_at": None,
                    "last_error_at": None,
                    "last_error_code": None,
                    "last_error_type": None,
                    "repair_issue_active": False,
                }
            ),
            "fcm": (
                fcm_manager.status()
                if fcm_manager is not None
                else {
                    "configured": False,
                    "active": False,
                    "firebase_registration_succeeded": False,
                    "ufanet_registration_succeeded": False,
                    "listener_started": False,
                    "listener_running": False,
                    "fallback_polling_active": True,
                    "watchdog_running": False,
                    "transport_state": None,
                    "reconnect_count": 0,
                    "consecutive_failures": 0,
                    "last_connected_at": None,
                    "last_disconnected_at": None,
                    "last_error_type": runtime.get("fcm_config_error_type"),
                    "received_push_count": 0,
                    "received_sip_push_count": 0,
                    "last_push_at": None,
                    "last_sip_push_at": None,
                }
            ),
            "archive": controller_state,
            "auto_save": (
                auto_manager.status(include_details=True)
                if auto_manager is not None
                else {
                    "enabled": bool(
                        options.get(
                            CONF_CALL_AUTOSAVE_ENABLED,
                            DEFAULT_CALL_AUTOSAVE_ENABLED,
                        )
                    ),
                    "lead_seconds": int(
                        options.get(
                            CONF_CALL_LEAD_SECONDS,
                            DEFAULT_CALL_LEAD_SECONDS,
                        )
                    ),
                    "after_seconds": int(
                        options.get(
                            CONF_CALL_AUTOSAVE_AFTER_SECONDS,
                            DEFAULT_CALL_AUTOSAVE_AFTER_SECONDS,
                        )
                    ),
                    "pending_count": 0,
                }
            ),
            "exports": {
                "count": len(items),
                "total_bytes": sum(int(item["size_bytes"]) for item in items),
                "auto_saved_count": sum(
                    1 for item in items if item.get("source") == "call"
                ),
                "manual_count": sum(
                    1 for item in items if item.get("source") != "call"
                ),
            },
        }

    async def async_get_ranges(call: ServiceCall) -> ServiceResponse:
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        camera_number = _camera_number(skud)
        try:
            camera = await api.async_get_camera(camera_number)
            ranges = await api.async_get_archive_ranges(camera_number)
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        return _ranges_response(call.data[ATTR_DEVICE_ID], skud, camera, ranges)

    async def async_get_call_events(call: ServiceCall) -> ServiceResponse:
        """Return call events for one intercom and one camera-local calendar day."""
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        camera_number = _camera_number(skud)
        requested_date: date = call.data["date"]

        try:
            camera = await api.async_get_camera(camera_number)
            timezone_name = str(camera.get("timezone") or hass.config.time_zone or "UTC")
            try:
                zone = ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                zone = dt_util.get_default_time_zone()

            day_start = datetime.combine(requested_date, time.min, tzinfo=zone)
            day_end = day_start + timedelta(days=1)
            day_start_utc = day_start.astimezone(timezone.utc)

            # The APK uses page_size=25. Keep the confirmed size and paginate
            # until we have passed the requested day or reached a hard safety cap.
            page_size = 25
            max_pages = 40
            seen: set[str] = set()
            matching: list[dict[str, Any]] = []

            for page in range(1, max_pages + 1):
                page_events = await api.async_get_call_history(
                    page=page, page_size=page_size
                )
                if not page_events:
                    break

                page_timestamps: list[datetime] = []
                for raw in page_events:
                    timestamp = _call_event_datetime(raw)
                    if timestamp is None:
                        continue
                    page_timestamps.append(timestamp)

                    if str(raw.get("camera_number") or "") != camera_number:
                        continue

                    local = timestamp.astimezone(zone)
                    if local.date() != requested_date:
                        continue

                    uuid = str(raw.get("uuid") or "")
                    dedupe_key = uuid or f"{raw.get('called_at')}:{camera_number}"
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)

                    second_of_day = (
                        local.hour * 3600 + local.minute * 60 + local.second
                    )
                    matching.append(
                        {
                            "uuid": uuid or None,
                            "called_at": raw.get("called_at"),
                            "timestamp": int(timestamp.timestamp()),
                            "local_datetime": local.isoformat(),
                            "local_date": local.date().isoformat(),
                            "local_time": local.strftime("%H:%M:%S"),
                            "second_of_day": second_of_day,
                            "camera_number": camera_number,
                            "address": raw.get("address"),
                            "porch": raw.get("porch"),
                            "flat": raw.get("flat"),
                            "event_timezone": raw.get("timezone"),
                        }
                    )

                # Once an entire page is older than the requested day, later
                # pages cannot contribute if the backend keeps its normal
                # newest-first ordering. This is only an optimization; the hard
                # page cap still protects against odd responses.
                if page_timestamps and max(page_timestamps) < day_start_utc:
                    break
                if len(page_events) < page_size:
                    break

        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        matching.sort(key=lambda item: int(item["timestamp"]))
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "camera_number": camera_number,
            "timezone": timezone_name,
            "date": requested_date.isoformat(),
            "count": len(matching),
            "events": matching,
        }

    async def async_get_last_call_preview_url(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Return a fresh preview URL only after an explicit authenticated call."""
        runtime, skud = _resolve_device_runtime(hass, call.data[ATTR_DEVICE_ID])
        api: UfanetApi = runtime["api"]
        call_coordinator = runtime.get("call_coordinator")
        camera_number = _camera_number(skud)
        latest = (
            call_coordinator.data.get(camera_number)
            if call_coordinator is not None
            and isinstance(getattr(call_coordinator, "data", None), dict)
            else None
        )
        uuid = str(latest.get("uuid") or "") if isinstance(latest, dict) else ""
        if not uuid:
            raise ServiceValidationError("No confirmed call is available")

        try:
            media = await api.async_get_call_media(uuid)
        except UfanetResponseError as err:
            raise ServiceValidationError(
                "Unable to obtain a valid preview for the latest call"
            ) from err
        except UfanetApiError as err:
            raise HomeAssistantError(
                "Unable to obtain the latest call preview"
            ) from err

        preview_url = media.get("preview")
        parsed = urlparse(preview_url) if isinstance(preview_url, str) else None
        try:
            valid_preview = bool(
                parsed is not None
                and parsed.scheme == "https"
                and parsed.hostname
                and parsed.username is None
                and parsed.password is None
            )
        except ValueError:
            valid_preview = False
        if not valid_preview:
            raise ServiceValidationError(
                "The latest call does not have a valid HTTPS preview"
            )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "called_at": latest.get("called_at"),
            "url": preview_url,
        }

    async def async_get_guest_access(call: ServiceCall) -> ServiceResponse:
        """Return temporary guest links and shared-access users."""
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        skud_id = int(skud["id"])
        try:
            all_temporary = await api.async_get_temporary_guest_links()
            shared_users = await api.async_get_shared_access_users(skud_id)
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        temporary_links: list[dict[str, Any]] = []
        for item in all_temporary:
            try:
                item_skud_id = int(item.get("skud_id"))
            except (TypeError, ValueError):
                continue
            if item_skud_id != skud_id:
                continue
            link = item.get("link")
            temporary_links.append(
                {
                    "skud_id": item_skud_id,
                    "time_end": item.get("time_end"),
                    "link": link,
                    "token": _temporary_link_token(link),
                    "preview_url": item.get("preview_url"),
                    "address": item.get("address"),
                    "name": item.get("name"),
                    "custom_name": item.get("custom_name"),
                }
            )

        normalized_users = [
            {
                "access_id": item.get("access_id", item.get("accessId")),
                "username": item.get("username"),
                "name": item.get("name"),
                "date_created": item.get("date_created", item.get("dateCreated")),
                "scope": item.get("scope"),
                "expires_at": item.get("expires_at", item.get("expiresAt")),
            }
            for item in shared_users
        ]

        generated_invites = guest_invite_store.list_for(
            device_id=call.data[ATTR_DEVICE_ID],
            skud_id=skud_id,
        )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": skud_id,
            "generated_count": len(generated_invites),
            "generated_invites": generated_invites,
            "temporary_count": len(temporary_links),
            "temporary_links": temporary_links,
            "shared_count": len(normalized_users),
            "shared_users": normalized_users,
        }

    async def async_create_temporary_guest_link(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Create a temporary web key with a duration measured in minutes."""
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        skud_id = int(skud["id"])
        duration_minutes = int(call.data["duration_minutes"])

        try:
            created = await api.async_create_temporary_guest_link(
                skud_id,
                duration_minutes,
            )
            current = await api.async_get_temporary_guest_links()
        except UfanetResponseError as err:
            raise ServiceValidationError(str(err)) from err
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        created_link = created.get("link")
        matched: dict[str, Any] | None = None
        for item in current:
            try:
                item_skud_id = int(item.get("skud_id"))
            except (TypeError, ValueError):
                continue
            if item_skud_id != skud_id:
                continue
            if item.get("link") == created_link:
                matched = item
                break

        if matched is None:
            # The POST itself is authoritative for the URL, but normally the
            # freshly created item is immediately visible in the GET list.
            matched = {
                "skud_id": skud_id,
                "link": created_link,
            }

        link = matched.get("link")
        token = _temporary_link_token(link)
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": skud_id,
            "duration_minutes": duration_minutes,
            "time_end": matched.get("time_end"),
            "link": link,
            "token": token,
            "preview_url": matched.get("preview_url"),
            "address": matched.get("address"),
            "name": matched.get("name"),
            "custom_name": matched.get("custom_name"),
        }

    async def async_revoke_temporary_guest_link(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Revoke one temporary web key after verifying it belongs to this SKUD."""
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        skud_id = int(skud["id"])
        requested_token = str(call.data["token"]).strip()
        if not requested_token:
            raise ServiceValidationError("Temporary guest token is empty")

        try:
            current = await api.async_get_temporary_guest_links()
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        matched: dict[str, Any] | None = None
        for item in current:
            try:
                item_skud_id = int(item.get("skud_id"))
            except (TypeError, ValueError):
                continue
            if item_skud_id != skud_id:
                continue
            if _temporary_link_token(item.get("link")) == requested_token:
                matched = item
                break

        if matched is None:
            raise ServiceValidationError(
                "Temporary guest link is not present for the selected intercom"
            )

        try:
            result = await api.async_revoke_temporary_guest_link(
                skud_id,
                requested_token,
            )
            after = await api.async_get_temporary_guest_links()
        except UfanetResponseError as err:
            raise ServiceValidationError(str(err)) from err
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        still_present = False
        for item in after:
            try:
                item_skud_id = int(item.get("skud_id"))
            except (TypeError, ValueError):
                continue
            if item_skud_id != skud_id:
                continue
            if _temporary_link_token(item.get("link")) == requested_token:
                still_present = True
                break

        if still_present:
            raise HomeAssistantError(
                "Ufanet returned from DELETE, but the temporary key is still present"
            )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": skud_id,
            "token": requested_token,
            "link": matched.get("link"),
            "time_end": matched.get("time_end"),
            "revoked": True,
            "response": result,
        }

    async def async_create_guest_invite(call: ServiceCall) -> ServiceResponse:
        """Create an invitation URL for shared intercom access."""
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        skud_id = int(skud["id"])
        try:
            result = await api.async_create_shared_guest_invite(skud_id)
        except UfanetResponseError as err:
            raise ServiceValidationError(str(err)) from err
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        stored_invite = await guest_invite_store.async_add(
            device_id=call.data[ATTR_DEVICE_ID],
            skud_id=skud_id,
            url=result["url"],
            access_id=result.get("access_id"),
        )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": skud_id,
            "url": result["url"],
            "access_id": result.get("access_id"),
            "invite_id": stored_invite["id"],
            "created_at": stored_invite["created_at"],
            "status": result.get("status"),
            "detail": result.get("detail"),
        }

    async def async_forget_guest_invite(call: ServiceCall) -> ServiceResponse:
        """Forget one locally persisted generated invite without revoking it."""
        _, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        skud_id = int(skud["id"])
        removed = await guest_invite_store.async_remove(
            device_id=call.data[ATTR_DEVICE_ID],
            skud_id=skud_id,
            invite_id=call.data["invite_id"],
        )
        if not removed:
            raise ServiceValidationError("Stored guest invitation was not found")

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": skud_id,
            "invite_id": call.data["invite_id"],
            "removed": True,
            "revoked_on_server": False,
        }

    async def async_revoke_shared_access(call: ServiceCall) -> ServiceResponse:
        """Revoke one accepted shared-access grant after verifying ownership."""
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        skud_id = int(skud["id"])
        requested_access_id = int(call.data["access_id"])

        try:
            current_users = await api.async_get_shared_access_users(skud_id)
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        matched: dict[str, Any] | None = None
        for item in current_users:
            raw_access_id = item.get("access_id", item.get("accessId"))
            try:
                access_id = int(raw_access_id)
            except (TypeError, ValueError):
                continue
            if access_id == requested_access_id:
                matched = item
                break

        if matched is None:
            raise ServiceValidationError(
                f"Shared access_id {requested_access_id} is not present "
                f"for selected intercom {skud_id}"
            )

        try:
            result = await api.async_revoke_shared_access(requested_access_id)
            users_after = await api.async_get_shared_access_users(skud_id)
        except UfanetResponseError as err:
            raise ServiceValidationError(str(err)) from err
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        still_present = False
        for item in users_after:
            raw_access_id = item.get("access_id", item.get("accessId"))
            try:
                if int(raw_access_id) == requested_access_id:
                    still_present = True
                    break
            except (TypeError, ValueError):
                continue

        if still_present:
            raise HomeAssistantError(
                "Ufanet returned success, but the shared access is still present"
            )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": skud_id,
            "access_id": requested_access_id,
            "username": matched.get("username"),
            "name": matched.get("name"),
            "scope": matched.get("scope"),
            "revoked": True,
            "status": result.get("status"),
            "detail": result.get("detail"),
        }

    async def async_get_download_url(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Export a recorded archive interval to a local MP4 file with ffmpeg.

        UCAMS does not allow arbitrary archive-<start>-<duration>.mp4 URLs with
        the normal archive token (HTTP 403 was live-confirmed). The reliable
        path is therefore:

          validated UCAMS HLS -> ffmpeg stream copy -> Home Assistant media dir

        The output remains a local persistent file and is exposed through the
        authenticated Home Assistant Media Source integration.
        """
        runtime, skud = _resolve_device_runtime(hass, call.data[ATTR_DEVICE_ID])
        api: UfanetApi = runtime["api"]
        options = runtime.get("options") or {}
        camera_number = _camera_number(skud)
        duration = int(call.data["duration"])
        retention_days = int(
            call.data.get(
                "retention_days",
                options.get(CONF_EXPORT_RETENTION_DAYS, DEFAULT_EXPORT_RETENTION_DAYS),
            )
        )
        max_total_mb = int(
            call.data.get(
                "max_total_mb",
                options.get(CONF_EXPORT_MAX_TOTAL_MB, DEFAULT_EXPORT_MAX_TOTAL_MB),
            )
        )
        auto_cleanup = bool(
            options.get(CONF_EXPORT_AUTO_CLEANUP, DEFAULT_EXPORT_AUTO_CLEANUP)
        )
        export_source = str(call.data.get("source") or "manual")
        event_id = str(call.data.get("event_id") or "").strip() or None
        event_ref = (
            hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:12]
            if export_source == "call" and event_id
            else None
        )

        try:
            camera = await api.async_get_camera(camera_number)
            timezone_name = str(camera.get("timezone") or hass.config.time_zone)
            start: datetime = call.data["start"]
            if start.tzinfo is None:
                try:
                    start_zone = ZoneInfo(timezone_name)
                except ZoneInfoNotFoundError:
                    start_zone = dt_util.get_default_time_zone()
                start = start.replace(tzinfo=start_zone)

            start_ts = int(start.timestamp())
            archive = await api.async_get_archive_url(
                camera_number,
                start_ts,
                duration,
            )
        except UfanetResponseError as err:
            raise ServiceValidationError(str(err)) from err
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        media_dirs = hass.config.media_dirs
        if not media_dirs:
            raise ServiceValidationError(
                "Home Assistant has no media directory configured. "
                "Enable media_source/default_config or configure homeassistant.media_dirs."
            )

        if "local" in media_dirs:
            media_key = "local"
        else:
            media_key = next(iter(media_dirs))

        media_root = Path(media_dirs[media_key])
        export_dir = media_root / "ufanet_intercom"
        await hass.async_add_executor_job(
            export_dir.mkdir,
            0o755,
            True,
            True,
        )

        try:
            local_zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            local_zone = dt_util.get_default_time_zone()

        local_start = datetime.fromtimestamp(
            int(archive["start"]),
            tz=timezone.utc,
        ).astimezone(local_zone)

        safe_camera = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in camera_number
        )
        filename_suffix = (
            f"_call_{event_ref}" if export_source == "call" and event_ref else ""
        )
        filename = (
            f"ufanet_{safe_camera}_"
            f"{local_start.strftime('%Y-%m-%d_%H-%M-%S')}_"
            f"{int(archive['duration'])}s{filename_suffix}.mp4"
        )

        if export_source == "call" and event_ref:
            existing_candidates = sorted(
                export_dir.glob(
                    f"{_camera_export_prefix(camera_number)}*_call_{event_ref}.mp4"
                )
            )
            if existing_candidates:
                existing_path = existing_candidates[0]
                file_size = existing_path.stat().st_size
                relative_path = f"ufanet_intercom/{existing_path.name}"
                return {
                    "device_id": call.data[ATTR_DEVICE_ID],
                    "skud_id": int(skud["id"]),
                    "camera_number": camera_number,
                    "timezone": timezone_name,
                    "start": start.isoformat(),
                    "start_utc": datetime.fromtimestamp(
                        archive["start"],
                        tz=timezone.utc,
                    ).isoformat(),
                    "start_camera": _local_iso(archive["start"], timezone_name),
                    "duration": archive["duration"],
                    "requested_duration": archive["requested_duration"],
                    "range_from": archive["range_from"],
                    "range_duration": archive["range_duration"],
                    "filename": existing_path.name,
                    "format": "mp4",
                    "content_type": "video/mp4",
                    "content_length": file_size,
                    "storage": "home_assistant_media",
                    "media_dir": media_key,
                    "media_content_id": (
                        f"media-source://media_source/{media_key}/{relative_path}"
                    ),
                    "relative_path": relative_path,
                    "source": "call",
                    "event_ref": event_ref,
                    "existing": True,
                    "cleanup": {
                        "deleted_count": 0,
                        "deleted_bytes": 0,
                        "deleted_files": [],
                        "remaining_count": None,
                        "remaining_bytes": None,
                        "limit_satisfied": True,
                        "skipped": True,
                    },
                }

        output_path = export_dir / filename
        temporary_path = export_dir / f".{filename}.part.mp4"

        # Do not leave a stale partial file from a previous failed export.
        if temporary_path.exists():
            await hass.async_add_executor_job(temporary_path.unlink)

        ffmpeg_binary = "ffmpeg"
        command = (
            ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(archive["url"]),
            "-t",
            str(int(archive["duration"])),
            "-map",
            "0:v:0?",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-avoid_negative_ts",
            "make_zero",
            str(temporary_path),
        )

        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # HLS segments normally download substantially faster than real
            # time, but allow a generous window for slower HA hardware/network.
            timeout_seconds = max(
                90,
                min(900, int(archive["duration"]) * 2 + 60),
            )

            try:
                _stdout, _stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds,
                )
            except TimeoutError as err:
                process.kill()
                await process.communicate()
                raise HomeAssistantError(
                    f"ffmpeg archive export timed out after {timeout_seconds} seconds"
                ) from err

            if process.returncode != 0:
                raise HomeAssistantError(
                    "ffmpeg could not export the Ufanet archive; "
                    "see the Home Assistant host diagnostics"
                )

            if not temporary_path.exists():
                raise HomeAssistantError(
                    "ffmpeg completed without creating an MP4 file"
                )

            file_size = temporary_path.stat().st_size
            if file_size <= 0:
                raise HomeAssistantError(
                    "ffmpeg created an empty MP4 file"
                )

            await hass.async_add_executor_job(
                temporary_path.replace,
                output_path,
            )

        except FileNotFoundError as err:
            raise ServiceValidationError(
                "ffmpeg executable was not found. Home Assistant OS and "
                "Home Assistant Container include ffmpeg; Core/venv installs "
                "must install ffmpeg separately."
            ) from err
        finally:
            if temporary_path.exists():
                try:
                    await hass.async_add_executor_job(temporary_path.unlink)
                except OSError:
                    pass

        if auto_cleanup:
            cleanup = await hass.async_add_executor_job(
                _cleanup_export_files_sync,
                export_dir,
                _camera_export_prefix(camera_number),
                retention_days,
                max_total_mb * 1024 * 1024,
                filename,
            )
        else:
            cleanup = {
                "deleted_count": 0,
                "deleted_bytes": 0,
                "deleted_files": [],
                "remaining_count": None,
                "remaining_bytes": None,
                "limit_satisfied": True,
                "skipped": True,
            }

        file_size = output_path.stat().st_size
        relative_path = f"ufanet_intercom/{filename}"
        media_content_id = (
            f"media-source://media_source/{media_key}/{relative_path}"
        )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "camera_number": camera_number,
            "timezone": timezone_name,
            "start": start.isoformat(),
            "start_utc": datetime.fromtimestamp(
                archive["start"],
                tz=timezone.utc,
            ).isoformat(),
            "start_camera": _local_iso(archive["start"], timezone_name),
            "duration": archive["duration"],
            "requested_duration": archive["requested_duration"],
            "range_from": archive["range_from"],
            "range_duration": archive["range_duration"],
            "filename": filename,
            "format": "mp4",
            "content_type": "video/mp4",
            "content_length": file_size,
            "storage": "home_assistant_media",
            "media_dir": media_key,
            "media_content_id": media_content_id,
            "relative_path": relative_path,
            "source": export_source,
            "event_ref": event_ref,
            "existing": False,
            "cleanup": cleanup,
        }

    async def async_list_archive_exports(
        call: ServiceCall,
    ) -> ServiceResponse:
        """List locally exported MP4 files for the selected intercom camera."""
        _, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        camera_number = _camera_number(skud)
        media_key, export_dir = _archive_export_location(hass)

        items = await hass.async_add_executor_job(
            _list_export_files_sync,
            export_dir,
            _camera_export_prefix(camera_number),
            media_key,
        )

        total_bytes = sum(int(item["size_bytes"]) for item in items)
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "camera_number": camera_number,
            "media_dir": media_key,
            "count": len(items),
            "total_bytes": total_bytes,
            "items": items,
        }

    async def async_delete_archive_export(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Delete exactly one local export owned by the selected camera."""
        _, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        camera_number = _camera_number(skud)
        filename = str(call.data["filename"]).strip()
        _, export_dir = _archive_export_location(hass)

        deleted = await hass.async_add_executor_job(
            _delete_export_file_sync,
            export_dir,
            _camera_export_prefix(camera_number),
            filename,
        )
        if not deleted:
            raise ServiceValidationError("Archive export file was not found")

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "camera_number": camera_number,
            "filename": filename,
            "deleted": True,
        }

    async def async_cleanup_archive_exports(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Apply age and total-size retention rules to local camera exports."""
        runtime, skud = _resolve_device_runtime(hass, call.data[ATTR_DEVICE_ID])
        options = runtime.get("options") or {}
        camera_number = _camera_number(skud)
        retention_days = int(
            call.data.get(
                "retention_days",
                options.get(CONF_EXPORT_RETENTION_DAYS, DEFAULT_EXPORT_RETENTION_DAYS),
            )
        )
        max_total_mb = int(
            call.data.get(
                "max_total_mb",
                options.get(CONF_EXPORT_MAX_TOTAL_MB, DEFAULT_EXPORT_MAX_TOTAL_MB),
            )
        )
        _, export_dir = _archive_export_location(hass)

        cleanup = await hass.async_add_executor_job(
            _cleanup_export_files_sync,
            export_dir,
            _camera_export_prefix(camera_number),
            retention_days,
            max_total_mb * 1024 * 1024,
            None,
        )

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "camera_number": camera_number,
            "retention_days": retention_days,
            "max_total_mb": max_total_mb,
            **cleanup,
        }

    async def async_get_url(call: ServiceCall) -> ServiceResponse:
        api, skud = _resolve_device(hass, call.data[ATTR_DEVICE_ID])
        camera_number = _camera_number(skud)
        duration = int(call.data["duration"])

        try:
            camera = await api.async_get_camera(camera_number)
            timezone_name = str(camera.get("timezone") or hass.config.time_zone)
            start: datetime = call.data["start"]
            if start.tzinfo is None:
                try:
                    start_zone = ZoneInfo(timezone_name)
                except ZoneInfoNotFoundError:
                    start_zone = dt_util.get_default_time_zone()
                start = start.replace(tzinfo=start_zone)
            start_ts = int(start.timestamp())
            archive = await api.async_get_archive_url(
                camera_number, start_ts, duration
            )
        except UfanetResponseError as err:
            raise ServiceValidationError(str(err)) from err
        except UfanetApiError as err:
            raise HomeAssistantError(str(err)) from err

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "skud_id": int(skud["id"]),
            "camera_number": camera_number,
            "timezone": timezone_name,
            "start": start.isoformat(),
            "start_utc": datetime.fromtimestamp(
                archive["start"], tz=timezone.utc
            ).isoformat(),
            "start_camera": _local_iso(archive["start"], timezone_name),
            "duration": archive["duration"],
            "requested_duration": archive["requested_duration"],
            "range_from": archive["range_from"],
            "range_duration": archive["range_duration"],
            "url": archive["url"],
            "vendor": archive["vendor"],
            "token_expires_at": (
                datetime.fromtimestamp(archive["token_expires_at"], tz=timezone.utc).isoformat()
                if archive.get("token_expires_at")
                else None
            ),
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SETTINGS,
        async_get_settings,
        schema=GET_SETTINGS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_RUNTIME_STATUS,
        async_get_runtime_status,
        schema=GET_RUNTIME_STATUS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_LAST_CALL_PREVIEW_URL,
        async_get_last_call_preview_url,
        schema=GET_LAST_CALL_PREVIEW_URL_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_ARCHIVE_RANGES,
        async_get_ranges,
        schema=GET_ARCHIVE_RANGES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_ARCHIVE_URL,
        async_get_url,
        schema=GET_ARCHIVE_URL_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
        async_get_download_url,
        schema=GET_ARCHIVE_DOWNLOAD_URL_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_ARCHIVE_EXPORTS,
        async_list_archive_exports,
        schema=LIST_ARCHIVE_EXPORTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_ARCHIVE_EXPORT,
        async_delete_archive_export,
        schema=DELETE_ARCHIVE_EXPORT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEANUP_ARCHIVE_EXPORTS,
        async_cleanup_archive_exports,
        schema=CLEANUP_ARCHIVE_EXPORTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CALL_EVENTS,
        async_get_call_events,
        schema=GET_CALL_EVENTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_GUEST_ACCESS,
        async_get_guest_access,
        schema=GET_GUEST_ACCESS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_TEMPORARY_GUEST_LINK,
        async_create_temporary_guest_link,
        schema=CREATE_TEMPORARY_GUEST_LINK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVOKE_TEMPORARY_GUEST_LINK,
        async_revoke_temporary_guest_link,
        schema=REVOKE_TEMPORARY_GUEST_LINK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_GUEST_INVITE,
        async_create_guest_invite,
        schema=CREATE_GUEST_INVITE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORGET_GUEST_INVITE,
        async_forget_guest_invite,
        schema=FORGET_GUEST_INVITE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVOKE_SHARED_ACCESS,
        async_revoke_shared_access,
        schema=REVOKE_SHARED_ACCESS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )




_EXPORT_FILE_RE = re.compile(
    r"^ufanet_(?P<camera>.+)_(?P<date>\d{4}-\d{2}-\d{2})_"
    r"(?P<clock>\d{2}-\d{2}-\d{2})_(?P<duration>\d+)s"
    r"(?:_(?P<source>call)_(?P<event_ref>[0-9a-f]{12}))?\.mp4$"
)


def _camera_export_prefix(camera_number: str) -> str:
    """Return the exact filename prefix used by the exporter."""
    safe_camera = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in str(camera_number)
    )
    return f"ufanet_{safe_camera}_"


def _archive_export_location(hass: HomeAssistant) -> tuple[str, Path]:
    """Resolve the Home Assistant media directory used by Ufanet exports."""
    media_dirs = hass.config.media_dirs
    if not media_dirs:
        raise ServiceValidationError(
            "Home Assistant has no media directory configured. "
            "Enable media_source/default_config or configure homeassistant.media_dirs."
        )

    media_key = "local" if "local" in media_dirs else next(iter(media_dirs))
    export_dir = Path(media_dirs[media_key]) / "ufanet_intercom"
    export_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    return media_key, export_dir


def _validated_export_path(
    export_dir: Path,
    expected_prefix: str,
    filename: str,
) -> Path:
    """Validate a user-supplied export basename without allowing traversal."""
    if not filename or Path(filename).name != filename:
        raise ServiceValidationError("Invalid archive export filename")
    if not filename.startswith(expected_prefix) or not filename.endswith(".mp4"):
        raise ServiceValidationError(
            "Archive export does not belong to the selected intercom camera"
        )

    path = export_dir / filename
    try:
        path.resolve().relative_to(export_dir.resolve())
    except ValueError as err:
        raise ServiceValidationError("Invalid archive export path") from err
    return path


def _export_item(
    path: Path,
    media_key: str,
) -> dict[str, Any]:
    """Build one media-library item from a local MP4 file."""
    stat = path.stat()
    match = _EXPORT_FILE_RE.match(path.name)

    duration_seconds: int | None = None
    recorded_local: str | None = None
    source = "manual"
    event_ref: str | None = None
    if match:
        duration_seconds = int(match.group("duration"))
        recorded_local = (
            f"{match.group('date')} "
            f"{match.group('clock').replace('-', ':')}"
        )
        source = match.group("source") or "manual"
        event_ref = match.group("event_ref")

    relative_path = f"ufanet_intercom/{path.name}"
    return {
        "filename": path.name,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
        "duration_seconds": duration_seconds,
        "recorded_local": recorded_local,
        "source": source,
        "event_ref": event_ref,
        "relative_path": relative_path,
        "media_content_id": (
            f"media-source://media_source/{media_key}/{relative_path}"
        ),
    }


def _list_export_files_sync(
    export_dir: Path,
    expected_prefix: str,
    media_key: str,
) -> list[dict[str, Any]]:
    """List camera-specific exports, newest first."""
    if not export_dir.exists():
        return []

    paths = [
        path
        for path in export_dir.iterdir()
        if path.is_file()
        and path.name.startswith(expected_prefix)
        and path.name.endswith(".mp4")
        and not path.name.startswith(".")
    ]
    paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [_export_item(path, media_key) for path in paths]


def _delete_export_file_sync(
    export_dir: Path,
    expected_prefix: str,
    filename: str,
) -> bool:
    """Delete one validated camera-specific export."""
    path = _validated_export_path(export_dir, expected_prefix, filename)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _cleanup_export_files_sync(
    export_dir: Path,
    expected_prefix: str,
    retention_days: int,
    max_total_bytes: int,
    keep_filename: str | None,
) -> dict[str, Any]:
    """Delete old exports and enforce a total-size cap.

    retention_days == 0 disables age cleanup.
    max_total_bytes == 0 disables size cleanup.
    keep_filename protects the just-created file during automatic cleanup.
    """
    if not export_dir.exists():
        return {
            "deleted_count": 0,
            "deleted_bytes": 0,
            "deleted_files": [],
            "remaining_count": 0,
            "remaining_bytes": 0,
            "limit_satisfied": True,
        }

    paths = [
        path
        for path in export_dir.iterdir()
        if path.is_file()
        and path.name.startswith(expected_prefix)
        and path.name.endswith(".mp4")
        and not path.name.startswith(".")
    ]

    deleted_files: list[str] = []
    deleted_bytes = 0
    now = time_module.time()

    # Phase 1: age retention.
    if retention_days > 0:
        cutoff = now - retention_days * 86400
        for path in list(paths):
            if path.name == keep_filename:
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                paths.remove(path)
                continue
            if stat.st_mtime < cutoff:
                size = stat.st_size
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                else:
                    deleted_files.append(path.name)
                    deleted_bytes += size
                if path in paths:
                    paths.remove(path)

    # Phase 2: total-size cap. Oldest files go first.
    existing: list[tuple[Path, int, float]] = []
    for path in paths:
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        existing.append((path, stat.st_size, stat.st_mtime))

    total_bytes = sum(size for _, size, _ in existing)
    if max_total_bytes > 0 and total_bytes > max_total_bytes:
        for path, size, _mtime in sorted(existing, key=lambda item: item[2]):
            if total_bytes <= max_total_bytes:
                break
            if path.name == keep_filename:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            deleted_files.append(path.name)
            deleted_bytes += size
            total_bytes -= size

    remaining: list[Path] = [
        path
        for path in export_dir.iterdir()
        if path.is_file()
        and path.name.startswith(expected_prefix)
        and path.name.endswith(".mp4")
        and not path.name.startswith(".")
    ]
    remaining_bytes = 0
    for path in remaining:
        try:
            remaining_bytes += path.stat().st_size
        except FileNotFoundError:
            pass

    limit_satisfied = (
        max_total_bytes <= 0 or remaining_bytes <= max_total_bytes
    )

    return {
        "deleted_count": len(deleted_files),
        "deleted_bytes": deleted_bytes,
        "deleted_files": deleted_files,
        "remaining_count": len(remaining),
        "remaining_bytes": remaining_bytes,
        "limit_satisfied": limit_satisfied,
    }


def _call_event_datetime(event: dict[str, Any]) -> datetime | None:
    """Parse called_at as an absolute instant.

    Some Ufanet responses expose a `timezone` field that does not match the
    numeric offset embedded in `called_at`. The aware `called_at` value is the
    authoritative instant; it is converted to the camera timezone afterwards.
    """
    value = event.get("called_at")
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)



def _temporary_link_token(link: Any) -> str | None:
    """Extract a temporary key token from its returned web URL."""
    if not isinstance(link, str) or not link:
        return None

    try:
        query = parse_qs(urlparse(link).query)
    except ValueError:
        return None

    values = query.get("token")
    if not values:
        return None

    token = values[0]
    return token if isinstance(token, str) and token else None


def _resolve_device_runtime(
    hass: HomeAssistant, device_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a Ufanet device to its loaded config-entry runtime and SKUD."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Device {device_id} was not found")

    skud_ids: list[int] = []
    for domain, identifier in device.identifiers:
        if domain != DOMAIN:
            continue
        try:
            skud_ids.append(int(identifier))
        except ValueError:
            continue
    if not skud_ids:
        raise ServiceValidationError("Selected device is not a Ufanet Intercom device")

    runtimes = hass.data.get(DOMAIN, {})
    for runtime in runtimes.values():
        if not isinstance(runtime, dict):
            continue
        coordinator = runtime.get("coordinator")
        if coordinator is None or not isinstance(coordinator.data, dict):
            continue
        for skud_id in skud_ids:
            skud = coordinator.data.get(skud_id)
            if skud is not None:
                return runtime, skud

    raise ServiceValidationError("Ufanet configuration entry for this device is not loaded")


def _resolve_device(
    hass: HomeAssistant, device_id: str
) -> tuple[UfanetApi, dict[str, Any]]:
    """Resolve a Home Assistant Ufanet device to its loaded runtime/API."""
    runtime, skud = _resolve_device_runtime(hass, device_id)
    return runtime["api"], skud


def _camera_number(skud: dict[str, Any]) -> str:
    value = skud.get("cctv_number")
    if not value:
        raise ServiceValidationError("Selected intercom has no linked UCAMS camera")
    return str(value)


def _ranges_response(
    device_id: str,
    skud: dict[str, Any],
    camera: dict[str, Any],
    ranges: list[dict[str, int]],
) -> dict[str, Any]:
    timezone_name = str(camera.get("timezone") or "UTC")
    tariff = camera.get("tariff") if isinstance(camera.get("tariff"), dict) else {}
    formatted = []
    normalized: list[tuple[int, int]] = []
    for item in sorted(ranges, key=lambda value: int(value["from"])):
        start = int(item["from"])
        duration = int(item["duration"])
        end = start + duration
        formatted.append(
            {
                "from": start,
                "duration": duration,
                "start_utc": datetime.fromtimestamp(start, tz=timezone.utc).isoformat(),
                "end_utc": datetime.fromtimestamp(end, tz=timezone.utc).isoformat(),
                "start_camera": _local_iso(start, timezone_name),
                "end_camera": _local_iso(end, timezone_name),
            }
        )
        normalized.append((start, end))

    days = _archive_days(normalized, timezone_name)
    earliest = min((start for start, _end in normalized), default=None)
    latest = max((end for _start, end in normalized), default=None)

    return {
        "device_id": device_id,
        "skud_id": int(skud["id"]),
        "camera_number": str(skud["cctv_number"]),
        "timezone": timezone_name,
        "archive_name": tariff.get("name"),
        "dvr_hours": tariff.get("dvr_hours"),
        "count": len(formatted),
        "earliest": earliest,
        "latest": latest,
        "earliest_camera": _local_iso(earliest, timezone_name) if earliest is not None else None,
        "latest_camera": _local_iso(latest, timezone_name) if latest is not None else None,
        "first_date": days[0]["date"] if days else None,
        "last_date": days[-1]["date"] if days else None,
        "days": days,
        "ranges": formatted,
    }


def _archive_days(
    ranges: list[tuple[int, int]],
    timezone_name: str,
) -> list[dict[str, Any]]:
    """Split Unix archive ranges into camera-local calendar days.

    Each interval uses an exclusive ``to`` timestamp and second-of-day values.
    ``end_second`` can be 86400, rendered by the frontend as 24:00.
    Tiny overlaps/gaps up to three seconds are merged because UCAMS ranges can
    contain boundary jitter of a few seconds.
    """
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = timezone.utc

    by_date: dict[str, list[dict[str, int]]] = {}

    for start, end in ranges:
        cursor = start
        while cursor < end:
            local = datetime.fromtimestamp(cursor, tz=zone)
            day = local.date()
            next_day = day + timedelta(days=1)
            next_midnight = datetime.combine(next_day, time.min, tzinfo=zone)
            boundary = int(next_midnight.timestamp())
            segment_end = min(end, boundary)

            midnight = datetime.combine(day, time.min, tzinfo=zone)
            midnight_ts = int(midnight.timestamp())
            start_second = max(0, cursor - midnight_ts)
            end_second = min(86400, segment_end - midnight_ts)

            by_date.setdefault(day.isoformat(), []).append(
                {
                    "from": cursor,
                    "to": segment_end,
                    "start_second": start_second,
                    "end_second": end_second,
                }
            )
            cursor = segment_end

    result: list[dict[str, Any]] = []
    for day_text in sorted(by_date):
        raw = sorted(by_date[day_text], key=lambda item: item["from"])
        merged: list[dict[str, int]] = []
        for item in raw:
            if merged and item["from"] <= merged[-1]["to"] + 3:
                merged[-1]["to"] = max(merged[-1]["to"], item["to"])
                merged[-1]["end_second"] = max(
                    merged[-1]["end_second"], item["end_second"]
                )
            else:
                merged.append(dict(item))

        intervals = []
        total = 0
        for item in merged:
            duration = item["to"] - item["from"]
            total += duration
            intervals.append(
                {
                    **item,
                    "duration": duration,
                    "start": _seconds_hms(item["start_second"]),
                    "end": _seconds_hms(item["end_second"]),
                }
            )

        result.append(
            {
                "date": day_text,
                "from": intervals[0]["from"],
                "to": intervals[-1]["to"],
                "total_duration": total,
                "intervals": intervals,
            }
        )

    return result


def _seconds_hms(value: int) -> str:
    if value >= 86400:
        return "24:00:00"
    hours, remainder = divmod(max(0, value), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def _local_iso(timestamp: int, timezone_name: str) -> str:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return datetime.fromtimestamp(timestamp, tz=zone).isoformat()
