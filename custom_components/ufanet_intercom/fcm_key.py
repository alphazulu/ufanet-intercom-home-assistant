"""Physical-key FCM handling layered on the base Ufanet FCM manager."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from .const import DOMAIN
from .fcm import UfanetFcmManager as BaseUfanetFcmManager

_LOGGER = logging.getLogger(__name__)

EVENT_KEY_ENROLLMENT = "ufanet_intercom_key_enrollment"
KEY_ADD_REASON = "key_add"


def _parse_optional_int(value: Any) -> int | None:
    """Parse an integer-like FCM field without accepting booleans."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class UfanetFcmManager(BaseUfanetFcmManager):
    """Extend the base FCM manager with physical-key enrollment completion."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.received_key_add_push_count = 0
        self.last_key_add_push_at: str | None = None
        self.last_key_add_result: str | None = None
        self._key_add_tasks: set[asyncio.Task[None]] = set()

    def _handle_push(
        self,
        notification: dict[str, Any],
        persistent_id: str,
        context: Any,
    ) -> None:
        """Handle base pushes plus native ``reason=key_add`` completion pushes."""
        super()._handle_push(notification, persistent_id, context)

        data = notification.get("data") if isinstance(notification, dict) else None
        if not isinstance(data, dict) or data.get("reason") != KEY_ADD_REASON:
            return

        received_at = datetime.now(timezone.utc).isoformat()
        self.received_key_add_push_count += 1
        self.last_key_add_push_at = received_at

        # Match the Android application exactly: an absent/unparseable status is
        # treated as 1 (error), and success additionally requires a key_id.
        status = _parse_optional_int(data.get("key_status"))
        if status is None:
            status = 1
        key_id = _parse_optional_int(data.get("key_id"))
        success = status == 0 and key_id is not None
        self.last_key_add_result = "success" if success else "error"

        # key_id/title/body are intentionally not retained, logged or published.
        task = self.hass.async_create_task(
            self._async_process_key_add_push(success, received_at),
            "ufanet_intercom_fcm_key_add_refresh",
        )
        self._key_add_tasks.add(task)
        task.add_done_callback(self._key_add_tasks.discard)

    async def _async_process_key_add_push(
        self,
        success: bool,
        received_at: str,
    ) -> None:
        """Refresh key inventory and publish a privacy-minimized HA event."""
        runtime = self.hass.data.get(DOMAIN, {}).get(self._entry_id)
        coordinator = (
            runtime.get("key_passage_coordinator")
            if isinstance(runtime, dict)
            else None
        )

        refresh_succeeded = False
        if coordinator is not None:
            try:
                await coordinator.async_request_refresh()
                refresh_succeeded = True
            except Exception as err:  # noqa: BLE001 - FCM worker must survive
                _LOGGER.warning(
                    "Unable to refresh physical-key inventory after key_add push: %s",
                    type(err).__name__,
                )

        self.hass.bus.async_fire(
            EVENT_KEY_ENROLLMENT,
            {
                "type": "key_enrollment",
                "source": "fcm",
                "result": "success" if success else "error",
                "received_at": received_at,
                "inventory_refresh_succeeded": refresh_succeeded,
            },
        )

    async def async_stop(self) -> None:
        """Cancel key-add workers before stopping the base FCM manager."""
        for task in self._key_add_tasks:
            task.cancel()
        if self._key_add_tasks:
            await asyncio.gather(*self._key_add_tasks, return_exceptions=True)
        self._key_add_tasks.clear()
        await super().async_stop()

    def status(self) -> dict[str, Any]:
        """Return base diagnostics plus privacy-safe key-add counters."""
        status = super().status()
        status.update(
            {
                "received_key_add_push_count": self.received_key_add_push_count,
                "last_key_add_push_at": self.last_key_add_push_at,
                "last_key_add_result": self.last_key_add_result,
            }
        )
        return status
