"""Tests for integration-level setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ufanet_intercom import (
    _ARCHIVE_CARD_MODULE_URL,
    _ARCHIVE_CARD_PATH,
    _PHYSICAL_KEYS_CARD_MODULE_URL,
    _PHYSICAL_KEYS_CARD_PATH,
    _path_is_file,
    async_setup,
    frontend as ha_frontend,
)


@pytest.mark.asyncio
async def test_packaged_card_check_runs_in_executor() -> None:
    """Keep packaged-file metadata access away from the event loop."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(return_value=True)
    hass.http.async_register_static_paths = AsyncMock()
    store = MagicMock()
    store.async_load = AsyncMock()

    with (
        patch(
            "custom_components.ufanet_intercom.UfanetGuestInviteStore",
            return_value=store,
        ),
        patch("custom_components.ufanet_intercom.async_setup_services") as setup_services,
        patch(
            "custom_components.ufanet_intercom.async_setup_key_services"
        ) as setup_key_services,
        patch.object(ha_frontend, "add_extra_js_url") as add_extra_js_url,
    ):
        assert await async_setup(hass, {}) is True

    setup_services.assert_called_once_with(hass, store)
    setup_key_services.assert_called_once_with(hass)
    hass.async_add_executor_job.assert_awaited_once_with(
        _path_is_file,
        _ARCHIVE_CARD_PATH,
    )
    hass.http.async_register_static_paths.assert_awaited_once()

    static_paths = hass.http.async_register_static_paths.await_args.args[0]
    assert len(static_paths) == 2
    assert str(_ARCHIVE_CARD_PATH) in {item.path for item in static_paths}
    assert str(_PHYSICAL_KEYS_CARD_PATH) in {item.path for item in static_paths}

    assert add_extra_js_url.call_args_list == [
        ((hass, _ARCHIVE_CARD_MODULE_URL),),
        ((hass, _PHYSICAL_KEYS_CARD_MODULE_URL),),
    ]
