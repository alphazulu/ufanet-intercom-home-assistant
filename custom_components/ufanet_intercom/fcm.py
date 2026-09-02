"""Optional headless FCM receiver for low-latency intercom call refreshes."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from firebase_messaging import FcmPushClient, FcmRegisterConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import UfanetApi
from .const import DOMAIN
from .firebase_config import firebase_config_fingerprint

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_PERSISTENT_IDS = 100
DEVICE_TITLE = "Home Assistant"
SIP_REFRESH_DELAYS_SECONDS = (0, 1, 4)

FCM_HEALTHY_STATES = frozenset({"RUNNING", "STARTED"})
FCM_TERMINAL_STATES = frozenset({"STOPPING", "STOPPED"})
FCM_WATCHDOG_INTERVAL_SECONDS = 5
FCM_TRANSPORT_STALL_SECONDS = 180
FCM_REPAIR_AFTER_SECONDS = 120
FCM_RESTART_BASE_SECONDS = 5
FCM_RESTART_MAX_SECONDS = 300


def _authorized_device_age_bucket(
    value: Any,
    *,
    now: datetime | None = None,
) -> str:
    """Reduce an authorized-device timestamp to a privacy-safe age bucket."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid authorized-device timestamp")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("authorized-device timestamp has no timezone")

    current = now or datetime.now(timezone.utc)
    age_seconds = (
        current.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)
    ).total_seconds()
    if age_seconds < 0:
        return "future"
    if age_seconds <= 24 * 60 * 60:
        return "le_24h"
    if age_seconds <= 7 * 24 * 60 * 60:
        return "1_7d"
    if age_seconds <= 30 * 24 * 60 * 60:
        return "7_30d"
    if age_seconds <= 90 * 24 * 60 * 60:
        return "30_90d"
    return "gt_90d"


def _fcm_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, STORAGE_VERSION, f"ufanet_intercom.fcm.{entry_id}")


def _owned_device_id(state: Any) -> str | None:
    """Return only an integration-generated virtual device ID."""
    if not isinstance(state, dict):
        return None
    value = state.get("ufanet_device_id")
    prefix = f"{DEVICE_TITLE}_"
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    try:
        UUID(value.removeprefix(prefix))
    except ValueError:
        return None
    return value


def _unregister_issue_id(entry_id: str) -> str:
    return f"fcm_unregister_failed_{entry_id}"


def _create_unregister_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        _unregister_issue_id(entry.entry_id),
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="fcm_unregister_failed",
        translation_placeholders={"entry_title": entry.title or entry.entry_id},
        data={"entry_id": entry.entry_id},
    )


