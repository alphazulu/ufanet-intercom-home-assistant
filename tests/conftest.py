"""Shared pytest fixtures for the Ufanet Intercom custom integration."""

from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


# pytest-homeassistant-custom-component uses an import mode where the repository
# root is not guaranteed to be on sys.path during test collection. Add it
# explicitly so custom_components can be imported without changing the runtime
# integration package layout.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load integrations from custom_components."""
    yield


@pytest.fixture(autouse=True)
def isolate_optional_motion_coordinator_in_legacy_lifecycle_tests(
    request,
    monkeypatch,
):
    """Keep legacy lifecycle tests focused on lifecycle wiring, not cloud polling."""
    if request.node.path.name != "test_lifecycle.py":
        yield
        return

    coordinator = MagicMock()
    coordinator.data = {}
    coordinator.new_events = {}
    coordinator.async_initialize = AsyncMock()
    coordinator.async_refresh = AsyncMock()
    coordinator.async_add_listener.return_value = lambda: None
    monkeypatch.setattr(
        "custom_components.ufanet_intercom.UfanetMotionAnalyticsCoordinator",
        MagicMock(return_value=coordinator),
    )
    yield
