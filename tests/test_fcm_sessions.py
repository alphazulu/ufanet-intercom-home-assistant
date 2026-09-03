"""Security and privacy tests for authorized FCM session inventory."""

from __future__ import annotations

from custom_components.ufanet_intercom.fcm_sessions import (
    authorized_session_ref,
    build_authorized_session_inventory,
    public_authorized_sessions,
    resolve_authorized_session,
)


def _row(device_id: str, title: object = "Phone", os_display: object = "Android"):
    return {
        "device_id": device_id,
        "title": title,
        "last_update": "2026-09-03T01:02:03Z",
        "is_call_access": True,
        "os_display": os_display,
    }


def test_session_refs_are_stable_opaque_and_entry_scoped() -> None:
    device_id = "private-provider-device-id"
    first = authorized_session_ref("entry-one", device_id)
    assert first == authorized_session_ref("entry-one", device_id)
    assert first != authorized_session_ref("entry-two", device_id)
    assert len(first) == 24
    assert device_id not in first


def test_public_inventory_hides_device_ids_and_marks_ha_owned() -> None:
    inventory = build_authorized_session_inventory(
        "entry-one",
        [
            _row("ha-private", title="Home Assistant", os_display="Android 16"),
            _row("phone-private", title="My Phone", os_display="iPhone"),
        ],
        {"ha-private"},
    )
    public = public_authorized_sessions(inventory)
    serialized = str(public)
    assert "ha-private" not in serialized
    assert "phone-private" not in serialized
    assert public[0]["last_update"].endswith("+00:00")
    assert {row["platform"] for row in public} == {"android", "ios"}
    protected = [row for row in public if row["protected"]]
    assert len(protected) == 1
    assert protected[0]["protected_reason"] == "home_assistant"


def test_invalid_provider_titles_and_platforms_are_bounded() -> None:
    inventory = build_authorized_session_inventory(
        "entry",
        [_row("one", title="bad\nname", os_display="bad\x00os")],
        set(),
    )
    public = public_authorized_sessions(inventory)[0]
    assert public["title"] == "Unknown device"
    assert public["platform"] == "unknown"


def test_resolve_uses_only_opaque_reference() -> None:
    inventory = build_authorized_session_inventory("entry", [_row("private")], set())
    ref = inventory[0]["public"]["session_ref"]
    assert resolve_authorized_session(inventory, ref) is inventory[0]
    assert resolve_authorized_session(inventory, "0" * 24) is None
