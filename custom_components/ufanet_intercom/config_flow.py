"""Config flow for Ufanet Intercom."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import UfanetApi, UfanetAuthError, UfanetConnectionError, UfanetResponseError
from .const import (
    CALL_UPDATE_MODE_FCM,
    CALL_UPDATE_MODE_POLLING,
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
    CONF_FCM_CONFIG_PATH,
    CONF_MEDIA_REFRESH_INTERVAL,
    CONF_PASSWORD,
    CONF_SKUD_SCAN_INTERVAL,
    CONF_USERNAME,
    DOMAIN,
    MAX_CALL_SCAN_INTERVAL_SECONDS,
    MAX_CALL_AUTOSAVE_AFTER_SECONDS,
    MAX_EXPORT_RETENTION_DAYS,
    MAX_EXPORT_TOTAL_MB,
    MAX_MEDIA_REFRESH_SECONDS,
    MAX_SKUD_SCAN_INTERVAL_SECONDS,
    MIN_CALL_SCAN_INTERVAL_SECONDS,
    MIN_MEDIA_REFRESH_SECONDS,
    MIN_SKUD_SCAN_INTERVAL_SECONDS,
)
from .firebase_config import (
    UfanetFirebaseConfigError,
    async_load_firebase_config,
)
from .options import DEFAULT_OPTIONS

_LOGGER = logging.getLogger(__name__)


class UfanetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ufanet Intercom."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip().upper()
            password = str(user_input[CONF_PASSWORD])
            result = await self._async_validate(username, password)
            if result is None:
                await self.async_set_unique_id(username.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=username,
                    data={CONF_USERNAME: username, CONF_PASSWORD: password},
                )
            errors["base"] = result

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Confirm new credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        username = str(entry.data[CONF_USERNAME])

        if user_input is not None:
            password = str(user_input[CONF_PASSWORD])
            result = await self._async_validate(username, password)
            if result is None:
                # Home Assistant owns the reauth entry context. Updating through
                # this helper avoids relying on private/read-only flow fields and
                # reloads the integration with the new credentials.
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: password},
                )
            errors["base"] = result

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"username": username},
        )

    async def _async_validate(self, username: str, password: str) -> str | None:
        api = UfanetApi(async_get_clientsession(self.hass), username, password)
        try:
            await api.async_login()
            await api.async_get_skuds()
        except UfanetAuthError:
            return "invalid_auth"
        except UfanetConnectionError:
            return "cannot_connect"
        except UfanetResponseError as err:
            _LOGGER.debug("Ufanet validation response error: %s", err)
            return "unknown"
        except Exception:  # noqa: BLE001 - config flow must not crash on unexpected API changes
            _LOGGER.exception("Unexpected error validating Ufanet credentials")
            return "unknown"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the Ufanet options flow."""
        return UfanetOptionsFlow()


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SKUD_SCAN_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_SKUD_SCAN_INTERVAL_SECONDS,
                max=MAX_SKUD_SCAN_INTERVAL_SECONDS,
            ),
        ),
        vol.Required(CONF_CALL_SCAN_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_CALL_SCAN_INTERVAL_SECONDS,
                max=MAX_CALL_SCAN_INTERVAL_SECONDS,
            ),
        ),
        vol.Required(CONF_CALL_UPDATE_MODE): vol.In(
            [CALL_UPDATE_MODE_POLLING, CALL_UPDATE_MODE_FCM]
        ),
        vol.Required(CONF_MEDIA_REFRESH_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_MEDIA_REFRESH_SECONDS,
                max=MAX_MEDIA_REFRESH_SECONDS,
            ),
        ),
        vol.Required(CONF_CALL_LEAD_SECONDS): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=60),
        ),
        vol.Required(CONF_CALL_AUTOSAVE_ENABLED): bool,
        vol.Required(CONF_CALL_AUTOSAVE_AFTER_SECONDS): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_CALL_AUTOSAVE_AFTER_SECONDS),
        ),
        vol.Required(CONF_ARCHIVE_DEFAULT_DURATION): vol.All(
            vol.Coerce(int),
            vol.Range(min=30, max=3600),
        ),
        vol.Required(CONF_ARCHIVE_DEFAULT_STEP): vol.In(
            [10, 30, 60, 120, 300, 600, 1800, 3600]
        ),
        vol.Required(CONF_EXPORT_DEFAULT_DURATION): vol.In(
            [30, 60, 120, 300, 600, 1800]
        ),
        vol.Required(CONF_EXPORT_RETENTION_DAYS): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_RETENTION_DAYS),
        ),
        vol.Required(CONF_EXPORT_MAX_TOTAL_MB): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_EXPORT_TOTAL_MB),
        ),
        vol.Required(CONF_EXPORT_AUTO_CLEANUP): bool,
    }
)


class UfanetOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage optional Ufanet runtime and archive settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show and save integration options."""
        if user_input is not None:
            pending = dict(user_input)
            pending[CONF_FCM_CONFIG_PATH] = self.config_entry.options.get(
                CONF_FCM_CONFIG_PATH,
                DEFAULT_OPTIONS[CONF_FCM_CONFIG_PATH],
            )
            if pending[CONF_CALL_UPDATE_MODE] == CALL_UPDATE_MODE_FCM:
                self._pending_options = pending
                return await self.async_step_fcm()
            return self.async_create_entry(title="", data=pending)

        suggested = {**DEFAULT_OPTIONS, **dict(self.config_entry.options)}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,
                suggested,
            ),
        )

    async def async_step_fcm(self, user_input: dict[str, Any] | None = None):
        """Validate the user-owned local Firebase configuration."""
        errors: dict[str, str] = {}
        suggested_path = self.config_entry.options.get(
            CONF_FCM_CONFIG_PATH,
            DEFAULT_OPTIONS[CONF_FCM_CONFIG_PATH],
        )
        if user_input is not None:
            config_path = str(user_input[CONF_FCM_CONFIG_PATH]).strip()
            suggested_path = config_path
            try:
                await async_load_firebase_config(self.hass, config_path)
            except FileNotFoundError:
                errors["base"] = "fcm_config_not_found"
            except UfanetFirebaseConfigError:
                errors["base"] = "invalid_fcm_config"
            else:
                pending = dict(getattr(self, "_pending_options", DEFAULT_OPTIONS))
                pending[CONF_CALL_UPDATE_MODE] = CALL_UPDATE_MODE_FCM
                pending[CONF_FCM_CONFIG_PATH] = config_path
                return self.async_create_entry(title="", data=pending)

        return self.async_show_form(
            step_id="fcm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_FCM_CONFIG_PATH): str}),
                {CONF_FCM_CONFIG_PATH: suggested_path},
            ),
            errors=errors,
        )
