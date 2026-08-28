"""Persistent local storage for generated Ufanet guest invites."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1
STORAGE_KEY = "ufanet_intercom.guest_invites"
MAX_STORED_INVITES = 200


class UfanetGuestInviteStore:
    """Persist invitation URLs that the Ufanet API cannot list afterwards."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._invites: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """Load persisted invitations."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            self._invites = []
            return

        invites = data.get("invites", [])
        if not isinstance(invites, list):
            self._invites = []
            return

        self._invites = [
            item
            for item in invites
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("url"), str)
        ]

    async def async_add(
        self,
        *,
        device_id: str,
        skud_id: int,
        url: str,
        access_id: Any = None,
    ) -> dict[str, Any]:
        """Store a generated invitation, deduplicating by URL."""
        for item in self._invites:
            if item.get("url") == url:
                return dict(item)

        invite = {
            "id": uuid4().hex,
            "device_id": device_id,
            "skud_id": int(skud_id),
            "url": url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "access_id": access_id,
            "source": "local_generated",
        }
        self._invites.insert(0, invite)
        self._invites = self._invites[:MAX_STORED_INVITES]
        await self._async_save()
        return dict(invite)

    def list_for(self, *, device_id: str, skud_id: int) -> list[dict[str, Any]]:
        """Return locally stored invitations for one HA/Ufanet device."""
        result = [
            dict(item)
            for item in self._invites
            if item.get("device_id") == device_id
            and int(item.get("skud_id", -1)) == int(skud_id)
        ]
        result.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return result

    async def async_remove(
        self,
        *,
        device_id: str,
        skud_id: int,
        invite_id: str,
    ) -> bool:
        """Forget one local record. This does NOT revoke it on Ufanet."""
        before = len(self._invites)
        self._invites = [
            item
            for item in self._invites
            if not (
                item.get("device_id") == device_id
                and int(item.get("skud_id", -1)) == int(skud_id)
                and item.get("id") == invite_id
            )
        ]
        changed = len(self._invites) != before
        if changed:
            await self._async_save()
        return changed

    async def _async_save(self) -> None:
        await self._store.async_save({"invites": self._invites})
