from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "custom_components/ufanet_intercom/services.py",
    "from .analytics import async_get_motion_timeline_events\n",
    "from .analytics import (\n    async_get_motion_capabilities,\n    async_get_motion_timeline_events,\n)\n",
)

old = '''        api: UfanetApi = runtime["api"]
        skud_id = int(skud["id"])
        requested_date: date = call.data["date"]

        analytics_coordinator = runtime.get("analytics_coordinator")
        analytics_data = getattr(analytics_coordinator, "data", None)
        supported = isinstance(analytics_data, dict) and skud_id in analytics_data

        controllers = runtime.get("archive_controllers") or {}
'''
new = '''        api: UfanetApi = runtime["api"]
        skud_id = int(skud["id"])
        camera_number = _camera_number(skud)
        requested_date: date = call.data["date"]

        analytics_coordinator = runtime.get("analytics_coordinator")
        analytics_data = getattr(analytics_coordinator, "data", None)
        analytics_snapshot_ready = (
            analytics_coordinator is not None
            and bool(getattr(analytics_coordinator, "last_update_success", False))
            and isinstance(analytics_data, dict)
        )
        try:
            if analytics_snapshot_ready:
                supported = skud_id in analytics_data
            else:
                supported = camera_number in await async_get_motion_capabilities(
                    api,
                    [camera_number],
                )
        except UfanetApiError:
            raise HomeAssistantError(
                "Unable to load motion timeline capabilities"
            ) from None

        controllers = runtime.get("archive_controllers") or {}
'''
replace("custom_components/ufanet_intercom/services.py", old, new)
replace(
    "custom_components/ufanet_intercom/services.py",
    '''        camera_number = _camera_number(skud)
        day_start = datetime.combine(requested_date, time.min, tzinfo=zone)
''',
    '''        day_start = datetime.combine(requested_date, time.min, tzinfo=zone)
''',
)

replace(
    "tests/test_motion_timeline_service.py",
    '''    analytics = SimpleNamespace(data={7: {"supported": True}})
''',
    '''    analytics = SimpleNamespace(
        data={7: {"supported": True}},
        last_update_success=True,
    )
''',
)

marker = '''@pytest.mark.asyncio
async def test_motion_timeline_service_skips_unsupported_camera(hass) -> None:
'''
addition = '''@pytest.mark.asyncio
async def test_motion_timeline_service_recovers_capability_when_snapshot_unavailable(hass) -> None:
    device, analytics = _install_runtime(hass)
    analytics.data = None
    analytics.last_update_success = False
    event_time = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)

    with (
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_capabilities",
            AsyncMock(return_value={"PRIVATE-CAMERA"}),
        ) as capabilities,
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_timeline_events",
            AsyncMock(return_value=[event_time]),
        ) as loader,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_MOTION_EVENTS,
            {"device_id": device.id, "date": "2026-09-02"},
            blocking=True,
            return_response=True,
        )

    capabilities.assert_awaited_once()
    loader.assert_awaited_once()
    assert response["supported"] is True
    assert response["count"] == 1


'''
path = ROOT / "tests/test_motion_timeline_service.py"
text = path.read_text(encoding="utf-8")
if text.count(marker) != 1:
    raise RuntimeError("service recovery test marker not found exactly once")
path.write_text(text.replace(marker, addition + marker, 1), encoding="utf-8")

# Ensure known-unsupported snapshot does not perform provider capability discovery.
replace(
    "tests/test_motion_timeline_service.py",
    '''    analytics.data = {}

    with patch(
        "custom_components.ufanet_intercom.services.async_get_motion_timeline_events",
        AsyncMock(),
    ) as loader:
''',
    '''    analytics.data = {}
    analytics.last_update_success = True

    with (
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_capabilities",
            AsyncMock(),
        ) as capabilities,
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_timeline_events",
            AsyncMock(),
        ) as loader,
    ):
''',
)
replace(
    "tests/test_motion_timeline_service.py",
    '''    assert response["supported"] is False
    assert response["events"] == []
    loader.assert_not_awaited()
''',
    '''    assert response["supported"] is False
    assert response["events"] == []
    capabilities.assert_not_awaited()
    loader.assert_not_awaited()
''',
)

(ROOT / ".github/workflows/apply-motion-recovery-patch.yml").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
