"""Tests for automatic call archive export scheduling."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ufanet_intercom.auto_export import (
    UfanetCallAutoSaveManager,
    _call_datetime,
    _event_ref,
)
from custom_components.ufanet_intercom.const import (
    CONF_CALL_AUTOSAVE_AFTER_SECONDS,
    CONF_CALL_AUTOSAVE_ENABLED,
    CONF_CALL_LEAD_SECONDS,
    DOMAIN,
    SERVICE_GET_ARCHIVE_DOWNLOAD_URL,
)


def _call(*, uuid: str = "call-1", seconds_ago: int = 120) -> dict[str, str]:
    return {
        "uuid": uuid,
        "called_at": (
            datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        ).isoformat(),
    }


def _manager(*, enabled: bool = True) -> tuple[UfanetCallAutoSaveManager, MagicMock]:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    manager = UfanetCallAutoSaveManager(
        hass,
        {
            CONF_CALL_AUTOSAVE_ENABLED: enabled,
            CONF_CALL_LEAD_SECONDS: 15,
            CONF_CALL_AUTOSAVE_AFTER_SECONDS: 45,
        },
    )
    return manager, hass


def test_call_datetime_and_event_reference_are_stable() -> None:
    parsed = _call_datetime({"called_at": "2026-08-28T10:00:00+10:00"})
    assert parsed == datetime(2026, 8, 28, 0, 0, tzinfo=timezone.utc)

    naive = _call_datetime({"called_at": "2026-08-28T10:00:00"})
    assert naive == datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    assert _call_datetime({"called_at": "bad"}) is None
    assert _call_datetime({}) is None
    assert _event_ref("same") == _event_ref("same")
    assert len(_event_ref("same")) == 12


def test_schedule_rejects_disabled_missing_and_invalid_calls() -> None:
    manager, _ = _manager(enabled=False)
    assert manager.schedule(_call(), "device") is False

    manager, _ = _manager()
    assert manager.schedule(_call(), None) is False
    assert manager.schedule({"uuid": "", "called_at": "bad"}, "device") is False
    assert manager.skipped_count == 1


def test_schedule_recovery_rejects_stale_or_future_calls() -> None:
    manager, _ = _manager()
    assert manager.schedule(_call(seconds_ago=1000), "device", recovery=True) is False

    future = {
        "uuid": "future",
        "called_at": (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
    }
    assert manager.schedule(future, "device", recovery=True) is False
    assert manager.scheduled_count == 0


def test_schedule_creates_one_task_and_deduplicates() -> None:
    manager, hass = _manager()
    task = MagicMock()

    def create_task(coro, name):
        assert name.startswith(f"{DOMAIN}_autosave_")
        coro.close()
        return task

    hass.async_create_task.side_effect = create_task
    call = _call()

    assert manager.schedule(call, "device-1") is True
    assert manager.schedule(call, "device-1") is False
    assert manager.scheduled_count == 1
    assert manager.last_call_at is not None
    task.add_done_callback.assert_called_once()

    callback = task.add_done_callback.call_args.args[0]
    callback(task)
    assert manager._tasks == {}  # noqa: SLF001
    assert manager._scheduled == set()  # noqa: SLF001


@pytest.mark.asyncio
async def test_export_success_records_result_and_service_payload() -> None:
    manager, hass = _manager()
    hass.services.async_call.return_value = {
        "filename": "saved.mp4",
        "existing": True,
    }
    call = _call(seconds_ago=300)

    await manager._async_export(call, "device-1", _event_ref(call["uuid"]))  # noqa: SLF001

    hass.services.async_call.assert_awaited_once()
    args = hass.services.async_call.await_args.args
    kwargs = hass.services.async_call.await_args.kwargs
    assert args[0:2] == (DOMAIN, SERVICE_GET_ARCHIVE_DOWNLOAD_URL)
    assert args[2]["device_id"] == "device-1"
    assert args[2]["source"] == "call"
    assert args[2]["event_id"] == call["uuid"]
    assert args[2]["duration"] == 60
    assert kwargs == {"blocking": True, "return_response": True}
    assert manager.success_count == 1
    assert manager.failure_count == 0
    assert manager.last_filename == "saved.mp4"
    assert manager.last_result_existing is True
    assert manager.last_error_type is None


@pytest.mark.asyncio
async def test_export_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, hass = _manager()
    hass.services.async_call.side_effect = [
        RuntimeError("temporary"),
        {"filename": "retry.mp4", "existing": False},
    ]
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.ufanet_intercom.auto_export.asyncio.sleep", sleep)
    call = _call(seconds_ago=300)

    await manager._async_export(call, "device-1", _event_ref(call["uuid"]))  # noqa: SLF001

    assert hass.services.async_call.await_count == 2
    sleep.assert_awaited_once()
    assert manager.success_count == 1
    assert manager.failure_count == 0
    assert manager.last_filename == "retry.mp4"


@pytest.mark.asyncio
async def test_export_exhausts_retries_and_sanitizes_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, hass = _manager()
    hass.services.async_call.side_effect = RuntimeError("x" * 700)
    monkeypatch.setattr(
        "custom_components.ufanet_intercom.auto_export.asyncio.sleep",
        AsyncMock(),
    )
    call = _call(seconds_ago=300)

    await manager._async_export(call, "device-1", _event_ref(call["uuid"]))  # noqa: SLF001

    assert hass.services.async_call.await_count == 3
    assert manager.failure_count == 1
    assert manager.last_error_type == "RuntimeError"
    assert manager.last_error_message == "x" * 500

    public = manager.status(include_details=False)
    assert "last_filename" not in public
    assert "last_error_message" not in public


@pytest.mark.asyncio
async def test_export_propagates_cancellation() -> None:
    manager, hass = _manager()
    hass.services.async_call.side_effect = asyncio.CancelledError
    call = _call(seconds_ago=300)

    with pytest.raises(asyncio.CancelledError):
        await manager._async_export(call, "device-1", _event_ref(call["uuid"]))  # noqa: SLF001


def test_cancel_all_cancels_pending_tasks() -> None:
    manager, _ = _manager()
    task1 = MagicMock()
    task2 = MagicMock()
    manager._tasks = {"a": task1, "b": task2}  # noqa: SLF001

    manager.cancel_all()

    task1.cancel.assert_called_once()
    task2.cancel.assert_called_once()
    assert manager._tasks == {}  # noqa: SLF001
