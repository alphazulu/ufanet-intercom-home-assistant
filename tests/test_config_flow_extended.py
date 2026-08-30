"""Extended Home Assistant config, reauth and options flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.api import UfanetAuthError
from custom_components.ufanet_intercom.const import (
    CALL_UPDATE_MODE_FCM,
    CONF_CALL_UPDATE_MODE,
    CONF_FCM_CONFIG_PATH,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.ufanet_intercom.options import DEFAULT_OPTIONS


@pytest.mark.asyncio
async def test_user_flow_maps_unexpected_exception(hass) -> None:
    with patch("custom_components.ufanet_intercom.config_flow.UfanetApi") as api_cls:
        api = api_cls.return_value
        api.async_login = AsyncMock(side_effect=RuntimeError("boom"))
        api.async_get_skuds = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_reauth_shows_password_form(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "old"},
        unique_id="ab123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["username"] == "AB123"


@pytest.mark.asyncio
async def test_reauth_success_updates_password_and_aborts(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "old"},
        unique_id="ab123",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.ufanet_intercom.config_flow.UfanetApi") as api_cls:
        api = api_cls.return_value
        api.async_login = AsyncMock(return_value=None)
        api.async_get_skuds = AsyncMock(return_value=[])

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PASSWORD: "new"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert entry.data[CONF_PASSWORD] == "new"


@pytest.mark.asyncio
async def test_reauth_failure_keeps_form_and_old_password(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "old"},
        unique_id="ab123",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.ufanet_intercom.config_flow.UfanetApi") as api_cls:
        api = api_cls.return_value
        api.async_login = AsyncMock(side_effect=UfanetAuthError("bad"))
        api.async_get_skuds = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_PASSWORD] == "old"


@pytest.mark.asyncio
async def test_options_flow_shows_form(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        options={},
        unique_id="ab123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.asyncio
async def test_options_flow_saves_valid_values(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        options={},
        unique_id="ab123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    values = dict(DEFAULT_OPTIONS)
    result = await hass.config_entries.options.async_configure(result["flow_id"], values)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == values


@pytest.mark.asyncio
async def test_options_flow_validates_fcm_config_before_saving(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        options={},
        unique_id="ab123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    values = {**DEFAULT_OPTIONS, CONF_CALL_UPDATE_MODE: CALL_UPDATE_MODE_FCM}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        values,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "fcm"

    with patch(
        "custom_components.ufanet_intercom.config_flow.async_load_firebase_config",
        AsyncMock(return_value={"project_id": "example"}),
    ) as load_config:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_FCM_CONFIG_PATH: "private/firebase_config.json"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        **values,
        CONF_FCM_CONFIG_PATH: "private/firebase_config.json",
    }
    load_config.assert_awaited_once_with(
        hass,
        "private/firebase_config.json",
    )


@pytest.mark.asyncio
async def test_options_flow_reports_missing_fcm_config(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        options={},
        unique_id="ab123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**DEFAULT_OPTIONS, CONF_CALL_UPDATE_MODE: CALL_UPDATE_MODE_FCM},
    )
    with patch(
        "custom_components.ufanet_intercom.config_flow.async_load_firebase_config",
        AsyncMock(side_effect=FileNotFoundError),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_FCM_CONFIG_PATH: "missing.json"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "fcm"
    assert result["errors"] == {"base": "fcm_config_not_found"}
