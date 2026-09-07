"""Resilient physical-key capability, inventory and passage coordination."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import KeyPassagePage, UfanetApiError, UfanetAuthError
from .coordinator import (
    UfanetKeyPassageCoordinator as BaseUfanetKeyPassageCoordinator,
    _advance_passage_cursor,
    _serialize_passage_cursors,
)


class UfanetKeyPassageCoordinator(BaseUfanetKeyPassageCoordinator):
    """Keep key capability/inventory usable when passage history is unavailable.

    Physical-key capability, account key inventory and passage history are three
    separate provider contracts. A failure of optional passage history must not
    turn a previously/just-confirmed key-capable intercom into an unsupported one.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.supported_skud_ids: set[int] = set()
        self.capability_known = False
        self.last_capability_error_type: str | None = None
        self.last_inventory_error_type: str | None = None
        self.last_history_error_type: str | None = None
        self.history_failure_count = 0

    def supports_skud(self, skud_id: int) -> bool:
        """Return a positive capability only after provider discovery succeeded."""
        return self.capability_known and int(skud_id) in self.supported_skud_ids

    async def _async_update_data(self) -> dict[int, dict[str, int | None | bool]]:
        """Refresh capability and inventory; treat passage history as best effort."""
        self.new_passages = {}

        # Capability discovery is authoritative. Preserve the last known set if
        # this request fails so a transient outage cannot erase known support.
        try:
            discovered = await self.api.async_get_key_recording_intercom_ids()
        except UfanetAuthError as err:
            self.last_capability_error_type = type(err).__name__
            raise ConfigEntryAuthFailed from err
        except UfanetApiError as err:
            self.last_capability_error_type = type(err).__name__
            raise UpdateFailed("Unable to refresh physical-key capability") from err

        self.last_capability_error_type = None
        self.capability_known = True
        self.supported_skud_ids = set(discovered) & self.skud_ids
        if not self.supported_skud_ids:
            self.last_inventory_error_type = None
            self.last_history_error_type = None
            self.history_failure_count = 0
            return {}

        ordered_ids = sorted(self.supported_skud_ids)

        # Key inventory is required for key count/list/rename and therefore is
        # still a coordinator-level failure. Capability remains independently
        # known even when inventory is temporarily unavailable.
        try:
            keys_result = await self.api.async_get_physical_keys()
        except UfanetAuthError as err:
            self.last_inventory_error_type = type(err).__name__
            raise ConfigEntryAuthFailed from err
        except UfanetApiError as err:
            self.last_inventory_error_type = type(err).__name__
            raise UpdateFailed("Unable to refresh physical-key inventory") from err
        self.last_inventory_error_type = None

        key_counts = dict.fromkeys(ordered_ids, 0)
        for key in keys_result:
            for skud_id in set(key["devices"]):
                if skud_id in key_counts:
                    key_counts[skud_id] += 1

        history_results = await asyncio.gather(
            *(self.api.async_get_key_passage_history(skud_id) for skud_id in ordered_ids),
            return_exceptions=True,
        )

        previous_cursors = dict(self._cursors)
        previous_data = self.data if isinstance(self.data, dict) else {}
        data: dict[int, dict[str, int | None | bool]] = {}
        first_history_error_type: str | None = None
        history_failure_count = 0

        for skud_id, result in zip(ordered_ids, history_results, strict=True):
            if isinstance(result, UfanetAuthError):
                self.last_history_error_type = type(result).__name__
                self.history_failure_count = 1
                raise ConfigEntryAuthFailed from result
            if isinstance(result, UfanetApiError):
                history_failure_count += 1
                if first_history_error_type is None:
                    first_history_error_type = type(result).__name__
                previous = previous_data.get(skud_id, {})
                data[skud_id] = {
                    "key_count": key_counts[skud_id],
                    "last_passage_at": previous.get("last_passage_at"),
                    "history_healthy": False,
                }
                continue
            if isinstance(result, BaseException):
                # Unexpected programming/runtime failures should remain visible
                # rather than being silently converted into provider health.
                raise result

            page: KeyPassagePage = result
            passages = page["results"]
            cursor, new_passages = _advance_passage_cursor(
                self._cursors.get(skud_id), passages
            )
            self._cursors[skud_id] = cursor
            if new_passages:
                self.new_passages[skud_id] = [
                    {
                        "key_name": passage["key_name"],
                        "occurred_at": datetime.fromtimestamp(
                            passage["timestamp"], tz=timezone.utc
                        ).isoformat(),
                    }
                    for passage in new_passages
                ]
            data[skud_id] = {
                "key_count": key_counts[skud_id],
                "last_passage_at": max(
                    (passage["timestamp"] for passage in passages), default=None
                ),
                "history_healthy": True,
            }

        self.last_history_error_type = first_history_error_type
        self.history_failure_count = history_failure_count

        if self._cursors != previous_cursors:
            try:
                await self._store.async_save(_serialize_passage_cursors(self._cursors))
            except Exception as err:
                self.new_passages = {}
                self._cursors = previous_cursors
                self.last_history_error_type = type(err).__name__
                raise UpdateFailed("Unable to save key-passage cursor state") from err

        return data

    def diagnostic_summary(self) -> dict[str, int | bool | str | None]:
        """Extend aggregate diagnostics with privacy-safe stage health."""
        summary = dict(super().diagnostic_summary())
        summary.update(
            {
                "capability_known": self.capability_known,
                "known_supported_intercom_count": len(self.supported_skud_ids),
                "capability_error_type": self.last_capability_error_type,
                "inventory_error_type": self.last_inventory_error_type,
                "history_error_type": self.last_history_error_type,
                "history_failure_count": self.history_failure_count,
            }
        )
        return summary
