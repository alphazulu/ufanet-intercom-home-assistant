"""Privacy and live-contract tests for the physical-key passage schema probe."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "tools"
    / "research"
    / "key_passage_probe_py"
    / "schema_probe.py"
)
SPEC = importlib.util.spec_from_file_location("ufanet_key_passage_schema_probe", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_safe_shape_summary_exposes_only_field_names_types_and_counts() -> None:
    response = probe.SafeResponse(
        status=200,
        content_type="application/json",
        body_length=321,
        payload={
            "count": 1,
            "current_page": 0,
            "page_count": 0,
            "page_size": 5,
            "results": [
                {
                    "key": "987654321",
                    "key_name": "PRIVATE KEY NAME",
                    "time_passage": 1_788_000_000,
                    "private_future_value": "DO NOT PRINT THIS VALUE",
                }
            ],
        },
    )

    summary = probe._safe_envelope_summary(response)

    assert "http=200" in summary
    assert "results_len=1" in summary
    assert "key:str" in summary
    assert "key_name:str" in summary
    assert "time_passage:int" in summary
    assert "private_future_value:str" in summary
    for private_value in (
        "987654321",
        "PRIVATE KEY NAME",
        "1788000000",
        "DO NOT PRINT THIS VALUE",
    ):
        assert private_value not in summary


def test_android_contract_accepts_live_numeric_string_key() -> None:
    response = probe.SafeResponse(
        status=200,
        content_type="application/json",
        body_length=100,
        payload={
            "count": 1,
            "current_page": 0,
            "page_count": 0,
            "page_size": 5,
            "results": [
                {
                    "key": "987654321",
                    "key_name": "PRIVATE KEY NAME",
                    "time_passage": 1_788_000_000,
                }
            ],
        },
    )

    assert probe._android_compatible_contract(response) == "ok"


def test_schema_probe_uses_private_external_id_filter_without_raw_output() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert '"filters": {"key": target_key["external_id"]}' in source
    assert '"external_id": external_id' in source
    assert "raw response" in source
    assert "print(target_key" not in source
    assert "print(keys" not in source
    assert "print(external_id" not in source
