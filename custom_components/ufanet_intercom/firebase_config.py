"""Load user-supplied Firebase Android client configuration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from homeassistant.core import HomeAssistant

MAX_FIREBASE_CONFIG_BYTES = 64 * 1024
REQUIRED_FIREBASE_FIELDS = (
    "project_id",
    "sender_id",
    "app_id",
    "package_name",
    "api_key",
)

_APP_ID_RE = re.compile(r"^\d+:(\d+):android:[A-Za-z0-9_-]+$")
_PACKAGE_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)


class UfanetFirebaseConfigError(ValueError):
    """The local Firebase configuration is missing or invalid."""


def resolve_firebase_config_path(
    config_dir: str | Path,
    configured_path: str,
) -> Path:
    """Resolve a configured path while keeping reads inside HA config."""
    root = Path(config_dir).resolve()
    raw = str(configured_path).strip()
    if not raw:
        raise UfanetFirebaseConfigError("Firebase config path is empty")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as err:
        raise UfanetFirebaseConfigError(
            "Firebase config must be stored inside the Home Assistant config directory"
        ) from err
    return resolved


def load_firebase_config(path: Path) -> dict[str, str]:
    """Read and validate a small extractor-produced JSON file."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    except OSError as err:
        raise UfanetFirebaseConfigError("Unable to inspect Firebase config") from err
    if size > MAX_FIREBASE_CONFIG_BYTES:
        raise UfanetFirebaseConfigError("Firebase config is unexpectedly large")

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as err:
        raise UfanetFirebaseConfigError("Firebase config is not valid JSON") from err
    if not isinstance(payload, dict):
        raise UfanetFirebaseConfigError("Firebase config must contain a JSON object")

    raw = payload.get("firebase", payload)
    if not isinstance(raw, dict):
        raise UfanetFirebaseConfigError("Firebase config has no firebase object")

    config: dict[str, str] = {}
    for field in REQUIRED_FIREBASE_FIELDS:
        value = raw.get(field)
        if value is None or not str(value).strip():
            raise UfanetFirebaseConfigError(
                f"Firebase config is missing required field {field}"
            )
        config[field] = str(value).strip()

    sender_id = config["sender_id"]
    if not sender_id.isdigit():
        raise UfanetFirebaseConfigError("Firebase sender_id must be numeric")
    app_match = _APP_ID_RE.fullmatch(config["app_id"])
    if app_match is None:
        raise UfanetFirebaseConfigError("Firebase app_id is not an Android app id")
    if app_match.group(1) != sender_id:
        raise UfanetFirebaseConfigError(
            "Firebase sender_id does not match the app_id project number"
        )
    if not _PACKAGE_RE.fullmatch(config["package_name"]):
        raise UfanetFirebaseConfigError("Firebase package_name is invalid")
    return config


async def async_load_firebase_config(
    hass: HomeAssistant,
    configured_path: str,
) -> dict[str, str]:
    """Resolve and read Firebase configuration outside the event loop."""
    path = resolve_firebase_config_path(hass.config.config_dir, configured_path)
    return await hass.async_add_executor_job(load_firebase_config, path)


def firebase_config_fingerprint(config: dict[str, str]) -> str:
    """Return a non-reversible identity used to bind persisted FCM state."""
    identity = "\n".join(
        config[field]
        for field in ("project_id", "sender_id", "app_id", "package_name")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
