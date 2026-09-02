"""Tests for privacy-minimized UCAMS motion analytics runtime support."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ufanet_intercom.analytics import (
    _MotionCursor,
    _MotionEventPage,
    _advance_cursor,
    _async_collect_motion_events,
    _parse_cursors,
    _serialize_cursors,
    UfanetMotionAnalyticsCoordinator,
    async_get_motion_capabilities,
    async_get_motion_events,
)
from custom_components.ufanet_intercom.api import UfanetResponseError


def _page(*events: dict, count: int | None = None, all_pages: int = 1) -> dict:
    return {
        "count": len(events) if count is None else count,
        "page": {
            "current": 1,
            "next": None,
            "previous": None,
            "all": all_pages,
            "page_size": 60,
        },
        "results": list(events),
    }


@pytest.mark.asyncio
async def test_motion_capabilities_request_only_minimal_fields() -> None:
    api = AsyncMock()
    api._async_ucams_json.return_value = {
        "results": [
            {"number": "CAM-A", "analytics": ["motion_alarm", "private_type"]},
            {"number": "CAM-B", "analytics": []},
        ]
    }

    supported = await async_get_motion_capabilities(api, ["CAM-A", "CAM-B"])

    assert supported == {"CAM-A"}
    api._async_ucams_json.assert_awaited_once_with(
        "POST",
        "/api/v0/cameras/this/",
        json_body={
            "fields": ["number", "analytics"],
            "numbers": ["CAM-A", "CAM-B"],
        },
    )


@pytest.mark.asyncio
async def test_motion_events_use_confirmed_wire_date_and_drop_all_other_fields() -> None:
    api = AsyncMock()
    api._async_ucams_json.return_value = _page(
        {
            "id": 41,
            "date": "2026-09-02T10:00:00Z",
            "length": 9,
            "camera_number": "PRIVATE-CAMERA",
            "text": "private",
            "full_screenshot_url": "https://private.invalid/image.jpg",
            "recognition": {"private": True},
        }
    )
    start = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)

    report = await async_get_motion_events(
        api,
        "PRIVATE-CAMERA",
        start=start,
        end=end,
    )

    assert report.complete is True
    assert report.events == (
        {
            "cursor_id": 41,
            "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        },
    )
    assert set(report.events[0]) == {"cursor_id", "occurred_at"}
    api._async_ucams_json.assert_awaited_once_with(
        "POST",
        "/api/v0/analytics/motion_alarm/report/",
        json_body={
            "camera_number": "PRIVATE-CAMERA",
            "start": "2026-09-02T09:00:00Z",
            "end": "2026-09-02T10:01:00Z",
            "limit": 25,
            "order_by_date": "desc",
        },
    )


@pytest.mark.asyncio
async def test_motion_events_mark_oversized_server_page_incomplete() -> None:
    api = AsyncMock()
    api._async_ucams_json.return_value = _page(
        *[
            {
                "id": index,
                "date": f"2026-09-02T10:{index % 60:02d}:00Z",
                "length": 1,
            }
            for index in range(75)
        ],
        count=75,
        all_pages=2,
    )

    report = await async_get_motion_events(
        api,
        "CAM",
        start=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc),
    )

    assert report.complete is False
    assert len(report.events) == 60
    assert {event["cursor_id"] for event in report.events} == set(range(60))


@pytest.mark.asyncio
async def test_truncated_window_is_split_without_losing_unseen_events(
    monkeypatch,
) -> None:
    start = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 2, 10, 2, tzinfo=timezone.utc)
    midpoint = start + (end - start) / 2
    calls = []

    async def fake_page(_api, _camera, *, start: datetime, end: datetime):
        calls.append((start, end))
        if len(calls) == 1:
            return _MotionEventPage(tuple(), False)
        if end == midpoint:
            return _MotionEventPage(
                tuple(
                    {
                        "cursor_id": index,
                        "occurred_at": start + timedelta(seconds=index),
                    }
                    for index in range(40)
                ),
                True,
            )
        return _MotionEventPage(
            tuple(
                {
                    "cursor_id": 40 + index,
                    "occurred_at": start + timedelta(seconds=index),
                }
                for index in range(35)
            ),
            True,
        )

    monkeypatch.setattr(
        "custom_components.ufanet_intercom.analytics.async_get_motion_events",
        fake_page,
    )

    events = await _async_collect_motion_events(
        AsyncMock(),
        "CAM",
        start=start,
        end=end,
    )

    assert len(calls) == 3
    assert calls[1] == (start, midpoint)
    assert calls[2] == (midpoint, end)
    assert len(events) == 75
    assert {event["cursor_id"] for event in events} == set(range(75))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {"id": 1, "time": 1788343200, "length": 1},
        {"id": 1, "date": "2026-09-02T10:00:00", "length": 1},
        {"id": "private-id", "date": "2026-09-02T10:00:00Z", "length": 1},
    ],
)
async def test_motion_events_reject_unconfirmed_or_invalid_cursor_schema(item) -> None:
    api = AsyncMock()
    api._async_ucams_json.return_value = _page(item)

    with pytest.raises(UfanetResponseError):
        await async_get_motion_events(
            api,
            "CAM",
            start=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc),
        )


def test_first_cursor_builds_baseline_without_replaying_history() -> None:
    events = [
        {
            "cursor_id": 10,
            "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        },
        {
            "cursor_id": 11,
            "occurred_at": datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc),
        },
    ]

    cursor, unseen = _advance_cursor(None, events)

    assert unseen == []
    assert cursor.timestamp == datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)
    assert cursor.ids == frozenset({11})


def test_empty_first_cursor_baselines_at_poll_time_not_unix_epoch() -> None:
    baseline = datetime(2026, 9, 2, 10, 1, 34, 793780, tzinfo=timezone.utc)

    cursor, unseen = _advance_cursor(None, [], baseline_at=baseline)

    assert unseen == []
    assert cursor == _MotionCursor(baseline, frozenset())


def test_cursor_detects_new_id_at_same_timestamp_and_newer_events_once() -> None:
    existing = _MotionCursor(
        datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        frozenset({10}),
    )
    events = [
        {
            "cursor_id": 10,
            "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        },
        {
            "cursor_id": 12,
            "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        },
        {
            "cursor_id": 13,
            "occurred_at": datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc),
        },
    ]

    cursor, unseen = _advance_cursor(existing, events)

    assert [event["cursor_id"] for event in unseen] == [12, 13]
    assert cursor.timestamp == datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)
    assert cursor.ids == frozenset({13})

    cursor_again, unseen_again = _advance_cursor(cursor, events)
    assert unseen_again == []
    assert cursor_again == cursor


def test_private_cursor_roundtrip_preserves_fractional_seconds_exactly() -> None:
    timestamp = datetime(2026, 9, 2, 10, 0, 34, 793780, tzinfo=timezone.utc)
    cursor = _MotionCursor(timestamp, frozenset({7, 9}))
    serialized = _serialize_cursors({"PRIVATE-CAMERA": cursor})

    assert serialized == {
        "cameras": {
            "PRIVATE-CAMERA": {
                "date": "2026-09-02T10:00:34.793780Z",
                "ids": [7, 9],
            }
        }
    }
    assert _parse_cursors(serialized) == {"PRIVATE-CAMERA": cursor}


def test_fractional_cursor_does_not_replay_after_storage_roundtrip() -> None:
    timestamp = datetime(2026, 9, 2, 10, 0, 34, 793780, tzinfo=timezone.utc)
    original = _MotionCursor(timestamp, frozenset({77}))
    restored = _parse_cursors(_serialize_cursors({"CAM": original}))["CAM"]

    next_cursor, unseen = _advance_cursor(
        restored,
        [{"cursor_id": 77, "occurred_at": timestamp}],
    )

    assert unseen == []
    assert next_cursor == original


@pytest.mark.asyncio
async def test_coordinator_sanitizes_api_error_and_rolls_back_partial_cursor(
    hass,
    monkeypatch,
) -> None:
    api = AsyncMock()
    coordinator = UfanetMotionAnalyticsCoordinator(
        hass,
        api,
        "entry",
        {1: "CAM-A", 2: "CAM-B"},
    )
    old_a = _MotionCursor(
        datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        frozenset({1}),
    )
    old_b = _MotionCursor(
        datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        frozenset({2}),
    )
    coordinator._cursors = {"CAM-A": old_a, "CAM-B": old_b}  # noqa: SLF001
    coordinator._store = SimpleNamespace(async_save=AsyncMock())  # noqa: SLF001

    async def fake_capabilities(_api, _numbers):
        return {"CAM-A", "CAM-B"}

    calls = 0

    async def fake_collect(_api, camera_number, **_kwargs):
        nonlocal calls
        calls += 1
        if camera_number == "CAM-B":
            raise UfanetResponseError("PRIVATE-CAMERA-ID secret server detail")
        return [
            {
                "cursor_id": 3,
                "occurred_at": datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc),
            }
        ]

    monkeypatch.setattr(
        "custom_components.ufanet_intercom.analytics.async_get_motion_capabilities",
        fake_capabilities,
    )
    monkeypatch.setattr(
        "custom_components.ufanet_intercom.analytics._async_collect_motion_events",
        fake_collect,
    )

    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()  # noqa: SLF001

    assert calls == 2
    assert str(err.value) == "UCAMS motion analytics update failed"
    assert "PRIVATE-CAMERA-ID" not in str(err.value)
    assert err.value.__cause__ is None
    assert coordinator._cursors == {"CAM-A": old_a, "CAM-B": old_b}  # noqa: SLF001
    assert coordinator.new_events == {}
    coordinator._store.async_save.assert_not_awaited()  # noqa: SLF001
