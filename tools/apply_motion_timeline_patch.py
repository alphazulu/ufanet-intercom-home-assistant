from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{path}: expected {count} occurrence(s), found {found}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


def append_before(path: str, marker: str, addition: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if addition.strip() in text:
        return
    if marker not in text:
        raise RuntimeError(f"{path}: marker not found")
    target.write_text(text.replace(marker, addition + marker, 1), encoding="utf-8")


# Public privacy boundary for archive timeline rendering.
replace(
    "custom_components/ufanet_intercom/analytics.py",
    "    return _merge_motion_events(older, newer)\n\n\nclass UfanetMotionAnalyticsCoordinator(\n",
    "    return _merge_motion_events(older, newer)\n\n\nasync def async_get_motion_timeline_events(\n    api: UfanetApi,\n    camera_number: str,\n    *,\n    start: datetime,\n    end: datetime,\n) -> list[datetime]:\n    \"\"\"Return only distinct event timestamps for an explicit archive window.\n\n    Provider event IDs remain inside the analytics boundary and are discarded\n    before an authenticated Home Assistant response service sees the data.\n    \"\"\"\n    events = await _async_collect_motion_events(\n        api,\n        camera_number,\n        start=start,\n        end=end,\n    )\n    return sorted({event[\"occurred_at\"] for event in events})\n\n\nclass UfanetMotionAnalyticsCoordinator(\n",
)

replace(
    "custom_components/ufanet_intercom/const.py",
    'SERVICE_GET_CALL_EVENTS = "get_call_events"\n',
    'SERVICE_GET_CALL_EVENTS = "get_call_events"\nSERVICE_GET_MOTION_EVENTS = "get_motion_events"\n',
)

replace(
    "custom_components/ufanet_intercom/services.py",
    "from .api import (\n",
    "from .analytics import async_get_motion_timeline_events\nfrom .api import (\n",
)
replace(
    "custom_components/ufanet_intercom/services.py",
    "    SERVICE_GET_CALL_EVENTS,\n",
    "    SERVICE_GET_CALL_EVENTS,\n    SERVICE_GET_MOTION_EVENTS,\n",
)
replace(
    "custom_components/ufanet_intercom/services.py",
    "GET_CALL_EVENTS_SCHEMA = vol.Schema(\n    {\n        vol.Required(ATTR_DEVICE_ID): cv.string,\n        vol.Required(\"date\"): cv.date,\n    }\n)\n\nGET_GUEST_ACCESS_SCHEMA = vol.Schema(\n",
    "GET_CALL_EVENTS_SCHEMA = vol.Schema(\n    {\n        vol.Required(ATTR_DEVICE_ID): cv.string,\n        vol.Required(\"date\"): cv.date,\n    }\n)\n\nGET_MOTION_EVENTS_SCHEMA = vol.Schema(\n    {\n        vol.Required(ATTR_DEVICE_ID): cv.string,\n        vol.Required(\"date\"): cv.date,\n    }\n)\n\nGET_GUEST_ACCESS_SCHEMA = vol.Schema(\n",
)
replace(
    "custom_components/ufanet_intercom/services.py",
    "        return {\n            \"device_id\": call.data[ATTR_DEVICE_ID],\n            \"skud_id\": int(skud[\"id\"]),\n            \"camera_number\": camera_number,\n            \"timezone\": timezone_name,\n            \"date\": requested_date.isoformat(),\n            \"count\": len(matching),\n            \"events\": matching,\n        }\n\n    async def async_get_last_call_preview_url(\n",
    "        return {\n            \"device_id\": call.data[ATTR_DEVICE_ID],\n            \"skud_id\": int(skud[\"id\"]),\n            \"camera_number\": camera_number,\n            \"timezone\": timezone_name,\n            \"date\": requested_date.isoformat(),\n            \"count\": len(matching),\n            \"events\": matching,\n        }\n\n    async def async_get_motion_events(call: ServiceCall) -> ServiceResponse:\n        \"\"\"Return privacy-minimized motion points for one archive-local day.\"\"\"\n        runtime, skud = _resolve_device_runtime(hass, call.data[ATTR_DEVICE_ID])\n        api: UfanetApi = runtime[\"api\"]\n        skud_id = int(skud[\"id\"])\n        requested_date: date = call.data[\"date\"]\n\n        analytics_coordinator = runtime.get(\"analytics_coordinator\")\n        analytics_data = getattr(analytics_coordinator, \"data\", None)\n        supported = isinstance(analytics_data, dict) and skud_id in analytics_data\n\n        controllers = runtime.get(\"archive_controllers\") or {}\n        controller = controllers.get(skud_id)\n        timezone_name = str(\n            getattr(controller, \"timezone_name\", None)\n            or hass.config.time_zone\n            or \"UTC\"\n        )\n        try:\n            zone = ZoneInfo(timezone_name)\n        except ZoneInfoNotFoundError:\n            zone = dt_util.get_default_time_zone()\n            timezone_name = str(getattr(zone, \"key\", None) or \"UTC\")\n\n        base_response: dict[str, Any] = {\n            \"device_id\": call.data[ATTR_DEVICE_ID],\n            \"skud_id\": skud_id,\n            \"timezone\": timezone_name,\n            \"date\": requested_date.isoformat(),\n            \"supported\": supported,\n        }\n        if not supported:\n            return {**base_response, \"count\": 0, \"events\": []}\n\n        camera_number = _camera_number(skud)\n        day_start = datetime.combine(requested_date, time.min, tzinfo=zone)\n        day_end = day_start + timedelta(days=1)\n        try:\n            event_times = await async_get_motion_timeline_events(\n                api,\n                camera_number,\n                start=day_start.astimezone(timezone.utc),\n                end=day_end.astimezone(timezone.utc),\n            )\n        except UfanetApiError:\n            raise HomeAssistantError(\n                \"Unable to load motion timeline events\"\n            ) from None\n\n        matching: list[dict[str, Any]] = []\n        for timestamp in event_times:\n            local = timestamp.astimezone(zone)\n            if local.date() != requested_date:\n                continue\n            second_of_day = (\n                local.hour * 3600\n                + local.minute * 60\n                + local.second\n                + local.microsecond / 1_000_000\n            )\n            local_time = local.strftime(\"%H:%M:%S.%f\").rstrip(\"0\").rstrip(\".\")\n            matching.append(\n                {\n                    \"timestamp\": timestamp.timestamp(),\n                    \"local_datetime\": local.isoformat(),\n                    \"local_time\": local_time,\n                    \"second_of_day\": second_of_day,\n                }\n            )\n\n        matching.sort(key=lambda item: float(item[\"timestamp\"]))\n        return {\n            **base_response,\n            \"count\": len(matching),\n            \"events\": matching,\n        }\n\n    async def async_get_last_call_preview_url(\n",
)
replace(
    "custom_components/ufanet_intercom/services.py",
    "    hass.services.async_register(\n        DOMAIN,\n        SERVICE_GET_CALL_EVENTS,\n        async_get_call_events,\n        schema=GET_CALL_EVENTS_SCHEMA,\n        supports_response=SupportsResponse.ONLY,\n    )\n    hass.services.async_register(\n        DOMAIN,\n        SERVICE_GET_GUEST_ACCESS,\n",
    "    hass.services.async_register(\n        DOMAIN,\n        SERVICE_GET_CALL_EVENTS,\n        async_get_call_events,\n        schema=GET_CALL_EVENTS_SCHEMA,\n        supports_response=SupportsResponse.ONLY,\n    )\n    hass.services.async_register(\n        DOMAIN,\n        SERVICE_GET_MOTION_EVENTS,\n        async_get_motion_events,\n        schema=GET_MOTION_EVENTS_SCHEMA,\n        supports_response=SupportsResponse.ONLY,\n    )\n    hass.services.async_register(\n        DOMAIN,\n        SERVICE_GET_GUEST_ACCESS,\n",
)

replace(
    "custom_components/ufanet_intercom/services.yaml",
    "get_last_call_preview_url:\n",
    "get_motion_events:\n  name: Get motion events\n  description: Return privacy-minimized UCAMS motion event times for one camera-local calendar day. Read-only; provider camera/event identifiers are not returned.\n  fields:\n    device_id:\n      name: Intercom\n      description: Ufanet Intercom device.\n      required: true\n      selector:\n        device:\n          integration: ufanet_intercom\n    date:\n      name: Date\n      description: Calendar date in the camera time zone.\n      required: true\n      selector:\n        date:\n\nget_last_call_preview_url:\n",
)

# Lovelace card: cache, fetch, point markers, and 18-second playback lead.
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    'const CARD_VERSION = "0.28.0";\n',
    'const CARD_VERSION = "0.28.0";\nconst MOTION_EVENT_LEAD_SECONDS = 18;\n',
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "    this._callEvents = [];\n    this._callEventsDate = null;\n    this._callEventsCache = new Map();\n",
    "    this._callEvents = [];\n    this._callEventsDate = null;\n    this._callEventsCache = new Map();\n    this._motionEvents = [];\n    this._motionEventsDate = null;\n    this._motionEventsSupported = null;\n    this._motionEventsError = false;\n    this._motionEventsCache = new Map();\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "  _callAddress(event) {\n",
    "  async _refreshMotionEvents(dateText, force = false) {\n    if (!dateText || !this._deviceId) return;\n\n    if (!force && this._motionEventsCache.has(dateText)) {\n      const cached = this._motionEventsCache.get(dateText) || {};\n      this._motionEvents = Array.isArray(cached.events) ? cached.events : [];\n      this._motionEventsDate = dateText;\n      this._motionEventsSupported = cached.supported === true;\n      this._motionEventsError = false;\n      this._renderTimeline(dateText);\n      return;\n    }\n\n    try {\n      const response = await this._callResponseService(\"get_motion_events\", {\n        device_id: this._deviceId,\n        date: dateText,\n      });\n      const supported = response?.supported === true;\n      const events = supported && Array.isArray(response?.events)\n        ? response.events\n            .map((item) => ({\n              timestamp: Number(item.timestamp),\n              local_datetime: item.local_datetime,\n              local_time: item.local_time,\n              second_of_day: Number(item.second_of_day),\n            }))\n            .filter(\n              (item) =>\n                Number.isFinite(item.timestamp) &&\n                Number.isFinite(item.second_of_day)\n            )\n            .sort((a, b) => a.timestamp - b.timestamp)\n        : [];\n\n      this._motionEventsCache.set(dateText, { supported, events });\n      const selectedDate = this.shadowRoot.getElementById(\"date\")?.value;\n      if (selectedDate === dateText) {\n        this._motionEvents = events;\n        this._motionEventsDate = dateText;\n        this._motionEventsSupported = supported;\n        this._motionEventsError = false;\n        this._renderTimeline(dateText);\n      }\n    } catch (_err) {\n      const selectedDate = this.shadowRoot.getElementById(\"date\")?.value;\n      if (selectedDate === dateText) {\n        this._motionEvents = [];\n        this._motionEventsDate = dateText;\n        this._motionEventsSupported = null;\n        this._motionEventsError = true;\n        this._renderTimeline(dateText);\n      }\n    }\n  }\n\n  async _loadMotionEvent(event) {\n    if (!event || !Number.isFinite(Number(event.timestamp))) return;\n    const eventEpoch = Number(event.timestamp);\n    const requested = eventEpoch - MOTION_EVENT_LEAD_SECONDS;\n    let resolved = this._resolveTarget(requested, 1);\n    if (resolved == null) resolved = this._resolveTarget(eventEpoch, -1);\n    if (resolved == null) {\n      this._setStatus(\"Для этого события движения запись архива недоступна\", \"warning\");\n      return;\n    }\n    await this._loadEpoch(resolved);\n  }\n\n  _callAddress(event) {\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "    this._renderDayIntervals(resolvedDate);\n    await this._refreshCallEvents(resolvedDate);\n",
    "    this._renderDayIntervals(resolvedDate);\n    await Promise.all([\n      this._refreshCallEvents(resolvedDate),\n      this._refreshMotionEvents(resolvedDate),\n    ]);\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "    if (this._callEventsDate !== local.date) {\n      void this._refreshCallEvents(local.date);\n    } else {\n      this._renderCallEvents(local.date);\n    }\n",
    "    if (this._callEventsDate !== local.date) {\n      void this._refreshCallEvents(local.date);\n    } else {\n      this._renderCallEvents(local.date);\n    }\n    if (this._motionEventsDate !== local.date) {\n      void this._refreshMotionEvents(local.date);\n    }\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    '    for (const node of [...track.querySelectorAll(".timeline-segment, .call-marker")]) {\n',
    '    for (const node of [...track.querySelectorAll(".timeline-segment, .call-marker, .motion-marker")]) {\n',
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "    const windowRange = this._timelineWindow();\n    track.dataset.pannable = this._timelineCanPan() ? \"true\" : \"false\";\n",
    "    const windowRange = this._timelineWindow();\n    const eventSummary = this.shadowRoot.getElementById(\"timeline-event-summary\");\n    if (eventSummary) {\n      const callText = this._callEventsDate === dateText ? String(this._callEvents.length) : \"…\";\n      let motionText = \"…\";\n      if (this._motionEventsDate === dateText) {\n        if (this._motionEventsSupported === true) {\n          motionText = String(this._motionEvents.length);\n        } else if (this._motionEventsError) {\n          motionText = \"ошибка\";\n        } else {\n          motionText = \"—\";\n        }\n      }\n      eventSummary.textContent = `🔔 ${callText} • движение ${motionText}`;\n    }\n    track.dataset.pannable = this._timelineCanPan() ? \"true\" : \"false\";\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "    if (this._callEventsDate === dateText && this._callEvents.length) {\n      for (const event of this._callEvents) {\n        const seconds = Number(event.second_of_day);\n        if (!Number.isFinite(seconds)) continue;\n        if (seconds < windowRange.start || seconds > windowRange.end) continue;\n\n        const left = ((seconds - windowRange.start) / windowRange.span) * 100;\n        const marker = document.createElement(\"button\");\n        marker.type = \"button\";\n        marker.className = \"call-marker\";\n        marker.style.left = `${Math.max(0, Math.min(100, left))}%`;\n        marker.textContent = \"🔔\";\n        const address = this._callAddress(event);\n        marker.title = `${event.local_time || \"\"}${address ? ` • ${address}` : \"\"}`;\n        marker.setAttribute(\"aria-label\", `Звонок ${marker.title}`);\n        marker.addEventListener(\"pointerdown\", (ev) => ev.stopPropagation());\n        marker.addEventListener(\"click\", (ev) => {\n          ev.stopPropagation();\n          void this._loadCallEvent(event);\n        });\n        track.appendChild(marker);\n      }\n    }\n\n    this._updateTimelineMarker(dateText);\n",
    "    if (this._callEventsDate === dateText && this._callEvents.length) {\n      for (const event of this._callEvents) {\n        const seconds = Number(event.second_of_day);\n        if (!Number.isFinite(seconds)) continue;\n        if (seconds < windowRange.start || seconds > windowRange.end) continue;\n\n        const left = ((seconds - windowRange.start) / windowRange.span) * 100;\n        const marker = document.createElement(\"button\");\n        marker.type = \"button\";\n        marker.className = \"call-marker\";\n        marker.style.left = `${Math.max(0, Math.min(100, left))}%`;\n        marker.textContent = \"🔔\";\n        const address = this._callAddress(event);\n        marker.title = `${event.local_time || \"\"}${address ? ` • ${address}` : \"\"}`;\n        marker.setAttribute(\"aria-label\", `Звонок ${marker.title}`);\n        marker.addEventListener(\"pointerdown\", (ev) => ev.stopPropagation());\n        marker.addEventListener(\"click\", (ev) => {\n          ev.stopPropagation();\n          void this._loadCallEvent(event);\n        });\n        track.appendChild(marker);\n      }\n    }\n\n    if (\n      this._motionEventsDate === dateText &&\n      this._motionEventsSupported === true &&\n      this._motionEvents.length\n    ) {\n      for (const event of this._motionEvents) {\n        const seconds = Number(event.second_of_day);\n        if (!Number.isFinite(seconds)) continue;\n        if (seconds < windowRange.start || seconds > windowRange.end) continue;\n\n        const left = ((seconds - windowRange.start) / windowRange.span) * 100;\n        const marker = document.createElement(\"button\");\n        marker.type = \"button\";\n        marker.className = \"motion-marker\";\n        marker.style.left = `${Math.max(0, Math.min(100, left))}%`;\n        marker.title = `Движение ${event.local_time || \"\"}`.trim();\n        marker.setAttribute(\"aria-label\", marker.title);\n        marker.addEventListener(\"pointerdown\", (ev) => ev.stopPropagation());\n        marker.addEventListener(\"click\", (ev) => {\n          ev.stopPropagation();\n          void this._loadMotionEvent(event);\n        });\n        track.appendChild(marker);\n      }\n    }\n\n    this._updateTimelineMarker(dateText);\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "        .timeline-zoom { display: inline-flex; gap: 4px; align-items: center; }\n",
    "        .timeline-zoom { display: inline-flex; gap: 4px; align-items: center; }\n        .timeline-event-summary {\n          margin-left: 7px; color: var(--secondary-text-color); font-size: 10px; font-weight: 400;\n        }\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "        .call-marker:hover { transform: translateX(-50%) scale(1.12); }\n        #timeline-marker {\n",
    "        .call-marker:hover { transform: translateX(-50%) scale(1.12); }\n        .motion-marker {\n          position: absolute; top: 0; bottom: 0; width: 12px; min-height: 0; padding: 0;\n          transform: translateX(-50%); z-index: 4; border: 0; border-radius: 0;\n          background: transparent; cursor: pointer;\n        }\n        .motion-marker::before {\n          content: \"\"; position: absolute; top: 3px; bottom: 3px; left: 4px; width: 4px;\n          border-radius: 2px; background: var(--success-color, #43a047);\n          box-shadow: 0 0 0 1px color-mix(in srgb, var(--card-background-color) 70%, transparent);\n        }\n        .motion-marker:hover::before { left: 3px; width: 6px; }\n        #timeline-marker {\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "              <span>Timeline архива</span>\n",
    "              <span>Timeline архива <span id=\"timeline-event-summary\" class=\"timeline-event-summary\"></span></span>\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "              <button id=\"refresh-calls\" type=\"button\">Обновить</button>\n",
    "              <button id=\"refresh-calls\" type=\"button\">Обновить события</button>\n",
)
replace(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    "    this.shadowRoot.getElementById(\"refresh-calls\")?.addEventListener(\"click\", () => {\n      const dateText = this.shadowRoot.getElementById(\"date\")?.value;\n      if (dateText) void this._refreshCallEvents(dateText, true);\n    });\n",
    "    this.shadowRoot.getElementById(\"refresh-calls\")?.addEventListener(\"click\", () => {\n      const dateText = this.shadowRoot.getElementById(\"date\")?.value;\n      if (dateText) {\n        void Promise.all([\n          this._refreshCallEvents(dateText, true),\n          this._refreshMotionEvents(dateText, true),\n        ]);\n      }\n    });\n",
)

# User-facing and reverse-engineered documentation.
replace(
    "README.md",
    "- Native archive browsing with recording ranges, timeline zoom/pan and call markers.\n",
    "- Native archive browsing with recording ranges, timeline zoom/pan, call markers, and read-only motion-event markers.\n",
)
replace(
    "README_RU.md",
    "- Просмотр видеоархива с диапазонами доступной записи, масштабированием/перемещением таймлайна и метками звонков.\n",
    "- Просмотр видеоархива с диапазонами доступной записи, масштабированием/перемещением таймлайна, метками звонков и read-only метками событий движения.\n",
)
replace(
    "README.md",
    "For every camera that explicitly advertises the live-confirmed `motion_alarm` capability, v0.28.0 creates a **Motion detected** event entity and exposes the matching **Motion detected** device trigger (`motion_detected`). The same normalized event is available on the Home Assistant bus as `ufanet_intercom_motion`.\n\n",
    "For every camera that explicitly advertises the live-confirmed `motion_alarm` capability, v0.28.0 creates a **Motion detected** event entity and exposes the matching **Motion detected** device trigger (`motion_detected`). The same normalized event is available on the Home Assistant bus as `ufanet_intercom_motion`. The archive timeline can also request the selected day's privacy-minimized motion timestamps and draw them as point markers over recorded ranges; selecting a marker starts playback about 18 seconds before the event while leaving the marker at the authoritative event time.\n\n",
)
replace(
    "README_RU.md",
    "Для каждой камеры, которая явно объявляет live-confirmed capability `motion_alarm`, v0.28.0 создаёт event entity **«Обнаружено движение»** и соответствующий device trigger **«Обнаружено движение»** в визуальном редакторе. То же нормализованное событие доступно на шине Home Assistant как `ufanet_intercom_motion`.\n\n",
    "Для каждой камеры, которая явно объявляет live-confirmed capability `motion_alarm`, v0.28.0 создаёт event entity **«Обнаружено движение»** и соответствующий device trigger **«Обнаружено движение»** в визуальном редакторе. То же нормализованное событие доступно на шине Home Assistant как `ufanet_intercom_motion`. Таймлайн архива также может запросить privacy-minimized timestamps движения за выбранный день и показать их точечными метками поверх диапазонов записи; при выборе метки воспроизведение начинается примерно за 18 секунд до события, а сама метка остаётся на авторитетном времени события.\n\n",
)
append_before(
    "docs/api/analytics.md",
    "## Errors, diagnostics, and privacy boundary\n",
    "## Archive timeline model observed in the Android client\n\n**Status: Observed**\n\nThe decompiled Android client maintains a separate point-event list for its archive timebar. Each `EventDataExistTimeSegment` stores an event timestamp, color, and type; the timebar draws that timestamp as a narrow overlay on the recorded-data bar. The player requests analytics for the currently available archive interval and keeps event timestamps separate from recording ranges.\n\nThe same client also contains `POST /api/v0/analytics/archive_events/` for an all-analytics archive query. That endpoint is **Observed only**: it has not been live-confirmed by this project and production Home Assistant code does not call it. Archive motion markers instead reuse the already Confirmed `POST /api/v0/analytics/motion_alarm/report/` endpoint with bounded `start`/`end` windows.\n\nThe official client uses an 18-second playback-before-event offset when opening an analytics event. The event timestamp itself is not shifted. The Home Assistant archive timeline follows that UI behavior: the point marker stays at the authoritative `date`, while clicking it seeks to approximately 18 seconds before the event when recording is available.\n\nThe authenticated `get_motion_events` Home Assistant response service returns only the selected camera-local date, support flag, count, and normalized event times needed by the Lovelace timeline. UCAMS camera numbers, provider event IDs, `length`, raw results, media, screenshots, and recognition data are not returned.\n\n",
)
append_before(
    "docs/api/analytics_RU.md",
    "## Ошибки, диагностика и граница приватности\n",
    "## Модель событий таймлайна в Android-клиенте\n\n**Статус: Observed**\n\nВ декомпилированном Android-клиенте для архивного timebar ведётся отдельный список точечных событий. Каждый `EventDataExistTimeSegment` хранит timestamp события, цвет и тип; timebar рисует timestamp узкой меткой поверх полосы наличия записи. Player запрашивает аналитику для доступного архивного интервала и не смешивает timestamps событий с диапазонами записи.\n\nВ клиенте также присутствует `POST /api/v0/analytics/archive_events/` для общего запроса архивной аналитики. Этот endpoint имеет статус только **Observed**: проект не подтверждал его live-запросом, поэтому production-код Home Assistant его не вызывает. Метки движения в архиве повторно используют уже Confirmed endpoint `POST /api/v0/analytics/motion_alarm/report/` с ограниченными окнами `start`/`end`.\n\nПри открытии analytics event официальный клиент использует playback offset примерно 18 секунд до события. Timestamp самого события не изменяется. Таймлайн Home Assistant повторяет эту UI-семантику: точечная метка остаётся на авторитетном `date`, а клик запускает запись примерно за 18 секунд до события, если этот участок архива доступен.\n\nАвторизованный response-service Home Assistant `get_motion_events` возвращает только выбранную camera-local дату, признак поддержки, количество и нормализованные времена событий, необходимые Lovelace timeline. Номера камер UCAMS, provider event IDs, `length`, raw results, media, screenshots и recognition data не возвращаются.\n\n",
)
replace(
    "docs/api/STATUS.md",
    "| Analytics | `POST /api/v0/analytics/motion_alarm/report/` | **Confirmed** | HTTP 200; envelope `count/page/results`; result fields `id/date/length`; `date` is authoritative and `id` is a private opaque cursor |\n",
    "| Analytics | `POST /api/v0/analytics/motion_alarm/report/` | **Confirmed** | HTTP 200; envelope `count/page/results`; result fields `id/date/length`; `date` is authoritative and `id` is a private opaque cursor |\n| Analytics | `POST /api/v0/analytics/archive_events/` | **Observed** | Decompiled Android archive player can request all analytics for an archive interval; not live-confirmed and not used by production runtime |\n",
)
replace(
    "docs/api/STATUS_RU.md",
    "| Аналитика | `POST /api/v0/analytics/motion_alarm/report/` | **Confirmed** | HTTP 200; envelope `count/page/results`; поля события `id/date/length`; `date` авторитетен, `id` используется только как приватный opaque cursor |\n",
    "| Аналитика | `POST /api/v0/analytics/motion_alarm/report/` | **Confirmed** | HTTP 200; envelope `count/page/results`; поля события `id/date/length`; `date` авторитетен, `id` используется только как приватный opaque cursor |\n| Аналитика | `POST /api/v0/analytics/archive_events/` | **Observed** | Декомпилированный Android archive player умеет запрашивать все analytics за архивный интервал; live-подтверждения нет, production runtime endpoint не использует |\n",
)

# Tests: helper privacy/dedup and service/frontend behavior.
replace(
    "tests/test_analytics.py",
    "    async_get_motion_events,\n)",
    "    async_get_motion_events,\n    async_get_motion_timeline_events,\n)",
)
append_before(
    "tests/test_analytics.py",
    "\n\n@pytest.mark.asyncio\nasync def test_coordinator_sanitizes_api_error_and_rolls_back_partial_cursor(\n",
    "\n\n@pytest.mark.asyncio\nasync def test_motion_timeline_events_drop_provider_ids_and_deduplicate_timestamp(\n    monkeypatch,\n) -> None:\n    first = datetime(2026, 9, 2, 10, 0, 34, 793780, tzinfo=timezone.utc)\n    second = datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)\n\n    async def fake_collect(_api, _camera, **_kwargs):\n        return [\n            {\"cursor_id\": 1001, \"occurred_at\": first},\n            {\"cursor_id\": 1002, \"occurred_at\": first},\n            {\"cursor_id\": 1003, \"occurred_at\": second},\n        ]\n\n    monkeypatch.setattr(\n        \"custom_components.ufanet_intercom.analytics._async_collect_motion_events\",\n        fake_collect,\n    )\n\n    result = await async_get_motion_timeline_events(\n        AsyncMock(),\n        \"PRIVATE-CAMERA\",\n        start=first - timedelta(minutes=1),\n        end=second + timedelta(minutes=1),\n    )\n\n    assert result == [first, second]\n    assert all(isinstance(item, datetime) for item in result)\n",
)

service_test = '''\"\"\"Tests for privacy-safe archive motion timeline service.\"\"\"\n\nfrom __future__ import annotations\n\nfrom datetime import datetime, timezone\nimport json\nfrom types import SimpleNamespace\nfrom unittest.mock import AsyncMock, MagicMock, patch\n\nimport pytest\nfrom homeassistant.exceptions import HomeAssistantError\nfrom homeassistant.helpers import device_registry as dr\nfrom pytest_homeassistant_custom_component.common import MockConfigEntry\n\nfrom custom_components.ufanet_intercom.api import UfanetResponseError\nfrom custom_components.ufanet_intercom.const import DOMAIN, SERVICE_GET_MOTION_EVENTS\nfrom custom_components.ufanet_intercom.services import async_setup_services\n\n\ndef _install_runtime(hass):\n    entry = MockConfigEntry(\n        domain=DOMAIN,\n        title=\"Motion timeline test\",\n        data={},\n        unique_id=\"motion-timeline-test\",\n    )\n    entry.add_to_hass(hass)\n    device = dr.async_get(hass).async_get_or_create(\n        config_entry_id=entry.entry_id,\n        identifiers={(DOMAIN, \"7\")},\n        name=\"Door\",\n    )\n    api = MagicMock()\n    coordinator = SimpleNamespace(\n        data={7: {\"id\": 7, \"cctv_number\": \"PRIVATE-CAMERA\"}},\n    )\n    analytics = SimpleNamespace(data={7: {\"supported\": True}})\n    controller = SimpleNamespace(timezone_name=\"UTC\")\n    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {\n        \"api\": api,\n        \"coordinator\": coordinator,\n        \"analytics_coordinator\": analytics,\n        \"archive_controllers\": {7: controller},\n        \"options\": {},\n    }\n    async_setup_services(hass, MagicMock())\n    return device, analytics\n\n\n@pytest.mark.asyncio\nasync def test_motion_timeline_service_returns_only_normalized_times(hass) -> None:\n    device, _analytics = _install_runtime(hass)\n    first = datetime(2026, 9, 2, 10, 0, 34, 793780, tzinfo=timezone.utc)\n    second = datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)\n\n    with patch(\n        \"custom_components.ufanet_intercom.services.async_get_motion_timeline_events\",\n        AsyncMock(return_value=[first, second]),\n    ) as loader:\n        response = await hass.services.async_call(\n            DOMAIN,\n            SERVICE_GET_MOTION_EVENTS,\n            {\"device_id\": device.id, \"date\": \"2026-09-02\"},\n            blocking=True,\n            return_response=True,\n        )\n\n    loader.assert_awaited_once()\n    assert response[\"supported\"] is True\n    assert response[\"count\"] == 2\n    assert response[\"events\"][0][\"local_time\"] == \"10:00:34.79378\"\n    assert response[\"events\"][0][\"second_of_day\"] == pytest.approx(36034.79378)\n    serialized = json.dumps(response, default=str)\n    assert \"PRIVATE-CAMERA\" not in serialized\n    assert \"cursor\" not in serialized.lower()\n    assert \"event_id\" not in serialized.lower()\n\n\n@pytest.mark.asyncio\nasync def test_motion_timeline_service_skips_unsupported_camera(hass) -> None:\n    device, analytics = _install_runtime(hass)\n    analytics.data = {}\n\n    with patch(\n        \"custom_components.ufanet_intercom.services.async_get_motion_timeline_events\",\n        AsyncMock(),\n    ) as loader:\n        response = await hass.services.async_call(\n            DOMAIN,\n            SERVICE_GET_MOTION_EVENTS,\n            {\"device_id\": device.id, \"date\": \"2026-09-02\"},\n            blocking=True,\n            return_response=True,\n        )\n\n    assert response[\"supported\"] is False\n    assert response[\"events\"] == []\n    loader.assert_not_awaited()\n\n\n@pytest.mark.asyncio\nasync def test_motion_timeline_service_sanitizes_ucams_error(hass) -> None:\n    device, _analytics = _install_runtime(hass)\n\n    with patch(\n        \"custom_components.ufanet_intercom.services.async_get_motion_timeline_events\",\n        AsyncMock(side_effect=UfanetResponseError(\"PRIVATE-CAMERA secret body\")),\n    ):\n        with pytest.raises(HomeAssistantError) as err:\n            await hass.services.async_call(\n                DOMAIN,\n                SERVICE_GET_MOTION_EVENTS,\n                {\"device_id\": device.id, \"date\": \"2026-09-02\"},\n                blocking=True,\n                return_response=True,\n            )\n\n    assert str(err.value) == \"Unable to load motion timeline events\"\n    assert \"PRIVATE-CAMERA\" not in str(err.value)\n'''\n(ROOT / "tests/test_motion_timeline_service.py").write_text(service_test, encoding="utf-8")

frontend_test = '''\"\"\"Static regression checks for archive motion timeline UI.\"\"\"\n\nfrom pathlib import Path\n\n\ndef test_frontend_motion_timeline_uses_privacy_safe_service_and_point_markers() -> None:\n    text = Path(\n        \"custom_components/ufanet_intercom/frontend/ufanet-archive-card.js\"\n    ).read_text(encoding=\"utf-8\")\n    assert 'const MOTION_EVENT_LEAD_SECONDS = 18;' in text\n    assert 'this._callResponseService(\"get_motion_events\"' in text\n    assert 'marker.className = \"motion-marker\"' in text\n    assert 'void this._loadMotionEvent(event);' in text\n\n    start = text.index(\"async _refreshMotionEvents\")\n    end = text.index(\"_callAddress(event)\", start)\n    boundary = text[start:end]\n    for private_name in (\"cursor_id\", \"camera_number\", \"length\", \"recognition\", \"media_url\"):\n        assert private_name not in boundary\n'''\n(ROOT / "tests/test_motion_timeline_frontend.py").write_text(frontend_test, encoding="utf-8")

# Temporary patch machinery must not remain in the PR tree.
(ROOT / ".github/workflows/apply-motion-timeline-patch.yml").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
