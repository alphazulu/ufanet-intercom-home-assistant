"""Tests for privacy-minimized UCAMS motion analytics runtime support."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from custom_components.ufanet_intercom.analytics import (
    _MotionCursor,
    _advance_cursor,
    _parse_cursors,
    _serialize_cursors,
    async_get_motion_capabilities,
    async_get_motion_events,
)
from custom_components.ufanet_intercom.api import UfanetResponseError


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
    api._async_ucams_json.return_value = {
        "count": 1,
        "page": {"page_size": 60},
        "results": [
            {
                "id": 41,
                "date": "2026-09-02T10:00:00Z",
                "length": 9,
                "camera_number": "PRIVATE-CAMERA",
                "text": "private",
                "full_screenshot_url": "https://private.invalid/image.jpg",
                "recognition": {"private": True},
            }
        ],
    }
    start = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)

    events = await async_get_motion_events(api, "PRIVATE-CAMERA", start=start, end=end)

    assert events == [
        {
            "cursor_id": 41,
            "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        }
    ]
    assert set(events[0]) == {"cursor_id", "occurred_at"}
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
async def test_motion_events_cap_server_oversized_page_locally() -> None:
    api = AsyncMock()
    api._async_ucams_json.return_value = {
        "results": [
            {
                "id": index,
                "date": f"2026-09-02T10:{index % 60:02d}:00Z",
                "length": 1,
            }
            for index in range(75)
        ]
    }

    events = await async_get_motion_events(
        api,
        "CAM",
        start=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc),
    )

    assert len(events) == 60
    assert {event["cursor_id"] for event in events} == set(range(60))


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
    api._async_ucams_json.return_value = {"results": [item]}

    with pytest.raises(UfanetResponseError):
        await async_get_motion_events(
            api,
            "CAM",
            start=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc),
        )


def test_first_cursor_builds_baseline_without_replaying_history() -> None:
    events = [
        {"cursor_id": 10, "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)},
        {"cursor_id": 11, "occurred_at": datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)},
    ]

    cursor, unseen = _advance_cursor(None, events)

    assert unseen == []
    assert cursor.timestamp == datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)
    assert cursor.ids == frozenset({11})


def test_cursor_detects_new_id_at_same_timestamp_and_newer_events_once() -> None:
    existing = _MotionCursor(
        datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        frozenset({10}),
    )
    events = [
        {"cursor_id": 10, "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)},
        {"cursor_id": 12, "occurred_at": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)},
        {"cursor_id": 13, "occurred_at": datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)},
    ]

    cursor, unseen = _advance_cursor(existing, events)

    assert [event["cursor_id"] for event in unseen] == [12, 13]
    assert cursor.timestamp == datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)
    assert cursor.ids == frozenset({13})

    cursor_again, unseen_again = _advance_cursor(cursor, events)
    assert unseen_again == []
    assert cursor_again == cursor


def test_private_cursor_roundtrip_contains_only_camera_date_and_ids() -> None:
    cursor = _MotionCursor(
        datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        frozenset({7, 9}),
    )
    serialized = _serialize_cursors({"PRIVATE-CAMERA": cursor})

    assert serialized == {
        "cameras": {
            "PRIVATE-CAMERA": {
                "date": "2026-09-02T10:00:00Z",
                "ids": [7, 9],
            }
        }
    }
    assert _parse_cursors(serialized) == {"PRIVATE-CAMERA": cursor}
