"""Contract and privacy tests for the UCAMS analytics research probe."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "tools"
    / "research"
    / "ucams_analytics_probe_py"
    / "probe.py"
)
SPEC = importlib.util.spec_from_file_location(
    "ufanet_ucams_analytics_probe", SCRIPT_PATH
)
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
async def test_audit_uses_only_safe_types_and_never_prints_private_values(
    capsys,
) -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                [
                    {
                        "id": 154273,
                        "address": "Private address",
                        "cctv_number": "PRIVATE-CAMERA-7",
                    }
                ],
            ),
            _FakeResponse(200, {"token": "private-ucams-token"}),
            _FakeResponse(
                200,
                {
                    "results": [
                        {
                            "number": "PRIVATE-CAMERA-7",
                            "analytics": [
                                "motion_alarm",
                                "perimeter_security",
                                "face_recognition",
                            ],
                            "tariff": {"name": "Private tariff", "dvr_hours": 72},
                            "timezone": "Private/Zone",
                        }
                    ]
                },
            ),
            _FakeResponse(
                200,
                [
                    {
                        "id": 918273,
                        "time": 1788220800,
                        "type": "motion_alarm",
                        "camera_number": "PRIVATE-CAMERA-7",
                        "full_screenshot_url": "https://private/image.jpg?token=secret",
                        "text": "Private event text",
                        "length": 42,
                        "private_server_field": "Private server value",
                    }
                ],
            ),
            _FakeResponse(
                200,
                {
                    "results": [
                        {
                            "id": 918274,
                            "time": 1788220801,
                            "type": "perimeter_security",
                            "camera_number": "PRIVATE-CAMERA-7",
                        }
                    ]
                },
            ),
        ]
    )

    await probe.audit_ucams_analytics(
        session,
        "private-ufanet-token",
        "https://ufanet.test",
        "https://ucams.test",
        hours=24,
        limit=5,
        max_cameras=5,
        now=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
    )

    assert [call[0] for call in session.calls] == [
        "GET",
        "POST",
        "POST",
        "POST",
        "POST",
    ]
    assert [call[1] for call in session.calls] == [
        "https://ufanet.test/api/v0/skud/shared/",
        "https://ucams.test/api/v0/auth/",
        "https://ucams.test/api/v0/cameras/this/",
        "https://ucams.test/api/v0/analytics/motion_alarm/report/",
        "https://ucams.test/api/v0/analytics/perimeter_security/report/",
    ]
    assert session.calls[0][2]["headers"]["Authorization"] == (
        "JWT private-ufanet-token"
    )
    assert session.calls[1][2]["headers"]["Authorization"] == (
        "JWT private-ufanet-token"
    )
    assert session.calls[1][2]["params"] == {"ttl": 20_800}
    assert session.calls[2][2]["headers"]["Authorization"] == (
        "Bearer private-ucams-token"
    )
    assert session.calls[2][2]["json"] == {
        "fields": ["number", "analytics", "tariff", "timezone"],
        "numbers": ["PRIVATE-CAMERA-7"],
    }
    assert session.calls[3][2]["json"] == {
        "camera_number": "PRIVATE-CAMERA-7",
        "start": "2026-09-01T12:00:00Z",
        "end": "2026-09-02T12:00:00Z",
        "limit": 5,
        "order_by_date": "desc",
    }

    output = capsys.readouterr().out
    for private_value in (
        "private-ufanet-token",
        "private-ucams-token",
        "PRIVATE-CAMERA-7",
        "Private address",
        "Private tariff",
        "Private/Zone",
        "918273",
        "1788220800",
        "https://private/image.jpg?token=secret",
        "Private event text",
        "private_server_field",
        "Private server value",
        "face_recognition",
    ):
        assert private_value not in output
    assert "motion_alarm=1 perimeter_security=1 other_analytics=1" in output
    assert "motion_alarm events [1]: returned=1 valid_timestamps=1" in output
    assert "unknown_fields=1 content_fields_present=true" in output
    assert "perimeter_security events [1]: returned=1" in output


@pytest.mark.asyncio
async def test_no_intercom_camera_skips_ucams_auth_and_events(capsys) -> None:
    session = _FakeSession([_FakeResponse(200, [{"id": 1, "cctv_number": None}])])

    await probe.audit_ucams_analytics(
        session,
        "access-token",
        "https://ufanet.test",
        "https://ucams.test",
        hours=24,
        limit=5,
        max_cameras=5,
    )

    assert len(session.calls) == 1
    assert "skipped=no_intercom_camera" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_no_safe_analytics_type_skips_event_requests(capsys) -> None:
    session = _FakeSession(
        [
            _FakeResponse(200, [{"cctv_number": "PRIVATE-CAMERA"}]),
            _FakeResponse(200, {"token": "ucams-token"}),
            _FakeResponse(
                200,
                {
                    "results": [
                        {
                            "number": "PRIVATE-CAMERA",
                            "analytics": ["face_recognition"],
                            "tariff": None,
                        }
                    ]
                },
            ),
        ]
    )

    await probe.audit_ucams_analytics(
        session,
        "access-token",
        "https://ufanet.test",
        "https://ucams.test",
        hours=24,
        limit=5,
        max_cameras=5,
    )

    assert len(session.calls) == 3
    output = capsys.readouterr().out
    assert "other_analytics=1" in output
    assert "face_recognition" not in output
    assert "skipped=no_safe_type_declared" in output


@pytest.mark.parametrize(
    ("payload", "envelope"),
    [
        ([], "list"),
        ({"results": []}, "dict.results"),
        ({"events": []}, "dict.events"),
        ({"data": []}, "dict.data"),
        ({"data": {"results": []}}, "dict.data.results"),
        ({"opaque-private-key": []}, "dict.single_list"),
    ],
)
def test_event_envelopes_are_summarized_without_printing_keys(
    payload: object,
    envelope: str,
) -> None:
    summary = probe.parse_event_summary(payload, "motion_alarm")
    assert summary.returned == 0
    assert summary.envelope == envelope


def test_event_summary_counts_mismatch_and_discards_sensitive_content() -> None:
    summary = probe.parse_event_summary(
        [
            {
                "id": 1,
                "time": 100,
                "type": "car_number",
                "number": "PRIVATE-PLATE",
                "plate_screenshot_url": "https://private/plate.jpg",
            }
        ],
        "motion_alarm",
    )

    assert summary.returned == 1
    assert summary.valid_timestamps == 1
    assert summary.unexpected_types == 1
    assert summary.content_fields_present is True
    assert summary.unknown_fields == 2
    assert summary.schema_fields == ("id", "time", "type")


@pytest.mark.parametrize(
    ("parser", "payload", "message"),
    [
        (probe.parse_intercom_camera_numbers, {}, "intercom discovery"),
        (
            probe.parse_intercom_camera_numbers,
            [{"cctv_number": {"private": "value"}}],
            "invalid camera",
        ),
        (probe.parse_camera_capabilities, [], "camera metadata"),
        (
            probe.parse_camera_capabilities,
            {"results": [{"number": "CAM", "analytics": "motion_alarm"}]},
            "invalid analytics",
        ),
    ],
)
def test_schema_validation_uses_fixed_safe_errors(parser, payload, message) -> None:
    with pytest.raises(probe.ProbeError, match=message):
        parser(payload)


def test_unknown_event_envelope_uses_fixed_safe_error() -> None:
    with pytest.raises(probe.ProbeError, match="unknown envelope"):
        probe.parse_event_summary(
            {"PRIVATE-CAMERA": {"secret": "value"}}, "motion_alarm"
        )


@pytest.mark.asyncio
async def test_http_error_does_not_echo_response_body_or_token(capsys) -> None:
    session = _FakeSession(
        [_FakeResponse(403, {"token": "private-token", "detail": "Private detail"})]
    )

    with pytest.raises(probe.ProbeError, match="HTTP 403"):
        await probe._request_json(
            session,
            "POST",
            "https://example.test",
            "/private",
            "safe label",
            auth_scheme="Bearer",
            auth_token="private-token",
        )

    output = capsys.readouterr().out
    assert "private-token" not in output
    assert "Private detail" not in output


@pytest.mark.asyncio
async def test_authentication_contracts_use_correct_schemes() -> None:
    session = _FakeSession(
        [
            _FakeResponse(200, {"token": {"access": "ufanet-access"}}),
            _FakeResponse(200, {"token": "ucams-access"}),
        ]
    )

    ufanet = await probe.authenticate_ufanet(
        session,
        "contract",
        "password",
        "https://ufanet.test",
    )
    ucams = await probe.authenticate_ucams(
        session,
        ufanet,
        "https://ucams.test",
    )

    assert ufanet == "ufanet-access"
    assert ucams == "ucams-access"
    assert session.calls[0][2]["json"] == {
        "contract": "CONTRACT",
        "password": "password",
    }
    assert session.calls[1][2]["headers"]["Authorization"] == "JWT ufanet-access"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["probe.py", "--hours", "0"], "--hours"),
        (["probe.py", "--limit", "26"], "--limit"),
        (["probe.py", "--max-cameras", "11"], "--max-cameras"),
    ],
)
def test_cli_rejects_unsafe_bounds(monkeypatch, capsys, args, message) -> None:
    monkeypatch.setattr(sys, "argv", args)
    assert probe.main() == 2
    assert message in capsys.readouterr().err
