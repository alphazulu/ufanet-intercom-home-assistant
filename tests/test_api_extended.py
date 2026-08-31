"""Extended regression tests for Ufanet/UCAMS auth and media handling."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientError
import pytest

from custom_components.ufanet_intercom.api import (
    UfanetApi,
    UfanetAuthError,
    UfanetCallPreviewError,
    UfanetConnectionError,
    UfanetResponseError,
    _response_message,
    normalize_call_preview_url,
)


def _jwt(exp: int) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"x.{encoded}.x"


@pytest.fixture
def api() -> UfanetApi:
    return UfanetApi(
        MagicMock(),
        "AB123",
        "secret",
        ufanet_base_url="https://ufanet.test",
        ucams_base_url="https://ucams.test",
    )


@pytest.mark.asyncio
async def test_refresh_returns_early_for_valid_access(api: UfanetApi) -> None:
    api._access_token = _jwt(4_000_000_000)  # noqa: SLF001
    api._request_json = AsyncMock()  # type: ignore[method-assign]
    await api._async_refresh_ufanet()  # noqa: SLF001
    api._request_json.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_refresh_without_refresh_token_falls_back_to_login(api: UfanetApi) -> None:
    api._access_token = None  # noqa: SLF001
    api._refresh_token = None  # noqa: SLF001
    api._async_login_unlocked = AsyncMock()  # type: ignore[method-assign]
    await api._async_refresh_ufanet()  # noqa: SLF001
    api._async_login_unlocked.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_refresh_failure_falls_back_to_login(api: UfanetApi) -> None:
    api._access_token = None  # noqa: SLF001
    api._refresh_token = "refresh"  # noqa: SLF001
    api._request_json = AsyncMock(side_effect=UfanetAuthError("expired"))  # type: ignore[method-assign]
    api._async_login_unlocked = AsyncMock()  # type: ignore[method-assign]
    await api._async_refresh_ufanet()  # noqa: SLF001
    api._async_login_unlocked.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_ufanet_request_retries_once_after_auth_failure(api: UfanetApi) -> None:
    api._access_token = "old"  # noqa: SLF001
    api._ensure_ufanet_access = AsyncMock()  # type: ignore[method-assign]
    api._async_refresh_ufanet = AsyncMock()  # type: ignore[method-assign]
    api._request_json = AsyncMock(side_effect=[UfanetAuthError("expired"), {"ok": True}])  # type: ignore[method-assign]

    result = await api._async_ufanet_json("GET", "/resource")  # noqa: SLF001

    assert result == {"ok": True}
    assert api._access_token is None  # noqa: SLF001
    api._async_refresh_ufanet.assert_awaited_once()  # type: ignore[attr-defined]
    assert api._request_json.await_count == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_ufanet_request_propagates_second_auth_failure(api: UfanetApi) -> None:
    api._ensure_ufanet_access = AsyncMock()  # type: ignore[method-assign]
    api._async_refresh_ufanet = AsyncMock()  # type: ignore[method-assign]
    api._request_json = AsyncMock(side_effect=UfanetAuthError("expired"))  # type: ignore[method-assign]
    with pytest.raises(UfanetAuthError):
        await api._async_ufanet_json("GET", "/resource")  # noqa: SLF001
    assert api._request_json.await_count == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_call_media_requires_object(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value=[])  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="CCTV history"):
        await api.async_get_call_media("uuid")


@pytest.mark.asyncio
async def test_register_fcm_device_uses_confirmed_contract(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={})  # type: ignore[method-assign]

    await api.async_register_fcm_device(
        token="fcm-token",
        device_id="Home Assistant_uuid",
        title="Home Assistant",
        application="example.android.app",
    )

    api._async_ufanet_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "/api/v0/fcm/",
        json_body={
            "token": "fcm-token",
            "device_id": "Home Assistant_uuid",
            "title": "Home Assistant",
            "application": "example.android.app",
            "os": 0,
            "token_type": 0,
        },
    )


@pytest.mark.asyncio
async def test_temporary_guest_list_contract(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={"result": [{"token": "one"}, None]})  # type: ignore[method-assign]
    assert await api.async_get_temporary_guest_links() == [{"token": "one"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], {"result": "not-a-list"}])
async def test_temporary_guest_list_rejects_bad_shapes(api: UfanetApi, payload: object) -> None:
    api._async_ufanet_json = AsyncMock(return_value=payload)  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="guest-link"):
        await api.async_get_temporary_guest_links()


@pytest.mark.asyncio
async def test_shared_access_users_requires_data_list(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(return_value={"data": {}})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="data list"):
        await api.async_get_shared_access_users(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], {}, {"data": {}}, {"data": {"url": ""}}])
async def test_shared_invite_rejects_bad_shapes(api: UfanetApi, payload: object) -> None:
    api._async_ufanet_json = AsyncMock(return_value=payload)  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError):
        await api.async_create_shared_guest_invite(1)


@pytest.mark.asyncio
async def test_ucams_auth_fetches_token_and_invalidates_camera_cache(api: UfanetApi) -> None:
    api._access_token = _jwt(4_000_000_000)  # noqa: SLF001
    api._camera_cache["CAM"] = {"number": "CAM"}  # noqa: SLF001
    api._request_json = AsyncMock(return_value={"token": "ucams-token"})  # type: ignore[method-assign]

    await api._ensure_ucams_auth()  # noqa: SLF001

    assert api._ucams_token == "ucams-token"  # noqa: SLF001
    assert api._camera_cache == {}  # noqa: SLF001
    api._request_json.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_ucams_auth_rejects_missing_token(api: UfanetApi) -> None:
    api._access_token = _jwt(4_000_000_000)  # noqa: SLF001
    api._request_json = AsyncMock(return_value={})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="no token"):
        await api._ensure_ucams_auth()  # noqa: SLF001


@pytest.mark.asyncio
async def test_ucams_request_retries_once_after_auth_failure(api: UfanetApi) -> None:
    api._ucams_token = "old"  # noqa: SLF001
    api._camera_cache["CAM"] = {}  # noqa: SLF001
    api._ensure_ucams_auth = AsyncMock()  # type: ignore[method-assign]
    api._request_json = AsyncMock(side_effect=[UfanetAuthError("expired"), {"ok": True}])  # type: ignore[method-assign]

    assert await api._async_ucams_json("GET", "/x") == {"ok": True}  # noqa: SLF001
    assert api._ucams_token is None  # noqa: SLF001
    assert api._camera_cache == {}  # noqa: SLF001
    assert api._request_json.await_count == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_camera_returns_valid_cached_value(api: UfanetApi) -> None:
    cached = {
        "number": "CAM",
        "token_l": _jwt(4_000_000_000),
        "token_r": _jwt(4_000_000_000),
        "server": {"domain": "media.example", "screenshot_domain": "shots.example"},
    }
    api._camera_cache["CAM"] = cached  # noqa: SLF001
    api._async_ucams_json = AsyncMock()  # type: ignore[method-assign]
    assert await api.async_get_camera("CAM") is cached
    api._async_ucams_json.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_camera_fetches_and_caches_fresh_tokens(api: UfanetApi) -> None:
    camera = {
        "number": "CAM",
        "token_l": "live",
        "token_r": "archive",
        "server": {"domain": "media.example", "screenshot_domain": "shots.example"},
    }
    api._async_ucams_json = AsyncMock(return_value={"results": [camera]})  # type: ignore[method-assign]

    result = await api.async_get_camera("CAM", force=True)

    assert result == camera
    assert api._camera_cache["CAM"] == camera  # noqa: SLF001
    payload = api._async_ucams_json.await_args.kwargs["json_body"]  # type: ignore[attr-defined]
    assert payload["numbers"] == ["CAM"]
    assert payload["token_l_ttl"] == payload["token_r_ttl"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"results": []},
        {"results": [{"token_l": "live", "server": {"domain": "media.example"}}]},
        {},
    ],
)
async def test_camera_rejects_incomplete_responses(api: UfanetApi, payload: object) -> None:
    api._async_ucams_json = AsyncMock(return_value=payload)  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError):
        await api.async_get_camera("CAM", force=True)


@pytest.mark.asyncio
async def test_snapshot_uses_small_suffix(api: UfanetApi) -> None:
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        return_value={"token_l": "live", "server": {"screenshot_domain": "shots.example"}}
    )
    api._request_bytes = AsyncMock(return_value=b"jpeg")  # type: ignore[method-assign]

    assert await api.async_get_snapshot("CAM/1", small=True) == b"jpeg"
    api._request_bytes.assert_awaited_once_with(  # type: ignore[attr-defined]
        "https://shots.example/api/v0/screenshots/CAM%2F1~600.jpg", params={"token": "live"}
    )


@pytest.mark.asyncio
async def test_call_preview_download_upgrades_http_and_limits_size(
    api: UfanetApi,
) -> None:
    api._request_bytes = AsyncMock(return_value=b"mp4")  # type: ignore[method-assign]

    assert await api.async_get_call_preview(
        "https://media.example/preview.mp4?token=private"
    ) == b"mp4"
    api._request_bytes.assert_awaited_once_with(  # type: ignore[attr-defined]
        "https://media.example/preview.mp4?token=private",
        allow_redirects=False,
    )

    api._request_bytes.reset_mock()  # type: ignore[attr-defined]
    assert await api.async_get_call_preview(
        "http://media.example/preview.mp4?token=private"
    ) == b"mp4"
    api._request_bytes.assert_awaited_once_with(  # type: ignore[attr-defined]
        "https://media.example/preview.mp4?token=private",
        allow_redirects=False,
    )

    api._request_bytes = AsyncMock(return_value=b"")  # type: ignore[method-assign]
    with pytest.raises(UfanetCallPreviewError, match="empty") as err:
        await api.async_get_call_preview("https://media.example/preview.mp4")
    assert err.value.code == "empty_preview"

    api._request_bytes = AsyncMock(return_value=b"mp4")  # type: ignore[method-assign]

    with (
        patch(
            "custom_components.ufanet_intercom.api.CALL_PREVIEW_MAX_BYTES",
            2,
        ),
        pytest.raises(UfanetCallPreviewError, match="size limit") as err,
    ):
        await api.async_get_call_preview("https://media.example/preview.mp4")
    assert err.value.code == "size_limit"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://media.example/preview.mp4", "unsupported_scheme"),
        ("/relative/preview.mp4", "missing_host"),
        (
            "https://user:password@media.example/preview.mp4",
            "embedded_credentials",
        ),
        ("https://[broken", "invalid_url"),
    ],
)
def test_call_preview_normalizer_returns_only_fixed_safe_errors(
    url: str,
    code: str,
) -> None:
    with pytest.raises(UfanetCallPreviewError) as err:
        normalize_call_preview_url(url)
    assert err.value.code == code


def test_call_preview_normalizer_reports_https_upgrade() -> None:
    url = "http://media.example/preview.mp4?token=PRIVATE"
    normalized, upgraded = normalize_call_preview_url(url)

    assert normalized == "https://media.example/preview.mp4?token=PRIVATE"
    assert upgraded is True
    assert normalize_call_preview_url(normalized) == (normalized, False)


@pytest.mark.asyncio
async def test_snapshot_refreshes_camera_once_after_auth_failure(api: UfanetApi) -> None:
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"token_l": "old", "server": {"screenshot_domain": "old.example"}},
            {"token_l": "new", "server": {"screenshot_domain": "new.example"}},
        ]
    )
    api._request_bytes = AsyncMock(side_effect=[UfanetAuthError("expired"), b"fresh"])  # type: ignore[method-assign]

    assert await api.async_get_snapshot("CAM") == b"fresh"
    assert api.async_get_camera.await_args_list[1].kwargs == {"force": True}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_archive_ranges_refreshes_token_after_auth_failure(api: UfanetApi) -> None:
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"token_r": "old", "server": {"domain": "media.example"}},
            {"token_r": "new", "server": {"domain": "media.example"}},
        ]
    )
    api._request_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=[UfanetAuthError("expired"), [{"ranges": [{"from": 10, "duration": 30}]}]]
    )

    assert await api.async_get_archive_ranges("CAM") == [{"from": 10, "duration": 30}]
    assert api.async_get_camera.await_args_list[1].kwargs == {"force": True}  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"ranges": {}}, "bad"])
async def test_archive_ranges_rejects_bad_shapes(api: UfanetApi, payload: object) -> None:
    api.async_get_camera = AsyncMock(  # type: ignore[method-assign]
        return_value={"token_r": "archive", "server": {"domain": "media.example"}}
    )
    api._request_json = AsyncMock(return_value=payload)  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError):
        await api.async_get_archive_ranges("CAM")


@pytest.mark.asyncio
async def test_archive_ranges_requires_token_and_domain(api: UfanetApi) -> None:
    api.async_get_camera = AsyncMock(return_value={"server": {}})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="archive token"):
        await api.async_get_archive_ranges("CAM")


@pytest.mark.asyncio
async def test_archive_url_rejects_non_positive_duration(api: UfanetApi) -> None:
    with pytest.raises(UfanetResponseError, match="greater than zero"):
        await api.async_get_archive_url("CAM", 100, 0)


@pytest.mark.asyncio
async def test_archive_url_requires_camera_archive_fields(api: UfanetApi) -> None:
    api.async_get_archive_ranges = AsyncMock(return_value=[{"from": 100, "duration": 100}])  # type: ignore[method-assign]
    api.async_get_camera = AsyncMock(return_value={"server": {}})  # type: ignore[method-assign]
    with pytest.raises(UfanetResponseError, match="archive token"):
        await api.async_get_archive_url("CAM", 120, 30)


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_kind", ["ufanet", "ucams"])
async def test_request_json_requires_matching_token(api: UfanetApi, auth_kind: str) -> None:
    with pytest.raises(UfanetAuthError, match="token is unavailable"):
        await api._request_json("GET", "https://example.test/x", auth_kind=auth_kind)  # noqa: SLF001


@pytest.mark.asyncio
async def test_request_json_handles_empty_and_invalid_json(api: UfanetApi) -> None:
    empty = MagicMock(status=200)
    empty.text = AsyncMock(return_value="")
    invalid = MagicMock(status=200)
    invalid.text = AsyncMock(return_value="not-json")
    session = MagicMock()
    session.request = AsyncMock(side_effect=[empty, invalid])
    api._session = session  # noqa: SLF001

    assert await api._request_json("GET", "https://example.test/empty", auth_kind=None) == {}  # noqa: SLF001
    with pytest.raises(UfanetResponseError, match="Invalid JSON"):
        await api._request_json("GET", "https://example.test/bad", auth_kind=None)  # noqa: SLF001


@pytest.mark.asyncio
async def test_request_json_maps_client_error(api: UfanetApi) -> None:
    session = MagicMock()
    session.request = AsyncMock(side_effect=ClientError("offline"))
    api._session = session  # noqa: SLF001
    with pytest.raises(UfanetConnectionError, match="offline"):
        await api._request_json("GET", "https://example.test/x", auth_kind=None)  # noqa: SLF001


@pytest.mark.asyncio
async def test_request_bytes_maps_statuses_and_returns_body(api: UfanetApi) -> None:
    ok = MagicMock(status=200)
    ok.read = AsyncMock(return_value=b"jpeg")
    auth = MagicMock(status=403)
    auth.read = AsyncMock(return_value=b"")
    server = MagicMock(status=500)
    server.read = AsyncMock(return_value=b"")
    redirect = MagicMock(status=302)
    redirect.read = AsyncMock(return_value=b"")
    session = MagicMock()
    session.get = AsyncMock(side_effect=[ok, auth, server, redirect])
    api._session = session  # noqa: SLF001

    assert await api._request_bytes("https://shots.test/a") == b"jpeg"  # noqa: SLF001
    with pytest.raises(UfanetAuthError, match="403"):
        await api._request_bytes("https://shots.test/b")  # noqa: SLF001
    with pytest.raises(UfanetConnectionError, match="500"):
        await api._request_bytes("https://shots.test/c")  # noqa: SLF001
    with pytest.raises(UfanetConnectionError, match="redirect blocked"):
        await api._request_bytes(  # noqa: SLF001
            "https://media.test/private",
            allow_redirects=False,
        )


@pytest.mark.asyncio
async def test_request_bytes_maps_client_error(api: UfanetApi) -> None:
    session = MagicMock()
    session.get = AsyncMock(side_effect=ClientError("offline"))
    api._session = session  # noqa: SLF001
    with pytest.raises(UfanetConnectionError, match="offline"):
        await api._request_bytes("https://shots.test/a")  # noqa: SLF001


def test_response_message_prefers_structured_detail() -> None:
    assert _response_message(422, '{"detail":"bad data"}') == "HTTP 422: bad data"
    assert _response_message(400, '{"error":"bad request"}') == "HTTP 400: bad request"
    assert _response_message(500, "line one\nline two") == "HTTP 500: line one line two"
    assert _response_message(503, "") == "HTTP 503"
