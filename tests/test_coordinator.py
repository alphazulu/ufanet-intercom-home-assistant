"""Tests for intercom and call-history coordinators."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ufanet_intercom.api import (
    UfanetAuthError,
    UfanetConnectionError,
)
from custom_components.ufanet_intercom.coordinator import (
    UfanetCallCoordinator,
    UfanetCoordinator,
    _event_timestamp,
)


def _api() -> MagicMock:
    api = MagicMock()
    api.async_get_skuds = AsyncMock(return_value=[])
    api.async_get_call_history = AsyncMock(return_value=[])
    api.async_get_call_media = AsyncMock(return_value={})
    return api


@pytest.mark.asyncio
async def test_intercom_coordinator_indexes_items_and_uses_configured_interval(hass) -> None:
    api = _api()
    api.async_get_skuds.return_value = [
        {"id": "7", "title": "Front"},
        {"id": 8, "title": "Back"},
    ]
    coordinator = UfanetCoordinator(hass, api, scan_interval_seconds=123)

    result = await coordinator._async_update_data()  # noqa: SLF001

    assert list(result) == [7, 8]
    assert result[7]["title"] == "Front"
    assert coordinator.scan_interval_seconds == 123
    assert coordinator.update_interval.total_seconds() == 123


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UfanetAuthError("expired"), ConfigEntryAuthFailed),
        (UfanetConnectionError("offline"), UpdateFailed),
    ],
)
async def test_intercom_coordinator_maps_api_errors(hass, error, expected) -> None:
    api = _api()
    api.async_get_skuds.side_effect = error
    coordinator = UfanetCoordinator(hass, api)

    with pytest.raises(expected):
        await coordinator._async_update_data()  # noqa: SLF001


def _event(
    uuid: str,
    called_at: str,
    camera: str | None = "CAM1",
) -> dict[str, str | None]:
    return {
        "uuid": uuid,
        "called_at": called_at,
        "camera_number": camera,
    }


@pytest.mark.asyncio
async def test_call_coordinator_first_poll_is_baseline_and_selects_latest_camera_event(
    hass,
) -> None:
    api = _api()
    api.async_get_call_history.return_value = [
        _event("older", "2026-08-28T09:00:00+00:00"),
        _event("latest", "2026-08-28T10:00:00Z"),
        _event("no-camera", "2026-08-28T11:00:00Z", None),
        {"uuid": ""},
        "garbage",
    ]
    api.async_get_call_media.side_effect = lambda uuid: {
        "preview": f"https://preview.invalid/{uuid}.jpg",
        "url": f"https://archive.invalid/{uuid}.mp4",
    }
    coordinator = UfanetCallCoordinator(hass, api)

    result = await coordinator._async_update_data()  # noqa: SLF001

    assert coordinator.new_calls == []
    assert coordinator._initialized is True  # noqa: SLF001
    assert coordinator._seen_uuids == {"older", "latest", "no-camera"}  # noqa: SLF001
    assert list(result) == ["CAM1"]
    assert result["CAM1"]["uuid"] == "latest"
    assert result["CAM1"]["preview_url"].endswith("latest.jpg")
    assert result["CAM1"]["archive_url"].endswith("latest.mp4")
    api.async_get_call_media.assert_awaited_once_with("latest")


@pytest.mark.asyncio
async def test_call_coordinator_emits_only_new_calls_sorted_and_enriched(hass) -> None:
    api = _api()
    coordinator = UfanetCallCoordinator(hass, api)
    api.async_get_call_media.side_effect = lambda uuid: {
        "preview": f"preview-{uuid}",
        "url": f"archive-{uuid}",
    }

    api.async_get_call_history.return_value = [
        _event("baseline", "2026-08-28T10:00:00Z"),
    ]
    await coordinator._async_update_data()  # noqa: SLF001

    api.async_get_call_history.return_value = [
        _event("newer", "2026-08-28T10:03:00Z", "CAM2"),
        _event("baseline", "2026-08-28T10:00:00Z", "CAM1"),
        _event("new-older", "2026-08-28T10:02:00Z", "CAM1"),
    ]
    result = await coordinator._async_update_data()  # noqa: SLF001

    assert [item["uuid"] for item in coordinator.new_calls] == ["new-older", "newer"]
    assert coordinator.new_calls[0]["preview_url"] == "preview-new-older"
    assert coordinator.new_calls[1]["archive_url"] == "archive-newer"
    assert result["CAM1"]["uuid"] == "new-older"
    assert result["CAM2"]["uuid"] == "newer"
    assert coordinator._seen_uuids == {"baseline", "new-older", "newer"}  # noqa: SLF001


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UfanetAuthError("expired"), ConfigEntryAuthFailed),
        (UfanetConnectionError("offline"), UpdateFailed),
    ],
)
async def test_failed_call_poll_clears_transient_new_calls(hass, error, expected) -> None:
    api = _api()
    api.async_get_call_history.side_effect = error
    coordinator = UfanetCallCoordinator(hass, api)
    coordinator.new_calls = [{"uuid": "must-not-replay"}]

    with pytest.raises(expected):
        await coordinator._async_update_data()  # noqa: SLF001

    assert coordinator.new_calls == []


@pytest.mark.asyncio
async def test_media_cache_reuses_then_refreshes_by_monotonic_age(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    api.async_get_call_media.side_effect = [
        {"preview": "preview-1", "url": "archive-1"},
        {"preview": "preview-2", "url": "archive-2"},
    ]
    coordinator = UfanetCallCoordinator(hass, api, media_refresh_seconds=30)
    times = iter([100.0, 110.0, 140.1])
    monkeypatch.setattr(
        "custom_components.ufanet_intercom.coordinator.time.monotonic",
        lambda: next(times),
    )
    event = _event("same", "2026-08-28T10:00:00Z")

    first = await coordinator._async_enrich_media(event)  # noqa: SLF001
    second = await coordinator._async_enrich_media(event)  # noqa: SLF001
    third = await coordinator._async_enrich_media(event)  # noqa: SLF001

    assert first["preview_url"] == "preview-1"
    assert second["archive_url"] == "archive-1"
    assert third["preview_url"] == "preview-2"
    assert api.async_get_call_media.await_count == 2


@pytest.mark.asyncio
async def test_media_enrichment_is_best_effort_and_ignores_missing_uuid(hass) -> None:
    api = _api()
    coordinator = UfanetCallCoordinator(hass, api)

    assert await coordinator._async_enrich_media({"called_at": "x"}) == {  # noqa: SLF001
        "called_at": "x"
    }
    api.async_get_call_media.side_effect = UfanetConnectionError("offline")
    event = _event("u1", "2026-08-28T10:00:00Z")
    assert await coordinator._async_enrich_media(event) == event  # noqa: SLF001


@pytest.mark.asyncio
async def test_seen_uuid_memory_is_bounded_to_recent_page(hass) -> None:
    api = _api()
    coordinator = UfanetCallCoordinator(hass, api)
    coordinator._initialized = True  # noqa: SLF001
    coordinator._seen_uuids = {f"old-{idx}" for idx in range(251)}  # noqa: SLF001
    api.async_get_call_history.return_value = [
        _event("current-1", "2026-08-28T10:00:00Z"),
        _event("current-2", "2026-08-28T10:01:00Z"),
    ]

    await coordinator._async_update_data()  # noqa: SLF001

    assert coordinator._seen_uuids == {"current-1", "current-2"}  # noqa: SLF001
    assert [item["uuid"] for item in coordinator.new_calls] == [
        "current-1",
        "current-2",
    ]


def test_event_timestamp_handles_offsets_naive_and_invalid_values() -> None:
    assert _event_timestamp({"called_at": "2026-08-28T10:00:00+10:00"}) == datetime(
        2026, 8, 28, 0, 0, tzinfo=timezone.utc
    )
    assert _event_timestamp({"called_at": "2026-08-28T10:00:00"}) == datetime(
        2026, 8, 28, 10, 0, tzinfo=timezone.utc
    )
    assert _event_timestamp({"called_at": "not-a-date"}) == datetime.min.replace(
        tzinfo=timezone.utc
    )
    assert _event_timestamp({}) == datetime.min.replace(tzinfo=timezone.utc)
