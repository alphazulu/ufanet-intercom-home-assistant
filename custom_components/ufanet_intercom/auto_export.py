"""Automatic archive export around new intercom calls."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CALL_AUTOSAVE_RECOVERY_WINDOW_SECONDS,
    CALL_AUTOSAVE_RETRIES,
    CALL_AUTOSAVE_RETRY_SECONDS,
    CALL_AUTOSAVE_SETTLE_SECONDS,
    CONF_CALL_AUTOSAVE_AFTER_SECONDS,
    CONF_CALL_AUTOSAVE_ENABLED,
    CONF_CALL_LEAD_SECONDS,
    DEFAULT_CALL_AUTOSAVE_AFTER_SECONDS,
    DEFAULT_CALL_AUTOSAVE_ENABLED,
    DEFAULT_CALL_LEAD_SECONDS,
    DOMAIN,
    SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
)

_LOGGER = logging.getLogger(__name__)


def _call_datetime(call: dict[str, Any]) -> datetime | None:
    value = call.get("called_at")
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_ref(uuid: str) -> str:
    return hashlib.sha256(uuid.encode("utf-8")).hexdigest()[:12]


class UfanetCallAutoSaveManager:
    """Schedule ffmpeg exports after the post-call archive window exists."""

    def __init__(
        self,
        hass: HomeAssistant,
        options: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.enabled = bool(
            options.get(CONF_CALL_AUTOSAVE_ENABLED, DEFAULT_CALL_AUTOSAVE_ENABLED)
        )
        self.lead_seconds = int(
            options.get(CONF_CALL_LEAD_SECONDS, DEFAULT_CALL_LEAD_SECONDS)
        )
        self.after_seconds = int(
            options.get(
                CONF_CALL_AUTOSAVE_AFTER_SECONDS,
                DEFAULT_CALL_AUTOSAVE_AFTER_SECONDS,
            )
        )

        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._scheduled: set[str] = set()

        self.scheduled_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.skipped_count = 0

        self.last_call_at: str | None = None
        self.last_export_at: str | None = None
        self.last_filename: str | None = None
        self.last_error_type: str | None = None
        self.last_error_message: str | None = None
        self.last_result_existing: bool | None = None

    def schedule(
        self,
        call: dict[str, Any],
        device_id: str | None,
        *,
        recovery: bool = False,
    ) -> bool:
        """Schedule one call export without blocking the coordinator listener."""
        if not self.enabled or not device_id:
            return False

        uuid = str(call.get("uuid") or "")
        called_at = _call_datetime(call)
        if not uuid or called_at is None:
            self.skipped_count += 1
            return False

        ref = _event_ref(uuid)
        if ref in self._scheduled or ref in self._tasks:
            return False

        if recovery:
            age = (datetime.now(timezone.utc) - called_at).total_seconds()
            if age < 0 or age > CALL_AUTOSAVE_RECOVERY_WINDOW_SECONDS:
                return False

        self._scheduled.add(ref)
        self.scheduled_count += 1
        self.last_call_at = called_at.isoformat()

        task = self.hass.async_create_task(
            self._async_export(call, device_id, ref),
            f"{DOMAIN}_autosave_{ref}",
        )
        self._tasks[ref] = task

        def _done(_task: asyncio.Task[Any], key: str = ref) -> None:
            self._tasks.pop(key, None)
            self._scheduled.discard(key)

        task.add_done_callback(_done)
        return True

    async def _async_export(
        self,
        call: dict[str, Any],
        device_id: str,
        ref: str,
    ) -> None:
        uuid = str(call["uuid"])
        called_at = _call_datetime(call)
        if called_at is None:
            self.skipped_count += 1
            return

        target_ready = (
            called_at.timestamp()
            + self.after_seconds
            + CALL_AUTOSAVE_SETTLE_SECONDS
        )
        delay = max(0.0, target_ready - datetime.now(timezone.utc).timestamp())
        if delay > 0:
            await asyncio.sleep(delay)

        start = called_at.timestamp() - self.lead_seconds
        duration = max(1, self.lead_seconds + self.after_seconds)

        last_error: Exception | None = None
        for attempt in range(1, CALL_AUTOSAVE_RETRIES + 1):
            try:
                response = await self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
                    {
                        "device_id": device_id,
                        "start": datetime.fromtimestamp(start, tz=timezone.utc),
                        "duration": duration,
                        "source": "call",
                        "event_id": uuid,
                    },
                    blocking=True,
                    return_response=True,
                )

                self.success_count += 1
                self.last_export_at = datetime.now(timezone.utc).isoformat()
                self.last_filename = (
                    str(response.get("filename")) if isinstance(response, dict)
                    and response.get("filename") else None
                )
                self.last_result_existing = (
                    bool(response.get("existing")) if isinstance(response, dict)
                    else None
                )
                self.last_error_type = None
                self.last_error_message = None
                _LOGGER.info(
                    "Auto-saved Ufanet call %s to %s",
                    ref,
                    self.last_filename or "Home Assistant Media",
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as err:  # service errors are intentionally retried
                last_error = err
                _LOGGER.warning(
                    "Ufanet call auto-save attempt %s/%s failed for %s: %s",
                    attempt,
                    CALL_AUTOSAVE_RETRIES,
                    ref,
                    err,
                )
                if attempt < CALL_AUTOSAVE_RETRIES:
                    await asyncio.sleep(CALL_AUTOSAVE_RETRY_SECONDS)

        self.failure_count += 1
        self.last_error_type = type(last_error).__name__ if last_error else "Unknown"
        message = str(last_error or "Unknown auto-save failure")
        self.last_error_message = message[-500:]
        _LOGGER.error("Ufanet call auto-save failed for %s", ref)

    def cancel_all(self) -> None:
        """Cancel pending exports during config-entry unload."""
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    def status(self, *, include_details: bool = True) -> dict[str, Any]:
        """Return runtime state; sensitive cloud tokens are never included."""
        data: dict[str, Any] = {
            "enabled": self.enabled,
            "lead_seconds": self.lead_seconds,
            "after_seconds": self.after_seconds,
            "settle_seconds": CALL_AUTOSAVE_SETTLE_SECONDS,
            "pending_count": len(self._tasks),
            "scheduled_count": self.scheduled_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "skipped_count": self.skipped_count,
            "last_call_at": self.last_call_at,
            "last_export_at": self.last_export_at,
            "last_result_existing": self.last_result_existing,
            "last_error_type": self.last_error_type,
        }
        if include_details:
            data["last_filename"] = self.last_filename
            data["last_error_message"] = self.last_error_message
        return data
