"""Tests for safe local Firebase configuration loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.ufanet_intercom.firebase_config import (
    MAX_FIREBASE_CONFIG_BYTES,
    UfanetFirebaseConfigError,
    async_load_firebase_config,
    firebase_config_fingerprint,
    load_firebase_config,
    resolve_firebase_config_path,
)

FIREBASE_CONFIG = {
    "project_id": "example-project",
    "sender_id": "123456789",
    "app_id": "1:123456789:android:abcdef012345",
    "package_name": "example.android.app",
    "api_key": "not-a-real-key",
}


def test_resolve_path_stays_inside_home_assistant_config(tmp_path: Path) -> None:
    expected = tmp_path / "ufanet_intercom" / "firebase_config.json"

    assert (
        resolve_firebase_config_path(
            tmp_path,
            "ufanet_intercom/firebase_config.json",
        )
        == expected
    )

    with pytest.raises(UfanetFirebaseConfigError, match="inside"):
        resolve_firebase_config_path(tmp_path, "../firebase_config.json")


@pytest.mark.parametrize("nested", [True, False])
def test_load_accepts_extractor_and_flat_formats(
    tmp_path: Path,
    nested: bool,
) -> None:
    path = tmp_path / "firebase_config.json"
    payload = {"schema_version": 1, "firebase": FIREBASE_CONFIG}
    path.write_text(
        json.dumps(payload if nested else FIREBASE_CONFIG),
        encoding="utf-8",
    )

    assert load_firebase_config(path) == FIREBASE_CONFIG
    fingerprint = firebase_config_fingerprint(FIREBASE_CONFIG)
    assert len(fingerprint) == 12
    assert FIREBASE_CONFIG["api_key"] not in fingerprint


@pytest.mark.parametrize(
    "updates, message",
    [
        ({"api_key": ""}, "api_key"),
        ({"sender_id": "not-numeric"}, "numeric"),
        ({"app_id": "not-an-app-id"}, "Android app id"),
        (
            {"app_id": "1:987654321:android:abcdef012345"},
            "does not match",
        ),
        ({"package_name": "not a package"}, "package_name"),
    ],
)
def test_load_rejects_invalid_fields(
    tmp_path: Path,
    updates: dict[str, str],
    message: str,
) -> None:
    path = tmp_path / "firebase_config.json"
    path.write_text(
        json.dumps({**FIREBASE_CONFIG, **updates}),
        encoding="utf-8",
    )

    with pytest.raises(UfanetFirebaseConfigError, match=message):
        load_firebase_config(path)


def test_load_rejects_invalid_json_and_large_file(tmp_path: Path) -> None:
    path = tmp_path / "firebase_config.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(UfanetFirebaseConfigError, match="valid JSON"):
        load_firebase_config(path)

    path.write_bytes(b"x" * (MAX_FIREBASE_CONFIG_BYTES + 1))
    with pytest.raises(UfanetFirebaseConfigError, match="large"):
        load_firebase_config(path)


@pytest.mark.asyncio
async def test_async_load_resolves_and_reads_in_executor(
    hass,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "ufanet_intercom" / "firebase_config.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"firebase": FIREBASE_CONFIG}), encoding="utf-8")
    hass.config.config_dir = str(tmp_path)

    calls: list[tuple[object, tuple[object, ...]]] = []

    async def run_executor_job(func, *args):
        calls.append((func, args))
        return func(*args)

    monkeypatch.setattr(hass, "async_add_executor_job", run_executor_job)

    assert await async_load_firebase_config(
        hass,
        "ufanet_intercom/firebase_config.json",
    ) == FIREBASE_CONFIG
    assert len(calls) == 1
    assert calls[0][1] == (
        str(tmp_path),
        "ufanet_intercom/firebase_config.json",
    )
