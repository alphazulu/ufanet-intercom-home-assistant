"""Shared pytest fixtures for the Ufanet Intercom custom integration."""

from pathlib import Path
import sys

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
