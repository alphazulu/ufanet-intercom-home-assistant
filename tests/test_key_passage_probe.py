"""Contract and privacy tests for the physical-key research probe."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "tools"
    / "research"
    / "key_passage_probe_py"
    / "probe.py"
)
SPEC = importlib.util.spec_from_file_location("ufanet_key_passage_probe", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


class _FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._text = json.dumps(payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_audit_uses_read_only_contract_and_never_prints_private_values(
    capsys,
) -> None:
    session = _FakeSession(
        [
            _FakeResponse(200, {"status": "ok", "data": {"features": ["keys"]}}),
            _FakeResponse(
                200,
                {
                    "result": {
                        "page_info": {"page": 1},
                        "intercoms": [
                            {
                                "id": 154273,
                                "address": "Private address",
                                "has_key_recording_support": True,
                            }
                        ],
                    }
                },
            ),
            _FakeResponse(
                200,
                {
                    "data": {
                        "keys": [
                            {
                                "id": 77,
                                "external_id": "private-external-id",
                                "name": "Private key name",
                                "create_date": 1720000000,
                                "devices": ["154273"],
                            }
                        ]
                    }
                },
            ),
            _FakeResponse(
                200,
                {
                    "count": 1,
                    "current_page": 0,
                    "page_count": 1,
                    "page_size": 5,
                    "results": [
                        {
                            "key": 77,
                            "key_name": "Private key name",
                            "time_passage": 1788220800,
                        }
                    ],
                },
            ),
        ]
    )

    await probe.audit_key_passages(
        session,
        "private-access-token",
        "https://example.test",
        page_size=5,
        max_intercoms=10,
    )

    assert [call[0] for call in session.calls] == ["GET", "POST", "POST", "POST"]
    assert [call[1] for call in session.calls] == [
        "https://example.test/api/v4/skud/features/",
        "https://example.test/api/v0/intercoms/",
        "https://example.test/api/v4/key/list/",
        "https://example.test/api/v4/key/skud/154273/key/pass_history/",
    ]
    assert session.calls[1][2]["json"] == {
        "page": 1,
        "page_size": 10,
        "filters": {"has_key_recording_support": True},
    }
    assert "json" not in session.calls[2][2]
    assert session.calls[3][2]["json"] == {"page": 0, "page_size": 5}
    assert all(
        call[2]["headers"]["Authorization"] == "JWT private-access-token"
        for call in session.calls
    )

    output = capsys.readouterr().out
    for private_value in (
        "private-access-token",
        "154273",
        "Private address",
        "private-external-id",
        "Private key name",
        "1788220800",
    ):
        assert private_value not in output
    assert "physical keys: count=1" in output
    assert (
        "passage history [1]: total=1 returned=1 valid_timestamps=1 linked_keys=1"
        in output
    )


@pytest.mark.asyncio
async def test_no_supported_intercom_skips_passage_request(capsys) -> None:
    session = _FakeSession(
        [
            _FakeResponse(200, {"data": {"features": ["keys"]}}),
            _FakeResponse(
                200,
                {
                    "result": {
                        "intercoms": [{"id": 1, "has_key_recording_support": False}]
                    }
                },
            ),
            _FakeResponse(200, {"data": {"keys": []}}),
        ]
    )

    await probe.audit_key_passages(
        session,
        "access-token",
        "https://example.test",
        page_size=5,
        max_intercoms=10,
    )

    assert len(session.calls) == 3
    assert "skipped=no_supported_intercom" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"data": {"features": "keys"}}, "features"),
        ({"result": {"intercoms": [{"id": "private"}]}}, "invalid id"),
        ({"data": {"keys": [{"id": 1}]}}, "external_id"),
        (
            {
                "count": 1,
                "current_page": 0,
                "page_count": 1,
                "page_size": 5,
                "results": [{"key": 1, "key_name": "private", "time_passage": "bad"}],
            },
            "time_passage",
        ),
    ],
)
def test_schema_validation_uses_fixed_safe_errors(payload, message) -> None:
    parser = {
        "features": probe.parse_features,
        "invalid id": probe.parse_intercoms,
        "external_id": probe.parse_keys,
        "time_passage": probe.parse_passages,
    }[message]

    with pytest.raises(probe.ProbeError, match=message):
        parser(payload)


@pytest.mark.asyncio
async def test_http_error_does_not_echo_response_body(capsys) -> None:
    session = _FakeSession([_FakeResponse(403, {"external_id": "private-external-id"})])

    with pytest.raises(probe.ProbeError, match="HTTP 403"):
        await probe._request_json(
            session,
            "POST",
            "https://example.test",
            "/private",
            "safe label",
            access_token="private-access-token",
        )

    output = capsys.readouterr().out
    assert "private-external-id" not in output
    assert "private-access-token" not in output