def _delete_unregister_issue(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(hass, DOMAIN, _unregister_issue_id(entry_id))


async def async_retry_pending_fcm_unregister(
    hass: HomeAssistant,
    entry: ConfigEntry,
    api: UfanetApi,
) -> bool:
    """Retry a failed FCM cleanup while polling mode remains operational."""
    store = _fcm_store(hass, entry.entry_id)
    try:
        state = await store.async_load()
    except Exception as err:  # noqa: BLE001 - optional cleanup must not block setup
        _LOGGER.warning(
            "Unable to load pending Ufanet FCM cleanup state: %s",
            type(err).__name__,
        )
        _create_unregister_issue(hass, entry)
        return True

    if not isinstance(state, dict) or state.get("unregister_pending") is not True:
        _delete_unregister_issue(hass, entry.entry_id)
        return False

    device_id = _owned_device_id(state)
    if device_id is None:
        _LOGGER.warning("Pending Ufanet FCM cleanup has no valid owned device ID")
        _create_unregister_issue(hass, entry)
        return True

    try:
        await api.async_unregister_fcm_device(device_id=device_id)
    except Exception as err:  # noqa: BLE001 - polling mode must still load
        _LOGGER.warning(
            "Unable to retry Ufanet FCM unregistration: %s",
            type(err).__name__,
        )
        _create_unregister_issue(hass, entry)
        return True

    try:
        await store.async_remove()
    except Exception as err:  # noqa: BLE001 - remote cleanup already succeeded
        _LOGGER.warning(
            "Unable to remove local Ufanet FCM state after unregistration: %s",
            type(err).__name__,
        )
    _delete_unregister_issue(hass, entry.entry_id)
    return False


async def async_remove_stored_fcm_registration(
    hass: HomeAssistant,
    entry: ConfigEntry,
    api: UfanetApi | None,
) -> None:
    """Best-effort remote and unconditional local cleanup on entry removal."""
    store = _fcm_store(hass, entry.entry_id)
    try:
        state = await store.async_load()
    except Exception as err:  # noqa: BLE001 - entry removal must finish
        state = None
        _LOGGER.warning(
            "Unable to load Ufanet FCM state during entry removal: %s",
            type(err).__name__,
        )

    device_id = _owned_device_id(state)
    if device_id is not None and api is not None:
        try:
            await api.async_unregister_fcm_device(device_id=device_id)
        except Exception as err:  # noqa: BLE001 - entry removal must finish
            _LOGGER.warning(
                "Unable to unregister Ufanet FCM device during entry removal: %s",
                type(err).__name__,
            )

    try:
        await store.async_remove()
    except Exception as err:  # noqa: BLE001 - entry removal must finish
        _LOGGER.warning(
            "Unable to remove local Ufanet FCM state during entry removal: %s",
            type(err).__name__,
        )
    for issue_id in (
        f"fcm_listener_unavailable_{entry.entry_id}",
        f"fcm_state_recovered_{entry.entry_id}",
        _unregister_issue_id(entry.entry_id),
    ):
        ir.async_delete_issue(hass, DOMAIN, issue_id)


class UfanetFcmManager:
    """Own FCM registration, MCS listener and private persisted state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: UfanetApi,
        firebase_config: dict[str, str],
        on_sip_push: Callable[[], Awaitable[None]],
        *,
        on_health_change: Callable[[bool], None] | None = None,
    ) -> None:
        self.hass = hass
        self.api = api
        self.firebase_config = firebase_config
        self._entry_id = entry.entry_id
        self._entry_title = entry.title or entry.entry_id
        self._issue_id = f"fcm_listener_unavailable_{entry.entry_id}"
        self._state_issue_id = f"fcm_state_recovered_{entry.entry_id}"
        self._on_sip_push = on_sip_push
        self._on_health_change = on_health_change
        self._entry = entry
        self._store = _fcm_store(hass, entry.entry_id)
        self._state: dict[str, Any] = {}
        self._client: FcmPushClient | None = None
        self._save_task: asyncio.Task[None] | None = None
        self._save_pending = False
        self._sip_tasks: set[asyncio.Task[None]] = set()
        self._watchdog_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._ever_connected = False
        self._unhealthy_since: float | None = None
        self._issue_active = False

        self.active = False
        self.firebase_registration_succeeded = False
        self.ufanet_registration_succeeded = False
        self.listener_started = False
        self.listener_running = False
        self.fallback_polling_active = True
        self.watchdog_running = False
        self.reconnect_count = 0
        self.consecutive_failures = 0
        self.last_error_type: str | None = None
        self.last_connected_at: str | None = None
        self.last_disconnected_at: str | None = None
        self.received_push_count = 0
        self.received_sip_push_count = 0
        self.last_push_at: str | None = None
        self.last_sip_push_at: str | None = None
        self.state_recovered = False
        self.state_recovery_reason: str | None = None
        self.unregister_pending = False
        self.last_unregistration_succeeded: bool | None = None
        self.last_unregistration_error_type: str | None = None
        self.authorized_device_check_succeeded = False
        self.authorized_device_registered: bool | None = None
        self.authorized_device_call_access: bool | None = None
        self.authorized_device_last_update_age: str | None = None
        self.authorized_device_check_error_type: str | None = None

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "fcm_credentials": None,
            "persistent_ids": [],
            "ufanet_device_id": f"{DEVICE_TITLE}_{uuid4()}",
            "ufanet_device_title": DEVICE_TITLE,
            "firebase_config_fingerprint": None,
            "unregister_pending": False,
        }

    @classmethod
    def _normalize_state(
        cls,
        stored: Any,
    ) -> tuple[dict[str, Any], str | None]:
        """Return a minimal valid private state and a privacy-safe recovery reason."""
        default = cls._default_state()
        if stored is None:
            return default, None
        if not isinstance(stored, dict):
            return default, "invalid_schema"

        invalid = False
        state = default

        credentials = stored.get("fcm_credentials")
        if credentials is None or isinstance(credentials, dict):
            state["fcm_credentials"] = credentials
        else:
            invalid = True

        persistent_ids = stored.get("persistent_ids")
        if isinstance(persistent_ids, list) and all(
            isinstance(value, str) for value in persistent_ids
        ):
            state["persistent_ids"] = persistent_ids[-MAX_PERSISTENT_IDS:]
        else:
            invalid = True

        title = stored.get("ufanet_device_title")
        if isinstance(title, str) and title.strip():
            state["ufanet_device_title"] = title
        else:
            invalid = True

        device_id = _owned_device_id(stored)
        if device_id is not None:
            state["ufanet_device_id"] = device_id
        else:
            invalid = True

        fingerprint = stored.get("firebase_config_fingerprint")
        if fingerprint is None or isinstance(fingerprint, str):
            state["firebase_config_fingerprint"] = fingerprint
        else:
            invalid = True

        unregister_pending = stored.get("unregister_pending", False)
        if isinstance(unregister_pending, bool):
            state["unregister_pending"] = unregister_pending
        else:
            invalid = True

        return state, "invalid_schema" if invalid else None

    async def async_start(self) -> bool:
        """Start FCM and keep supervising the optional transport."""
        self._stopping = False
        self.active = False
        self.listener_running = False
        self.fallback_polling_active = True
        self._unhealthy_since = time.monotonic()

        load_failed = False
        try:
            stored = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - optional state must not block setup
            stored = None
            load_failed = True
            _LOGGER.warning(
                "Unable to load optional Ufanet FCM state: %s",
                type(err).__name__,
            )
        self._state, recovery_reason = self._normalize_state(stored)
        if load_failed:
            recovery_reason = "load_error"

        fingerprint = firebase_config_fingerprint(self.firebase_config)
        previous = self._state.get("firebase_config_fingerprint")
        if previous not in (None, fingerprint):
            owned_device_id = _owned_device_id(self._state)
            self._state = self._default_state()
            if owned_device_id is not None:
                # The virtual Ufanet installation is independent from Firebase
                # credentials. Reuse its validated ID so the restoring POST
                # replaces the old token instead of leaving an orphaned device.
                self._state["ufanet_device_id"] = owned_device_id
            recovery_reason = "firebase_identity_changed"
        self._state["firebase_config_fingerprint"] = fingerprint

        self.state_recovered = recovery_reason is not None
        self.state_recovery_reason = recovery_reason
        self.unregister_pending = bool(self._state.get("unregister_pending"))
        if self.state_recovered:
            self._create_state_recovery_issue()
        else:
            self._delete_state_recovery_issue()

        started = await self._async_attempt_start()
        await self._async_evaluate_transport()
        self.watchdog_running = True
        self._watchdog_task = self.hass.async_create_background_task(
            self._async_watchdog_loop(),
            "ufanet_intercom_fcm_watchdog",
        )
        return started

    async def _async_attempt_start(self) -> bool:
        """Register a fresh client and launch its listener tasks once."""
        self.firebase_registration_succeeded = False
        self.ufanet_registration_succeeded = False
        self.listener_started = False
        self.authorized_device_check_succeeded = False
        self.authorized_device_registered = None
        self.authorized_device_call_access = None
        self.authorized_device_last_update_age = None
        self.authorized_device_check_error_type = None

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
            self.unregister_pending = False
            self._state["unregister_pending"] = False
            self.last_unregistration_succeeded = None
            self.last_unregistration_error_type = None
            _delete_unregister_issue(self.hass, self._entry_id)
            await self._client.start()
            self.listener_started = True
            await self._async_refresh_authorized_device_status()
        except Exception as err:  # noqa: BLE001 - optional transport is isolated
            self.last_error_type = type(err).__name__
            self.consecutive_failures += 1
            _LOGGER.warning(
                "Unable to start optional Ufanet FCM receiver: %s",
                type(err).__name__,
            )
            await self._safe_stop_client()
            await self._async_save_state()
            return False

        await self._async_save_state()
        _LOGGER.info(
            "Ufanet FCM listener tasks started; polling remains active until transport login"
        )
        return True

    async def _async_watchdog_loop(self) -> None:
        """Monitor the MCS listener and recreate it after terminal failures."""
        try:
            while not self._stopping:
                await asyncio.sleep(FCM_WATCHDOG_INTERVAL_SECONDS)
                try:
                    await self._async_watchdog_iteration()
                except Exception as err:  # noqa: BLE001 - watchdog must survive
                    self.last_error_type = type(err).__name__
                    _LOGGER.exception("Unexpected error in Ufanet FCM watchdog")
        finally:
            self.watchdog_running = False

    async def _async_watchdog_iteration(self) -> None:
        """Run one testable supervisor iteration."""
        if self._stopping:
            return

        healthy = await self._async_evaluate_transport()
        if healthy:
            return

        now = time.monotonic()
        unhealthy_for = now - (self._unhealthy_since or now)
        if unhealthy_for >= FCM_REPAIR_AFTER_SECONDS:
            self._create_repair_issue()

        state = self._transport_state()
        terminal = self._client is None or state in FCM_TERMINAL_STATES
        stalled = self.listener_started and unhealthy_for >= FCM_TRANSPORT_STALL_SECONDS
        if not terminal and not stalled:
            return

        delay = min(
            FCM_RESTART_BASE_SECONDS
            * (2 ** min(max(0, self.consecutive_failures - 1), 16)),
            FCM_RESTART_MAX_SECONDS,
        )
        _LOGGER.warning(
            "Ufanet FCM transport unavailable (%s); restarting in %s seconds",
            state or "not started",
            delay,
        )
        await self._safe_stop_client()
        await asyncio.sleep(delay)
        if self._stopping:
            return
        await self._async_attempt_start()
        await self._async_evaluate_transport()

    async def _async_evaluate_transport(self) -> bool:
        """Update health state from the client's actual MCS run state."""
        healthy = (
            self.listener_started and self._transport_state() in FCM_HEALTHY_STATES
        )
        if healthy == self.listener_running:
            if not healthy and self._unhealthy_since is None:
                self._unhealthy_since = time.monotonic()
            return healthy

        now = datetime.now(timezone.utc).isoformat()
        if healthy:
            if self._ever_connected:
                self.reconnect_count += 1
            self._ever_connected = True
            self.last_connected_at = now
            self.last_error_type = None
            self.consecutive_failures = 0
            self._unhealthy_since = None
            self._delete_repair_issue()
            _LOGGER.info("Ufanet FCM transport is connected")
        else:
            if self.listener_running:
                self.last_disconnected_at = now
            self._unhealthy_since = time.monotonic()
            _LOGGER.warning(
                "Ufanet FCM transport disconnected; normal call-history polling restored"
            )

        self.listener_running = healthy
        self.active = healthy
        self.fallback_polling_active = not healthy
        if self._on_health_change is not None:
            try:
                self._on_health_change(healthy)
            except Exception as err:  # noqa: BLE001 - keep supervision alive
                _LOGGER.warning(
                    "Unable to apply Ufanet FCM health transition: %s",
                    type(err).__name__,
                )
        return healthy

    async def async_stop(self) -> None:
        """Stop the MCS listener, watchdog and flush private state."""
        self._stopping = True
        watchdog = self._watchdog_task
        self._watchdog_task = None
        if watchdog is not None:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)
        self.watchdog_running = False

        await self._safe_stop_client()
        self.active = False
        self.listener_running = False
        self.fallback_polling_active = False
        self._delete_repair_issue()
        for task in self._sip_tasks:
            task.cancel()
        if self._sip_tasks:
            await asyncio.gather(*self._sip_tasks, return_exceptions=True)
        self._sip_tasks.clear()
        self._queue_save()
        if self._save_task is not None:
            await self._save_task

    async def async_unregister(self) -> bool:
        """Remove this manager's owned registration after FCM is disabled."""
        self.unregister_pending = True
        self._state["unregister_pending"] = True
        await self._async_save_state()
        device_id = _owned_device_id(self._state)
        if device_id is None:
            self.last_unregistration_succeeded = False
            self.last_unregistration_error_type = "InvalidOwnedDeviceId"
            _create_unregister_issue(self.hass, self._entry)
            return False

        try:
            await self.api.async_unregister_fcm_device(device_id=device_id)
        except Exception as err:  # noqa: BLE001 - polling fallback must load
            self.last_unregistration_succeeded = False
            self.last_unregistration_error_type = type(err).__name__
            _LOGGER.warning(
                "Unable to unregister disabled Ufanet FCM device: %s",
                type(err).__name__,
            )
            _create_unregister_issue(self.hass, self._entry)
            return False

        self.unregister_pending = False
        self.last_unregistration_succeeded = True
        self.last_unregistration_error_type = None
        self._state["unregister_pending"] = False
        try:
            await self._store.async_remove()
        except Exception as err:  # noqa: BLE001 - remote cleanup already succeeded
            _LOGGER.warning(
                "Unable to remove local Ufanet FCM state after unregistration: %s",
                type(err).__name__,
            )
        _delete_unregister_issue(self.hass, self._entry_id)
        return True

    async def _async_refresh_authorized_device_status(self) -> None:
        """Verify this manager's owned Ufanet registration without exposing its ID."""
        self.authorized_device_check_succeeded = False
        self.authorized_device_registered = None
        self.authorized_device_call_access = None
        self.authorized_device_last_update_age = None
        self.authorized_device_check_error_type = None

        device_id = _owned_device_id(self._state)
        if device_id is None:
            self.authorized_device_check_error_type = "InvalidOwnedDeviceId"
            return

        try:
            status = await self.api.async_get_fcm_authorization_status(
                device_id=device_id
            )
            if status is None:
                self.authorized_device_registered = False
                self.authorized_device_check_succeeded = True
                return

            self.authorized_device_registered = True
            self.authorized_device_call_access = bool(status["call_access"])
            self.authorized_device_last_update_age = _authorized_device_age_bucket(
                status["last_update"]
            )
            self.authorized_device_check_succeeded = True
        except Exception as err:  # noqa: BLE001 - verification must not block FCM
            self.authorized_device_check_error_type = type(err).__name__
            _LOGGER.warning(
                "Unable to verify Ufanet FCM authorization: %s",
                type(err).__name__,
            )

    async def _safe_stop_client(self) -> None:
        client = self._client
        self._client = None
        self.listener_started = False
        if client is None:
            return
        try:
            await client.stop()
        except Exception as err:  # noqa: BLE001 - unload must always complete
            _LOGGER.debug(
                "Unable to stop Ufanet FCM receiver cleanly: %s",
                type(err).__name__,
            )

    def _transport_state(self) -> str | None:
        run_state = getattr(self._client, "run_state", None)
        if run_state is None:
            return None
        return str(getattr(run_state, "name", run_state))

    def _create_repair_issue(self) -> None:
        if self._issue_active:
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="fcm_listener_unavailable",
            translation_placeholders={"entry_title": self._entry_title},
            data={"entry_id": self._entry_id},
        )
        self._issue_active = True

    def _delete_repair_issue(self) -> None:
        if not self._issue_active:
            return
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        self._issue_active = False

    def _create_state_recovery_issue(self) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._state_issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="fcm_state_recovered",
            translation_placeholders={"entry_title": self._entry_title},
            data={"entry_id": self._entry_id},
        )

    def _delete_state_recovery_issue(self) -> None:
        ir.async_delete_issue(self.hass, DOMAIN, self._state_issue_id)

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
            except Exception as err:  # noqa: BLE001 - callback must not kill MCS
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
        except Exception as err:  # noqa: BLE001 - persistence is optional
            self.last_error_type = type(err).__name__
            _LOGGER.warning(
                "Unable to save optional Ufanet FCM state: %s",
                type(err).__name__,
            )

    def status(self) -> dict[str, Any]:
        """Return token-free runtime state for diagnostics and the card."""
        return {
            "configured": True,
            "active": self.active,
            "firebase_registration_succeeded": (self.firebase_registration_succeeded),
            "ufanet_registration_succeeded": self.ufanet_registration_succeeded,
            "authorized_device_check_succeeded": (
                self.authorized_device_check_succeeded
            ),
            "authorized_device_registered": self.authorized_device_registered,
            "authorized_device_call_access": self.authorized_device_call_access,
            "authorized_device_last_update_age": (
                self.authorized_device_last_update_age
            ),
            "authorized_device_check_error_type": (
                self.authorized_device_check_error_type
            ),
            "listener_started": self.listener_started,
            "listener_running": self.listener_running,
            "fallback_polling_active": self.fallback_polling_active,
            "watchdog_running": self.watchdog_running,
            "transport_state": self._transport_state(),
            "reconnect_count": self.reconnect_count,
            "consecutive_failures": self.consecutive_failures,
            "last_connected_at": self.last_connected_at,
            "last_disconnected_at": self.last_disconnected_at,
            "last_error_type": self.last_error_type,
            "received_push_count": self.received_push_count,
            "received_sip_push_count": self.received_sip_push_count,
            "last_push_at": self.last_push_at,
            "last_sip_push_at": self.last_sip_push_at,
            "state_recovered": self.state_recovered,
            "state_recovery_reason": self.state_recovery_reason,
            "unregister_pending": self.unregister_pending,
            "last_unregistration_succeeded": self.last_unregistration_succeeded,
            "last_unregistration_error_type": self.last_unregistration_error_type,
        }
