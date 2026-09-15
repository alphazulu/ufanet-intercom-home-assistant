"""Privacy-safe Home Assistant response services for standalone UCAMS cameras."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import voluptuous as vol

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .analytics import (
    async_get_motion_capabilities,
    async_get_motion_timeline_events,
)
from .api import UfanetApiError, UfanetResponseError
from .const import (
    CONF_ARCHIVE_DEFAULT_DURATION,
    CONF_ARCHIVE_DEFAULT_STEP,
    CONF_EXPORT_AUTO_CLEANUP,
    CONF_EXPORT_DEFAULT_DURATION,
    CONF_EXPORT_MAX_TOTAL_MB,
    CONF_EXPORT_RETENTION_DAYS,
    DEFAULT_ARCHIVE_DURATION_SECONDS,
    DEFAULT_ARCHIVE_STEP_SECONDS,
    DEFAULT_EXPORT_AUTO_CLEANUP,
    DEFAULT_EXPORT_DEFAULT_DURATION_SECONDS,
    DEFAULT_EXPORT_MAX_TOTAL_MB,
    DEFAULT_EXPORT_RETENTION_DAYS,
    DOMAIN,
    MAX_ARCHIVE_DURATION_SECONDS,
    MAX_EXPORT_RETENTION_DAYS,
    MAX_EXPORT_TOTAL_MB,
)
from .private_runtime import UfanetPrivateCameraRuntime
from .services import (
    _archive_days,
    _async_archive_export_location,
    _camera_export_prefix,
    _cleanup_export_files_sync,
    _delete_export_file_sync,
    _file_size_if_exists_sync,
    _list_export_files_sync,
    _local_iso,
    _required_file_size_sync,
    _unlink_if_exists_sync,
)

SERVICE_PRIVATE_GET_SETTINGS = "get_private_camera_settings"
SERVICE_PRIVATE_GET_ARCHIVE_RANGES = "get_private_archive_ranges"
SERVICE_PRIVATE_GET_ARCHIVE_URL = "get_private_archive_url"
SERVICE_PRIVATE_GET_ARCHIVE_DOWNLOAD_URL = "get_private_archive_download_url"
SERVICE_PRIVATE_LIST_ARCHIVE_EXPORTS = "list_private_archive_exports"
SERVICE_PRIVATE_DELETE_ARCHIVE_EXPORT = "delete_private_archive_export"
SERVICE_PRIVATE_CLEANUP_ARCHIVE_EXPORTS = "cleanup_private_archive_exports"
SERVICE_PRIVATE_GET_MOTION_EVENTS = "get_private_motion_events"
SERVICE_PRIVATE_GET_CALL_EVENTS = "get_private_call_events"

_DEVICE_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})
_ARCHIVE_URL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("start"): cv.datetime,
        vol.Optional("duration", default=DEFAULT_ARCHIVE_DURATION_SECONDS): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=MAX_ARCHIVE_DURATION_SECONDS),
        ),
    }
)
_ARCHIVE_EXPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("start"): cv.datetime,
        vol.Optional("duration", default=DEFAULT_ARCHIVE_DURATION_SECONDS): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=MAX_ARCHIVE_DURATION_SECONDS),
        ),
        vol.Optional("retention_days"): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_RETENTION_DAYS),
        ),
        vol.Optional("max_total_mb"): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_TOTAL_MB),
        ),
        vol.Optional("source", default="manual"): vol.In(["manual"]),
    }
)
_DELETE_EXPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("filename"): cv.string,
    }
)
_CLEANUP_EXPORTS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional("retention_days"): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_RETENTION_DAYS),
        ),
        vol.Optional("max_total_mb"): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_TOTAL_MB),
        ),
    }
)
_DATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required("date"): cv.date,
    }
)


def _resolve_private_target(
    hass: HomeAssistant,
    device_id: str,
) -> tuple[dict[str, Any], UfanetPrivateCameraRuntime, str, dict[str, Any]]:
    """Resolve a standalone camera from its opaque Home Assistant device identity."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError("Selected Ufanet camera device was not found")

    target_refs = [
        identifier
        for domain, identifier in device.identifiers
        if domain == DOMAIN and str(identifier).startswith("ucams_camera_")
    ]
    if not target_refs:
        raise ServiceValidationError("Selected device is not a standalone Ufanet camera")

    for runtime in hass.data.get(DOMAIN, {}).values():
        if not isinstance(runtime, dict):
            continue
        manager = runtime.get("private_camera_runtime")
        if not isinstance(manager, UfanetPrivateCameraRuntime):
            continue
        for target_ref in target_refs:
            camera = manager.camera_for_target(str(target_ref))
            if camera is not None:
                return runtime, manager, str(target_ref), camera

    raise ServiceValidationError("Standalone Ufanet camera runtime is not available")


