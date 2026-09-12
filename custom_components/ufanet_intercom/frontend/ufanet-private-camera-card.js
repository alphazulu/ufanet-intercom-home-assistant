(() => {
  "use strict";

  const CARD_TAG = "ufanet-intercom-card";
  const EXTENSION_MARK = Symbol.for("ufanet_intercom.private_camera_card");
  const INTERCOM_ONLY_TABS = new Set([
    "guests",
    "sessions",
    "diagnostics",
    "keys",
  ]);
  const SERVICE_MAP = Object.freeze({
    get_settings: "get_private_camera_settings",
    get_archive_ranges: "get_private_archive_ranges",
    get_archive_url: "get_private_archive_url",
    get_archive_download_url: "get_private_archive_download_url",
    list_archive_exports: "list_private_archive_exports",
    delete_archive_export: "delete_private_archive_export",
    cleanup_archive_exports: "cleanup_private_archive_exports",
    get_motion_events: "get_private_motion_events",
    get_call_events: "get_private_call_events",
  });

  function isStandaloneUniqueId(value) {
    const uniqueId = String(value || "");
    return (
      uniqueId.startsWith("ucams_private_camera_") ||
      uniqueId.startsWith("ucams_private_archive_camera_") ||
      uniqueId.startsWith("ucams_camera_")
    );
  }

  function installPrivateCameraExtension(CardClass) {
    if (!CardClass?.prototype || CardClass.prototype[EXTENSION_MARK]) return;

    const proto = CardClass.prototype;
    Object.defineProperty(proto, EXTENSION_MARK, {
      configurable: false,
      enumerable: false,
      value: true,
      writable: false,
    });

    const originalRenderSkeleton = proto._renderSkeleton;
    const originalLoadIntegrationSettings = proto._loadIntegrationSettings;
    const originalResolveLiveEntity = proto._resolveLiveEntity;
    const originalSetActiveTab = proto._setActiveTab;
    const originalCallResponseService = proto._callResponseService;
    const originalSetConfig = proto.setConfig;

    proto._standaloneCamera = null;

    proto._detectStandaloneCamera = async function () {
      if (this._standaloneCamera === true) return true;
      if (!this._hass) return false;

      try {
        if (this._config?.entity) {
          const configured = await this._hass.callWS({
            type: "config/entity_registry/get",
            entity_id: this._config.entity,
          });
          if (isStandaloneUniqueId(configured?.unique_id)) {
            this._standaloneCamera = true;
            this._applyStandaloneCameraUi();
            return true;
          }
        }

        if (!this._deviceId) return false;
        const entities =
          this._deviceRegistryEntities ||
          (await this._hass.callWS({ type: "config/entity_registry/list" }));
        this._deviceRegistryEntities = entities;
        const standalone = Array.isArray(entities) && entities.some(
          (item) =>
            item?.device_id === this._deviceId &&
            isStandaloneUniqueId(item?.unique_id)
        );
        this._standaloneCamera = standalone;
        if (standalone) this._applyStandaloneCameraUi();
        return standalone;
      } catch (_err) {
        return this._standaloneCamera === true;
      }
    };

    proto._applyStandaloneCameraUi = function () {
      if (!this.shadowRoot || this._standaloneCamera !== true) return;

      this._openDoorEntityId = null;
      this._lastCallEntityId = null;
      this._lastCallImageEntityId = null;
      this._lastCallStateSeen = null;
      this._callEvents = [];
      this._callEventsDate = null;
      this._callEventsCache?.clear?.();

      for (const tab of INTERCOM_ONLY_TABS) {
        const button = this.shadowRoot.getElementById(`tab-${tab}`);
        const panel = this.shadowRoot.getElementById(`panel-${tab}`);
        if (button) button.hidden = true;
        if (panel) panel.hidden = true;
      }

      const calls = this.shadowRoot.querySelector(".calls");
      if (calls) calls.hidden = true;

      for (const id of [
        "live-door-state",
        "live-open-door",
        "live-last-call",
        "live-open-call-archive",
        "live-open-call-preview",
      ]) {
        const element = this.shadowRoot.getElementById(id);
        if (element) element.hidden = true;
      }

      const header = this.shadowRoot.querySelector(".header");
      if (
        header &&
        !Object.prototype.hasOwnProperty.call(this._userConfig || {}, "title")
      ) {
        header.textContent = "Камера Ufanet";
      }

      const tabs = this.shadowRoot.querySelector(".tabs");
      if (tabs) tabs.setAttribute("aria-label", "Раздел камеры Ufanet");

      if (INTERCOM_ONLY_TABS.has(this._activeTab)) {
        this._activeTab = "archive";
      }
    };

    proto._callResponseService = async function (service, serviceData) {
      if (this._standaloneCamera === true && SERVICE_MAP[service]) {
        return originalCallResponseService.call(
          this,
          SERVICE_MAP[service],
          serviceData
        );
      }
      return originalCallResponseService.call(this, service, serviceData);
    };

    proto._loadIntegrationSettings = async function (...args) {
      await this._detectStandaloneCamera();
      const result = await originalLoadIntegrationSettings.apply(this, args);
      this._applyStandaloneCameraUi();
      return result;
    };

    proto._resolveLiveEntity = async function (...args) {
      const result = await originalResolveLiveEntity.apply(this, args);
      await this._detectStandaloneCamera();
      this._applyStandaloneCameraUi();
      return result;
    };

    proto._renderSkeleton = function (...args) {
      const result = originalRenderSkeleton.apply(this, args);
      this._applyStandaloneCameraUi();
      return result;
    };

    proto._setActiveTab = function (tab, updateStatus = true) {
      if (this._standaloneCamera === true && INTERCOM_ONLY_TABS.has(tab)) {
        tab = "archive";
      }
      const result = originalSetActiveTab.call(this, tab, updateStatus);
      this._applyStandaloneCameraUi();
      return result;
    };

    proto.setConfig = function (config) {
      this._standaloneCamera = null;
      const result = originalSetConfig.call(this, config);
      return result;
    };

    function installOnExistingCards(root) {
      if (!root?.querySelectorAll) return;
      for (const element of root.querySelectorAll("*")) {
        if (element.localName === CARD_TAG) {
          void element._detectStandaloneCamera?.().then(() => {
            element._applyStandaloneCameraUi?.();
          });
        }
        if (element.shadowRoot) installOnExistingCards(element.shadowRoot);
      }
    }

    queueMicrotask(() => installOnExistingCards(document));
  }

  async function boot() {
    try {
      await customElements.whenDefined(CARD_TAG);
      const CardClass = customElements.get(CARD_TAG);
      installPrivateCameraExtension(CardClass);
    } catch (err) {
      console.error("Ufanet standalone-camera card extension failed to initialize", err);
    }
  }

  void boot();
})();
