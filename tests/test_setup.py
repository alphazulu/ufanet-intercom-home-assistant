"""Tests for integration-level setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.ufanet_intercom import (
    _ARCHIVE_CARD_MODULE_URL,
    _ARCHIVE_CARD_PATH,
    _KEY_HISTORY_CARD_MODULE_URL,
    _KEY_HISTORY_CARD_PATH,
    _PHYSICAL_KEYS_CARD_MODULE_URL,
    _PHYSICAL_KEYS_CARD_PATH,
    _async_ensure_lovelace_module,
    _path_is_file,
    async_setup,
    frontend as ha_frontend,
)


class _FakeResourceCollection:
    """Minimal writable Lovelace storage-resource collection."""

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = list(items or [])
        self.info_loaded = False
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []

    async def async_get_info(self) -> dict:
        self.info_loaded = True
        return {}

    def async_items(self) -> list[dict]:
        return self.items

    async def async_create_item(self, data: dict) -> dict:
        item = {"id": f"resource-{len(self.items) + 1}", **data}
        self.items.append(item)
        self.created.append(dict(data))
        return item

    async def async_update_item(self, item_id: str, data: dict) -> dict:
        item = next(item for item in self.items if item.get("id") == item_id)
        item.update(data)
        self.updated.append((item_id, dict(data)))
        return item


@pytest.mark.asyncio
async def test_packaged_card_check_runs_in_executor_and_falls_back_without_lovelace() -> None:
    """Keep file checks off-loop and preserve extra-JS fallback outside storage mode."""
    hass = MagicMock()
    hass.data = {}
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
    assert hass.async_add_executor_job.await_args_list == [
        call(_path_is_file, _ARCHIVE_CARD_PATH),
        call(_path_is_file, _PHYSICAL_KEYS_CARD_PATH),
        call(_path_is_file, _KEY_HISTORY_CARD_PATH),
    ]
    hass.http.async_register_static_paths.assert_awaited_once()

    static_paths = hass.http.async_register_static_paths.await_args.args[0]
    assert len(static_paths) == 3
    assert str(_ARCHIVE_CARD_PATH) in {item.path for item in static_paths}
    assert str(_PHYSICAL_KEYS_CARD_PATH) in {item.path for item in static_paths}
    assert str(_KEY_HISTORY_CARD_PATH) in {item.path for item in static_paths}

    assert add_extra_js_url.call_args_list == [
        call(hass, _ARCHIVE_CARD_MODULE_URL),
        call(hass, _PHYSICAL_KEYS_CARD_MODULE_URL),
        call(hass, _KEY_HISTORY_CARD_MODULE_URL),
    ]


@pytest.mark.asyncio
async def test_storage_mode_registers_modules_before_dashboard_without_extra_js() -> None:
    """Storage-mode cards are normal Lovelace resources, avoiding load-order races."""
    resources = _FakeResourceCollection()
    lovelace = MagicMock()
    lovelace.resources = resources

    hass = MagicMock()
    hass.data = {"lovelace": lovelace}
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
        patch("custom_components.ufanet_intercom.async_setup_key_services"),
        patch.object(ha_frontend, "add_extra_js_url") as add_extra_js_url,
    ):
        assert await async_setup(hass, {}) is True

    assert resources.info_loaded is True
    assert resources.created == [
        {"res_type": "module", "url": _ARCHIVE_CARD_MODULE_URL},
        {"res_type": "module", "url": _PHYSICAL_KEYS_CARD_MODULE_URL},
        {"res_type": "module", "url": _KEY_HISTORY_CARD_MODULE_URL},
    ]
    assert {item["url"] for item in resources.items} == {
        _ARCHIVE_CARD_MODULE_URL,
        _PHYSICAL_KEYS_CARD_MODULE_URL,
        _KEY_HISTORY_CARD_MODULE_URL,
    }
    add_extra_js_url.assert_not_called()


@pytest.mark.asyncio
async def test_lovelace_module_registration_reuses_and_updates_own_resource() -> None:
    """Do not duplicate resources and safely refresh an older cache-bust URL."""
    base = _ARCHIVE_CARD_MODULE_URL.partition("?")[0]
    resources = _FakeResourceCollection(
        [
            {
                "id": "existing",
                "res_type": "module",
                "url": f"{base}?v=old-validation",
            }
        ]
    )
    lovelace = MagicMock()
    lovelace.resources = resources
    hass = MagicMock()
    hass.data = {"lovelace": lovelace}

    assert await _async_ensure_lovelace_module(hass, _ARCHIVE_CARD_MODULE_URL) is True
    assert resources.created == []
    assert resources.updated == [
        (
            "existing",
            {"res_type": "module", "url": _ARCHIVE_CARD_MODULE_URL},
        )
    ]

    resources.updated.clear()
    assert await _async_ensure_lovelace_module(hass, _ARCHIVE_CARD_MODULE_URL) is True
    assert resources.created == []
    assert resources.updated == []