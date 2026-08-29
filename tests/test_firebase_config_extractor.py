from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "research"
    / "fcm_probe_py"
    / "extract_firebase_config.py"
)
SPEC = importlib.util.spec_from_file_location("firebase_config_extractor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


def _args(source: Path, **overrides):
    values = {
        "source": str(source),
        "output": str(source / "firebase_config.json"),
        "project_id": None,
        "sender_id": None,
        "app_id": None,
        "package_name": None,
        "api_key": None,
        "include_unused": False,
        "overwrite": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_extracts_synthetic_android_firebase_config(tmp_path: Path) -> None:
    sender = "123456789012"
    api_key = "AIzaSyntheticClientKeyOnlyForUnitTests000"
    (tmp_path / "resources.xml").write_text(
        f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<resources>
  <string name=\"project_id\">example-firebase-project</string>
  <string name=\"gcm_defaultSenderId\">{sender}</string>
  <string name=\"google_app_id\">1:{sender}:android:abcdef0123456789</string>
  <string name=\"google_api_key\">{api_key}</string>
  <string name=\"google_crash_reporting_api_key\">{api_key}</string>
  <string name=\"firebase_database_url\">https://example.invalid</string>
  <string name=\"google_storage_bucket\">example.invalid</string>
</resources>
""",
        encoding="utf-8",
    )
    app_dir = tmp_path / "com" / "example" / "client"
    app_dir.mkdir(parents=True)
    (app_dir / "BuildConfig.java").write_text(
        'public final class BuildConfig { public static final String APPLICATION_ID = "com.example.client"; }',
        encoding="utf-8",
    )

    payload = extractor.extract(_args(tmp_path))

    assert payload == {
        "schema_version": 1,
        "firebase": {
            "project_id": "example-firebase-project",
            "sender_id": sender,
            "app_id": f"1:{sender}:android:abcdef0123456789",
            "package_name": "com.example.client",
            "api_key": api_key,
        },
    }


def test_unused_metadata_is_opt_in(tmp_path: Path) -> None:
    sender = "123456789012"
    (tmp_path / "resources.xml").write_text(
        f"""<resources>
  <string name=\"project_id\">example-project</string>
  <string name=\"gcm_defaultSenderId\">{sender}</string>
  <string name=\"google_app_id\">1:{sender}:android:abcdef</string>
  <string name=\"google_api_key\">AIzaSyntheticKey</string>
  <string name=\"firebase_database_url\">https://database.example.invalid</string>
  <string name=\"google_storage_bucket\">bucket.example.invalid</string>
</resources>""",
        encoding="utf-8",
    )

    args = _args(
        tmp_path,
        package_name="com.example.client",
        include_unused=True,
    )
    payload = extractor.extract(args)

    assert payload["unused_metadata"] == {
        "database_url": "https://database.example.invalid",
        "storage_bucket": "bucket.example.invalid",
    }


def test_ambiguous_api_keys_are_not_printed_in_error(tmp_path: Path) -> None:
    sender = "123456789012"
    key_one = "AIzaSyntheticKeyOne"
    key_two = "AIzaSyntheticKeyTwo"
    (tmp_path / "one.xml").write_text(
        f"""<resources>
  <string name=\"project_id\">example-project</string>
  <string name=\"gcm_defaultSenderId\">{sender}</string>
  <string name=\"google_app_id\">1:{sender}:android:abcdef</string>
  <string name=\"google_api_key\">{key_one}</string>
</resources>""",
        encoding="utf-8",
    )
    (tmp_path / "two.xml").write_text(
        f"""<resources><string name=\"google_api_key\">{key_two}</string></resources>""",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as exc_info:
        extractor.extract(_args(tmp_path, package_name="com.example.client"))

    message = str(exc_info.value)
    assert key_one not in message
    assert key_two not in message
    assert "sha256=" in message
