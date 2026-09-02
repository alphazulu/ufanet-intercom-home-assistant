"""Tests for the Ufanet/UCAMS API client."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ufanet_intercom.api import (
    UfanetApi,
    UfanetAuthError,
    UfanetConnectionError,
    UfanetResponseError,
    _jwt_exp,
    _token_valid_for,
)


def _jwt(exp: int, **extra: object) -> str:
    payload = {"exp": exp, **extra}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"x.{encoded}.x"


@pytest.fixture
def api() -> UfanetApi:
    return UfanetApi(
        MagicMock(),
        " ab123 ",
        "secret",
        ufanet_base_url="https://ufanet.test",
        ucams_base_url="https://ucams.test",
    )


def test_username_is_normalized(api: UfanetApi) -> None:
    assert api.username == " AB123 "


def test_jwt_exp_parses_raw_and_prefixed_tokens() -> None:
    token = _jwt(1234567890)
    assert _jwt_exp(token) == 1234567890
    assert _jwt_exp(f"JWT {token}") == 1234567890
    assert _jwt_exp(f"Bearer {token}") == 1234567890
    assert _jwt_exp("not-a-jwt") is None
    assert _jwt_exp(None) is None


def test_token_valid_for_respects_safety_margin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("custom_components.ufanet_intercom.api.time.time", lambda: 1_000)
    assert _token_valid_for(_jwt(1_500), 120) is True
    assert _token_valid_for(_jwt(1_100), 120) is False
    # Opaque tokens without an exp claim are considered usable until the server rejects them.
    assert _token_valid_for("opaque-token", 120) is True
    assert _token_valid_for(None, 120) is False


@pytest.mark.asyncio
async def test_login_sets_tokens_and_clears_ucams_cache(api: UfanetApi) -> None:
    api._ucams_token = "old"  # noqa: SLF001
    api._camera_cache["cam"] = {"number": "cam"}  # noqa: SLF001
    api._request_json = AsyncMock(  # type: ignore[method-assign]
        return_value={"token": {"access": "access", "refresh": "refresh"}}
    )

    await api.async_login()

    assert api.access_token == "access"
    assert api._refresh_token == "refresh"  # noqa: SLF001
    assert api._ucams_token is None  # noqa: SLF001
    assert api._camera_cache == {}  # noqa: SLF001
    api._request_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "https://ufanet.test/api/v1/auth/auth_by_contract/",
        json_body={"contract": " AB123 ", "password": "secret"},
        auth_kind=None,
        auth_failure_statuses={400, 401, 403},
    )


@pytest.mark.asyncio
async def test_login_rejects_missing_tokens(api: UfanetApi) -> None:
    api._request_json = AsyncMock(return_value={})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="access/refresh"):
        await api.async_login()


@pytest.mark.asyncio
async def test_refresh_uses_refresh_token_and_invalidates_ucams(api: UfanetApi) -> None:
    api._access_token = None  # noqa: SLF001
    api._refresh_token = "JWT refresh-token"  # noqa: SLF001
    api._ucams_token = "old-ucams"  # noqa: SLF001
    api._camera_cache["cam"] = {}  # noqa: SLF001
    api._request_json = AsyncMock(  # type: ignore[method-assign]
        return_value={"access": "new-access", "refresh": "new-refresh"}
    )

    await api._async_refresh_ufanet()  # noqa: SLF001

    assert api._access_token == "new-access"  # noqa: SLF001
    assert api._refresh_token == "new-refresh"  # noqa: SLF001
    assert api._ucams_token is None  # noqa: SLF001
    assert api._camera_cache == {}  # noqa: SLF001
    api._request_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "https://ufanet.test/api/v1/auth/refresh/",
        json_body={"token": "refresh-token"},
        auth_kind=None,
    )


@pytest.mark.asyncio
async def test_skud_discovery_merges_shared_and_owned_by_id(api: UfanetApi) -> None:
    async def fake_request(method: str, path: str, **kwargs):
        assert method == "GET"
        if path == "/api/v0/skud/shared/":
            return [
                {"id": 1, "title": "shared copy"},
                {"id": 2, "title": "shared only"},
                "garbage",
            ]
        if path == "/api/v0/skud/":
            return [{"id": 1, "title": "owned copy"}]
        raise AssertionError(path)

    api._async_ufanet_json = fake_request  # type: ignore[method-assign]
    result = await api.async_get_skuds()
    by_id = {item["id"]: item for item in result}

    assert by_id[1]["title"] == "owned copy"
    assert by_id[1]["_is_shared"] is False
    assert by_id[2]["_is_shared"] is True


@pytest.mark.asyncio
async def test_key_recording_discovery_uses_confirmed_filter_and_paginates(
    api: UfanetApi,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_request(method: str, path: str, **kwargs):
        assert method == "POST"
        assert path == "/api/v0/intercoms/"
        calls.append(kwargs["json_body"])
        page = kwargs["json_body"]["page"]
        return {
            "result": {
                "page_info": {
                    "count": 2,
                    "next_page": 2 if page == 1 else None,
                    "prev_page": None if page == 1 else 1,
                },
                "intercoms": [
                    {
                        "id": page,
                        "has_key_recording_support": True,
                    }
                ],
            }
        }

    api._async_ufanet_json = fake_request  # type: ignore[method-assign]

    assert await api.async_get_key_recording_intercom_ids() == {1, 2}
    assert calls == [
        {
            "page": 1,
            "page_size": 10,
            "filters": {"has_key_recording_support": True},
        },
        {
            "page": 2,
            "page_size": 10,
            "filters": {"has_key_recording_support": True},
        },
    ]


@pytest.mark.asyncio
async def test_physical_keys_return_only_private_runtime_minimum(
    api: UfanetApi,
) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "data": {
                "keys": [
                    {
                        "id": 77,
                        "external_id": "must-not-be-retained",
                        "name": "Private key name",
                        "create_date": 1788220800,
                        "devices": ["7", 8],
                    }
                ]
            }
        }
    )

    assert await api.async_get_physical_keys() == [
        {"key_id": 77, "devices": (7, 8)}
    ]
    api._async_ufanet_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "/api/v4/key/list/",
    )


@pytest.mark.asyncio
async def test_key_passage_history_normalizes_confirmed_contract(
    api: UfanetApi,
) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "count": 1,
            "current_page": 0,
            "page_count": 1,
            "page_size": 25,
            "results": [
                {
                    "key": 77,
                    "key_name": "Front key",
                    "time_passage": 1788220800,
                }
            ],
        }
    )

    result = await api.async_get_key_passage_history(7)

    assert result == {
        "count": 1,
        "current_page": 0,
        "page_count": 1,
        "page_size": 25,
        "results": [
            {
                "key_id": 77,
                "key_name": "Front key",
                "timestamp": 1788220800,
            }
        ],
    }
    api._async_ufanet_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "/api/v4/key/skud/7/key/pass_history/",
        json_body={"page": 0, "page_size": 25},
    )


@pytest.mark.asyncio
async def test_empty_physical_keys_and_passages_are_valid(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"data": {"keys": []}},
            {
                "count": 0,
                "current_page": 0,
                "page_count": 0,
                "page_size": 25,
                "results": [],
            },
        ]
    )

    assert await api.async_get_physical_keys() == []
    assert (await api.async_get_key_passage_history(7))["results"] == []


@pytest.mark.asyncio
async def test_key_passage_rejects_unrepresentable_timestamp(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "count": 1,
            "current_page": 0,
            "page_count": 1,
            "page_size": 25,
            "results": [
                {
                    "key": 1,
                    "key_name": "Private name",
                    "time_passage": 253_402_300_800,
                }
            ],
        }
    )

    with pytest.raises(UfanetResponseError, match="invalid fields"):
        await api.async_get_key_passage_history(7)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"uuid": "1"}, "bad"], [{"uuid": "1"}]),
        ({"results": [{"uuid": "2"}, None]}, [{"uuid": "2"}]),
    ],
)
async def test_call_history_accepts_known_response_shapes(
    api: UfanetApi, payload: object, expected: list[dict[str, str]]
) -> None:
    api._async_ufanet_json = AsyncMock(return_value=payload)  # type: ignore[method-assign]
    assert await api.async_get_call_history(page=2, page_size=10) == expected
    api._async_ufanet_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "GET",
        "/api/v1/skuds/call-history/",
        params={"page": 2, "page_size": 10},
    )


@pytest.mark.asyncio
async def test_call_history_rejects_unknown_shape(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={"unexpected": []})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="call-history"):
        await api.async_get_call_history()


@pytest.mark.asyncio
async def test_temporary_guest_create_uses_minutes_as_string(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={"link": "https://guest.invalid/key"})  # type: ignore[method-assign]

    result = await api.async_create_temporary_guest_link(154273, 180)

    assert result["link"].endswith("/key")
    api._async_ufanet_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "/api/v1/skuds/skud_share_open/",
        json_body={"time": "180", "id": 154273},
    )


@pytest.mark.asyncio
async def test_temporary_guest_create_requires_link(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={"result": True})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="no link"):
        await api.async_create_temporary_guest_link(1, 60)


@pytest.mark.asyncio
async def test_shared_access_users_filter_non_objects(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={"data": [{"id": 1}, None, "bad"]})  # type: ignore[method-assign]
    assert await api.async_get_shared_access_users(7) == [{"id": 1}]


@pytest.mark.asyncio
async def test_shared_invite_returns_normalized_payload(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "status": "ok",
            "detail": "created",
            "data": {"url": "https://guest.invalid/invite", "access_id": 55},
        }
    )
    assert await api.async_create_shared_guest_invite(9) == {
        "url": "https://guest.invalid/invite",
        "access_id": 55,
        "status": "ok",
        "detail": "created",
    }


@pytest.mark.asyncio
async def test_shared_access_revoke_rejects_negative_ack(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={"status": "error"})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="not confirmed"):
        await api.async_revoke_shared_access(55)


@pytest.mark.asyncio
async def test_hls_url_escapes_camera_and_selects_tracks(api: UfanetApi) -> None:
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "token_l": "live token",
            "server": {"domain": "media.example"},
        }
    )
    url = await api.async_get_hls_url("CAM/1", stream_number=2)
    assert url == "https://media.example/CAM%2F1/index.m3u8?token=live+token&tracks=v2a1"


@pytest.mark.asyncio
async def test_archive_ranges_filters_invalid_and_tiny_ranges(api: UfanetApi) -> None:
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        return_value={"token_r": "archive", "server": {"domain": "media.example"}}
    )
    api._request_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "ranges": [
                {"from": 100, "duration": 60},
                {"from": "200", "duration": "4"},
                {"from": 300, "duration": 3},
                {"from": "bad", "duration": 10},
                None,
            ]
        }
    )

    assert await api.async_get_archive_ranges("CAM") == [
        {"from": 100, "duration": 60},
        {"from": 200, "duration": 4},
    ]


@pytest.mark.asyncio
async def test_archive_url_ums_clips_to_contiguous_range(api: UfanetApi) -> None:
    api.async_get_archive_ranges = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"from": 1_000, "duration": 100}]
    )
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "token_r": "archive-token",
            "server": {"domain": "media.example", "vendor_name": "UMS"},
        }
    )

    result = await api.async_get_archive_url("CAM/1", 1_080, 60)

    assert result["duration"] == 20
    assert result["requested_duration"] == 60
    assert result["url"] == (
        "https://media.example/CAM%2F1/archive-1080-20.m3u8?token=archive-token"
    )


@pytest.mark.asyncio
async def test_archive_url_non_ums_uses_tracks_path(api: UfanetApi) -> None:
    api.async_get_archive_ranges = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"from": 1_000, "duration": 500}]
    )
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "token_r": "archive-token",
            "server": {"domain": "media.example", "vendor_name": "OTHER"},
        }
    )
    result = await api.async_get_archive_url("CAM", 1_100, 30)
    assert result["url"] == (
        "https://media.example/CAM/tracks-v1a1/archive-1100-30.m3u8?token=archive-token"
    )


@pytest.mark.asyncio
async def test_archive_url_rejects_time_outside_ranges(api: UfanetApi) -> None:
    api.async_get_archive_ranges = AsyncMock(return_value=[{"from": 100, "duration": 50}])  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="outside recorded"):
        await api.async_get_archive_url("CAM", 200, 30)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("auth_kind", "token_attr", "token_value", "expected_header"),
    [
        ("ufanet", "_access_token", "JWT access", "JWT access"),
        ("ucams", "_ucams_token", "Bearer ucams", "Bearer ucams"),
    ],
)
async def test_request_json_uses_correct_authorization_scheme(
    api: UfanetApi,
    auth_kind: str,
    token_attr: str,
    token_value: str,
    expected_header: str,
) -> None:
    response = MagicMock(status=200)
    response.text = AsyncMock(return_value='{"ok": true}')
    session = MagicMock()
    session.request = AsyncMock(return_value=response)
    api._session = session  # noqa: SLF001
    setattr(api, token_attr, token_value)

    assert await api._request_json("GET", "https://example.test/x", auth_kind=auth_kind) == {"ok": True}  # noqa: SLF001
    headers = session.request.await_args.kwargs["headers"]
    assert headers["Authorization"] == expected_header


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "exc_type"),
    [
        (401, UfanetAuthError),
        (422, UfanetResponseError),
        (500, UfanetConnectionError),
    ],
)
async def test_request_json_maps_http_errors(
    api: UfanetApi, status: int, exc_type: type[Exception]
) -> None:
    response = MagicMock(status=status)
    response.text = AsyncMock(return_value='{"detail": "failure"}')
    session = MagicMock()
    session.request = AsyncMock(return_value=response)
    api._session = session  # noqa: SLF001

    with pytest.raises(exc_type, match="failure"):
        await api._request_json("GET", "https://example.test/x", auth_kind=None)  # noqa: SLF001


def test_diagnostic_auth_state_never_returns_token_values(api: UfanetApi) -> None:
    api._access_token = _jwt(2_000)  # noqa: SLF001
    api._refresh_token = _jwt(3_000)  # noqa: SLF001
    api._ucams_token = _jwt(4_000)  # noqa: SLF001
    api._camera_cache["one"] = {}  # noqa: SLF001

    state = api.diagnostic_auth_state()

    assert state == {
        "ufanet_access_present": True,
        "ufanet_access_expires_at": 2_000,
        "ufanet_refresh_present": True,
        "ufanet_refresh_expires_at": 3_000,
        "ucams_access_present": True,
        "ucams_access_expires_at": 4_000,
        "cached_camera_count": 1,
    }
    serialized = json.dumps(state)
    assert api._access_token not in serialized  # noqa: SLF001
    assert api._refresh_token not in serialized  # noqa: SLF001
    assert api._ucams_token not in serialized  # noqa: SLF001
