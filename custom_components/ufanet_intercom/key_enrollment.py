"""Physical-key enrollment support for Ufanet intercoms."""

from __future__ import annotations

from .api import UfanetApi

KEY_ENROLLMENT_WINDOW_SECONDS = 60


async def async_start_physical_key_enrollment(api: UfanetApi, skud_id: int) -> None:
    """Arm one intercom for physical-key auto-collection.

    The Android application uses this endpoint to start a 60-second collection
    window. A successful response means only that enrollment mode was enabled;
    it does not prove that a physical key was subsequently presented or saved.
    """
    await api._async_ufanet_json(  # noqa: SLF001 - package-internal transport wrapper
        "POST",
        f"/api/v4/key/skud/{int(skud_id)}/auto_collect/enable/",
    )