def _private_ranges_response(
    device_id: str,
    target_ref: str,
    camera: dict[str, Any],
    ranges: list[dict[str, int]],
) -> dict[str, Any]:
    """Build the normal archive timeline shape without provider camera identifiers."""
    timezone_name = str(camera.get("timezone") or "UTC")
    tariff = camera.get("tariff") if isinstance(camera.get("tariff"), dict) else {}
    formatted: list[dict[str, Any]] = []
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
        "camera_ref": target_ref,
        "timezone": timezone_name,
        "archive_name": tariff.get("name"),
        "dvr_hours": tariff.get("dvr_hours"),
        "count": len(formatted),
        "earliest": earliest,
        "latest": latest,
        "earliest_camera": (
            _local_iso(earliest, timezone_name) if earliest is not None else None
        ),
        "latest_camera": (
            _local_iso(latest, timezone_name) if latest is not None else None
        ),
        "first_date": days[0]["date"] if days else None,
        "last_date": days[-1]["date"] if days else None,
        "days": days,
        "ranges": formatted,
    }


def async_setup_private_camera_services(hass: HomeAssistant) -> None:
    """Register standalone-camera-only response services once."""
    if hass.services.has_service(DOMAIN, SERVICE_PRIVATE_GET_ARCHIVE_RANGES):
        return

    async def async_get_settings(call: ServiceCall) -> ServiceResponse:
        runtime, _manager, target_ref, _camera = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        options = runtime.get("options") or {}
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
            "archive_default_duration_seconds": int(
                options.get(
                    CONF_ARCHIVE_DEFAULT_DURATION,
                    DEFAULT_ARCHIVE_DURATION_SECONDS,
                )
            ),
            "archive_default_step_seconds": int(
                options.get(CONF_ARCHIVE_DEFAULT_STEP, DEFAULT_ARCHIVE_STEP_SECONDS)
            ),
            "export_default_duration_seconds": int(
                options.get(
                    CONF_EXPORT_DEFAULT_DURATION,
                    DEFAULT_EXPORT_DEFAULT_DURATION_SECONDS,
                )
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

    async def async_get_ranges(call: ServiceCall) -> ServiceResponse:
        runtime, manager, target_ref, camera_item = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        if not manager.archive_available(target_ref):
            raise ServiceValidationError("Archive is not available for this Ufanet camera")
        camera_number = str(camera_item["number"])
        api = runtime["api"]
        try:
            camera = await api.async_get_camera(camera_number)
            ranges = await api.async_get_archive_ranges(camera_number)
        except UfanetApiError:
            raise HomeAssistantError("Unable to load standalone Ufanet archive ranges") from None
        return _private_ranges_response(
            call.data[ATTR_DEVICE_ID],
            target_ref,
            camera,
            ranges,
        )

    async def async_get_url(call: ServiceCall) -> ServiceResponse:
        runtime, manager, target_ref, camera_item = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        if not manager.archive_available(target_ref):
            raise ServiceValidationError("Archive is not available for this Ufanet camera")
        camera_number = str(camera_item["number"])
        api = runtime["api"]
        duration = int(call.data["duration"])
        try:
            camera = await api.async_get_camera(camera_number)
            timezone_name = str(camera.get("timezone") or hass.config.time_zone or "UTC")
            start: datetime = call.data["start"]
            if start.tzinfo is None:
                try:
                    start_zone = ZoneInfo(timezone_name)
                except ZoneInfoNotFoundError:
                    start_zone = dt_util.get_default_time_zone()
                start = start.replace(tzinfo=start_zone)
            archive = await api.async_get_archive_url(
                camera_number,
                int(start.timestamp()),
                duration,
            )
        except UfanetResponseError:
            raise ServiceValidationError("Requested standalone archive interval is unavailable") from None
        except UfanetApiError:
            raise HomeAssistantError("Unable to load standalone Ufanet archive video") from None

        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
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
            "url": archive["url"],
            "vendor": archive["vendor"],
            "token_expires_at": (
                datetime.fromtimestamp(
                    archive["token_expires_at"],
                    tz=timezone.utc,
                ).isoformat()
                if archive.get("token_expires_at")
                else None
            ),
        }

    async def async_get_motion_events(call: ServiceCall) -> ServiceResponse:
        runtime, manager, target_ref, camera_item = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        api = runtime["api"]
        camera_number = str(camera_item["number"])
        requested_date: date = call.data["date"]
        analytics = manager.analytics_coordinator
        data = analytics.data
        snapshot_ready = bool(
            analytics.last_update_success and isinstance(data, dict)
        )
        try:
            if snapshot_ready:
                supported = target_ref in data
            else:
                supported = camera_number in await async_get_motion_capabilities(
                    api,
                    [camera_number],
                )
        except UfanetApiError:
            raise HomeAssistantError("Unable to load standalone motion capabilities") from None

        controller = manager.archive_controllers.get(target_ref)
        timezone_name = str(
            getattr(controller, "timezone_name", None)
            or camera_item.get("timezone")
            or hass.config.time_zone
            or "UTC"
        )
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            zone = dt_util.get_default_time_zone()
            timezone_name = str(getattr(zone, "key", None) or "UTC")

        base_response: dict[str, Any] = {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
            "timezone": timezone_name,
            "date": requested_date.isoformat(),
            "supported": supported,
        }
        if not supported:
            return {**base_response, "count": 0, "events": []}

        day_start = datetime.combine(requested_date, time.min, tzinfo=zone)
        day_end = day_start.replace() + (datetime.min.replace(year=1, month=1, day=2) - datetime.min)
        try:
            event_times = await async_get_motion_timeline_events(
                api,
                camera_number,
                start=day_start.astimezone(timezone.utc),
                end=day_end.astimezone(timezone.utc),
            )
        except UfanetApiError:
            raise HomeAssistantError("Unable to load standalone motion timeline events") from None

        matching: list[dict[str, Any]] = []
        for timestamp in event_times:
            local = timestamp.astimezone(zone)
            if local.date() != requested_date:
                continue
            second_of_day = (
                local.hour * 3600
                + local.minute * 60
                + local.second
                + local.microsecond / 1_000_000
            )
            matching.append(
                {
                    "timestamp": timestamp.timestamp(),
                    "local_datetime": local.isoformat(),
                    "local_time": local.strftime("%H:%M:%S.%f").rstrip("0").rstrip("."),
                    "second_of_day": second_of_day,
                }
            )
        matching.sort(key=lambda item: float(item["timestamp"]))
        return {**base_response, "count": len(matching), "events": matching}

    async def async_get_call_events(call: ServiceCall) -> ServiceResponse:
        _runtime, _manager, target_ref, camera_item = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        requested_date: date = call.data["date"]
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
            "timezone": str(camera_item.get("timezone") or hass.config.time_zone or "UTC"),
            "date": requested_date.isoformat(),
            "count": 0,
            "events": [],
        }

    async def async_export_archive(call: ServiceCall) -> ServiceResponse:
        runtime, manager, target_ref, camera_item = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        if not manager.archive_available(target_ref):
            raise ServiceValidationError("Archive is not available for this Ufanet camera")
        api = runtime["api"]
        options = runtime.get("options") or {}
        camera_number = str(camera_item["number"])
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

        try:
            camera = await api.async_get_camera(camera_number)
            timezone_name = str(camera.get("timezone") or hass.config.time_zone or "UTC")
            start: datetime = call.data["start"]
            if start.tzinfo is None:
                try:
                    start_zone = ZoneInfo(timezone_name)
                except ZoneInfoNotFoundError:
                    start_zone = dt_util.get_default_time_zone()
                start = start.replace(tzinfo=start_zone)
            archive = await api.async_get_archive_url(
                camera_number,
                int(start.timestamp()),
                duration,
            )
        except UfanetResponseError:
            raise ServiceValidationError("Requested standalone archive interval is unavailable") from None
        except UfanetApiError:
            raise HomeAssistantError("Unable to prepare standalone Ufanet archive export") from None

        media_key, export_dir = await _async_archive_export_location(hass)
        try:
            local_zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            local_zone = dt_util.get_default_time_zone()
        local_start = datetime.fromtimestamp(
            int(archive["start"]),
            tz=timezone.utc,
        ).astimezone(local_zone)

        filename = (
            f"ufanet_{target_ref}_"
            f"{local_start.strftime('%Y-%m-%d_%H-%M-%S')}_"
            f"{int(archive['duration'])}s.mp4"
        )
        output_path = export_dir / filename
        temporary_path = export_dir / f".{filename}.part.mp4"
        await hass.async_add_executor_job(_unlink_if_exists_sync, temporary_path)

        command = (
            "ffmpeg",
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
            timeout_seconds = max(90, min(900, int(archive["duration"]) * 2 + 60))
            try:
                await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            except TimeoutError as err:
                process.kill()
                await process.communicate()
                raise HomeAssistantError("Standalone archive export timed out") from err
            if process.returncode != 0:
                raise HomeAssistantError("ffmpeg could not export the standalone Ufanet archive")
            file_size = await hass.async_add_executor_job(
                _file_size_if_exists_sync,
                temporary_path,
            )
            if file_size is None or file_size <= 0:
                raise HomeAssistantError("ffmpeg did not create a valid standalone archive MP4")
            await hass.async_add_executor_job(temporary_path.replace, output_path)
        except FileNotFoundError as err:
            raise ServiceValidationError("ffmpeg executable was not found") from err
        finally:
            try:
                await hass.async_add_executor_job(_unlink_if_exists_sync, temporary_path)
            except OSError:
                pass

        prefix = _camera_export_prefix(target_ref)
        if auto_cleanup:
            cleanup = await hass.async_add_executor_job(
                _cleanup_export_files_sync,
                export_dir,
                prefix,
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

        file_size = await hass.async_add_executor_job(_required_file_size_sync, output_path)
        relative_path = f"ufanet_intercom/{filename}"
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
            "timezone": timezone_name,
            "start": start.isoformat(),
            "start_utc": datetime.fromtimestamp(archive["start"], tz=timezone.utc).isoformat(),
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
            "media_content_id": f"media-source://media_source/{media_key}/{relative_path}",
            "relative_path": relative_path,
            "source": "manual",
            "event_ref": None,
            "existing": False,
            "cleanup": cleanup,
        }

    async def async_list_exports(call: ServiceCall) -> ServiceResponse:
        _runtime, _manager, target_ref, _camera = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        media_key, export_dir = await _async_archive_export_location(hass)
        items = await hass.async_add_executor_job(
            _list_export_files_sync,
            export_dir,
            _camera_export_prefix(target_ref),
            media_key,
        )
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
            "media_dir": media_key,
            "count": len(items),
            "total_bytes": sum(int(item["size_bytes"]) for item in items),
            "items": items,
        }

    async def async_delete_export(call: ServiceCall) -> ServiceResponse:
        _runtime, _manager, target_ref, _camera = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        _media_key, export_dir = await _async_archive_export_location(hass)
        filename = str(call.data["filename"]).strip()
        deleted = await hass.async_add_executor_job(
            _delete_export_file_sync,
            export_dir,
            _camera_export_prefix(target_ref),
            filename,
        )
        if not deleted:
            raise ServiceValidationError("Standalone archive export file was not found")
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
            "filename": filename,
            "deleted": True,
        }

    async def async_cleanup_exports(call: ServiceCall) -> ServiceResponse:
        runtime, _manager, target_ref, _camera = _resolve_private_target(
            hass,
            call.data[ATTR_DEVICE_ID],
        )
        options = runtime.get("options") or {}
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
        _media_key, export_dir = await _async_archive_export_location(hass)
        cleanup = await hass.async_add_executor_job(
            _cleanup_export_files_sync,
            export_dir,
            _camera_export_prefix(target_ref),
            retention_days,
            max_total_mb * 1024 * 1024,
            None,
        )
        return {
            "device_id": call.data[ATTR_DEVICE_ID],
            "camera_ref": target_ref,
            "retention_days": retention_days,
            "max_total_mb": max_total_mb,
            **cleanup,
        }

    registrations = (
        (SERVICE_PRIVATE_GET_SETTINGS, async_get_settings, _DEVICE_SCHEMA),
        (SERVICE_PRIVATE_GET_ARCHIVE_RANGES, async_get_ranges, _DEVICE_SCHEMA),
        (SERVICE_PRIVATE_GET_ARCHIVE_URL, async_get_url, _ARCHIVE_URL_SCHEMA),
        (
            SERVICE_PRIVATE_GET_ARCHIVE_DOWNLOAD_URL,
            async_export_archive,
            _ARCHIVE_EXPORT_SCHEMA,
        ),
        (SERVICE_PRIVATE_LIST_ARCHIVE_EXPORTS, async_list_exports, _DEVICE_SCHEMA),
        (
            SERVICE_PRIVATE_DELETE_ARCHIVE_EXPORT,
            async_delete_export,
            _DELETE_EXPORT_SCHEMA,
        ),
        (
            SERVICE_PRIVATE_CLEANUP_ARCHIVE_EXPORTS,
            async_cleanup_exports,
            _CLEANUP_EXPORTS_SCHEMA,
        ),
        (SERVICE_PRIVATE_GET_MOTION_EVENTS, async_get_motion_events, _DATE_SCHEMA),
        (SERVICE_PRIVATE_GET_CALL_EVENTS, async_get_call_events, _DATE_SCHEMA),
    )
    for service, handler, schema in registrations:
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schema,
            supports_response=SupportsResponse.ONLY,
        )
