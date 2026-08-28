"""Tests for local archive export file management helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import time
from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.ufanet_intercom.services import (
    _archive_days,
    _archive_export_location,
    _call_event_datetime,
    _camera_export_prefix,
    _cleanup_export_files_sync,
    _delete_export_file_sync,
    _export_item,
    _list_export_files_sync,
    _seconds_hms,
    _temporary_link_token,
    _validated_export_path,
)


def _write(path: Path, size: int, *, mtime: float | None = None) -> Path:
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_camera_prefix_sanitizes_filename_characters() -> None:
    assert _camera_export_prefix("CAM/1:2") == "ufanet_CAM_1_2_"


def test_archive_export_location_prefers_local_and_requires_media(tmp_path: Path) -> None:
    hass = MagicMock()
    hass.config.media_dirs = {}
    with pytest.raises(ServiceValidationError, match="no media directory"):
        _archive_export_location(hass)

    hass.config.media_dirs = {"other": str(tmp_path / "other")}
    key, path = _archive_export_location(hass)
    assert key == "other"
    assert path == tmp_path / "other" / "ufanet_intercom"
    assert path.is_dir()

    hass.config.media_dirs = {
        "other": str(tmp_path / "other2"),
        "local": str(tmp_path / "local"),
    }
    key, path = _archive_export_location(hass)
    assert key == "local"
    assert path == tmp_path / "local" / "ufanet_intercom"


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "../ufanet_CAM_file.mp4",
        "sub/ufanet_CAM_file.mp4",
        "ufanet_OTHER_file.mp4",
        "ufanet_CAM_file.txt",
    ],
)
def test_validated_export_path_rejects_unowned_or_unsafe_names(
    tmp_path: Path,
    filename: str,
) -> None:
    with pytest.raises(ServiceValidationError):
        _validated_export_path(tmp_path, "ufanet_CAM_", filename)


def test_validated_export_path_accepts_owned_basename(tmp_path: Path) -> None:
    filename = "ufanet_CAM_2026-08-28_10-20-30_60s.mp4"
    assert _validated_export_path(tmp_path, "ufanet_CAM_", filename) == tmp_path / filename


def test_export_item_parses_manual_and_call_names(tmp_path: Path) -> None:
    manual = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-20-30_60s.mp4",
        10,
    )
    call = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-20-30_60s_call_012345abcdef.mp4",
        20,
    )

    manual_item = _export_item(manual, "local")
    call_item = _export_item(call, "local")

    assert manual_item["duration_seconds"] == 60
    assert manual_item["recorded_local"] == "2026-08-28 10:20:30"
    assert manual_item["source"] == "manual"
    assert manual_item["event_ref"] is None
    assert call_item["source"] == "call"
    assert call_item["event_ref"] == "012345abcdef"
    assert call_item["media_content_id"].endswith(call.name)


def test_list_exports_filters_camera_hidden_and_non_mp4_and_sorts(
    tmp_path: Path,
) -> None:
    now = time.time()
    old = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-00-00_60s.mp4",
        10,
        mtime=now - 10,
    )
    new = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-01-00_60s.mp4",
        20,
        mtime=now,
    )
    _write(tmp_path / "ufanet_OTHER_2026-08-28_10-02-00_60s.mp4", 30)
    _write(tmp_path / ".ufanet_CAM_partial.mp4", 40)
    _write(tmp_path / "ufanet_CAM_notes.txt", 50)

    items = _list_export_files_sync(tmp_path, "ufanet_CAM_", "local")

    assert [item["filename"] for item in items] == [new.name, old.name]


def test_delete_export_file_is_scoped_and_reports_missing(tmp_path: Path) -> None:
    filename = "ufanet_CAM_2026-08-28_10-00-00_60s.mp4"
    _write(tmp_path / filename, 10)

    assert _delete_export_file_sync(tmp_path, "ufanet_CAM_", filename) is True
    assert not (tmp_path / filename).exists()
    assert _delete_export_file_sync(tmp_path, "ufanet_CAM_", filename) is False


def test_cleanup_age_retention_deletes_old_files_but_keeps_named_file(
    tmp_path: Path,
) -> None:
    now = time.time()
    old = _write(
        tmp_path / "ufanet_CAM_2026-08-01_10-00-00_60s.mp4",
        10,
        mtime=now - 10 * 86400,
    )
    keep = _write(
        tmp_path / "ufanet_CAM_2026-08-01_11-00-00_60s.mp4",
        20,
        mtime=now - 10 * 86400,
    )
    fresh = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-00-00_60s.mp4",
        30,
        mtime=now,
    )

    result = _cleanup_export_files_sync(
        tmp_path,
        "ufanet_CAM_",
        retention_days=5,
        max_total_bytes=0,
        keep_filename=keep.name,
    )

    assert old.name in result["deleted_files"]
    assert keep.exists()
    assert fresh.exists()
    assert result["remaining_count"] == 2
    assert result["remaining_bytes"] == 50
    assert result["limit_satisfied"] is True


def test_cleanup_size_cap_removes_oldest_and_can_protect_new_file(
    tmp_path: Path,
) -> None:
    now = time.time()
    first = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-00-00_60s.mp4",
        40,
        mtime=now - 30,
    )
    second = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-01-00_60s.mp4",
        40,
        mtime=now - 20,
    )
    keep = _write(
        tmp_path / "ufanet_CAM_2026-08-28_10-02-00_60s.mp4",
        40,
        mtime=now - 10,
    )

    result = _cleanup_export_files_sync(
        tmp_path,
        "ufanet_CAM_",
        retention_days=0,
        max_total_bytes=80,
        keep_filename=keep.name,
    )

    assert not first.exists()
    assert second.exists()
    assert keep.exists()
    assert result["deleted_count"] == 1
    assert result["remaining_bytes"] == 80
    assert result["limit_satisfied"] is True


def test_cleanup_missing_directory_is_noop(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert _cleanup_export_files_sync(
        missing,
        "ufanet_CAM_",
        retention_days=30,
        max_total_bytes=100,
        keep_filename=None,
    ) == {
        "deleted_count": 0,
        "deleted_bytes": 0,
        "deleted_files": [],
        "remaining_count": 0,
        "remaining_bytes": 0,
        "limit_satisfied": True,
    }


def test_call_datetime_uses_aware_called_at_as_authoritative_instant() -> None:
    parsed = _call_event_datetime({"called_at": "2026-08-28T10:00:00+10:00"})
    assert parsed == datetime(2026, 8, 28, 0, 0, tzinfo=timezone.utc)
    assert _call_event_datetime({"called_at": "bad"}) is None
    assert _call_event_datetime({}) is None


def test_temporary_token_parser_is_strict() -> None:
    assert _temporary_link_token("https://example.test/key?token=abc") == "abc"
    assert _temporary_link_token("https://example.test/key") is None
    assert _temporary_link_token(None) is None


def test_archive_days_merges_small_jitter_and_splits_midnight() -> None:
    start = int(datetime(2026, 8, 27, 23, 59, 50, tzinfo=timezone.utc).timestamp())
    ranges = [
        (start, start + 10),
        (start + 12, start + 20),
    ]

    days = _archive_days(ranges, "UTC")

    assert len(days) == 2
    assert days[0]["date"] == "2026-08-27"
    assert days[0]["intervals"][0]["end"] == "24:00:00"
    assert days[1]["date"] == "2026-08-28"
    assert days[1]["total_duration"] == 8
    assert _seconds_hms(86400) == "24:00:00"
    assert _seconds_hms(3661) == "01:01:01"
