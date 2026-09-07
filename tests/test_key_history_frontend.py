"""Static regression tests for the physical-key history Lovelace extension."""

from __future__ import annotations

from pathlib import Path


FRONTEND = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ufanet_intercom"
    / "frontend"
    / "ufanet-key-history-card.js"
)


def test_key_history_frontend_selects_key_and_loads_lower_panel() -> None:
    source = FRONTEND.read_text(encoding="utf-8")

    assert '"get_physical_key_passages"' in source
    assert "physical-key-history-section" in source
    assert "История проходов" in source
    assert "_selectPhysicalKeyForHistory" in source
    assert 'key_ref: selected.key_ref' in source
    assert 'typeof item.occurred_at === "string"' in source
    assert "Показать ещё" in source


def test_key_history_frontend_does_not_render_provider_identifiers_or_delete() -> None:
    source = FRONTEND.read_text(encoding="utf-8")

    # The browser receives only opaque key_ref plus privacy-safe passage times.
    assert "provider key ID" not in source
    assert "external_id" not in source
    assert "key_id" not in source
    assert "time_passage" not in source
    assert "key_name" not in source
    assert "delete_physical_key" not in source
    assert "Удалить ключ" not in source
