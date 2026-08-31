"""Privacy-safe status and Repairs supervision for last-call images."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

FFMPEG_PROBE_TIMEOUT_SECONDS = 10
IMAGE_FAILURES_BEFORE_REPAIR = 3


@dataclass(slots=True)
class _ImageStatus:
    """Mutable status for one intercom image without media identifiers."""

    preview_available: bool = False
    preview_https_upgraded: bool = False
    preview_payload_kind: str | None = None
    retry_suppressed: bool = False
    ready: bool = False
    loading: bool = False
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error_code: str | None = None
    last_error_type: str | None = None


class UfanetLastCallImageStatusManager:
    """Track safe image health and maintain one auto-closing repair issue."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        skuds: Iterable[dict[str, Any]],
    ) -> None:
        self.hass = hass
        self._entry_id = entry.entry_id
        self._entry_title = entry.title
        self._issue_id = f"last_call_image_unavailable_{entry.entry_id}"
        self._issue_active = False
        self.ffmpeg_available: bool | None = None
        self._statuses = {
            int(skud["id"]): _ImageStatus()
            for skud in skuds
            if skud.get("id") is not None and skud.get("cctv_number")
        }

    async def async_initialize(self) -> None:
        """Probe ffmpeg once so diagnostics are useful before the first call."""
        if not self._statuses:
            return
        self.ffmpeg_available = await async_check_ffmpeg()
        self._update_repair_issue()

    def status(self, skud_id: int) -> dict[str, Any]:
        """Return token-free status for one intercom."""
        value = self._statuses.get(int(skud_id))
        if value is None:
            return {
                "configured": False,
                "ffmpeg_available": self.ffmpeg_available,
                "ready": False,
                "loading": False,
                "preview_available": False,
                "preview_https_upgraded": False,
                "preview_payload_kind": None,
                "retry_suppressed": False,
                "success_count": 0,
                "failure_count": 0,
                "consecutive_failures": 0,
                "last_success_at": None,
                "last_error_at": None,
                "last_error_code": None,
                "last_error_type": None,
                "repair_issue_active": self._issue_active,
            }
        return {
            "configured": True,
            "ffmpeg_available": self.ffmpeg_available,
            "ready": value.ready,
            "loading": value.loading,
            "preview_available": value.preview_available,
            "preview_https_upgraded": value.preview_https_upgraded,
            "preview_payload_kind": value.preview_payload_kind,
            "retry_suppressed": value.retry_suppressed,
            "success_count": value.success_count,
            "failure_count": value.failure_count,
            "consecutive_failures": value.consecutive_failures,
            "last_success_at": value.last_success_at,
            "last_error_at": value.last_error_at,
            "last_error_code": value.last_error_code,
            "last_error_type": value.last_error_type,
            "repair_issue_active": self._issue_active,
        }

    def summary(self) -> dict[str, Any]:
        """Return aggregate token-free status for config-entry diagnostics."""
        values = list(self._statuses.values())
        latest_error = max(
            (value for value in values if value.last_error_at),
            key=lambda value: str(value.last_error_at),
            default=None,
        )
        latest_success = max(
            (str(value.last_success_at) for value in values if value.last_success_at),
            default=None,
        )
        return {
            "configured": bool(values),
            "ffmpeg_available": self.ffmpeg_available,
            "camera_count": len(values),
            "ready_count": sum(value.ready for value in values),
            "loading_count": sum(value.loading for value in values),
            "preview_available_count": sum(value.preview_available for value in values),
            "preview_https_upgraded_count": sum(
                value.preview_https_upgraded for value in values
            ),
            "retry_suppressed_count": sum(value.retry_suppressed for value in values),
            "success_count": sum(value.success_count for value in values),
            "failure_count": sum(value.failure_count for value in values),
            "consecutive_failures": sum(value.consecutive_failures for value in values),
            "last_success_at": latest_success,
            "last_error_at": (
                latest_error.last_error_at if latest_error is not None else None
            ),
            "last_error_code": (
                latest_error.last_error_code if latest_error is not None else None
            ),
            "last_error_type": (
                latest_error.last_error_type if latest_error is not None else None
            ),
            "repair_issue_active": self._issue_active,
        }

    @callback
    def set_preview_available(self, skud_id: int, available: bool) -> None:
        """Record whether the latest internal event has a preview capability."""
        value = self._statuses.get(int(skud_id))
        if value is not None:
            value.preview_available = bool(available)
            if not available:
                value.preview_https_upgraded = False
                value.preview_payload_kind = None
                value.retry_suppressed = False

    @callback
    def set_preview_https_upgraded(self, skud_id: int, upgraded: bool) -> None:
        """Record only whether an HTTP URL was rewritten before any request."""
        value = self._statuses.get(int(skud_id))
        if value is not None:
            value.preview_https_upgraded = bool(upgraded)

    @callback
    def set_preview_payload_kind(self, skud_id: int, kind: str | None) -> None:
        """Record only a fixed media-signature class, never response data."""
        value = self._statuses.get(int(skud_id))
        if value is not None:
            value.preview_payload_kind = (
                kind
                if kind in {"jpeg", "png", "gif", "webm", "mp4", "mpeg_ts", "unknown"}
                else None
            )

    @callback
    def set_retry_suppressed(self, skud_id: int, suppressed: bool) -> None:
        """Record whether a permanent failure is suppressed for this call."""
        value = self._statuses.get(int(skud_id))
        if value is not None:
            value.retry_suppressed = bool(suppressed)

    @callback
    def mark_loading(self, skud_id: int) -> None:
        """Record an in-progress extraction."""
        value = self._statuses.get(int(skud_id))
        if value is not None:
            value.loading = True

    @callback
    def mark_cancelled(self, skud_id: int) -> None:
        """Clear an obsolete extraction without counting it as a failure."""
        value = self._statuses.get(int(skud_id))
        if value is not None:
            value.loading = False

    @callback
    def mark_success(self, skud_id: int) -> None:
        """Record a successful JPEG extraction and close recovered issues."""
        value = self._statuses.get(int(skud_id))
        if value is None:
            return
        value.ready = True
        value.loading = False
        value.success_count += 1
        value.consecutive_failures = 0
        value.retry_suppressed = False
        value.last_success_at = _now_iso()
        value.last_error_at = None
        value.last_error_code = None
        value.last_error_type = None
        self.ffmpeg_available = True
        self._update_repair_issue()

    @callback
    def mark_failure(
        self,
        skud_id: int,
        error_type: str,
        *,
        error_code: str,
        ffmpeg_available: bool | None = None,
    ) -> None:
        """Record a fixed reason code and type, never potentially private text."""
        value = self._statuses.get(int(skud_id))
        if value is None:
            return
        value.loading = False
        value.failure_count += 1
        value.consecutive_failures += 1
        value.last_error_at = _now_iso()
        value.last_error_code = str(error_code)
        value.last_error_type = str(error_type)
        if ffmpeg_available is not None:
            self.ffmpeg_available = ffmpeg_available
        self._update_repair_issue()

    @callback
    def stop(self) -> None:
        """Remove transient Repairs state when the config entry unloads."""
        if self._issue_active:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            self._issue_active = False

    @callback
    def _update_repair_issue(self) -> None:
        problem = self.ffmpeg_available is False or any(
            value.consecutive_failures >= IMAGE_FAILURES_BEFORE_REPAIR
            for value in self._statuses.values()
        )
        if problem and not self._issue_active:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id,
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="last_call_image_unavailable",
                translation_placeholders={"entry_title": self._entry_title},
                data={"entry_id": self._entry_id},
            )
            self._issue_active = True
        elif not problem and self._issue_active:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            self._issue_active = False


async def async_check_ffmpeg() -> bool:
    """Return whether a local ffmpeg executable answers a version probe."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        return False

    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=FFMPEG_PROBE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        return False
    return process.returncode == 0


def _now_iso() -> str:
    """Return a timezone-aware timestamp for diagnostics."""
    return datetime.now(timezone.utc).isoformat()
