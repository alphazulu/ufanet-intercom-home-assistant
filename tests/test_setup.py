"""Tests for integration-level setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ufanet_intercom import (
    _ARCHIVE_CARD_PATH,
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
        patch("custom_components.ufanet_intercom.async_setup_services"),
        patch.object(ha_frontend, "add_extra_js_url"),
    ):
        assert await async_setup(hass, {}) is True

    hass.async_add_executor_job.assert_awaited_once_with(
        _path_is_file,
        _ARCHIVE_CARD_PATH,
    )
    hass.http.async_register_static_paths.assert_awaited_once()
