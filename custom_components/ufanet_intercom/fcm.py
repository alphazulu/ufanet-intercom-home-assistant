"""Optional headless FCM receiver for low-latency intercom call refreshes."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timezone
import logging
from typing import Any
from uuid import uuid4

from firebase_messaging import FcmPushClient, FcmRegisterConfig

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import UfanetApi
from .firebase_config import firebase_config_fingerprint

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_PERSISTENT_IDS = 100
DEVICE_TITLE = "Home Assistant"
SIP_REFRESH_DELAYS_SECONDS = (0, 1, 4)


class UfanetFcmManager:
    """Own FCM registration, MCS listener and private persisted state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: UfanetApi,
        firebase_config: dict[str, str],
        on_sip_push: Callable[[], Awaitable[None]],
    ) -> None:
        self.hass = hass
        self.api = api
        self.firebase_config = firebase_config
        self._on_sip_push = on_sip_push
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"ufanet_intercom.fcm.{entry.entry_id}",
        )
        self._state: dict[str, Any] = {}
        self._client: FcmPushClient | None = None
        self._save_task: asyncio.Task[None] | None = None
        self._save_pending = False
        self._sip_tasks: set[asyncio.Task[None]] = set()

        self.active = False
        self.firebase_registration_succeeded = False
        self.ufanet_registration_succeeded = False
        self.listener_started = False
        self.last_error_type: str | None = None
        self.received_push_count = 0
        self.received_sip_push_count = 0
        self.last_push_at: str | None = None
        self.last_sip_push_at: str | None = None

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "fcm_credentials": None,
            "persistent_ids": [],
            "ufanet_device_id": f"{DEVICE_TITLE}_{uuid4()}",
            "ufanet_device_title": DEVICE_TITLE,
            "firebase_config_fingerprint": None,
        }

    async def async_start(self) -> bool:
        """Register the virtual device and start the MCS listener."""
        self.active = False
        self.firebase_registration_succeeded = False
        self.ufanet_registration_succeeded = False
        self.listener_started = False

        try:
            stored = await self._store.async_load()
        except Exception as err:  # optional state must not block the integration
            stored = None
            self.last_error_type = type(err).__name__
            _LOGGER.warning(
                "Unable to load optional Ufanet FCM state: %s",
                type(err).__name__,
            )
        self._state = stored if isinstance(stored, dict) else self._default_state()
        for key, value in self._default_state().items():
            self._state.setdefault(key, value)

        fingerprint = firebase_config_fingerprint(self.firebase_config)
        previous = self._state.get("firebase_config_fingerprint")
        if previous not in (None, fingerprint):
            self._state = self._default_state()
        self._state["firebase_config_fingerprint"] = fingerprint

        persistent_ids = self._state.get("persistent_ids")
        if not isinstance(persistent_ids, list):
            persistent_ids = []
            self._state["persistent_ids"] = persistent_ids

        try:
            config = FcmRegisterConfig(
                project_id=self.firebase_config["project_id"],
                app_id=self.firebase_config["app_id"],
                api_key=self.firebase_config["api_key"],
                messaging_sender_id=self.firebase_config["sender_id"],
                bundle_id=self.firebase_config["package_name"],
                persistend_ids=list(persistent_ids),
            )
            self._client = FcmPushClient(
                self._handle_push,
                config,
                credentials=self._state.get("fcm_credentials"),
                credentials_updated_callback=self._persist_credentials,
                received_persistent_ids=list(persistent_ids),
                http_client_session=async_get_clientsession(self.hass),
            )
            token = await self._client.checkin_or_register()
            self.firebase_registration_succeeded = True
            await self.api.async_register_fcm_device(
                token=token,
                device_id=str(self._state["ufanet_device_id"]),
                title=str(self._state["ufanet_device_title"]),
                application=self.firebase_config["package_name"],
            )
            self.ufanet_registration_succeeded = True
            await self._client.start()
            self.listener_started = True
        except Exception as err:  # optional transport must not break the intercom
            self.last_error_type = type(err).__name__
            _LOGGER.warning(
                "Unable to start optional Ufanet FCM receiver: %s",
                type(err).__name__,
            )
            if self._client is not None:
                await self._safe_stop_client()
            await self._async_save_state()
            return False

        self.active = True
        self.last_error_type = None
        await self._async_save_state()
        _LOGGER.info("Ufanet FCM receiver started; polling remains as a safety fallback")
        return True

    async def async_stop(self) -> None:
        """Stop the MCS listener and flush private state."""
        await self._safe_stop_client()
        self.active = False
        for task in self._sip_tasks:
            task.cancel()
        if self._sip_tasks:
            await asyncio.gather(*self._sip_tasks, return_exceptions=True)
        self._sip_tasks.clear()
        self._queue_save()
        if self._save_task is not None:
            await self._save_task

    async def _safe_stop_client(self) -> None:
        client = self._client
        self._client = None
        self.listener_started = False
        if client is None:
            return
        try:
            await client.stop()
        except Exception as err:  # unload must always complete
            _LOGGER.debug(
                "Unable to stop Ufanet FCM receiver cleanly: %s",
                type(err).__name__,
            )

    def _persist_credentials(self, credentials: dict[str, Any]) -> None:
        self._state["fcm_credentials"] = credentials
        self._queue_save()

    def _handle_push(
        self,
        notification: dict[str, Any],
        persistent_id: str,
        _context: Any,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.received_push_count += 1
        self.last_push_at = now

        persistent_ids = self._state.setdefault("persistent_ids", [])
        if isinstance(persistent_ids, list) and persistent_id:
            if persistent_id not in persistent_ids:
                persistent_ids.append(persistent_id)
            del persistent_ids[:-MAX_PERSISTENT_IDS]
        self._queue_save()

        data = notification.get("data") if isinstance(notification, dict) else None
        if not isinstance(data, dict) or data.get("reason") != "sip":
            return

        self.received_sip_push_count += 1
        self.last_sip_push_at = now
        task = self.hass.async_create_task(
            self._async_process_sip_push(),
            "ufanet_intercom_fcm_sip_refresh",
        )
        self._sip_tasks.add(task)
        task.add_done_callback(self._sip_tasks.discard)

    async def _async_process_sip_push(self) -> None:
        for delay in SIP_REFRESH_DELAYS_SECONDS:
            if delay:
                await asyncio.sleep(delay)
            try:
                await self._on_sip_push()
                self.last_error_type = None
            except Exception as err:  # callback failure must not kill MCS
                self.last_error_type = type(err).__name__
                _LOGGER.warning(
                    "Unable to refresh Ufanet call history after FCM push: %s",
                    type(err).__name__,
                )

    def _queue_save(self) -> None:
        self._save_pending = True
        if self._save_task is None or self._save_task.done():
            self._save_task = self.hass.async_create_task(
                self._async_save_loop(),
                "ufanet_intercom_fcm_state_save",
            )

    async def _async_save_loop(self) -> None:
        while self._save_pending:
            self._save_pending = False
            await self._async_save_state()

    async def _async_save_state(self) -> None:
        try:
            await self._store.async_save(deepcopy(self._state))
        except Exception as err:  # optional state must not block unload/setup
            self.last_error_type = type(err).__name__
            _LOGGER.warning(
                "Unable to save optional Ufanet FCM state: %s",
                type(err).__name__,
            )

    def status(self) -> dict[str, Any]:
        """Return token-free runtime state for diagnostics and the card."""
        run_state = getattr(self._client, "run_state", None)
        return {
            "configured": True,
            "active": self.active,
            "firebase_registration_succeeded": (
                self.firebase_registration_succeeded
            ),
            "ufanet_registration_succeeded": self.ufanet_registration_succeeded,
            "listener_started": self.listener_started,
            "transport_state": (
                getattr(run_state, "name", str(run_state))
                if run_state is not None
                else None
            ),
            "last_error_type": self.last_error_type,
            "received_push_count": self.received_push_count,
            "received_sip_push_count": self.received_sip_push_count,
            "last_push_at": self.last_push_at,
            "last_sip_push_at": self.last_sip_push_at,
        }
