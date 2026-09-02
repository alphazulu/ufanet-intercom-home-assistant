const CARD_VERSION = "0.28.0";
const MOTION_EVENT_LEAD_SECONDS = 18;

class UfanetArchiveCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._userConfig = null;
    this._integrationSettings = null;
    this._initialized = false;
    this._initializing = false;
    this._deviceId = null;
    this._ranges = [];
    this._days = [];
    this._daysByDate = new Map();
    this._timezone = "UTC";
    this._earliest = null;
    this._latest = null;
    this._currentEpoch = null;
    this._player = null;
    this._loading = false;
    this._timelineZoomHours = 24;
    this._timelineCenterSeconds = 43200;
    this._lastTimelineWheelAt = 0;
    this._timelineDrag = null;
    this._timelineSuppressClickUntil = 0;
    this._callEvents = [];
    this._callEventsDate = null;
    this._callEventsCache = new Map();
    this._motionEvents = [];
    this._motionEventsDate = null;
    this._motionEventsSupported = null;
    this._motionEventsError = false;
    this._motionEventsCache = new Map();
    this._activeTab = "archive";
    this._liveEntityId = null;
    this._openDoorEntityId = null;
    this._lastCallEntityId = null;
    this._lastCallImageEntityId = null;
    this._deviceRegistryEntities = null;
    this._lastCallStateSeen = null;
    this._liveCallFlashTimer = null;
    this._liveCard = null;
    this._archiveDownload = null;
    this._archiveExports = [];
    this._archiveExportsLoaded = false;
    this._archiveExportsLoading = false;
    this._guestAccess = null;
    this._guestLoading = false;
    this._guestInviteUrl = null;
    this._runtimeStatus = null;
    this._runtimeStatusLoading = false;
  }

  static getStubConfig() {
    return {
      duration: 300,
      step: 60,
      timeline_zoom: 24,
      call_lead_seconds: 15,
      default_tab: "archive",
      export_retention_days: 30,
      export_max_gb: 5,
      title: "Домофон Ufanet",
    };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { domain: "camera" } },
        },
        {
          name: "live_entity",
          selector: { entity: { domain: "camera" } },
        },
        {
          name: "default_tab",
          selector: {
            select: {
              options: [
                { value: "live", label: "Live" },
                { value: "archive", label: "Архив" },
                { value: "guests", label: "Гости" },
                { value: "diagnostics", label: "Диагностика" },
              ],
            },
          },
        },
        { name: "title", selector: { text: {} } },
        {
          name: "duration",
          selector: {
            number: { min: 30, max: 3600, step: 30, unit_of_measurement: "s" },
          },
        },
        {
          name: "step",
          selector: {
            number: { min: 10, max: 3600, step: 10, unit_of_measurement: "s" },
          },
        },
        {
          name: "timeline_zoom",
          selector: {
            select: {
              options: [
                { value: "24", label: "24 часа" },
                { value: "6", label: "6 часов" },
                { value: "1", label: "1 час" },
              ],
            },
          },
        },
        {
          name: "call_lead_seconds",
          selector: {
            number: { min: 0, max: 60, step: 1, unit_of_measurement: "s" },
          },
        },
        {
          name: "export_retention_days",
          selector: {
            number: { min: 0, max: 3650, step: 1, unit_of_measurement: "d" },
          },
        },
        {
          name: "export_max_gb",
          selector: {
            number: { min: 0, max: 1024, step: 0.5, unit_of_measurement: "GB" },
          },
        },
      ],
      computeLabel: (schema) => ({
        entity: "Камера Ufanet (для определения устройства)",
        live_entity: "Live-камера (необязательно, определяется автоматически)",
        default_tab: "Вкладка по умолчанию",
        title: "Заголовок",
        duration: "Длительность фрагмента",
        step: "Шаг назад/вперёд",
        timeline_zoom: "Начальный масштаб timeline",
        call_lead_seconds: "Начинать видео за N секунд до звонка",
        export_retention_days: "Хранить экспортированные видео, дней (0 = без ограничения)",
        export_max_gb: "Максимальный объём экспортов, ГБ (0 = без ограничения)",
      })[schema.name] || schema.name,
    };
  }

  setConfig(config) {
    if (!config || (!config.entity && !config.device_id)) {
      throw new Error("Specify a Ufanet camera entity or device_id");
    }

    this._userConfig = { ...config };
    this._integrationSettings = null;

    this._config = {
      title: "Домофон Ufanet",
      duration: 300,
      step: 60,
      timeline_zoom: 24,
      call_lead_seconds: 15,
      default_tab: "archive",
      ...config,
    };

    this._activeTab = ["live", "archive", "guests", "diagnostics"].includes(this._config.default_tab)
      ? this._config.default_tab
      : "archive";
    this._liveEntityId = this._config.live_entity || null;

    const configuredZoom = Number(this._config.timeline_zoom);
    this._timelineZoomHours = [24, 6, 1].includes(configuredZoom)
      ? configuredZoom
      : 24;

    this._initialized = false;
    this._deviceId = this._config.device_id || null;
    this._renderSkeleton();

    if (this.isConnected && this._hass) {
      void this._initialize();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (this._liveCard) {
      this._liveCard.hass = hass;
    }

    if (this._initialized && this._lastCallEntityId) {
      const nextState = hass?.states?.[this._lastCallEntityId]?.state || null;
      if (
        this._lastCallStateSeen &&
        nextState &&
        !["unknown", "unavailable"].includes(nextState) &&
        nextState !== this._lastCallStateSeen
      ) {
        this._flashNewLiveCall();
      }
      if (nextState) {
        this._lastCallStateSeen = nextState;
      }
      this._renderLiveMeta();
    }

    if (this.isConnected && this._config && !this._initialized) {
      void this._initialize();
    }
  }

  connectedCallback() {
    if (this._config) {
      this._renderSkeleton();
    }
    if (this._hass && this._config && !this._initialized) {
      void this._initialize();
    }
  }

  disconnectedCallback() {
    if (this._liveCallFlashTimer) {
      clearTimeout(this._liveCallFlashTimer);
      this._liveCallFlashTimer = null;
    }
  }

  getCardSize() {
    return 8;
  }

  async _initialize() {
    if (this._initializing || this._initialized || !this._hass || !this._config) {
      return;
    }

    this._initializing = true;
    this._setStatus("Загрузка диапазонов архива…", "info");

    try {
      await this._ensureHlsPlayer();

      if (!this._deviceId) {
        const entry = await this._hass.callWS({
          type: "config/entity_registry/get",
          entity_id: this._config.entity,
        });
        this._deviceId = entry?.device_id;
      }

      if (!this._deviceId) {
        throw new Error("Не удалось определить device_id выбранной камеры");
      }

      await this._loadIntegrationSettings();
      await this._resolveLiveEntity();

      await this._refreshRanges();
      if (!this._ranges.length) {
        throw new Error("Архивных записей не найдено");
      }

      this._initialized = true;
      await this._goLatest(false);
      this._setActiveTab(this._activeTab, false);
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    } finally {
      this._initializing = false;
    }
  }

  _hasYamlOption(name) {
    return Object.prototype.hasOwnProperty.call(this._userConfig || {}, name);
  }

  async _loadIntegrationSettings() {
    if (!this._deviceId) return;

    try {
      this._integrationSettings = await this._callResponseService(
        "get_settings",
        {
          device_id: this._deviceId,
        }
      );
    } catch (_err) {
      // Keep all existing card defaults/YAML values if the backend is older
      // or the settings action is temporarily unavailable.
      this._integrationSettings = null;
      return;
    }

    const settings = this._integrationSettings || {};

    if (!this._hasYamlOption("call_lead_seconds")) {
      this._config.call_lead_seconds = Number(
        settings.call_lead_seconds ??
        this._config.call_lead_seconds ??
        15
      );
    }

    if (!this._hasYamlOption("duration")) {
      this._config.duration = Number(
        settings.archive_default_duration_seconds ??
        this._config.duration ??
        300
      );
    }

    if (!this._hasYamlOption("step")) {
      this._config.step = Number(
        settings.archive_default_step_seconds ??
        this._config.step ??
        60
      );
    }

    if (!this._hasYamlOption("export_retention_days")) {
      this._config.export_retention_days = Number(
        settings.export_retention_days ?? 30
      );
    }

    if (!this._hasYamlOption("export_max_gb")) {
      this._config.export_max_gb =
        Number(settings.export_max_total_mb ?? 5120) / 1024;
    }

    if (!this._hasYamlOption("export_default_duration")) {
      this._config.export_default_duration = Number(
        settings.export_default_duration_seconds ?? 300
      );
    }

    const duration = this.shadowRoot.getElementById("duration");
    if (duration && !this._hasYamlOption("duration")) {
      duration.value = String(this._config.duration);
    }

    const step = this.shadowRoot.getElementById("step");
    if (step && !this._hasYamlOption("step")) {
      step.value = String(this._config.step);
    }

    const exportDuration =
      this.shadowRoot.getElementById("archive-export-duration");
    if (
      exportDuration &&
      !this._hasYamlOption("export_default_duration")
    ) {
      const wanted = String(this._config.export_default_duration || 300);

      if (
        ![...exportDuration.options].some(
          (option) => option.value === wanted
        )
      ) {
        const option = document.createElement("option");
        option.value = wanted;
        option.textContent = this._formatStep(Number(wanted));
        exportDuration.appendChild(option);
      }

      exportDuration.value = wanted;
    }

    this._renderArchiveExports();
    this._renderRuntimeStatus();
  }

  async _resolveLiveEntity() {
    if (
      this._liveEntityId &&
      this._openDoorEntityId &&
      this._lastCallEntityId
    ) {
      return this._liveEntityId;
    }

    try {
      const entities = this._deviceRegistryEntities || await this._hass.callWS({
        type: "config/entity_registry/list",
      });
      this._deviceRegistryEntities = entities;

      const sameDevice = Array.isArray(entities)
        ? entities.filter((item) => item?.device_id === this._deviceId)
        : [];

      const cameras = sameDevice.filter((item) =>
        String(item?.entity_id || "").startsWith("camera.")
      );

      const live = cameras.find((item) => {
        const uniqueId = String(item?.unique_id || "");
        return (
          !uniqueId.includes("_archive_camera_") &&
          uniqueId.includes("_camera_")
        );
      });

      if (live?.entity_id && !this._config.live_entity) {
        this._liveEntityId = live.entity_id;
      }

      const nonArchive = cameras.find(
        (item) => !String(item?.unique_id || "").includes("_archive_camera_")
      );
      if (!this._liveEntityId && nonArchive?.entity_id) {
        this._liveEntityId = nonArchive.entity_id;
      }

      const doorEntities = sameDevice.filter((item) =>
        String(item?.entity_id || "").startsWith("button.")
      );
      const primaryDoor = doorEntities.find(
        (item) => String(item?.unique_id || "").endsWith("_open_door_1")
      );
      const anyDoor = doorEntities.find(
        (item) => String(item?.unique_id || "").includes("_open_door_")
      );
      this._openDoorEntityId =
        this._config.open_door_entity ||
        primaryDoor?.entity_id ||
        anyDoor?.entity_id ||
        this._openDoorEntityId;

      const sensors = sameDevice.filter((item) =>
        String(item?.entity_id || "").startsWith("sensor.")
      );
      const lastCall = sensors.find(
        (item) => String(item?.unique_id || "").endsWith("_last_call")
      );
      if (lastCall?.entity_id) {
        this._lastCallEntityId = lastCall.entity_id;
      }

      const images = sameDevice.filter((item) =>
        String(item?.entity_id || "").startsWith("image.")
      );
      const lastCallImage = images.find(
        (item) => String(item?.unique_id || "").endsWith("_last_call_image")
      );
      if (lastCallImage?.entity_id) {
        this._lastCallImageEntityId = lastCallImage.entity_id;
      }
    } catch (_err) {
      // Fall back below.
    }

    this._liveEntityId =
      this._config.live_entity ||
      this._liveEntityId ||
      this._config.entity ||
      null;

    if (this._lastCallEntityId && this._hass?.states?.[this._lastCallEntityId]) {
      this._lastCallStateSeen =
        this._hass.states[this._lastCallEntityId].state || null;
    }

    return this._liveEntityId;
  }

  _entityAvailable(entityId) {
    if (!entityId || !this._hass?.states?.[entityId]) return false;
    return !["unavailable", "unknown"].includes(
      String(this._hass.states[entityId].state || "")
    );
  }

  _lastCallState() {
    if (!this._lastCallEntityId || !this._hass?.states) return null;
    const state = this._hass.states[this._lastCallEntityId];
    if (!state || ["unknown", "unavailable"].includes(state.state)) return null;
    const epoch = Date.parse(state.state) / 1000;
    if (!Number.isFinite(epoch)) return null;
    return { state, epoch };
  }

  _formatRelativeEpoch(epoch) {
    const deltaSeconds = Math.round(epoch - Date.now() / 1000);
    const abs = Math.abs(deltaSeconds);
    const formatter = new Intl.RelativeTimeFormat("ru-RU", { numeric: "auto" });

    if (abs < 60) return formatter.format(deltaSeconds, "second");
    if (abs < 3600) return formatter.format(Math.round(deltaSeconds / 60), "minute");
    if (abs < 86400) return formatter.format(Math.round(deltaSeconds / 3600), "hour");
    return formatter.format(Math.round(deltaSeconds / 86400), "day");
  }

  _renderLiveMeta() {
    const cameraState = this.shadowRoot.getElementById("live-camera-state");
    const doorState = this.shadowRoot.getElementById("live-door-state");
    const doorButton = this.shadowRoot.getElementById("live-open-door");
    const callBox = this.shadowRoot.getElementById("live-last-call");
    const callTime = this.shadowRoot.getElementById("live-last-call-time");
    const callAddress = this.shadowRoot.getElementById("live-last-call-address");
    const archiveButton = this.shadowRoot.getElementById("live-open-call-archive");
    const previewButton = this.shadowRoot.getElementById("live-open-call-preview");
    const imageButton = this.shadowRoot.getElementById("live-open-call-image");

    const cameraAvailable = this._entityAvailable(this._liveEntityId);
    const doorAvailable = this._entityAvailable(this._openDoorEntityId);

    if (cameraState) {
      cameraState.textContent = cameraAvailable ? "Камера online" : "Камера недоступна";
      cameraState.dataset.available = cameraAvailable ? "true" : "false";
    }
    if (doorState) {
      doorState.textContent = doorAvailable ? "Домофон доступен" : "Домофон недоступен";
      doorState.dataset.available = doorAvailable ? "true" : "false";
    }
    if (doorButton) {
      doorButton.disabled = !doorAvailable;
      doorButton.title = this._openDoorEntityId || "Кнопка открытия двери не найдена";
    }

    const lastCall = this._lastCallState();
    if (!lastCall) {
      if (callBox) callBox.dataset.empty = "true";
      if (callTime) callTime.textContent = "Звонков пока нет";
      if (callAddress) callAddress.textContent = "";
      if (archiveButton) archiveButton.disabled = true;
      if (previewButton) previewButton.hidden = true;
      if (imageButton) imageButton.hidden = true;
      return;
    }

    if (callBox) callBox.dataset.empty = "false";

    if (callTime) {
      callTime.textContent =
        `${this._formatDisplayTime(lastCall.epoch)} • ` +
        `${this._formatRelativeEpoch(lastCall.epoch)}`;
    }

    const attrs = lastCall.state.attributes || {};
    const addressParts = [];
    if (attrs.address) addressParts.push(String(attrs.address));
    if (attrs.porch != null && String(attrs.porch) !== "") {
      addressParts.push(`подъезд ${attrs.porch}`);
    }
    if (attrs.flat != null && String(attrs.flat) !== "") {
      addressParts.push(`кв. ${attrs.flat}`);
    }
    if (callAddress) {
      callAddress.textContent = addressParts.join(", ") || "Домофон";
    }

    if (archiveButton) archiveButton.disabled = false;
    if (previewButton) {
      previewButton.hidden = !attrs.has_preview;
      previewButton.title = attrs.has_preview
        ? "Временный URL будет получен только после нажатия"
        : "Preview-видео недоступно";
    }
    if (imageButton) {
      const imageState = this._lastCallImageEntityId
        ? this._hass?.states?.[this._lastCallImageEntityId]
        : null;
      const imageReady = Boolean(
        imageState &&
        !["unknown", "unavailable"].includes(imageState.state) &&
        imageState.attributes?.access_token
      );
      imageButton.hidden = !imageReady;
      imageButton.title = imageReady
        ? this._lastCallImageEntityId
        : "Снимок последнего звонка ещё не готов";
    }
  }

  _flashNewLiveCall() {
    const box = this.shadowRoot.getElementById("live-last-call");
    const tab = this.shadowRoot.getElementById("tab-live");
    box?.classList.add("new-call");
    tab?.classList.add("new-call");

    if (this._liveCallFlashTimer) {
      clearTimeout(this._liveCallFlashTimer);
    }
    this._liveCallFlashTimer = setTimeout(() => {
      box?.classList.remove("new-call");
      tab?.classList.remove("new-call");
      this._liveCallFlashTimer = null;
    }, 7000);

    this._setStatus("Новый звонок в домофон", "warning");
  }

  async _openDoorFromLive() {
    if (!this._openDoorEntityId || !this._entityAvailable(this._openDoorEntityId)) {
      this._setStatus("Кнопка открытия двери недоступна", "error");
      return;
    }

    const confirmed = window.confirm(
      "Открыть дверь домофона сейчас?"
    );
    if (!confirmed) return;

    const button = this.shadowRoot.getElementById("live-open-door");
    if (button) button.disabled = true;
    this._setStatus("Открываю дверь…", "info");

    try {
      await this._hass.callWS({
        type: "call_service",
        domain: "button",
        service: "press",
        service_data: { entity_id: this._openDoorEntityId },
      });
      this._setStatus("Ufanet подтвердил команду открытия двери", "ok");
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    } finally {
      this._renderLiveMeta();
    }
  }

  async _openLastCallArchive() {
    const lastCall = this._lastCallState();
    if (!lastCall) return;

    this._setActiveTab("archive", false);
    await this._loadCallEvent({ timestamp: lastCall.epoch });
  }

  async _openLastCallPreview() {
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;
    try {
      const response = await this._callResponseService(
        "get_last_call_preview_url",
        { device_id: this._deviceId }
      );
      if (!response?.url) {
        throw new Error("Сервис не вернул URL preview-видео");
      }
      if (popup) {
        popup.location.replace(response.url);
      } else {
        window.open(response.url, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      popup?.close();
      this._setStatus(this._errorText(err), "error");
    }
  }

  _openLastCallImage() {
    const entityId = this._lastCallImageEntityId;
    const imageState = entityId ? this._hass?.states?.[entityId] : null;
    const token = imageState?.attributes?.access_token;
    if (!entityId || !token) {
      this._setStatus("Снимок последнего звонка ещё не готов", "warning");
      return;
    }
    const url =
      `/api/image_proxy/${encodeURIComponent(entityId)}` +
      `?token=${encodeURIComponent(token)}`;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async _refreshLivePanel() {
    this._setStatus("Обновление LIVE…", "info");

    try {
      const entities = [
        this._liveEntityId,
        this._lastCallEntityId,
        this._lastCallImageEntityId,
      ]
        .filter(Boolean);
      if (entities.length) {
        await this._hass.callWS({
          type: "call_service",
          domain: "homeassistant",
          service: "update_entity",
          service_data: { entity_id: entities },
        });
      }
    } catch (_err) {
      // Recreating the live card below is still useful if update_entity is not
      // supported by a particular entity.
    }

    const host = this.shadowRoot.getElementById("live-host");
    if (this._liveCard) {
      this._liveCard.remove();
      this._liveCard = null;
    }
    if (host) {
      host.innerHTML = '<div class="panel-message">Перезапуск live-потока…</div>';
    }

    await this._ensureLiveCard();
    this._renderLiveMeta();
    this._setStatus("LIVE обновлён", "ok");
  }

  _setActiveTab(tab, updateStatus = true) {
    const normalized = ["live", "archive", "guests", "diagnostics"].includes(tab)
      ? tab
      : "archive";
    this._activeTab = normalized;

    for (const name of ["live", "archive", "guests", "diagnostics"]) {
      const panel = this.shadowRoot.getElementById(`panel-${name}`);
      const button = this.shadowRoot.getElementById(`tab-${name}`);
      if (panel) {
        panel.hidden = name !== normalized;
      }
      if (button) {
        const active = name === normalized;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      }
    }

    if (normalized === "live") {
      void this._ensureLiveCard();
      this._renderLiveMeta();
    } else if (normalized === "archive") {
      if (!this._archiveExportsLoaded) {
        void this._refreshArchiveExports(false);
      }
    } else if (normalized === "guests") {
      void this._refreshGuestAccess(false);
    } else if (normalized === "diagnostics") {
      void this._refreshRuntimeStatus(false);
    }

    if (updateStatus) {
      const names = {
        live: "LIVE",
        archive: "Архив",
        guests: "Гости",
        diagnostics: "Диагностика",
      };
      this._setStatus(`Раздел: ${names[normalized]}`, "info");
    }
  }

  async _ensureLiveCard() {
    const host = this.shadowRoot.getElementById("live-host");
    if (!host || !this._hass) return;

    await this._resolveLiveEntity();
    if (!this._liveEntityId || !this._hass.states?.[this._liveEntityId]) {
      host.innerHTML = `
        <div class="panel-message">
          Live-камера не найдена автоматически.<br>
          Укажите <code>live_entity: camera....</code> в YAML карточки.
        </div>
      `;
      return;
    }

    if (this._liveCard) {
      this._liveCard.hass = this._hass;
      return;
    }

    try {
      const helpers = await window.loadCardHelpers();
      const card = await helpers.createCardElement({
        type: "picture-entity",
        entity: this._liveEntityId,
        camera_view: "live",
        show_name: false,
        show_state: false,
      });
      card.hass = this._hass;
      this._liveCard = card;
      host.textContent = "";
      host.appendChild(card);

      const label = this.shadowRoot.getElementById("live-entity-label");
      if (label) label.textContent = this._liveEntityId;
      this._renderLiveMeta();
    } catch (err) {
      host.innerHTML = `<div class="panel-message error">${this._escapeHtml(this._errorText(err))}</div>`;
    }
  }

  async _refreshGuestAccess(force = false) {
    if (!this._deviceId || !this._hass) return;
    if (this._guestLoading) return;
    if (this._guestAccess && !force) {
      this._renderGuestAccess();
      return;
    }

    this._guestLoading = true;
    this._setGuestStatus("Загрузка гостевых доступов…", "info");
    this._setGuestButtonsDisabled(true);

    try {
      this._guestAccess = await this._callResponseService("get_guest_access", {
        device_id: this._deviceId,
      });
      this._renderGuestAccess();
      this._setGuestStatus("Гостевые доступы обновлены", "ok");
    } catch (err) {
      this._setGuestStatus(this._errorText(err), "error");
    } finally {
      this._guestLoading = false;
      this._setGuestButtonsDisabled(false);
    }
  }

  async _createGuestInvite() {
    if (!this._deviceId || this._guestLoading) return;

    const confirmed = window.confirm(
      "Создать новую ссылку-приглашение на доступ к домофону? " +
      "Любой, кто получит эту ссылку и сможет принять приглашение, " +
      "может получить гостевой доступ."
    );
    if (!confirmed) return;

    this._guestLoading = true;
    this._setGuestButtonsDisabled(true);
    this._setGuestStatus("Создание приглашения…", "info");

    try {
      const response = await this._callResponseService("create_guest_invite", {
        device_id: this._deviceId,
      });

      if (!response?.url) {
        throw new Error("API не вернул ссылку приглашения");
      }

      this._guestInviteUrl = response.url;

      if (!this._guestAccess) {
        this._guestAccess = {};
      }
      const generated = Array.isArray(this._guestAccess.generated_invites)
        ? this._guestAccess.generated_invites
        : [];
      this._guestAccess.generated_invites = [
        {
          id: response.invite_id,
          device_id: this._deviceId,
          skud_id: response.skud_id,
          url: response.url,
          created_at: response.created_at,
          access_id: response.access_id ?? null,
          source: "local_generated",
        },
        ...generated.filter((item) => item?.id !== response.invite_id),
      ];
      this._guestAccess.generated_count = this._guestAccess.generated_invites.length;

      this._renderGuestAccess();
      this._renderGuestInvite();
      this._setGuestStatus(
        "Приглашение создано и сохранено локально в Home Assistant. " +
        "Статус принятия сервер для такой ссылки отдельно не сообщает.",
        "ok"
      );
    } catch (err) {
      this._setGuestStatus(this._errorText(err), "error");
    } finally {
      this._guestLoading = false;
      this._setGuestButtonsDisabled(false);
    }
  }

  async _forgetGeneratedGuestInvite(item) {
    if (!item?.id || !this._deviceId || this._guestLoading) return;

    const confirmed = window.confirm(
      "Убрать эту ссылку из локального списка Home Assistant? " +
      "Это НЕ отзовёт приглашение на сервере Ufanet."
    );
    if (!confirmed) return;

    this._guestLoading = true;
    this._setGuestButtonsDisabled(true);
    this._setGuestStatus("Удаление локальной записи…", "info");

    try {
      await this._callResponseService("forget_guest_invite", {
        device_id: this._deviceId,
        invite_id: item.id,
      });

      if (this._guestInviteUrl === item.url) {
        this._guestInviteUrl = null;
      }

      const generated = Array.isArray(this._guestAccess?.generated_invites)
        ? this._guestAccess.generated_invites
        : [];
      this._guestAccess.generated_invites = generated.filter(
        (candidate) => candidate?.id !== item.id
      );
      this._guestAccess.generated_count = this._guestAccess.generated_invites.length;

      this._renderGuestAccess();
      this._setGuestStatus(
        "Локальная запись удалена. Серверное приглашение не отзывалось.",
        "ok"
      );
    } catch (err) {
      this._setGuestStatus(this._errorText(err), "error");
    } finally {
      this._guestLoading = false;
      this._setGuestButtonsDisabled(false);
    }
  }

  async _revokeSharedAccess(item) {
    if (!item?.access_id || !this._deviceId || this._guestLoading) return;

    const identity = item.name || item.username || `access_id ${item.access_id}`;
    const confirmed = window.confirm(
      `Отозвать гостевой доступ у ${identity}?\n\n` +
      `access_id: ${item.access_id}\n` +
      "После подтверждения доступ к домофону будет удалён на сервере Ufanet."
    );
    if (!confirmed) return;

    this._guestLoading = true;
    this._setGuestButtonsDisabled(true);
    this._setGuestStatus(`Отзыв доступа ${identity}…`, "info");

    try {
      await this._callResponseService("revoke_shared_access", {
        device_id: this._deviceId,
        access_id: Number(item.access_id),
      });

      const shared = Array.isArray(this._guestAccess?.shared_users)
        ? this._guestAccess.shared_users
        : [];
      this._guestAccess.shared_users = shared.filter(
        (candidate) => String(candidate?.access_id) !== String(item.access_id)
      );
      this._guestAccess.shared_count = this._guestAccess.shared_users.length;
      this._renderGuestAccess();

      this._setGuestStatus(
        `Доступ ${identity} отозван. Проверяю список на сервере…`,
        "ok"
      );

      // Server-side verification is also performed by the HA action.
      // Refresh once more so the UI mirrors the authoritative list.
      this._guestAccess = null;
    } catch (err) {
      this._setGuestStatus(this._errorText(err), "error");
      this._guestLoading = false;
      this._setGuestButtonsDisabled(false);
      return;
    }

    this._guestLoading = false;
    this._setGuestButtonsDisabled(false);
    await this._refreshGuestAccess(true);
  }

  async _createTemporaryGuestLink() {
    if (!this._deviceId || this._guestLoading) return;

    const select = this.shadowRoot.getElementById("temporary-duration");
    const durationMinutes = Number(select?.value || 60);
    if (!Number.isFinite(durationMinutes) || durationMinutes < 1) {
      this._setGuestStatus("Некорректная длительность временного ключа", "error");
      return;
    }

    const hours = durationMinutes / 60;
    const label = Number.isInteger(hours)
      ? `${hours} ч`
      : `${durationMinutes} мин`;

    const confirmed = window.confirm(
      `Создать временный ключ на ${label}?\n\n` +
      "Ссылка позволит открыть выбранный домофон до истечения срока."
    );
    if (!confirmed) return;

    this._guestLoading = true;
    this._setGuestButtonsDisabled(true);
    this._setGuestStatus(`Создание временного ключа на ${label}…`, "info");

    try {
      const response = await this._callResponseService(
        "create_temporary_guest_link",
        {
          device_id: this._deviceId,
          duration_minutes: durationMinutes,
        }
      );

      if (response?.link) {
        this._guestTemporaryCreatedUrl = response.link;
      }

      this._setGuestStatus(
        `Временный ключ на ${label} создан. Обновляю серверный список…`,
        "ok"
      );
    } catch (err) {
      this._setGuestStatus(this._errorText(err), "error");
      this._guestLoading = false;
      this._setGuestButtonsDisabled(false);
      return;
    }

    this._guestLoading = false;
    this._setGuestButtonsDisabled(false);
    this._guestAccess = null;
    await this._refreshGuestAccess(true);
  }

  async _revokeTemporaryGuestLink(item) {
    if (!item?.token || !this._deviceId || this._guestLoading) return;

    const expiry = this._formatGuestExpiry(item.time_end);
    const confirmed = window.confirm(
      `Отозвать временный ключ${expiry ? ` (${expiry})` : ""}?\n\n` +
      "Ссылка перестанет давать временный доступ к домофону."
    );
    if (!confirmed) return;

    this._guestLoading = true;
    this._setGuestButtonsDisabled(true);
    this._setGuestStatus("Отзыв временного ключа…", "info");

    try {
      await this._callResponseService("revoke_temporary_guest_link", {
        device_id: this._deviceId,
        token: item.token,
      });

      const current = Array.isArray(this._guestAccess?.temporary_links)
        ? this._guestAccess.temporary_links
        : [];
      this._guestAccess.temporary_links = current.filter(
        (candidate) => candidate?.token !== item.token
      );
      this._guestAccess.temporary_count =
        this._guestAccess.temporary_links.length;
      this._renderGuestAccess();

      this._setGuestStatus(
        "Временный ключ отозван. Проверяю серверный список…",
        "ok"
      );
    } catch (err) {
      this._setGuestStatus(this._errorText(err), "error");
      this._guestLoading = false;
      this._setGuestButtonsDisabled(false);
      return;
    }

    this._guestLoading = false;
    this._setGuestButtonsDisabled(false);
    this._guestAccess = null;
    await this._refreshGuestAccess(true);
  }

  _formatGuestExpiry(value) {
    if (!value) return "";
    try {
      return `до ${new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "short",
        timeStyle: "medium",
      }).format(new Date(value))}`;
    } catch (_err) {
      return `до ${value}`;
    }
  }

  _renderGuestAccess() {
    const generatedHost = this.shadowRoot.getElementById("guest-generated-list");
    const temporaryHost = this.shadowRoot.getElementById("guest-temporary-list");
    const sharedHost = this.shadowRoot.getElementById("guest-shared-list");
    const counts = this.shadowRoot.getElementById("guest-counts");
    if (!generatedHost || !temporaryHost || !sharedHost) return;

    generatedHost.textContent = "";
    temporaryHost.textContent = "";
    sharedHost.textContent = "";

    const generated = Array.isArray(this._guestAccess?.generated_invites)
      ? this._guestAccess.generated_invites
      : [];
    const temporary = Array.isArray(this._guestAccess?.temporary_links)
      ? this._guestAccess.temporary_links
      : [];
    const shared = Array.isArray(this._guestAccess?.shared_users)
      ? this._guestAccess.shared_users
      : [];

    if (counts) {
      counts.textContent =
        `Созданные приглашения: ${generated.length} • ` +
        `Временные ссылки: ${temporary.length} • ` +
        `Shared-пользователи: ${shared.length}`;
    }

    if (!generated.length) {
      const empty = document.createElement("div");
      empty.className = "guest-empty";
      empty.textContent =
        "Сохранённых приглашений нет. Новые ссылки будут сохраняться в Home Assistant автоматически.";
      generatedHost.appendChild(empty);
    } else {
      for (const item of generated) {
        const row = document.createElement("div");
        row.className = "guest-row";

        const main = document.createElement("div");
        main.className = "guest-row-main";

        const title = document.createElement("div");
        title.className = "guest-row-title";
        title.textContent = "Shared-приглашение";

        const details = [];
        if (item.created_at) {
          try {
            details.push(
              `создано ${new Intl.DateTimeFormat("ru-RU", {
                dateStyle: "short",
                timeStyle: "medium",
              }).format(new Date(item.created_at))}`
            );
          } catch (_err) {
            details.push(`создано ${item.created_at}`);
          }
        }
        details.push("сохранено локально");
        details.push("статус принятия неизвестен");

        const meta = document.createElement("div");
        meta.className = "guest-row-meta";
        meta.textContent = details.join(" • ");

        main.append(title, meta);

        const actions = document.createElement("div");
        actions.className = "guest-row-actions";

        if (item.url) {
          const copy = document.createElement("button");
          copy.type = "button";
          copy.className = "small-button";
          copy.textContent = "Копировать";
          copy.addEventListener("click", () => void this._copyText(item.url));

          const open = document.createElement("button");
          open.type = "button";
          open.className = "small-button";
          open.textContent = "Открыть";
          open.addEventListener("click", () =>
            window.open(item.url, "_blank", "noopener,noreferrer")
          );

          actions.append(copy, open);
        }

        const forget = document.createElement("button");
        forget.type = "button";
        forget.className = "small-button danger-button";
        forget.textContent = "Убрать";
        forget.title = "Удалить только локальную запись; серверное приглашение не отзывается";
        forget.addEventListener("click", () =>
          void this._forgetGeneratedGuestInvite(item)
        );
        actions.appendChild(forget);

        row.append(main, actions);
        generatedHost.appendChild(row);
      }
    }

    if (!temporary.length) {
      const empty = document.createElement("div");
      empty.className = "guest-empty";
      empty.textContent = "Активных временных ссылок нет.";
      temporaryHost.appendChild(empty);
    } else {
      for (const item of temporary) {
        const row = document.createElement("div");
        row.className = "guest-row";

        const main = document.createElement("div");
        main.className = "guest-row-main";
        const title = document.createElement("div");
        title.className = "guest-row-title";
        title.textContent =
          item.custom_name || item.name || "Временный ключ";

        const details = [];
        const expiry = this._formatGuestExpiry(item.time_end);
        if (expiry) details.push(expiry);
        if (item.address) details.push(item.address);

        const meta = document.createElement("div");
        meta.className = "guest-row-meta";
        meta.textContent = details.join(" • ") || "Активный временный ключ";
        main.append(title, meta);

        const actions = document.createElement("div");
        actions.className = "guest-row-actions";
        if (item.link) {
          const copy = document.createElement("button");
          copy.type = "button";
          copy.className = "small-button";
          copy.textContent = "Копировать";
          copy.addEventListener("click", () => void this._copyText(item.link));

          const open = document.createElement("button");
          open.type = "button";
          open.className = "small-button";
          open.textContent = "Открыть";
          open.addEventListener("click", () =>
            window.open(item.link, "_blank", "noopener,noreferrer")
          );

          actions.append(copy, open);
        }

        if (item.token) {
          const revoke = document.createElement("button");
          revoke.type = "button";
          revoke.className = "small-button danger-button";
          revoke.textContent = "Отозвать";
          revoke.title = "Удалить временный ключ на сервере Ufanet";
          revoke.addEventListener("click", () =>
            void this._revokeTemporaryGuestLink(item)
          );
          actions.appendChild(revoke);
        }

        row.append(main, actions);
        temporaryHost.appendChild(row);
      }
    }

    if (!shared.length) {
      const empty = document.createElement("div");
      empty.className = "guest-empty";
      empty.textContent = "Shared-доступ пока никому не выдан.";
      sharedHost.appendChild(empty);
    } else {
      for (const item of shared) {
        const row = document.createElement("div");
        row.className = "guest-row";

        const main = document.createElement("div");
        main.className = "guest-row-main";
        const title = document.createElement("div");
        title.className = "guest-row-title";
        title.textContent = item.name || item.username || `Доступ ${item.access_id ?? ""}`;

        const details = [];
        if (item.username && item.username !== item.name) details.push(item.username);
        if (item.scope) details.push(`scope: ${item.scope}`);
        if (item.expires_at) details.push(`до ${item.expires_at}`);

        const meta = document.createElement("div");
        meta.className = "guest-row-meta";
        meta.textContent = details.join(" • ") || "Shared access";

        main.append(title, meta);

        const actions = document.createElement("div");
        actions.className = "guest-row-actions";

        if (item.access_id) {
          const revoke = document.createElement("button");
          revoke.type = "button";
          revoke.className = "small-button danger-button";
          revoke.textContent = "Отозвать доступ";
          revoke.title = `Отозвать accepted shared access ${item.access_id}`;
          revoke.addEventListener("click", () =>
            void this._revokeSharedAccess(item)
          );
          actions.appendChild(revoke);
        }

        row.append(main, actions);
        sharedHost.appendChild(row);
      }
    }

    this._renderGuestInvite();
  }

  _renderGuestInvite() {
    const box = this.shadowRoot.getElementById("guest-invite-box");
    const input = this.shadowRoot.getElementById("guest-invite-url");
    if (!box || !input) return;

    if (!this._guestInviteUrl) {
      box.hidden = true;
      input.value = "";
      return;
    }

    box.hidden = false;
    input.value = this._guestInviteUrl;
  }

  async _copyText(text) {
    if (!text) return;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        this._setGuestStatus("Ссылка скопирована в буфер обмена", "ok");
        return;
      }
    } catch (_err) {
      // Fallback below.
    }

    const input = this.shadowRoot.getElementById("guest-invite-url");
    if (input && input.value === text) {
      input.focus();
      input.select();
      try {
        document.execCommand("copy");
        this._setGuestStatus("Ссылка скопирована", "ok");
        return;
      } catch (_err) {
        // Fall through.
      }
    }

    this._setGuestStatus("Не удалось скопировать автоматически — выделите ссылку вручную.", "warning");
  }

  _setGuestButtonsDisabled(disabled) {
    for (const id of ["refresh-guests", "create-guest-invite", "create-temporary-guest"]) {
      const button = this.shadowRoot.getElementById(id);
      if (button) button.disabled = disabled;
    }
  }

  _setGuestStatus(message, type = "info") {
    const status = this.shadowRoot.getElementById("guest-status");
    if (!status) return;
    status.textContent = message || "";
    status.dataset.type = type;
  }

  _escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async _ensureHlsPlayer() {
    if (customElements.get("ha-hls-player")) {
      return;
    }

    if (window.loadCardHelpers) {
      try {
        const helpers = await window.loadCardHelpers();
        if (helpers?.createCardElement && this._config.entity) {
          await helpers.createCardElement({
            type: "picture-entity",
            entity: this._config.entity,
            camera_view: "live",
          });
        }
      } catch (_err) {
        // Fall through to whenDefined below.
      }
    }

    if (!customElements.get("ha-hls-player")) {
      await Promise.race([
        customElements.whenDefined("ha-hls-player"),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("HA HLS player is not available")), 10000)
        ),
      ]);
    }
  }

  async _callResponseService(service, serviceData) {
    const result = await this._hass.callWS({
      type: "call_service",
      domain: "ufanet_intercom",
      service,
      service_data: serviceData,
      return_response: true,
    });
    return result?.response ?? result;
  }

  async _refreshRanges() {
    const response = await this._callResponseService("get_archive_ranges", {
      device_id: this._deviceId,
    });

    this._timezone = response?.timezone || "UTC";
    this._earliest = Number.isFinite(Number(response?.earliest))
      ? Number(response.earliest)
      : null;
    this._latest = Number.isFinite(Number(response?.latest))
      ? Number(response.latest)
      : null;

    this._ranges = Array.isArray(response?.ranges)
      ? response.ranges
          .map((item) => ({
            from: Number(item.from),
            duration: Number(item.duration),
          }))
          .filter(
            (item) =>
              Number.isFinite(item.from) &&
              Number.isFinite(item.duration) &&
              item.duration > 0
          )
          .sort((a, b) => a.from - b.from)
      : [];

    this._days = Array.isArray(response?.days)
      ? response.days
          .filter((day) => day?.date && Array.isArray(day?.intervals))
          .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      : [];
    this._daysByDate = new Map(this._days.map((day) => [day.date, day]));

    const tz = this.shadowRoot.getElementById("timezone");
    if (tz) {
      tz.textContent = this._timezone;
    }

    const dateInput = this.shadowRoot.getElementById("date");
    if (dateInput && this._days.length) {
      dateInput.min = response?.first_date || this._days[0].date;
      dateInput.max = response?.last_date || this._days[this._days.length - 1].date;
    }

    const windowInfo = this.shadowRoot.getElementById("archive-window");
    if (windowInfo && this._earliest != null && this._latest != null) {
      windowInfo.textContent =
        `Доступный архив: ${this._formatDisplayTime(this._earliest)} — ` +
        `${this._formatDisplayTime(this._latest)}`;
    }

    this._renderDayIntervals(dateInput?.value || null);
  }

  async _refreshCallEvents(dateText, force = false) {
    if (!dateText || !this._deviceId) return;

    if (!force && this._callEventsCache.has(dateText)) {
      this._callEvents = this._callEventsCache.get(dateText) || [];
      this._callEventsDate = dateText;
      this._renderCallEvents(dateText);
      this._renderTimeline(dateText);
      return;
    }

    const label = this.shadowRoot.getElementById("calls-label");
    if (label) label.textContent = `Звонки за ${dateText}: загрузка…`;

    try {
      const response = await this._callResponseService("get_call_events", {
        device_id: this._deviceId,
        date: dateText,
      });

      const events = Array.isArray(response?.events)
        ? response.events
            .map((item) => ({
              ...item,
              timestamp: Number(item.timestamp),
              second_of_day: Number(item.second_of_day),
            }))
            .filter(
              (item) =>
                Number.isFinite(item.timestamp) &&
                Number.isFinite(item.second_of_day)
            )
            .sort((a, b) => a.timestamp - b.timestamp)
        : [];

      this._callEventsCache.set(dateText, events);
      const selectedDate = this.shadowRoot.getElementById("date")?.value;
      if (selectedDate === dateText) {
        this._callEvents = events;
        this._callEventsDate = dateText;
        this._renderCallEvents(dateText);
        this._renderTimeline(dateText);
      }
    } catch (err) {
      if (label) label.textContent = `Звонки: ${this._errorText(err)}`;
    }
  }

  async _refreshMotionEvents(dateText, force = false) {
    if (!dateText || !this._deviceId) return;

    if (!force && this._motionEventsCache.has(dateText)) {
      const cached = this._motionEventsCache.get(dateText) || {};
      this._motionEvents = Array.isArray(cached.events) ? cached.events : [];
      this._motionEventsDate = dateText;
      this._motionEventsSupported = cached.supported === true;
      this._motionEventsError = false;
      this._renderTimeline(dateText);
      return;
    }

    try {
      const response = await this._callResponseService("get_motion_events", {
        device_id: this._deviceId,
        date: dateText,
      });
      const supported = response?.supported === true;
      const events = supported && Array.isArray(response?.events)
        ? response.events
            .map((item) => ({
              timestamp: Number(item.timestamp),
              local_datetime: item.local_datetime,
              local_time: item.local_time,
              second_of_day: Number(item.second_of_day),
            }))
            .filter(
              (item) =>
                Number.isFinite(item.timestamp) &&
                Number.isFinite(item.second_of_day)
            )
            .sort((a, b) => a.timestamp - b.timestamp)
        : [];

      this._motionEventsCache.set(dateText, { supported, events });
      const selectedDate = this.shadowRoot.getElementById("date")?.value;
      if (selectedDate === dateText) {
        this._motionEvents = events;
        this._motionEventsDate = dateText;
        this._motionEventsSupported = supported;
        this._motionEventsError = false;
        this._renderTimeline(dateText);
      }
    } catch (_err) {
      const selectedDate = this.shadowRoot.getElementById("date")?.value;
      if (selectedDate === dateText) {
        this._motionEvents = [];
        this._motionEventsDate = dateText;
        this._motionEventsSupported = null;
        this._motionEventsError = true;
        this._renderTimeline(dateText);
      }
    }
  }

  async _loadMotionEvent(event) {
    if (!event || !Number.isFinite(Number(event.timestamp))) return;
    const eventEpoch = Number(event.timestamp);
    const requested = eventEpoch - MOTION_EVENT_LEAD_SECONDS;
    let resolved = this._resolveTarget(requested, 1);
    if (resolved == null) resolved = this._resolveTarget(eventEpoch, -1);
    if (resolved == null) {
      this._setStatus("Для этого события движения запись архива недоступна", "warning");
      return;
    }
    await this._loadEpoch(resolved);
  }

  _callAddress(event) {
    const parts = [];
    if (event?.address) parts.push(String(event.address));
    if (event?.porch != null && String(event.porch) !== "") {
      parts.push(`подъезд ${event.porch}`);
    }
    if (event?.flat != null && String(event.flat) !== "") {
      parts.push(`кв. ${event.flat}`);
    }
    return parts.join(", ");
  }

  _callLeadSeconds() {
    return Math.max(0, Math.min(60, Number(this._config.call_lead_seconds ?? 15)));
  }

  async _loadCallEvent(event) {
    if (!event || !Number.isFinite(Number(event.timestamp))) return;
    const requested = Number(event.timestamp) - this._callLeadSeconds();
    let resolved = this._resolveTarget(requested, 1);
    if (resolved == null) resolved = this._resolveTarget(Number(event.timestamp), -1);
    if (resolved == null) {
      this._setStatus("Для этого звонка соответствующая запись архива недоступна", "warning");
      return;
    }
    await this._loadEpoch(resolved);
  }

  _renderCallEvents(dateText) {
    const host = this.shadowRoot.getElementById("call-events");
    const label = this.shadowRoot.getElementById("calls-label");
    if (!host || !label) return;

    host.textContent = "";
    const events = this._callEventsDate === dateText ? this._callEvents : [];
    label.textContent = `Звонки за ${dateText || "—"}: ${events.length}`;

    if (!events.length) {
      const empty = document.createElement("div");
      empty.className = "calls-empty";
      empty.textContent = "Вызовов за выбранный день нет";
      host.appendChild(empty);
      return;
    }

    for (const event of events) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "call-row";
      const address = this._callAddress(event);

      const icon = document.createElement("span");
      icon.className = "call-row-icon";
      icon.textContent = "🔔";

      const main = document.createElement("span");
      main.className = "call-row-main";
      const time = document.createElement("span");
      time.className = "call-row-time";
      time.textContent = String(event.local_time || "").slice(0, 8);
      const addressNode = document.createElement("span");
      addressNode.className = "call-row-address";
      addressNode.textContent = address || "Вызов домофона";
      main.append(time, addressNode);

      const action = document.createElement("span");
      action.className = "call-row-action";
      action.textContent = "Перейти";

      row.append(icon, main, action);
      row.title = "Открыть архив вокруг момента звонка";
      row.addEventListener("click", () => void this._loadCallEvent(event));
      host.appendChild(row);
    }
  }

  _duration() {
    const input = this.shadowRoot.getElementById("duration");
    return Math.max(30, Number(input?.value || this._config.duration || 300));
  }

  _step() {
    const input = this.shadowRoot.getElementById("step");
    return Math.max(10, Number(input?.value || this._config.step || 60));
  }

  _formatStep(value) {
    if (value % 3600 === 0) {
      return `${value / 3600} ч`;
    }
    if (value % 60 === 0) {
      return `${value / 60} мин`;
    }
    return `${value} с`;
  }

  _updateStepButtons() {
    const label = this._formatStep(this._step());
    const previous = this.shadowRoot.getElementById("previous");
    const next = this.shadowRoot.getElementById("next");
    if (previous) previous.textContent = `⏪ Назад ${label}`;
    if (next) next.textContent = `Вперёд ${label} ⏩`;
  }

  async _goLatest(refresh = true) {
    if (refresh || !this._ranges.length) {
      await this._refreshRanges();
    }
    if (!this._ranges.length) {
      throw new Error("Архивных записей не найдено");
    }

    const newest = this._ranges.reduce((best, item) => {
      const end = item.from + item.duration;
      const bestEnd = best.from + best.duration;
      return end > bestEnd ? item : best;
    });

    const duration = this._duration();
    const start = Math.max(newest.from, newest.from + newest.duration - duration);
    await this._loadEpoch(start);
  }

  async _shift(direction) {
    if (this._currentEpoch == null) {
      await this._goLatest();
      return;
    }

    const target = this._currentEpoch + direction * this._step();
    let resolved = this._resolveTarget(target, direction);

    // A card can stay open while new archive appears. Refresh once at the
    // newest edge before reporting that there is no newer recording.
    if (resolved == null && direction > 0) {
      await this._refreshRanges();
      resolved = this._resolveTarget(target, direction);
    }

    if (resolved == null) {
      this._setStatus(
        direction < 0 ? "Более старой записи нет" : "Более новой записи нет",
        "warning"
      );
      return;
    }

    await this._loadEpoch(resolved);
  }

  _resolveTarget(target, direction) {
    for (const range of this._ranges) {
      const end = range.from + range.duration;
      if (range.from <= target && target < end) {
        return target;
      }
    }

    if (direction > 0) {
      const next = this._ranges.find((range) => range.from > target);
      return next ? next.from : null;
    }

    for (let i = this._ranges.length - 1; i >= 0; i -= 1) {
      const range = this._ranges[i];
      const end = range.from + range.duration;
      if (end <= target) {
        return Math.max(range.from, end - 1);
      }
    }
    return null;
  }

  _timeToSeconds(value) {
    const parts = String(value || "00:00:00").split(":").map(Number);
    return (parts[0] || 0) * 3600 + (parts[1] || 0) * 60 + (parts[2] || 0);
  }

  _secondsToTime(value) {
    const seconds = Math.max(0, Math.min(86399, Math.floor(value)));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  _nearestRecordedDate(dateText) {
    if (!this._days.length) return null;
    if (this._daysByDate.has(dateText)) return dateText;

    const target = Date.parse(`${dateText}T00:00:00Z`);
    let best = this._days[0].date;
    let bestDistance = Math.abs(Date.parse(`${best}T00:00:00Z`) - target);
    for (const day of this._days.slice(1)) {
      const distance = Math.abs(Date.parse(`${day.date}T00:00:00Z`) - target);
      if (distance < bestDistance) {
        best = day.date;
        bestDistance = distance;
      }
    }
    return best;
  }

  _resolveLocalSelection(dateText, seconds) {
    const resolvedDate = this._nearestRecordedDate(dateText);
    if (!resolvedDate) return null;

    const day = this._daysByDate.get(resolvedDate);
    if (!day?.intervals?.length) return null;

    for (const interval of day.intervals) {
      const start = Number(interval.start_second);
      const end = Number(interval.end_second);
      if (start <= seconds && seconds < end) {
        return {
          date: resolvedDate,
          seconds,
          epoch: Number(interval.from) + (seconds - start),
          adjusted: resolvedDate !== dateText,
        };
      }
    }

    let best = null;
    for (const interval of day.intervals) {
      const start = Number(interval.start_second);
      const end = Number(interval.end_second);
      const candidates = [
        { seconds: start, epoch: Number(interval.from) },
        {
          seconds: Math.max(start, Math.min(86399, end - 1)),
          epoch: Math.max(Number(interval.from), Number(interval.to) - 1),
        },
      ];
      for (const candidate of candidates) {
        const distance = Math.abs(candidate.seconds - seconds);
        if (best == null || distance < best.distance) {
          best = { ...candidate, distance };
        }
      }
    }

    return best
      ? {
          date: resolvedDate,
          seconds: best.seconds,
          epoch: best.epoch,
          adjusted: true,
        }
      : null;
  }

  async _handleDateChange() {
    const dateInput = this.shadowRoot.getElementById("date");
    const timeInput = this.shadowRoot.getElementById("time");
    if (!dateInput?.value) return;

    const originalDate = dateInput.value;
    const resolvedDate = this._nearestRecordedDate(originalDate);
    if (!resolvedDate) return;

    if (resolvedDate !== originalDate) {
      dateInput.value = resolvedDate;
      this._setStatus(
        `За ${originalDate} записи нет. Выбрана ближайшая дата ${resolvedDate}.`,
        "warning"
      );
    }

    this._renderDayIntervals(resolvedDate);
    await Promise.all([
      this._refreshCallEvents(resolvedDate),
      this._refreshMotionEvents(resolvedDate),
    ]);
    const day = this._daysByDate.get(resolvedDate);
    if (!day?.intervals?.length) return;

    const currentSeconds = this._timeToSeconds(timeInput?.value || "00:00:00");
    const resolved = this._resolveLocalSelection(resolvedDate, currentSeconds);
    if (resolved && timeInput) {
      timeInput.value = this._secondsToTime(resolved.seconds);
    }
    await this._loadFromInputs();
  }

  async _loadFromInputs() {
    const dateInput = this.shadowRoot.getElementById("date");
    const timeInput = this.shadowRoot.getElementById("time");
    if (!dateInput?.value || !timeInput?.value) return;

    const requestedDate = dateInput.value;
    const requestedSeconds = this._timeToSeconds(timeInput.value);
    const resolved = this._resolveLocalSelection(requestedDate, requestedSeconds);
    if (!resolved) {
      this._setStatus("Для выбранной даты архивных записей нет", "warning");
      return;
    }

    if (resolved.adjusted) {
      dateInput.value = resolved.date;
      timeInput.value = this._secondsToTime(resolved.seconds);
      this._renderDayIntervals(resolved.date);
      this._setStatus(
        `В выбранное время записи нет. Перенесено на ${resolved.date} ${timeInput.value}.`,
        "warning"
      );
    }

    const start = `${resolved.date}T${this._secondsToTime(resolved.seconds)}`;
    await this._loadStart(start);
  }

  async _loadEpoch(epoch) {
    await this._loadStart(new Date(epoch * 1000).toISOString());
  }

  async _loadStart(start) {
    if (this._loading) return;

    this._loading = true;
    this._setButtonsDisabled(true);
    this._setStatus("Загрузка видео…", "info");

    try {
      const response = await this._callResponseService("get_archive_url", {
        device_id: this._deviceId,
        start,
        duration: this._duration(),
      });

      if (!response?.url) {
        throw new Error("Сервис не вернул URL архива");
      }

      this._currentEpoch = Date.parse(response.start_utc) / 1000;
      this._archiveDownload = null;
      this._renderArchiveDownloadReady();
      this._setDateTimeInputs(this._currentEpoch);

      const effective = this.shadowRoot.getElementById("effective-duration");
      if (effective) {
        effective.textContent =
          Number(response.duration) !== Number(response.requested_duration)
            ? `Фрагмент обрезан до ${response.duration} с из-за конца непрерывной записи`
            : "";
      }

      await this._setPlayerUrl(response.url);
      this._setStatus(`Архив: ${this._formatDisplayTime(this._currentEpoch)}`, "ok");
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    } finally {
      this._loading = false;
      this._setButtonsDisabled(false);
    }
  }

  _exportRetentionDays() {
    const value = Number(this._config?.export_retention_days ?? 30);
    if (!Number.isFinite(value)) return 30;
    return Math.max(0, Math.min(3650, Math.round(value)));
  }

  _exportMaxTotalMb() {
    const gb = Number(this._config?.export_max_gb ?? 5);
    if (!Number.isFinite(gb)) return 5120;
    return Math.max(0, Math.round(gb * 1024));
  }

  _formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) return "0 Б";
    if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(value >= 10 * 1024 ** 3 ? 1 : 2)} ГБ`;
    if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(value >= 10 * 1024 ** 2 ? 1 : 2)} МБ`;
    if (value >= 1024) return `${(value / 1024).toFixed(1)} КБ`;
    return `${value} Б`;
  }

  _formatDurationShort(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return "—";
    const total = Math.round(value);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    return `${minutes}:${String(secs).padStart(2, "0")}`;
  }

  async _refreshArchiveExports(force = false) {
    if (!this._deviceId || !this._hass) return;
    if (this._archiveExportsLoading) return;
    if (this._archiveExportsLoaded && !force) {
      this._renderArchiveExports();
      return;
    }

    this._archiveExportsLoading = true;
    const refresh = this.shadowRoot.getElementById("archive-library-refresh");
    if (refresh) refresh.disabled = true;

    try {
      const response = await this._callResponseService("list_archive_exports", {
        device_id: this._deviceId,
      });
      this._archiveExports = Array.isArray(response?.items) ? response.items : [];
      this._archiveExportsTotalBytes = Number(response?.total_bytes || 0);
      this._archiveExportsLoaded = true;
      this._renderArchiveExports();
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    } finally {
      this._archiveExportsLoading = false;
      if (refresh) refresh.disabled = false;
    }
  }

  _renderArchiveExports() {
    const host = this.shadowRoot.getElementById("archive-library-list");
    const summary = this.shadowRoot.getElementById("archive-library-summary");
    const policy = this.shadowRoot.getElementById("archive-library-policy");
    if (!host) return;

    const items = Array.isArray(this._archiveExports) ? this._archiveExports : [];
    if (summary) {
      summary.textContent =
        `${items.length} файл(ов) • ${this._formatBytes(this._archiveExportsTotalBytes || 0)}`;
    }
    if (policy) {
      const days = this._exportRetentionDays();
      const maxMb = this._exportMaxTotalMb();
      const ageText = days > 0 ? `${days} дн.` : "без срока";
      const sizeText = maxMb > 0
        ? this._formatBytes(maxMb * 1024 * 1024)
        : "без лимита";
      policy.textContent = `Автоочистка: ${ageText} • ${sizeText}`;
    }

    host.textContent = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "archive-library-empty";
      empty.textContent = "Сохранённых MP4 пока нет.";
      host.appendChild(empty);
      return;
    }

    for (const item of items) {
      const row = document.createElement("div");
      row.className = "archive-library-row";

      const main = document.createElement("div");
      main.className = "archive-library-main";

      const title = document.createElement("div");
      title.className = "archive-library-title";
      const baseTitle = item.recorded_local || item.filename || "Экспорт MP4";
      title.textContent =
        item.source === "call" ? `🔔 Звонок • ${baseTitle}` : baseTitle;

      const details = [];
      if (item.duration_seconds != null) {
        details.push(this._formatDurationShort(item.duration_seconds));
      }
      details.push(this._formatBytes(item.size_bytes));
      if (item.modified_at) {
        try {
          details.push(
            `сохранено ${new Intl.DateTimeFormat("ru-RU", {
              dateStyle: "short",
              timeStyle: "short",
            }).format(new Date(item.modified_at))}`
          );
        } catch (_err) {
          // Ignore formatting failure.
        }
      }

      const meta = document.createElement("div");
      meta.className = "archive-library-meta";
      meta.textContent = details.join(" • ");

      main.append(title, meta);

      const actions = document.createElement("div");
      actions.className = "archive-library-actions";

      const open = document.createElement("button");
      open.type = "button";
      open.className = "small-button";
      open.textContent = "Открыть";
      open.addEventListener("click", () => void this._openStoredArchiveExport(item, false));

      const download = document.createElement("button");
      download.type = "button";
      download.className = "small-button";
      download.textContent = "Скачать";
      download.addEventListener("click", () => void this._openStoredArchiveExport(item, true));

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "small-button danger-button";
      remove.textContent = "Удалить";
      remove.addEventListener("click", () => void this._deleteStoredArchiveExport(item));

      actions.append(open, download, remove);
      row.append(main, actions);
      host.appendChild(row);
    }
  }

  async _resolveStoredExport(item) {
    if (!item?.media_content_id) {
      throw new Error("У файла отсутствует media_content_id");
    }
    const resolved = await this._hass.callWS({
      type: "media_source/resolve_media",
      media_content_id: item.media_content_id,
      expires: 21600,
    });
    if (!resolved?.url) {
      throw new Error("Media Source не вернул URL");
    }
    return resolved.url;
  }

  async _openStoredArchiveExport(item, download = false) {
    try {
      const url = await this._resolveStoredExport(item);
      if (!download) {
        window.open(url, "_blank", "noopener,noreferrer");
        return;
      }

      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = item.filename || "ufanet_archive.mp4";
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    }
  }

  async _deleteStoredArchiveExport(item) {
    if (!item?.filename) return;
    const confirmed = window.confirm(
      `Удалить сохранённый ролик?\n\n${item.filename}\n\n` +
      "Файл будет физически удалён из Home Assistant Media."
    );
    if (!confirmed) return;

    try {
      await this._callResponseService("delete_archive_export", {
        device_id: this._deviceId,
        filename: item.filename,
      });
      this._archiveExports = this._archiveExports.filter(
        (candidate) => candidate?.filename !== item.filename
      );
      this._archiveExportsTotalBytes = this._archiveExports.reduce(
        (sum, candidate) => sum + Number(candidate?.size_bytes || 0),
        0
      );
      this._renderArchiveExports();
      this._setStatus("Экспортированный MP4 удалён", "ok");
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    }
  }

  async _cleanupStoredArchiveExports() {
    const days = this._exportRetentionDays();
    const maxMb = this._exportMaxTotalMb();
    const confirmed = window.confirm(
      "Применить правила автоочистки сейчас?\n\n" +
      `Возраст: ${days > 0 ? `${days} дней` : "без ограничения"}\n` +
      `Объём: ${maxMb > 0 ? this._formatBytes(maxMb * 1024 * 1024) : "без ограничения"}`
    );
    if (!confirmed) return;

    const button = this.shadowRoot.getElementById("archive-library-cleanup");
    if (button) button.disabled = true;
    try {
      const serviceData = { device_id: this._deviceId };
      if (this._hasYamlOption("export_retention_days")) {
        serviceData.retention_days = days;
      }
      if (this._hasYamlOption("export_max_gb")) {
        serviceData.max_total_mb = maxMb;
      }
      const response = await this._callResponseService(
        "cleanup_archive_exports",
        serviceData
      );
      this._setStatus(
        `Очистка завершена: удалено ${response?.deleted_count || 0} файл(ов), ` +
        `${this._formatBytes(response?.deleted_bytes || 0)}`,
        response?.limit_satisfied === false ? "warning" : "ok"
      );
      this._archiveExportsLoaded = false;
      await this._refreshArchiveExports(true);
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    } finally {
      if (button) button.disabled = false;
    }
  }

  _formatExpiry(value) {
    const epoch = Number(value);
    if (!Number.isFinite(epoch) || epoch <= 0) return "—";
    const delta = epoch - Date.now() / 1000;
    if (delta <= 0) return "истёк";
    if (delta < 3600) return `${Math.round(delta / 60)} мин`;
    return `${(delta / 3600).toFixed(delta >= 36000 ? 0 : 1)} ч`;
  }

  async _refreshRuntimeStatus(force = false) {
    if (!this._deviceId || !this._hass || this._runtimeStatusLoading) return;
    if (this._runtimeStatus && !force) {
      this._renderRuntimeStatus();
      return;
    }

    this._runtimeStatusLoading = true;
    const button = this.shadowRoot.getElementById("diagnostics-refresh");
    if (button) button.disabled = true;

    try {
      this._runtimeStatus = await this._callResponseService(
        "get_runtime_status",
        { device_id: this._deviceId }
      );
      this._renderRuntimeStatus();
    } catch (err) {
      this._setStatus(this._errorText(err), "error");
    } finally {
      this._runtimeStatusLoading = false;
      if (button) button.disabled = false;
    }
  }

  _diagnosticSection(host, titleText, rows) {
    const section = document.createElement("div");
    section.className = "diagnostics-section";

    const title = document.createElement("div");
    title.className = "diagnostics-section-title";
    title.textContent = titleText;
    section.appendChild(title);

    for (const [labelText, valueRaw, state] of rows) {
      const row = document.createElement("div");
      row.className = "diagnostics-row";

      const label = document.createElement("span");
      label.className = "diagnostics-label";
      label.textContent = labelText;

      const value = document.createElement("span");
      value.className = "diagnostics-value";
      value.textContent =
        valueRaw === null || valueRaw === undefined || valueRaw === ""
          ? "—"
          : String(valueRaw);
      if (state) value.dataset.state = state;

      row.append(label, value);
      section.appendChild(row);
    }

    host.appendChild(section);
  }

  _imageErrorReason(code) {
    const reasons = {
      invalid_url: "preview URL не прошёл HTTPS-проверку",
      unsupported_scheme: "неподдерживаемая схема preview URL",
      missing_host: "в preview URL отсутствует hostname",
      embedded_credentials: "preview URL содержит встроенные credentials",
      empty_preview: "получен пустой preview",
      size_limit: "preview превышает 32 МиБ",
      download_error: "ошибка загрузки preview",
      decode_error: "ffmpeg не смог извлечь JPEG",
      ffmpeg_unavailable: "ffmpeg недоступен",
      unexpected_error: "непредвиденная ошибка",
    };
    return reasons[code] || code || null;
  }

  _renderRuntimeStatus() {
    const host = this.shadowRoot.getElementById("diagnostics-content");
    if (!host) return;

    host.textContent = "";
    const status = this._runtimeStatus;
    if (!status) {
      const empty = document.createElement("div");
      empty.className = "panel-message";
      empty.textContent = "Нажмите «Обновить», чтобы получить диагностику.";
      host.appendChild(empty);
      return;
    }

    const skud = status.skud || {};
    const camera = status.camera || {};
    const auth = status.auth || {};
    const coordinator = status.coordinator || {};
    const calls = status.call_coordinator || {};
    const fcm = status.fcm || {};
    const image = status.last_call_image || {};
    const archive = status.archive || {};
    const auto = status.auto_save || {};
    const exports = status.exports || {};

    this._diagnosticSection(host, "Интеграция", [
      ["Версия", status.version],
      ["Device ID", status.device_id],
      ["SKUD ID", skud.id],
      ["Роль / модель", `${skud.role || "—"} / ${skud.model ?? "—"}`],
      ["Open", `${skud.open_type || "—"} / ${skud.open_in_talk || "—"}`],
    ]);

    this._diagnosticSection(host, "Камера / UCAMS", [
      ["Camera number", camera.number],
      ["Server", camera.server_domain],
      ["Vendor", camera.server_vendor],
      ["Timezone", camera.timezone],
      ["Потоков", camera.streams_count],
      ["Тариф", camera.tariff_name],
      ["Архив", camera.dvr_hours != null ? `${camera.dvr_hours} ч` : null],
      ["Ошибка camera API", status.camera_error_type],
    ]);

    this._diagnosticSection(host, "Авторизация", [
      [
        "Ufanet access",
        auth.ufanet_access_present
          ? `есть • ещё ${this._formatExpiry(auth.ufanet_access_expires_at)}`
          : "нет",
        auth.ufanet_access_present ? "ok" : "error",
      ],
      [
        "Refresh token",
        auth.ufanet_refresh_present
          ? `есть • ещё ${this._formatExpiry(auth.ufanet_refresh_expires_at)}`
          : "нет",
        auth.ufanet_refresh_present ? "ok" : "error",
      ],
      [
        "UCAMS token",
        auth.ucams_access_present
          ? `есть • ещё ${this._formatExpiry(auth.ucams_access_expires_at)}`
          : "нет",
        auth.ucams_access_present ? "ok" : "warning",
      ],
    ]);

    this._diagnosticSection(host, "Polling / архив", [
      ["Режим звонков", status.call_update_mode || "polling"],
      [
        "SKUD coordinator",
        `${coordinator.update_interval_seconds ?? "—"} с • ${
          coordinator.last_update_success ? "OK" : "ошибка"
        }`,
        coordinator.last_update_success ? "ok" : "error",
      ],
      [
        "Call coordinator",
        `${calls.update_interval_seconds ?? "—"} с • ${
          calls.last_update_success ? "OK" : "ошибка"
        }`,
        calls.last_update_success ? "ok" : "error",
      ],
      ["Последний звонок доступен", calls.latest_call_present ? "да" : "нет"],
      ["Archive controller", archive.ready ? "ready" : "not ready", archive.ready ? "ok" : "warning"],
      ["Archive duration / step", `${archive.duration_seconds ?? "—"} / ${archive.step_seconds ?? "—"} с`],
    ]);

    this._diagnosticSection(host, "Снимок последнего звонка", [
      ["Настроен", image.configured ? "да" : "нет", image.configured ? "ok" : "warning"],
      [
        "ffmpeg",
        image.ffmpeg_available === true
          ? "доступен"
          : image.ffmpeg_available === false
            ? "не найден / не запускается"
            : "не проверен",
        image.ffmpeg_available === true
          ? "ok"
          : image.ffmpeg_available === false
            ? "error"
            : "warning",
      ],
      ["JPEG готов", image.ready ? "да" : "нет", image.ready ? "ok" : "warning"],
      ["Preview доступен", image.preview_available ? "да" : "нет"],
      ["HTTP → HTTPS", image.preview_https_upgraded ? "применено" : "не требовалось", image.preview_https_upgraded ? "warning" : "ok"],
      ["Формат preview", image.preview_payload_kind],
      ["Повтор для звонка", image.retry_suppressed ? "остановлен" : "разрешён", image.retry_suppressed ? "warning" : null],
      ["Извлечение", image.loading ? "выполняется" : "ожидание", image.loading ? "warning" : null],
      ["Успешно / ошибок", `${image.success_count ?? 0} / ${image.failure_count ?? 0}`],
      ["Ошибок подряд", image.consecutive_failures ?? 0, Number(image.consecutive_failures || 0) > 0 ? "warning" : null],
      ["Последний JPEG", image.last_success_at],
      ["Причина ошибки", this._imageErrorReason(image.last_error_code), image.last_error_code ? "error" : null],
      ["Тип исключения", image.last_error_type, image.last_error_type ? "error" : null],
      ["Repairs warning", image.repair_issue_active ? "активен" : "нет", image.repair_issue_active ? "error" : "ok"],
    ]);

    if (status.call_update_mode === "fcm") {
      this._diagnosticSection(host, "FCM (экспериментально)", [
        ["Настроен", fcm.configured ? "да" : "нет", fcm.configured ? "ok" : "error"],
        [
          "Регистрация Firebase/FCM",
          fcm.firebase_registration_succeeded ? "успешно" : "не выполнена",
          fcm.firebase_registration_succeeded ? "ok" : "error",
        ],
        [
          "Регистрация в Ufanet",
          fcm.ufanet_registration_succeeded ? "принята" : "не выполнена",
          fcm.ufanet_registration_succeeded ? "ok" : "error",
        ],
        [
          "Задачи listener",
          fcm.listener_started ? "запущен" : "не запущен",
          fcm.listener_started ? "ok" : "error",
        ],
        [
          "Headless listener",
          fcm.listener_running ? "подключён" : "не подключён",
          fcm.listener_running ? "ok" : "warning",
        ],
        ["Транспорт", fcm.transport_state, fcm.active ? "ok" : "warning"],
        [
          "Резервный polling",
          fcm.fallback_polling_active ? "активен" : "редкий контрольный",
          fcm.fallback_polling_active ? "warning" : "ok",
        ],
        ["Watchdog", fcm.watchdog_running ? "работает" : "остановлен", fcm.watchdog_running ? "ok" : "error"],
        [
          "Локальное состояние",
          fcm.state_recovered ? "восстановлено" : "исправно",
          fcm.state_recovered ? "warning" : "ok",
        ],
        ["Причина восстановления", fcm.state_recovery_reason, fcm.state_recovery_reason ? "warning" : null],
        [
          "Удаление регистрации",
          fcm.unregister_pending
            ? "ожидает повтора"
            : fcm.last_unregistration_succeeded === true
              ? "успешно"
              : "не требуется",
          fcm.unregister_pending ? "warning" : "ok",
        ],
        ["Ошибка удаления", fcm.last_unregistration_error_type, fcm.last_unregistration_error_type ? "error" : null],
        ["Переподключения / ошибки", `${fcm.reconnect_count ?? 0} / ${fcm.consecutive_failures ?? 0}`],
        ["Push / SIP", `${fcm.received_push_count ?? 0} / ${fcm.received_sip_push_count ?? 0}`],
        ["Последнее подключение", fcm.last_connected_at],
        ["Последнее отключение", fcm.last_disconnected_at],
        ["Последний SIP push", fcm.last_sip_push_at],
        ["Последняя ошибка", fcm.last_error_type, fcm.last_error_type ? "error" : null],
      ]);
    }

    this._diagnosticSection(host, "Автосохранение звонков", [
      ["Включено", auto.enabled ? "да" : "нет", auto.enabled ? "ok" : "warning"],
      ["Фрагмент", `${auto.lead_seconds ?? 0} с до + ${auto.after_seconds ?? 0} с после`],
      ["Ожидают", auto.pending_count ?? 0],
      ["Запланировано", auto.scheduled_count ?? 0],
      ["Успешно", auto.success_count ?? 0, Number(auto.success_count || 0) > 0 ? "ok" : null],
      ["Ошибок", auto.failure_count ?? 0, Number(auto.failure_count || 0) > 0 ? "error" : null],
      ["Последний файл", auto.last_filename],
      ["Последняя ошибка", auto.last_error_type || auto.last_error_message],
    ]);

    this._diagnosticSection(host, "Медиатека", [
      ["Всего файлов", exports.count ?? 0],
      ["Авто 🔔", exports.auto_saved_count ?? 0],
      ["Ручных", exports.manual_count ?? 0],
      ["Объём", this._formatBytes(exports.total_bytes || 0)],
    ]);
  }

  async _copyRuntimeStatus() {
    if (!this._runtimeStatus) {
      await this._refreshRuntimeStatus(true);
    }
    if (!this._runtimeStatus) return;

    const text = JSON.stringify(this._runtimeStatus, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      this._setStatus("Диагностика скопирована в буфер обмена", "ok");
    } catch (_err) {
      this._setStatus("Не удалось скопировать диагностику", "error");
    }
  }

  async _copyArchiveDownloadUrl() {
    const url = this._archiveDownload?.url;
    if (!url) return;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        this._setStatus("Защищённый URL MP4 скопирован", "ok");
        return;
      }
    } catch (_err) {
      // Fall back to selecting the visible link below.
    }

    this._setStatus(
      "Не удалось скопировать автоматически — откройте готовую MP4-ссылку.",
      "warning"
    );
  }

  _archiveExportDuration() {
    const value = Number(
      this.shadowRoot.getElementById("archive-export-duration")?.value ||
      this._config?.export_default_duration ||
      300
    );
    return Math.max(1, Math.min(21600, value));
  }

  async _prepareArchiveDownload() {
    if (this._currentEpoch == null || this._loading) {
      this._setStatus("Сначала выберите точку архива", "warning");
      return;
    }

    const button = this.shadowRoot.getElementById("prepare-archive-download");
    if (button) button.disabled = true;
    this._setStatus("Экспортирую HLS в MP4 через ffmpeg…", "info");

    try {
      const serviceData = {
        device_id: this._deviceId,
        start: new Date(this._currentEpoch * 1000).toISOString(),
        duration: this._archiveExportDuration(),
      };
      if (this._hasYamlOption("export_retention_days")) {
        serviceData.retention_days = this._exportRetentionDays();
      }
      if (this._hasYamlOption("export_max_gb")) {
        serviceData.max_total_mb = this._exportMaxTotalMb();
      }

      const response = await this._callResponseService(
        "get_archive_download_url",
        serviceData
      );

      if (!response?.media_content_id) {
        throw new Error("Сервис не вернул media_content_id экспортированного MP4");
      }

      let resolved;
      try {
        resolved = await this._hass.callWS({
          type: "media_source/resolve_media",
          media_content_id: response.media_content_id,
          expires: 21600,
        });
      } catch (err) {
        throw new Error(
          `MP4 сохранён в Home Assistant Media, но не удалось получить ссылку: ${this._errorText(err)}`
        );
      }

      if (!resolved?.url) {
        throw new Error("Media Source не вернул URL экспортированного MP4");
      }

      this._archiveDownload = {
        ...response,
        url: resolved.url,
        mime_type: resolved.mime_type || response.content_type || "video/mp4",
      };
      this._renderArchiveDownloadReady();

      const clipped =
        Number(response.duration) !== Number(response.requested_duration)
          ? `; обрезан до ${response.duration} с на границе записи`
          : "";
      const cleanupDeleted = Number(response.cleanup?.deleted_count || 0);
      const cleanupText = cleanupDeleted
        ? `; автоочистка удалила ${cleanupDeleted} файл(ов)`
        : "";
      const limitWarning = response.cleanup?.limit_satisfied === false
        ? "; новый файл оставлен, но лимит объёма всё ещё превышен"
        : "";
      this._setStatus(
        `MP4 сохранён в Home Assistant Media${clipped}${cleanupText}${limitWarning}`,
        response.cleanup?.limit_satisfied === false ? "warning" : "ok"
      );
      this._archiveExportsLoaded = false;
      void this._refreshArchiveExports(true);
    } catch (err) {
      this._archiveDownload = null;
      this._renderArchiveDownloadReady();
      this._setStatus(this._errorText(err), "error");
    } finally {
      if (button) button.disabled = false;
    }
  }

  _renderArchiveDownloadReady() {
    const box = this.shadowRoot.getElementById("archive-download-ready");
    const link = this.shadowRoot.getElementById("archive-download-link");
    const copy = this.shadowRoot.getElementById("archive-download-copy");
    const meta = this.shadowRoot.getElementById("archive-download-meta");
    if (!box || !link || !meta) return;

    if (!this._archiveDownload?.url) {
      box.hidden = true;
      link.removeAttribute("href");
      return;
    }

    const response = this._archiveDownload;
    box.hidden = false;
    link.href = response.url;
    link.download = response.filename || "ufanet_archive.mp4";
    link.textContent = "Скачать / открыть MP4";

    if (copy) {
      copy.disabled = false;
    }

    const details = [`${response.duration} с`];
    if (Number(response.content_length) > 0) {
      const mb = Number(response.content_length) / 1024 / 1024;
      details.push(`≈ ${mb.toFixed(mb >= 10 ? 1 : 2)} МБ`);
    }
    if (response.storage === "home_assistant_media") {
      details.push("сохранено в Media");
    }
    meta.textContent = details.join(" • ");
  }

  async _setPlayerUrl(url) {
    await this._ensureHlsPlayer();

    if (!this._player) {
      const host = this.shadowRoot.getElementById("player-host");
      host.textContent = "";

      this._player = document.createElement("ha-hls-player");
      this._player.controls = true;
      this._player.autoPlay = true;
      this._player.playsInline = true;
      this._player.muted = false;
      this._player.aspectRatio = 16 / 9;
      this._player.fitMode = "contain";
      host.appendChild(this._player);
    }

    this._player.url = url;
  }

  _formatLocalParts(epoch) {
    const parts = new Intl.DateTimeFormat("sv-SE", {
      timeZone: this._timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(epoch * 1000));

    const map = {};
    for (const part of parts) {
      if (part.type !== "literal") map[part.type] = part.value;
    }
    return {
      date: `${map.year}-${map.month}-${map.day}`,
      time: `${map.hour}:${map.minute}:${map.second}`,
    };
  }

  _formatDisplayTime(epoch) {
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: this._timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).format(new Date(epoch * 1000));
  }

  _setDateTimeInputs(epoch) {
    const local = this._formatLocalParts(epoch);
    const dateInput = this.shadowRoot.getElementById("date");
    const timeInput = this.shadowRoot.getElementById("time");
    if (dateInput) dateInput.value = local.date;
    if (timeInput) timeInput.value = local.time;
    if (Number(this._timelineZoomHours) < 24) {
      this._timelineCenterSeconds = this._timeToSeconds(local.time);
    }
    this._renderDayIntervals(local.date);
    if (this._callEventsDate !== local.date) {
      void this._refreshCallEvents(local.date);
    } else {
      this._renderCallEvents(local.date);
    }
    if (this._motionEventsDate !== local.date) {
      void this._refreshMotionEvents(local.date);
    }
  }

  _formatIntervalTime(value) {
    const raw = String(value || "");
    if (raw.startsWith("24:00")) return "24:00";
    return raw.slice(0, 5);
  }

  _timelineWindow() {
    const zoomHours = [24, 6, 1].includes(Number(this._timelineZoomHours))
      ? Number(this._timelineZoomHours)
      : 24;
    const span = zoomHours * 3600;

    if (span >= 86400) {
      return { start: 0, end: 86400, span: 86400 };
    }

    let center = Number(this._timelineCenterSeconds);
    if (!Number.isFinite(center)) {
      center = this._timeToSeconds(
        this.shadowRoot.getElementById("time")?.value || "12:00:00"
      );
    }

    let windowStart = center - span / 2;
    windowStart = Math.max(0, Math.min(86400 - span, windowStart));
    return {
      start: windowStart,
      end: windowStart + span,
      span,
    };
  }

  _formatAxisTime(seconds) {
    if (seconds >= 86400 - 0.5) return "24:00";
    const value = Math.max(0, Math.min(86399, Math.round(seconds)));
    const h = Math.floor(value / 3600);
    const m = Math.floor((value % 3600) / 60);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  _renderTimelineAxis(windowRange) {
    const axis = this.shadowRoot.getElementById("timeline-axis");
    const windowLabel = this.shadowRoot.getElementById("timeline-window-label");
    if (!axis) return;

    axis.textContent = "";
    for (let i = 0; i <= 4; i += 1) {
      const seconds = windowRange.start + (windowRange.span * i) / 4;
      const span = document.createElement("span");
      span.textContent = this._formatAxisTime(seconds);
      axis.appendChild(span);
    }

    if (windowLabel) {
      windowLabel.textContent =
        `${this._formatAxisTime(windowRange.start)}–${this._formatAxisTime(windowRange.end)}`;
    }
  }

  _currentLocalSecondsForTimeline() {
    const selectedDate = this.shadowRoot.getElementById("date")?.value;
    if (this._currentEpoch != null && selectedDate) {
      const local = this._formatLocalParts(this._currentEpoch);
      if (local.date === selectedDate) {
        return this._timeToSeconds(local.time);
      }
    }
    return this._timeToSeconds(
      this.shadowRoot.getElementById("time")?.value || "12:00:00"
    );
  }

  _updateZoomButtons() {
    for (const hours of [24, 6, 1]) {
      const button = this.shadowRoot.getElementById(`zoom-${hours}`);
      if (!button) continue;
      const active = Number(this._timelineZoomHours) === hours;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  _setTimelineZoom(hours, centerSeconds = null, announce = false) {
    const normalized = [24, 6, 1].includes(Number(hours)) ? Number(hours) : 24;
    this._timelineZoomHours = normalized;

    if (normalized < 24) {
      const center = centerSeconds == null
        ? this._currentLocalSecondsForTimeline()
        : Number(centerSeconds);
      if (Number.isFinite(center)) {
        this._timelineCenterSeconds = Math.max(0, Math.min(86399, center));
      }
    }

    this._updateZoomButtons();
    const dateText = this.shadowRoot.getElementById("date")?.value || null;
    this._renderTimeline(dateText);

    if (announce) {
      this._setStatus(
        normalized === 24
          ? "Timeline: весь день"
          : `Timeline: масштаб ${normalized} ч`,
        "info"
      );
    }
  }

  _timelineSecondsFromPointer(clientX) {
    const track = this.shadowRoot.getElementById("timeline-track");
    if (!track) return null;
    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) return null;
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const windowRange = this._timelineWindow();
    return Math.max(
      0,
      Math.min(86399, windowRange.start + ratio * windowRange.span)
    );
  }

  _handleTimelineWheel(event) {
    if (!event || Math.abs(Number(event.deltaY || 0)) < 1) return;

    const levels = [24, 6, 1];
    const currentIndex = levels.indexOf(Number(this._timelineZoomHours));
    const index = currentIndex >= 0 ? currentIndex : 0;
    const zoomIn = event.deltaY < 0;
    const nextIndex = zoomIn
      ? Math.min(levels.length - 1, index + 1)
      : Math.max(0, index - 1);

    if (nextIndex === index) {
      // At the end of the zoom range, allow normal page scrolling.
      return;
    }

    const now = Date.now();
    if (now - this._lastTimelineWheelAt < 120) {
      event.preventDefault();
      return;
    }
    this._lastTimelineWheelAt = now;
    event.preventDefault();

    const track = this.shadowRoot.getElementById("timeline-track");
    if (!track) return;
    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) return;

    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const oldWindow = this._timelineWindow();
    const focusSeconds = oldWindow.start + ratio * oldWindow.span;
    const newHours = levels[nextIndex];
    const newSpan = newHours * 3600;

    // Keep the time under the mouse pointer approximately under the same
    // pointer position after zooming, then clamp the window to 00:00–24:00.
    let desiredStart = focusSeconds - ratio * newSpan;
    desiredStart = Math.max(0, Math.min(86400 - newSpan, desiredStart));
    const center = desiredStart + newSpan / 2;
    this._setTimelineZoom(newHours, center, false);
  }

  _timelineCanPan() {
    return Number(this._timelineZoomHours) < 24;
  }

  _clampTimelineCenter(centerSeconds) {
    const windowRange = this._timelineWindow();
    const halfSpan = windowRange.span / 2;
    const minCenter = halfSpan;
    const maxCenter = 86400 - halfSpan;
    return Math.max(minCenter, Math.min(maxCenter, Number(centerSeconds)));
  }

  _handleTimelinePointerDown(event) {
    if (!this._timelineCanPan()) return;
    if (!event || event.button !== 0 || event.isPrimary === false) return;

    const track = this.shadowRoot.getElementById("timeline-track");
    if (!track) return;

    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) return;

    const windowRange = this._timelineWindow();
    this._timelineDrag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startCenter: windowRange.start + windowRange.span / 2,
      width: rect.width,
      span: windowRange.span,
      moved: false,
    };

    track.dataset.dragging = "false";
  }

  _handleTimelinePointerMove(event) {
    const drag = this._timelineDrag;
    if (!drag || event.pointerId !== drag.pointerId) return;

    const track = this.shadowRoot.getElementById("timeline-track");
    if (!track) return;

    const deltaX = event.clientX - drag.startX;

    // Keep small pointer jitter as an ordinary click.
    if (!drag.moved && Math.abs(deltaX) < 5) return;

    if (!drag.moved) {
      drag.moved = true;
      try {
        track.setPointerCapture(event.pointerId);
      } catch (_err) {
        // Pointer capture is an enhancement; panning still works without it.
      }
      track.dataset.dragging = "true";
    }

    event.preventDefault();

    // DVR/map-like behavior: dragging content to the right reveals earlier time;
    // dragging left reveals later time.
    const deltaSeconds = -(deltaX / drag.width) * drag.span;
    const nextCenter = this._clampTimelineCenter(
      drag.startCenter + deltaSeconds
    );

    this._timelineCenterSeconds = nextCenter;
    const dateText = this.shadowRoot.getElementById("date")?.value || null;
    this._renderTimeline(dateText);
  }

  _finishTimelinePointerDrag(event) {
    const drag = this._timelineDrag;
    if (!drag || (event && event.pointerId !== drag.pointerId)) return;

    const track = this.shadowRoot.getElementById("timeline-track");

    if (drag.moved) {
      // Pointerup normally generates a click. Suppress that click so a finished
      // pan never seeks the archive accidentally.
      this._timelineSuppressClickUntil = Date.now() + 350;
      if (track) {
        track.dataset.dragging = "false";
        try {
          if (track.hasPointerCapture(drag.pointerId)) {
            track.releasePointerCapture(drag.pointerId);
          }
        } catch (_err) {
          // Ignore unsupported/expired capture.
        }
      }

      const windowRange = this._timelineWindow();
      this._setStatus(
        `Timeline: ${this._formatAxisTime(windowRange.start)}–${this._formatAxisTime(windowRange.end)}`,
        "info"
      );
    } else if (track) {
      track.dataset.dragging = "false";
    }

    this._timelineDrag = null;
  }

  _renderTimeline(dateText) {
    const track = this.shadowRoot.getElementById("timeline-track");
    const hint = this.shadowRoot.getElementById("timeline-hint");
    if (!track) return;

    for (const node of [...track.querySelectorAll(".timeline-segment, .call-marker, .motion-marker")]) {
      node.remove();
    }

    const windowRange = this._timelineWindow();
    const eventSummary = this.shadowRoot.getElementById("timeline-event-summary");
    if (eventSummary) {
      const callText = this._callEventsDate === dateText ? String(this._callEvents.length) : "…";
      let motionText = "…";
      if (this._motionEventsDate === dateText) {
        if (this._motionEventsSupported === true) {
          motionText = String(this._motionEvents.length);
        } else if (this._motionEventsError) {
          motionText = "ошибка";
        } else {
          motionText = "—";
        }
      }
      eventSummary.textContent = `🔔 ${callText} • движение ${motionText}`;
    }
    track.dataset.pannable = this._timelineCanPan() ? "true" : "false";
    this._renderTimelineAxis(windowRange);
    this._updateZoomButtons();

    const day = dateText ? this._daysByDate.get(dateText) : null;
    if (!day?.intervals?.length) {
      track.dataset.empty = "true";
      if (hint) {
        hint.textContent = dateText
          ? `За ${dateText} записи нет`
          : "Выберите дату";
      }
      this._updateTimelineMarker(dateText);
      return;
    }

    track.dataset.empty = "false";
    if (hint) {
      hint.textContent = Number(this._timelineZoomHours) === 24
        ? "Клик — переход • колесо ↑ — увеличить"
        : "Клик — переход • drag — прокрутка • колесо — масштаб";
    }

    for (const interval of day.intervals) {
      const originalStart = Math.max(0, Math.min(86400, Number(interval.start_second)));
      const originalEnd = Math.max(originalStart, Math.min(86400, Number(interval.end_second)));
      if (originalEnd <= originalStart) continue;

      const visibleStart = Math.max(originalStart, windowRange.start);
      const visibleEnd = Math.min(originalEnd, windowRange.end);
      if (visibleEnd <= visibleStart) continue;

      const segment = document.createElement("button");
      segment.type = "button";
      segment.className = "timeline-segment";
      segment.style.left = `${((visibleStart - windowRange.start) / windowRange.span) * 100}%`;
      segment.style.width = `${((visibleEnd - visibleStart) / windowRange.span) * 100}%`;
      segment.title = `${this._formatIntervalTime(interval.start)}–${this._formatIntervalTime(interval.end)}`;
      segment.setAttribute("aria-label", `Запись ${segment.title}`);
      segment.addEventListener("click", (event) => {
        event.stopPropagation();
        if (Date.now() < this._timelineSuppressClickUntil) return;
        const rect = segment.getBoundingClientRect();
        const ratio = rect.width > 0
          ? Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
          : 0;
        const seconds = Math.min(
          86399,
          Math.floor(visibleStart + ratio * (visibleEnd - visibleStart))
        );
        const epoch = Number(interval.from) + Math.max(0, seconds - originalStart);
        void this._loadEpoch(epoch);
      });
      track.appendChild(segment);
    }

    if (this._callEventsDate === dateText && this._callEvents.length) {
      for (const event of this._callEvents) {
        const seconds = Number(event.second_of_day);
        if (!Number.isFinite(seconds)) continue;
        if (seconds < windowRange.start || seconds > windowRange.end) continue;

        const left = ((seconds - windowRange.start) / windowRange.span) * 100;
        const marker = document.createElement("button");
        marker.type = "button";
        marker.className = "call-marker";
        marker.style.left = `${Math.max(0, Math.min(100, left))}%`;
        marker.textContent = "🔔";
        const address = this._callAddress(event);
        marker.title = `${event.local_time || ""}${address ? ` • ${address}` : ""}`;
        marker.setAttribute("aria-label", `Звонок ${marker.title}`);
        marker.addEventListener("pointerdown", (ev) => ev.stopPropagation());
        marker.addEventListener("click", (ev) => {
          ev.stopPropagation();
          void this._loadCallEvent(event);
        });
        track.appendChild(marker);
      }
    }

    if (
      this._motionEventsDate === dateText &&
      this._motionEventsSupported === true &&
      this._motionEvents.length
    ) {
      for (const event of this._motionEvents) {
        const seconds = Number(event.second_of_day);
        if (!Number.isFinite(seconds)) continue;
        if (seconds < windowRange.start || seconds > windowRange.end) continue;

        const left = ((seconds - windowRange.start) / windowRange.span) * 100;
        const marker = document.createElement("button");
        marker.type = "button";
        marker.className = "motion-marker";
        marker.style.left = `${Math.max(0, Math.min(100, left))}%`;
        marker.title = `Движение ${event.local_time || ""}`.trim();
        marker.setAttribute("aria-label", marker.title);
        marker.addEventListener("pointerdown", (ev) => ev.stopPropagation());
        marker.addEventListener("click", (ev) => {
          ev.stopPropagation();
          void this._loadMotionEvent(event);
        });
        track.appendChild(marker);
      }
    }

    this._updateTimelineMarker(dateText);
  }

  _updateTimelineMarker(dateText) {
    const marker = this.shadowRoot.getElementById("timeline-marker");
    const markerLabel = this.shadowRoot.getElementById("timeline-marker-label");
    if (!marker) return;

    if (this._currentEpoch == null || !dateText) {
      marker.hidden = true;
      if (markerLabel) markerLabel.hidden = true;
      return;
    }

    const local = this._formatLocalParts(this._currentEpoch);
    if (local.date !== dateText) {
      marker.hidden = true;
      if (markerLabel) markerLabel.hidden = true;
      return;
    }

    const seconds = this._timeToSeconds(local.time);
    const windowRange = this._timelineWindow();
    if (seconds < windowRange.start || seconds > windowRange.end) {
      marker.hidden = true;
      if (markerLabel) markerLabel.hidden = true;
      return;
    }

    const left = Math.max(
      0,
      Math.min(100, ((seconds - windowRange.start) / windowRange.span) * 100)
    );
    marker.style.left = `${left}%`;
    marker.hidden = false;

    if (markerLabel) {
      markerLabel.textContent = local.time.slice(0, 5);
      markerLabel.style.left = `${left}%`;
      markerLabel.hidden = false;
    }
  }

  async _handleTimelineClick(event) {
    if (Date.now() < this._timelineSuppressClickUntil) return;

    const dateInput = this.shadowRoot.getElementById("date");
    const timeInput = this.shadowRoot.getElementById("time");
    if (!dateInput?.value) return;

    const requested = this._timelineSecondsFromPointer(event.clientX);
    if (requested == null) return;
    const requestedSeconds = Math.min(86399, Math.floor(requested));
    const resolved = this._resolveLocalSelection(dateInput.value, requestedSeconds);
    if (!resolved) {
      this._setStatus("Для выбранной даты архивных записей нет", "warning");
      return;
    }

    if (timeInput) timeInput.value = this._secondsToTime(resolved.seconds);
    if (resolved.adjusted) {
      this._setStatus(
        `В ${this._secondsToTime(requestedSeconds)} записи нет. ` +
        `Переход к ближайшей записи ${this._secondsToTime(resolved.seconds)}.`,
        "warning"
      );
    }
    await this._loadEpoch(resolved.epoch);
  }

  _renderDayIntervals(dateText) {
    this._renderTimeline(dateText);
    const host = this.shadowRoot.getElementById("day-intervals");
    const label = this.shadowRoot.getElementById("day-label");
    if (!host || !label) return;

    host.textContent = "";
    if (!dateText) {
      label.textContent = "Доступные интервалы";
      return;
    }

    const day = this._daysByDate.get(dateText);
    if (!day?.intervals?.length) {
      label.textContent = `За ${dateText} записи нет`;
      return;
    }

    const totalMinutes = Math.round(Number(day.total_duration || 0) / 60);
    label.textContent = `Запись за ${dateText}: ${day.intervals.length} интервал(ов), ${totalMinutes} мин`;

    for (const interval of day.intervals) {
      const button = document.createElement("button");
      button.className = "interval-chip";
      button.textContent = `${this._formatIntervalTime(interval.start)}–${this._formatIntervalTime(interval.end)}`;
      button.title = "Перейти к началу этого участка записи";
      button.addEventListener("click", () => void this._loadEpoch(Number(interval.from)));
      host.appendChild(button);
    }

    if (this._callEventsDate === dateText) {
      this._renderCallEvents(dateText);
    }
  }

  _setButtonsDisabled(disabled) {
    for (const button of this.shadowRoot.querySelectorAll("button")) {
      button.disabled = disabled;
    }
  }

  _setStatus(message, type = "info") {
    const status = this.shadowRoot.getElementById("status");
    if (!status) return;
    status.textContent = message || "";
    status.dataset.type = type;
  }

  _errorText(err) {
    if (!err) return "Неизвестная ошибка";
    if (typeof err === "string") return err;
    if (err.message) return err.message;
    return String(err);
  }

  _renderSkeleton() {
    if (!this.shadowRoot || !this._config) return;

    this._liveCard = null;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { overflow: hidden; }
        [hidden] { display: none !important; }
        .header { font-size: 20px; font-weight: 500; padding: 16px 16px 8px; }

        .tabs {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 4px;
          padding: 0 12px 12px;
          border-bottom: 1px solid var(--divider-color);
        }
        .tab-button {
          min-height: 40px;
          border-radius: 9px;
          background: transparent;
          color: var(--secondary-text-color);
          font-size: 13px;
          font-weight: 600;
        }
        .tab-button.active {
          color: var(--primary-color);
          background: color-mix(in srgb, var(--primary-color) 12%, transparent);
        }
        .panel { min-width: 0; }
        .panel-message {
          padding: 26px 16px;
          color: var(--secondary-text-color);
          text-align: center;
          line-height: 1.5;
        }
        .panel-message.error { color: var(--error-color); }

        /* LIVE */
        #live-host {
          min-height: 260px;
          background: #000;
        }
        #live-host > * { display: block; }
        .live-controls {
          padding: 12px 16px;
          display: grid;
          gap: 10px;
        }
        .live-status-row {
          display: flex;
          flex-wrap: wrap;
          gap: 7px;
          align-items: center;
        }
        .live-status-pill {
          padding: 5px 9px;
          border-radius: 999px;
          font-size: 11px;
          background: var(--secondary-background-color);
          color: var(--secondary-text-color);
        }
        .live-status-pill[data-available="true"] {
          color: var(--success-color, #43a047);
        }
        .live-status-pill[data-available="false"] {
          color: var(--error-color);
        }
        .live-main-actions {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 8px;
        }
        .open-door-button {
          min-height: 54px;
          color: var(--text-primary-color, #fff);
          background: var(--primary-color);
          font-size: 16px;
          font-weight: 700;
        }
        .live-last-call {
          padding: 11px;
          border-radius: 10px;
          background: var(--secondary-background-color);
          border: 1px solid transparent;
          transition: box-shadow .2s ease, border-color .2s ease;
        }
        .live-last-call.new-call {
          border-color: var(--warning-color, #f0a000);
          box-shadow: 0 0 0 3px color-mix(in srgb, var(--warning-color, #f0a000) 22%, transparent);
        }
        .tab-button.new-call {
          color: var(--warning-color, #f0a000);
          box-shadow: inset 0 0 0 1px var(--warning-color, #f0a000);
        }
        .live-last-call-title {
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
        }
        .live-last-call-time {
          font-size: 14px;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
        .live-last-call-address {
          color: var(--secondary-text-color);
          font-size: 12px;
          margin-top: 3px;
        }
        .live-call-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 8px;
        }
        .live-footer {
          padding: 0 16px 12px;
          color: var(--secondary-text-color);
          font-size: 11px;
        }

        /* ARCHIVE */
        #archive-window { padding: 10px 16px 10px; font-size: 12px; color: var(--secondary-text-color); }
        .controls {
          padding: 6px 16px 12px;
          display: grid;
          grid-template-columns: minmax(145px, 1.2fr) minmax(120px, 1fr) minmax(105px, .8fr) minmax(105px, .8fr);
          gap: 10px;
          align-items: end;
        }
        label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--secondary-text-color); }
        input, select {
          box-sizing: border-box; width: 100%; min-height: 40px; padding: 7px 9px;
          color: var(--primary-text-color); background: var(--card-background-color, var(--ha-card-background));
          border: 1px solid var(--divider-color); border-radius: 8px; font: inherit;
        }
        .timeline-wrap { padding: 0 16px 14px; }
        .timeline-head {
          display: flex; justify-content: space-between; gap: 8px; align-items: center;
          margin-bottom: 5px; color: var(--secondary-text-color); font-size: 12px;
        }
        .timeline-zoom { display: inline-flex; gap: 4px; align-items: center; }
        .timeline-event-summary {
          margin-left: 7px; color: var(--secondary-text-color); font-size: 10px; font-weight: 400;
        }
        .zoom-button {
          min-height: 28px; padding: 3px 9px; border-radius: 8px; font-size: 11px; font-weight: 500;
        }
        .zoom-button.active { color: var(--text-primary-color, #fff); background: var(--primary-color); }
        .timeline-subhead {
          display: flex; justify-content: space-between; gap: 8px; margin-bottom: 5px;
          color: var(--secondary-text-color); font-size: 10px;
        }
        #timeline-hint { text-align: right; }
        #timeline-axis {
          display: grid; grid-template-columns: repeat(5, 1fr); margin: 0 0 4px;
          color: var(--secondary-text-color); font-size: 10px; line-height: 1;
        }
        #timeline-axis span:nth-child(2), #timeline-axis span:nth-child(3), #timeline-axis span:nth-child(4) { text-align: center; }
        #timeline-axis span:last-child { text-align: right; }
        #timeline-track {
          position: relative; width: 100%; height: 34px; overflow: visible;
          border-radius: 8px; background: var(--divider-color); cursor: crosshair;
          box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary-text-color) 12%, transparent);
          touch-action: pan-y;
        }
        #timeline-track::before {
          content: ""; position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
          background: repeating-linear-gradient(
            to right,
            transparent 0,
            transparent calc(25% - 1px),
            color-mix(in srgb, var(--primary-text-color) 16%, transparent) calc(25% - 1px),
            color-mix(in srgb, var(--primary-text-color) 16%, transparent) 25%
          );
          z-index: 3;
        }
        .timeline-segment {
          position: absolute; top: 0; bottom: 0; min-height: 0; padding: 0; border-radius: 0;
          background: var(--primary-color); opacity: .78; z-index: 1; cursor: pointer;
        }
        .timeline-segment:first-of-type { border-radius: 7px 0 0 7px; }
        .timeline-segment:hover { opacity: 1; background: var(--primary-color); }
        .call-marker {
          position: absolute; top: -11px; width: 24px; height: 24px; min-height: 24px;
          padding: 0; transform: translateX(-50%); border-radius: 50%; z-index: 5;
          display: flex; align-items: center; justify-content: center; font-size: 13px;
          background: var(--card-background-color, var(--ha-card-background));
          border: 2px solid var(--warning-color, #f0a000); cursor: pointer;
          box-shadow: 0 1px 3px rgba(0,0,0,.28);
        }
        .call-marker:hover { transform: translateX(-50%) scale(1.12); }
        .motion-marker {
          position: absolute; top: 0; bottom: 0; width: 12px; min-height: 0; padding: 0;
          transform: translateX(-50%); z-index: 4; border: 0; border-radius: 0;
          background: transparent; cursor: pointer;
        }
        .motion-marker::before {
          content: ""; position: absolute; top: 3px; bottom: 3px; left: 4px; width: 4px;
          border-radius: 2px; background: var(--success-color, #43a047);
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--card-background-color) 70%, transparent);
        }
        .motion-marker:hover::before { left: 3px; width: 6px; }
        #timeline-marker {
          position: absolute; top: -5px; bottom: -5px; width: 3px; transform: translateX(-1px);
          background: var(--error-color); border-radius: 2px; z-index: 6; pointer-events: none;
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--card-background-color) 75%, transparent);
        }
        #timeline-marker-label {
          position: absolute; top: -25px; transform: translateX(-50%); z-index: 7; pointer-events: none;
          padding: 2px 5px; border-radius: 5px; background: var(--primary-text-color);
          color: var(--card-background-color, var(--ha-card-background)); font-size: 10px; font-weight: 600;
          white-space: nowrap;
        }
        #timeline-track[data-pannable="true"] { cursor: grab; }
        #timeline-track[data-pannable="true"][data-dragging="true"] { cursor: grabbing; user-select: none; }
        #timeline-track[data-pannable="true"][data-dragging="true"] .timeline-segment { cursor: grabbing; }
        #timeline-track[data-empty="true"] { opacity: .55; cursor: default; }
        .day-ranges { padding: 0 16px 12px; }
        #day-label { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 7px; }
        #day-intervals { display: flex; flex-wrap: wrap; gap: 6px; max-height: 86px; overflow-y: auto; }

        button {
          min-height: 42px; border: 0; border-radius: 10px; color: var(--primary-text-color);
          background: var(--secondary-background-color); cursor: pointer; font: inherit; font-weight: 500;
        }
        button:hover { background: var(--divider-color); }
        button:disabled { opacity: .5; cursor: wait; }
        .interval-chip { min-height: 30px; padding: 4px 9px; border-radius: 14px; font-size: 12px; font-weight: 400; }

        .calls { padding: 0 16px 14px; }
        .calls-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; margin-bottom: 7px; }
        #calls-label { font-size: 12px; color: var(--secondary-text-color); }
        #refresh-calls { min-height: 30px; padding: 4px 10px; font-size: 12px; border-radius: 14px; }
        #call-events { display: grid; gap: 6px; }
        .calls-empty { color: var(--secondary-text-color); font-size: 12px; padding: 4px 0; }
        .call-row {
          width: 100%; min-height: 46px; display: grid; grid-template-columns: 30px 1fr auto;
          gap: 8px; align-items: center; padding: 6px 10px; text-align: left; font-weight: 400;
        }
        .call-row-icon { font-size: 17px; text-align: center; }
        .call-row-main { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
        .call-row-time { font-weight: 600; font-variant-numeric: tabular-nums; }
        .call-row-address { color: var(--secondary-text-color); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .call-row-action { color: var(--primary-color); font-size: 12px; font-weight: 600; }

        .buttons { padding: 0 16px 14px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
        #player-host {
          width: 100%; min-height: 240px; background: #000; display: flex; align-items: center; justify-content: center;
        }
        #player-host ha-hls-player { width: 100%; min-height: 240px; aspect-ratio: 16 / 9; background: #000; }

        .archive-export {
          padding: 12px 16px 14px;
          border-top: 1px solid var(--divider-color);
        }
        .archive-export-row {
          display: grid;
          grid-template-columns: minmax(140px, 200px) minmax(170px, max-content);
          gap: 8px;
          align-items: end;
        }
        .archive-download-ready {
          margin-top: 9px;
          padding: 9px 10px;
          border-radius: 9px;
          background: var(--secondary-background-color);
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }
        .archive-download-ready a {
          color: var(--primary-color);
          font-weight: 600;
          text-decoration: none;
        }
        .archive-download-meta {
          color: var(--secondary-text-color);
          font-size: 11px;
          flex: 1 1 150px;
        }
        .archive-library {
          padding: 0 16px 16px;
          border-top: 1px solid var(--divider-color);
        }
        .archive-library-head {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
          padding: 12px 0 8px;
        }
        .archive-library-head-title {
          font-size: 13px;
          font-weight: 600;
        }
        .archive-library-summary {
          color: var(--secondary-text-color);
          font-size: 11px;
          flex: 1 1 140px;
        }
        .archive-library-policy {
          color: var(--secondary-text-color);
          font-size: 11px;
          margin-bottom: 8px;
        }
        .archive-library-list {
          display: grid;
          gap: 6px;
        }
        .archive-library-empty {
          color: var(--secondary-text-color);
          font-size: 12px;
          padding: 8px 0;
        }
        .archive-library-row {
          display: flex;
          gap: 10px;
          align-items: center;
          padding: 9px 10px;
          border-radius: 9px;
          background: var(--secondary-background-color);
        }
        .archive-library-main {
          min-width: 0;
          flex: 1;
        }
        .archive-library-title {
          font-size: 13px;
          font-weight: 600;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .archive-library-meta {
          color: var(--secondary-text-color);
          font-size: 11px;
          margin-top: 2px;
        }
        .archive-library-actions {
          display: flex;
          gap: 5px;
          flex-wrap: wrap;
          justify-content: flex-end;
        }

        /* GUESTS */
        .guest-toolbar {
          padding: 14px 16px 10px;
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }
        .guest-toolbar .primary-action {
          color: var(--text-primary-color, #fff);
          background: var(--primary-color);
        }
        .guest-summary {
          flex: 1 1 220px;
          min-width: 0;
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        .diagnostics-toolbar {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
          padding: 12px 16px;
          border-bottom: 1px solid var(--divider-color);
        }
        .diagnostics-toolbar-title {
          font-size: 13px;
          font-weight: 600;
          flex: 1 1 160px;
        }
        .diagnostics-content {
          padding: 12px 16px 16px;
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 10px;
        }
        .diagnostics-section {
          border-radius: 10px;
          background: var(--secondary-background-color);
          padding: 10px 12px;
          min-width: 0;
        }
        .diagnostics-section-title {
          font-size: 12px;
          font-weight: 700;
          margin-bottom: 7px;
        }
        .diagnostics-row {
          display: grid;
          grid-template-columns: minmax(105px, 0.9fr) minmax(100px, 1.1fr);
          gap: 8px;
          padding: 3px 0;
          font-size: 11px;
          border-top: 1px solid color-mix(in srgb, var(--divider-color) 65%, transparent);
        }
        .diagnostics-row:first-of-type { border-top: 0; }
        .diagnostics-label { color: var(--secondary-text-color); }
        .diagnostics-value {
          text-align: right;
          overflow-wrap: anywhere;
          font-variant-numeric: tabular-nums;
        }
        .diagnostics-value[data-state="ok"] { color: var(--success-color, #43a047); }
        .diagnostics-value[data-state="warning"] { color: var(--warning-color, #f0a000); }
        .diagnostics-value[data-state="error"] { color: var(--error-color); }

        .guest-section { padding: 4px 16px 14px; }
        .temporary-create {
          display: grid;
          grid-template-columns: minmax(120px, 180px) minmax(170px, max-content);
          gap: 8px;
          align-items: end;
          margin: 0 0 8px;
        }
        .temporary-duration-label { margin: 0; }
        .guest-section-title {
          font-size: 13px;
          font-weight: 600;
          margin: 0 0 8px;
        }
        .guest-list { display: grid; gap: 6px; }
        .guest-empty {
          color: var(--secondary-text-color);
          font-size: 12px;
          padding: 8px 0;
        }
        .guest-row {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 9px 10px;
          border-radius: 9px;
          background: var(--secondary-background-color);
        }
        .guest-row-main { flex: 1; min-width: 0; }
        .guest-row-title {
          font-size: 13px;
          font-weight: 600;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .guest-row-meta {
          margin-top: 2px;
          color: var(--secondary-text-color);
          font-size: 11px;
          overflow-wrap: anywhere;
        }
        .guest-row-actions { display: flex; gap: 5px; flex-wrap: wrap; justify-content: flex-end; }
        .small-button {
          min-height: 32px;
          padding: 4px 9px;
          border-radius: 8px;
          font-size: 11px;
        }
        .danger-button {
          color: var(--error-color);
        }
        .guest-invite {
          margin: 4px 16px 14px;
          padding: 12px;
          border-radius: 10px;
          background: color-mix(in srgb, var(--primary-color) 8%, var(--card-background-color));
          border: 1px solid color-mix(in srgb, var(--primary-color) 28%, transparent);
        }
        .guest-invite-title { font-size: 13px; font-weight: 600; margin-bottom: 7px; }
        .guest-invite-warning { color: var(--secondary-text-color); font-size: 11px; margin-bottom: 8px; }
        .guest-invite-controls {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto auto;
          gap: 6px;
        }
        .guest-status {
          padding: 0 16px 14px;
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        #guest-status[data-type="error"] { color: var(--error-color); }
        #guest-status[data-type="warning"] { color: var(--warning-color, #f0a000); }
        #guest-status[data-type="ok"] { color: var(--success-color, #43a047); }

        .footer {
          padding: 10px 16px 14px; display: flex; gap: 8px; flex-wrap: wrap; justify-content: space-between;
          color: var(--secondary-text-color); font-size: 12px;
        }
        #status[data-type="error"] { color: var(--error-color); }
        #status[data-type="warning"] { color: var(--warning-color, #f0a000); }
        #status[data-type="ok"] { color: var(--success-color, #43a047); }
        #effective-duration { color: var(--warning-color, #f0a000); }

        @media (max-width: 700px) {
          .controls { grid-template-columns: 1fr 1fr; }
          .guest-invite-controls { grid-template-columns: 1fr 1fr; }
          .guest-invite-controls input { grid-column: 1 / -1; }
          .temporary-create { grid-template-columns: 1fr; }
          .archive-export-row { grid-template-columns: 1fr; }
          .live-main-actions { grid-template-columns: 1fr; }
          .archive-library-row { align-items: flex-start; flex-direction: column; }
          .archive-library-actions { width: 100%; justify-content: flex-start; }
        }
      </style>

      <ha-card>
        <div class="header">${this._config.title || "Домофон Ufanet"}</div>

        <div class="tabs" role="tablist" aria-label="Раздел домофона">
          <button id="tab-live" class="tab-button" type="button" role="tab">LIVE</button>
          <button id="tab-archive" class="tab-button" type="button" role="tab">АРХИВ</button>
          <button id="tab-guests" class="tab-button" type="button" role="tab">ГОСТИ</button>
          <button id="tab-diagnostics" class="tab-button" type="button" role="tab">ДИАГНОСТИКА</button>
        </div>

        <section id="panel-live" class="panel" role="tabpanel" hidden>
          <div id="live-host">
            <div class="panel-message">Загрузка live-камеры…</div>
          </div>

          <div class="live-controls">
            <div class="live-status-row">
              <span id="live-camera-state" class="live-status-pill">Камера…</span>
              <span id="live-door-state" class="live-status-pill">Домофон…</span>
            </div>

            <div class="live-main-actions">
              <button id="live-open-door" type="button" class="open-door-button">
                🚪 Открыть дверь
              </button>
              <button id="live-refresh" type="button">Обновить LIVE</button>
            </div>

            <div id="live-last-call" class="live-last-call" data-empty="true">
              <div class="live-last-call-title">Последний звонок</div>
              <div id="live-last-call-time" class="live-last-call-time">Загрузка…</div>
              <div id="live-last-call-address" class="live-last-call-address"></div>
              <div class="live-call-actions">
                <button id="live-open-call-archive" type="button" class="small-button">
                  Посмотреть запись
                </button>
                <button id="live-open-call-preview" type="button" class="small-button" hidden>
                  Preview-видео
                </button>
                <button id="live-open-call-image" type="button" class="small-button" hidden>
                  Снимок звонка
                </button>
              </div>
            </div>
          </div>

          <div class="live-footer">
            Live entity: <span id="live-entity-label">определяется…</span>
          </div>
        </section>

        <section id="panel-archive" class="panel" role="tabpanel" hidden>
          <div id="archive-window">Определение доступного диапазона…</div>

          <div class="controls">
            <label>Дата<input id="date" type="date"></label>
            <label>Время<input id="time" type="time" step="1"></label>
            <label>
              Длительность, с
              <input id="duration" type="number" min="30" max="3600" step="30" value="${Number(this._config.duration || 300)}">
            </label>
            <label>
              Шаг
              <select id="step">
                ${[10, 30, 60, 120, 300, 600, 1800, 3600]
                  .map((value) => `<option value="${value}" ${Number(this._config.step || 60) === value ? "selected" : ""}>${this._formatStep(value)}</option>`)
                  .join("")}
              </select>
            </label>
          </div>

          <div class="timeline-wrap">
            <div class="timeline-head">
              <span>Timeline архива <span id="timeline-event-summary" class="timeline-event-summary"></span></span>
              <div class="timeline-zoom" role="group" aria-label="Масштаб timeline">
                <button id="zoom-24" class="zoom-button" type="button" aria-pressed="true">24 ч</button>
                <button id="zoom-6" class="zoom-button" type="button" aria-pressed="false">6 ч</button>
                <button id="zoom-1" class="zoom-button" type="button" aria-pressed="false">1 ч</button>
              </div>
            </div>
            <div class="timeline-subhead">
              <span id="timeline-window-label">00:00–24:00</span>
              <span id="timeline-hint">Загрузка диапазонов…</span>
            </div>
            <div id="timeline-axis" aria-hidden="true">
              <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
            </div>
            <div id="timeline-track" role="group" aria-label="Архивная шкала времени">
              <div id="timeline-marker" hidden></div>
              <div id="timeline-marker-label" hidden></div>
            </div>
          </div>

          <div class="day-ranges">
            <div id="day-label">Доступные интервалы</div>
            <div id="day-intervals"></div>
          </div>

          <div class="calls">
            <div class="calls-head">
              <div id="calls-label">Звонки: загрузка…</div>
              <button id="refresh-calls" type="button">Обновить события</button>
            </div>
            <div id="call-events"></div>
          </div>

          <div class="buttons">
            <button id="previous">⏪ Назад</button>
            <button id="latest">Последнее</button>
            <button id="next">Вперёд ⏩</button>
          </div>

          <div id="player-host"><span style="color:#aaa">Загрузка архива…</span></div>

          <div class="archive-export">
            <div class="archive-export-row">
              <label>
                Сохранить от текущей отметки
                <select id="archive-export-duration">
                  <option value="30">30 секунд</option>
                  <option value="60">1 минута</option>
                  <option value="120">2 минуты</option>
                  <option value="300" selected>5 минут</option>
                  <option value="600">10 минут</option>
                  <option value="1800">30 минут</option>
                </select>
              </label>
              <button id="prepare-archive-download" type="button">
                Подготовить MP4
              </button>
            </div>

            <div id="archive-download-ready" class="archive-download-ready" hidden>
              <a id="archive-download-link" target="_blank" rel="noopener noreferrer">
                Скачать / открыть MP4
              </a>
              <span id="archive-download-meta" class="archive-download-meta"></span>
              <button id="archive-download-copy" type="button" class="small-button">
                Копировать URL
              </button>
            </div>
          </div>

          <div class="archive-library">
            <div class="archive-library-head">
              <span class="archive-library-head-title">Сохранённые видео</span>
              <span id="archive-library-summary" class="archive-library-summary">Загрузка…</span>
              <button id="archive-library-refresh" type="button" class="small-button">Обновить</button>
              <button id="archive-library-cleanup" type="button" class="small-button">Очистить по правилам</button>
            </div>
            <div id="archive-library-policy" class="archive-library-policy"></div>
            <div id="archive-library-list" class="archive-library-list">
              <div class="archive-library-empty">Загрузка медиатеки…</div>
            </div>
          </div>
        </section>

        <section id="panel-guests" class="panel" role="tabpanel" hidden>
          <div class="guest-toolbar">
            <div id="guest-counts" class="guest-summary">Гостевые доступы ещё не загружены</div>
            <button id="refresh-guests" type="button" class="small-button">Обновить</button>
            <button id="create-guest-invite" type="button" class="primary-action">Создать приглашение</button>
          </div>

          <div id="guest-invite-box" class="guest-invite" hidden>
            <div class="guest-invite-title">Новое приглашение</div>
            <div class="guest-invite-warning">
              Ссылка является ключом доступа. Передавайте её только нужному получателю.
              Пользователь появится в Shared access после принятия приглашения.
            </div>
            <div class="guest-invite-controls">
              <input id="guest-invite-url" type="text" readonly aria-label="Ссылка приглашения">
              <button id="copy-guest-invite" type="button" class="small-button">Копировать</button>
              <button id="open-guest-invite" type="button" class="small-button">Открыть</button>
            </div>
          </div>

          <div class="guest-section">
            <div class="guest-section-title">Созданные приглашения</div>
            <div class="guest-row-meta" style="margin-bottom:8px">
              Ufanet не предоставляет API списка непринятых create_token-ссылок,
              поэтому новые приглашения сохраняются локально в Home Assistant.
            </div>
            <div id="guest-generated-list" class="guest-list">
              <div class="guest-empty">Нажмите «Обновить» для загрузки.</div>
            </div>
          </div>

          <div class="guest-section">
            <div class="guest-section-title">Временные ключи</div>
            <div class="temporary-create">
              <label class="temporary-duration-label">
                Срок
                <select id="temporary-duration">
                  <option value="60">1 час</option>
                  <option value="180">3 часа</option>
                  <option value="360">6 часов</option>
                  <option value="720">12 часов</option>
                  <option value="1440">24 часа</option>
                </select>
              </label>
              <button id="create-temporary-guest" type="button" class="primary-action">
                Создать временный ключ
              </button>
            </div>
            <div class="guest-row-meta" style="margin:0 0 8px">
              Эти ссылки хранятся на сервере Ufanet и автоматически исчезают после окончания срока.
            </div>
            <div id="guest-temporary-list" class="guest-list">
              <div class="guest-empty">Нажмите «Обновить» для загрузки.</div>
            </div>
          </div>

          <div class="guest-section">
            <div class="guest-section-title">Shared access</div>
            <div id="guest-shared-list" class="guest-list">
              <div class="guest-empty">Нажмите «Обновить» для загрузки.</div>
            </div>
          </div>

          <div id="guest-status" class="guest-status">Готово</div>
        </section>

        <section id="panel-diagnostics" class="panel" role="tabpanel" hidden>
          <div class="diagnostics-toolbar">
            <span class="diagnostics-toolbar-title">Техническое состояние Ufanet Intercom</span>
            <button id="diagnostics-refresh" type="button" class="small-button">Обновить</button>
            <button id="diagnostics-copy" type="button" class="small-button">Копировать JSON</button>
          </div>
          <div id="diagnostics-content" class="diagnostics-content">
            <div class="panel-message">Нажмите «Обновить», чтобы получить диагностику.</div>
          </div>
        </section>

        <div class="footer">
          <span id="status">Инициализация…</span>
          <span>TZ: <span id="timezone">—</span> <span id="effective-duration"></span></span>
        </div>
      </ha-card>
    `;

    this._updateStepButtons();
    this._updateZoomButtons();

    this.shadowRoot.getElementById("tab-live")?.addEventListener("click", () => this._setActiveTab("live"));
    this.shadowRoot.getElementById("tab-archive")?.addEventListener("click", () => this._setActiveTab("archive"));
    this.shadowRoot.getElementById("tab-guests")?.addEventListener("click", () => this._setActiveTab("guests"));
    this.shadowRoot.getElementById("tab-diagnostics")?.addEventListener("click", () => this._setActiveTab("diagnostics"));

    this.shadowRoot.getElementById("live-open-door")?.addEventListener(
      "click",
      () => void this._openDoorFromLive()
    );
    this.shadowRoot.getElementById("live-refresh")?.addEventListener(
      "click",
      () => void this._refreshLivePanel()
    );
    this.shadowRoot.getElementById("live-open-call-archive")?.addEventListener(
      "click",
      () => void this._openLastCallArchive()
    );
    this.shadowRoot.getElementById("live-open-call-preview")?.addEventListener(
      "click",
      () => void this._openLastCallPreview()
    );
    this.shadowRoot.getElementById("live-open-call-image")?.addEventListener(
      "click",
      () => this._openLastCallImage()
    );

    const timelineTrack = this.shadowRoot.getElementById("timeline-track");
    timelineTrack?.addEventListener("click", (event) => void this._handleTimelineClick(event));
    timelineTrack?.addEventListener("wheel", (event) => this._handleTimelineWheel(event), { passive: false });
    timelineTrack?.addEventListener("pointerdown", (event) => this._handleTimelinePointerDown(event));
    timelineTrack?.addEventListener("pointermove", (event) => this._handleTimelinePointerMove(event));
    timelineTrack?.addEventListener("pointerup", (event) => this._finishTimelinePointerDrag(event));
    timelineTrack?.addEventListener("pointercancel", (event) => this._finishTimelinePointerDrag(event));

    this.shadowRoot.getElementById("zoom-24")?.addEventListener("click", () => this._setTimelineZoom(24, null, true));
    this.shadowRoot.getElementById("zoom-6")?.addEventListener("click", () => this._setTimelineZoom(6, null, true));
    this.shadowRoot.getElementById("zoom-1")?.addEventListener("click", () => this._setTimelineZoom(1, null, true));
    this.shadowRoot.getElementById("date")?.addEventListener("change", () => void this._handleDateChange());
    this.shadowRoot.getElementById("time")?.addEventListener("change", () => void this._loadFromInputs());
    this.shadowRoot.getElementById("duration")?.addEventListener("change", () => {
      if (this._currentEpoch != null) void this._loadEpoch(this._currentEpoch);
    });
    this.shadowRoot.getElementById("step")?.addEventListener("change", () => this._updateStepButtons());
    this.shadowRoot.getElementById("previous")?.addEventListener("click", () => void this._shift(-1));
    this.shadowRoot.getElementById("next")?.addEventListener("click", () => void this._shift(1));
    this.shadowRoot.getElementById("latest")?.addEventListener("click", () => void this._goLatest(true));
    this.shadowRoot.getElementById("refresh-calls")?.addEventListener("click", () => {
      const dateText = this.shadowRoot.getElementById("date")?.value;
      if (dateText) {
        void Promise.all([
          this._refreshCallEvents(dateText, true),
          this._refreshMotionEvents(dateText, true),
        ]);
      }
    });

    this.shadowRoot.getElementById("prepare-archive-download")?.addEventListener(
      "click",
      () => void this._prepareArchiveDownload()
    );
    this.shadowRoot.getElementById("archive-download-copy")?.addEventListener(
      "click",
      () => void this._copyArchiveDownloadUrl()
    );
    this.shadowRoot.getElementById("archive-library-refresh")?.addEventListener(
      "click",
      () => void this._refreshArchiveExports(true)
    );
    this.shadowRoot.getElementById("archive-library-cleanup")?.addEventListener(
      "click",
      () => void this._cleanupStoredArchiveExports()
    );
    this.shadowRoot.getElementById("diagnostics-refresh")?.addEventListener(
      "click",
      () => void this._refreshRuntimeStatus(true)
    );
    this.shadowRoot.getElementById("diagnostics-copy")?.addEventListener(
      "click",
      () => void this._copyRuntimeStatus()
    );

    this.shadowRoot.getElementById("refresh-guests")?.addEventListener("click", () => void this._refreshGuestAccess(true));
    this.shadowRoot.getElementById("create-guest-invite")?.addEventListener("click", () => void this._createGuestInvite());
    this.shadowRoot.getElementById("create-temporary-guest")?.addEventListener("click", () => void this._createTemporaryGuestLink());
    this.shadowRoot.getElementById("copy-guest-invite")?.addEventListener("click", () => {
      if (this._guestInviteUrl) void this._copyText(this._guestInviteUrl);
    });
    this.shadowRoot.getElementById("open-guest-invite")?.addEventListener("click", () => {
      if (this._guestInviteUrl) window.open(this._guestInviteUrl, "_blank", "noopener,noreferrer");
    });

    this._setActiveTab(this._activeTab, false);
    this._renderLiveMeta();
    this._renderArchiveDownloadReady();
    this._renderArchiveExports();
    this._renderRuntimeStatus();
  }

}

if (!customElements.get("ufanet-archive-card")) {
  customElements.define("ufanet-archive-card", UfanetArchiveCard);
}

if (!customElements.get("ufanet-intercom-card")) {
  class UfanetIntercomCard extends UfanetArchiveCard {}
  customElements.define("ufanet-intercom-card", UfanetIntercomCard);
}

window.customCards = window.customCards || [];

if (!window.customCards.some((card) => card.type === "ufanet-intercom-card")) {
  window.customCards.push({
    type: "ufanet-intercom-card",
    name: "Ufanet Intercom",
    description: "LIVE, архив, звонки и гостевые доступы Ufanet",
    preview: false,
  });
}

if (!window.customCards.some((card) => card.type === "ufanet-archive-card")) {
  window.customCards.push({
    type: "ufanet-archive-card",
    name: "Ufanet Intercom (legacy card type)",
    description: "Совместимый алиас единой карточки Ufanet",
    preview: false,
  });
}

console.info(
  `%c Ufanet Archive Card %c v${CARD_VERSION} `,
  "background:#0CBA9B;color:white;padding:2px 4px;border-radius:3px 0 0 3px",
  "background:#444;color:white;padding:2px 4px;border-radius:0 3px 3px 0"
);