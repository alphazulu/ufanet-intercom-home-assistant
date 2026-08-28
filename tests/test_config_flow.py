"""Tests for the Home Assistant config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.api import (
    UfanetAuthError,
    UfanetConnectionError,
    UfanetResponseError,
)
from custom_components.ufanet_intercom.const import CONF_PASSWORD, CONF_USERNAME, DOMAIN


@pytest.mark.asyncio
async def test_user_flow_shows_form(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_user_flow_success_normalizes_username(hass) -> None:
    with patch("custom_components.ufanet_intercom.config_flow.UfanetApi") as api_cls:
        api = api_cls.return_value
        api.async_login = AsyncMock(return_value=None)
        api.async_get_skuds = AsyncMock(return_value=[])

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: " ab123 ", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "AB123"
    assert result["data"] == {CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"}
    api_cls.assert_called_once()
    assert api_cls.call_args.args[1:] == ("AB123", "secret")
    api.async_login.assert_awaited_once()
    api.async_get_skuds.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UfanetAuthError("bad credentials"), "invalid_auth"),
        (UfanetConnectionError("offline"), "cannot_connect"),
        (UfanetResponseError("changed response"), "unknown"),
    ],
)
async def test_user_flow_maps_api_errors(hass, error: Exception, expected: str) -> None:
    with patch("custom_components.ufanet_intercom.config_flow.UfanetApi") as api_cls:
        api = api_cls.return_value
        api.async_login = AsyncMock(side_effect=error)
        api.async_get_skuds = AsyncMock(return_value=[])

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


@pytest.mark.asyncio
async def test_user_flow_maps_skud_validation_failure(hass) -> None:
    with patch("custom_components.ufanet_intercom.config_flow.UfanetApi") as api_cls:
        api = api_cls.return_value
        api.async_login = AsyncMock(return_value=None)
        api.async_get_skuds = AsyncMock(side_effect=UfanetResponseError("bad skud response"))

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
async def test_duplicate_username_aborts(hass) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "old"},
        unique_id="ab123",
    )
    existing.add_to_hass(hass)

    with patch("custom_components.ufanet_intercom.config_flow.UfanetApi") as api_cls:
        api = api_cls.return_value
        api.async_login = AsyncMock(return_value=None)
        api.async_get_skuds = AsyncMock(return_value=[])

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
