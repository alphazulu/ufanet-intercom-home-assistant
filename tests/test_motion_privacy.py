"""Targeted privacy regressions for UCAMS motion analytics."""

from __future__ import annotations

from datetime import timedelta
import json
from types import SimpleNamespace

from custom_components.ufanet_intercom.diagnostics import _motion_analytics_summary


def test_motion_diagnostics_expose_only_aggregate_state_and_error_type() -> None:
    coordinator = SimpleNamespace(
        update_interval=timedelta(seconds=60),
        last_exception=RuntimeError(
            "PRIVATE-CAMERA-123 token=SECRET raw UCAMS response body"
        ),
        last_update_success=False,
        diagnostic_summary=lambda: {
            "supported_intercom_count": 1,
            "new_event_batch_count": 2,
            "stored_cursor_count": 1,
        },
    )
    runtime = {
        "analytics_coordinator": coordinator,
        "camera_number": "PRIVATE-CAMERA-123",
        "cursor_id": 918273,
    }

    summary = _motion_analytics_summary(runtime)
    serialized = json.dumps(summary)

    assert summary == {
        "present": True,
        "last_update_success": False,
        "last_exception_type": "RuntimeError",
        "update_interval_seconds": 60.0,
        "supported_intercom_count": 1,
        "new_event_batch_count": 2,
        "stored_cursor_count": 1,
    }
    for private_value in (
        "PRIVATE-CAMERA-123",
        "SECRET",
        "raw UCAMS response body",
        "918273",
    ):
        assert private_value not in serialized
