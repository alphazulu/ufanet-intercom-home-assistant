(() => {
  "use strict";

  const CARD_TAG = "ufanet-intercom-card";
  const EXTENSION_MARK = Symbol.for("ufanet_intercom.physical_keys_card");
  const ORIGINAL_TABS = ["live", "archive", "guests", "sessions", "diagnostics"];
  const KEY_TAB = "keys";
  const ENROLLMENT_SECONDS = 60;

  function formatCreatedAt(value) {
    const timestamp = Date.parse(String(value || ""));
    if (!Number.isFinite(timestamp)) return String(value || "дата неизвестна");
    try {
      return new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(timestamp));
    } catch (_err) {
      return String(value || "дата неизвестна");
    }
  }

  function installPhysicalKeyExtension(CardClass) {
    if (!CardClass?.prototype || CardClass.prototype[EXTENSION_MARK]) return;

    const proto = CardClass.prototype;
    Object.defineProperty(proto, EXTENSION_MARK, {
      configurable: false,
      enumerable: false,
      value: true,
      writable: false,
    });

    const originalRenderSkeleton = proto._renderSkeleton;
    const originalSetActiveTab = proto._setActiveTab;
    const originalSetConfig = proto.setConfig;
    const originalDisconnectedCallback = proto.disconnectedCallback;
    const originalGetConfigForm = CardClass.getConfigForm?.bind(CardClass);

    proto._physicalKeysSnapshot = null;
    proto._physicalKeysLoading = false;
    proto._physicalKeyEnrollmentEntityId = null;
    proto._physicalKeyEnrollmentTimer = null;
    proto._physicalKeyEnrollmentDeadline = null;

    proto._setPhysicalKeyStatus = function (message, type = "info") {
      const status = this.shadowRoot?.getElementById("physical-key-status");
      if (!status) return;
      status.textContent = message || "";
      status.dataset.type = type;
    };

    proto._setPhysicalKeyButtonsDisabled = function (disabled) {
      const refresh = this.shadowRoot?.getElementById("refresh-physical-keys");
      const add = this.shadowRoot?.getElementById("add-physical-key");
      if (refresh) refresh.disabled = disabled;
      if (add) {
        const available =
          this._physicalKeyEnrollmentEntityId &&
          typeof this._entityAvailable === "function" &&
          this._entityAvailable(this._physicalKeyEnrollmentEntityId);
        add.disabled = disabled || !available;
      }
      for (const button of this.shadowRoot?.querySelectorAll(
        ".physical-key-rename"
      ) || []) {
        button.disabled = disabled;
      }
    };

    proto._resolvePhysicalKeyEnrollmentEntity = async function () {
      if (!this._deviceId || !this._hass) return null;

      try {
        const entities =
          this._deviceRegistryEntities ||
          (await this._hass.callWS({ type: "config/entity_registry/list" }));
        this._deviceRegistryEntities = entities;

        const sameDevice = Array.isArray(entities)
          ? entities.filter((item) => item?.device_id === this._deviceId)
          : [];
        const enrollment = sameDevice.find(
          (item) =>
            String(item?.entity_id || "").startsWith("button.") &&
            String(item?.unique_id || "").endsWith("_add_physical_key")
        );
        this._physicalKeyEnrollmentEntityId = enrollment?.entity_id || null;
      } catch (_err) {
        this._physicalKeyEnrollmentEntityId = null;
      }

      this._setPhysicalKeyButtonsDisabled(this._physicalKeysLoading);
      return this._physicalKeyEnrollmentEntityId;
    };

    proto._renderPhysicalKeys = function () {
      const host = this.shadowRoot?.getElementById("physical-key-list");
      const summary = this.shadowRoot?.getElementById("physical-key-summary");
      if (!host) return;

      host.textContent = "";
      const snapshot = this._physicalKeysSnapshot;
      const keys = Array.isArray(snapshot?.keys) ? snapshot.keys : [];

      if (summary) {
        summary.textContent = snapshot
          ? `Зарегистрировано: ${Number(snapshot.count ?? keys.length)}`
          : "Список ещё не загружен";
      }

      if (!snapshot) {
        const empty = document.createElement("div");
        empty.className = "physical-key-empty";
        empty.textContent = "Нажмите «Обновить», чтобы получить список физических ключей.";
        host.appendChild(empty);
        this._setPhysicalKeyButtonsDisabled(this._physicalKeysLoading);
        return;
      }

      if (!keys.length) {
        const empty = document.createElement("div");
        empty.className = "physical-key-empty";
        empty.textContent = "Зарегистрированных физических ключей нет.";
        host.appendChild(empty);
        this._setPhysicalKeyButtonsDisabled(this._physicalKeysLoading);
        return;
      }

      for (const item of keys) {
        if (!item || typeof item.key_ref !== "string") continue;

        const row = document.createElement("div");
        row.className = "physical-key-row";

        const icon = document.createElement("ha-icon");
        icon.className = "physical-key-icon";
        icon.setAttribute("icon", "mdi:key-variant");

        const main = document.createElement("div");
        main.className = "physical-key-main";

        const name = document.createElement("div");
        name.className = "physical-key-name";
        name.textContent = String(item.name || "Физический ключ");

        const meta = document.createElement("div");
        meta.className = "physical-key-meta";
        meta.textContent = `Добавлен: ${formatCreatedAt(item.created_at)}`;
        if (item.created_at) meta.title = String(item.created_at);

        main.append(name, meta);

        const actions = document.createElement("div");
        actions.className = "physical-key-actions";

        const rename = document.createElement("button");
        rename.type = "button";
        rename.className = "small-button physical-key-rename";
        rename.textContent = "Переименовать";
        rename.title = "Изменить пользовательское имя физического ключа";
        rename.addEventListener("click", () => void this._renamePhysicalKey(item));
        actions.appendChild(rename);

        row.append(icon, main, actions);
        host.appendChild(row);
      }

      this._setPhysicalKeyButtonsDisabled(this._physicalKeysLoading);
    };

    proto._refreshPhysicalKeys = async function (force = false) {
      if (!this._deviceId || !this._hass || this._physicalKeysLoading) return;
      if (this._physicalKeysSnapshot && !force) {
        this._renderPhysicalKeys();
        await this._resolvePhysicalKeyEnrollmentEntity();
        return;
      }

      this._physicalKeysLoading = true;
      this._setPhysicalKeyButtonsDisabled(true);
      this._setPhysicalKeyStatus("Загрузка физических ключей…", "info");

      try {
        const response = await this._callResponseService("list_physical_keys", {
          device_id: this._deviceId,
        });
        if (!response || !Array.isArray(response.keys)) {
          throw new Error("Сервис не вернул список физических ключей");
        }

        const keys = response.keys.filter(
          (item) =>
            item &&
            typeof item.key_ref === "string" &&
            typeof item.name === "string" &&
            typeof item.created_at === "string"
        );
        if (keys.length !== response.keys.length) {
          throw new Error("Сервис вернул некорректную запись физического ключа");
        }

        this._physicalKeysSnapshot = {
          count: Number(response.count ?? keys.length),
          keys,
        };
        this._renderPhysicalKeys();
        this._setPhysicalKeyStatus("Список физических ключей обновлён", "ok");
      } catch (err) {
        this._setPhysicalKeyStatus(this._errorText(err), "error");
      } finally {
        this._physicalKeysLoading = false;
        await this._resolvePhysicalKeyEnrollmentEntity();
        this._setPhysicalKeyButtonsDisabled(false);
      }
    };

    proto._renamePhysicalKey = async function (item) {
      if (
        !item?.key_ref ||
        !this._deviceId ||
        !this._hass ||
        this._physicalKeysLoading
      ) {
        return;
      }

      const currentName = String(item.name || "");
      const requested = window.prompt(
        "Новое имя физического ключа:",
        currentName
      );
      if (requested === null) return;

      const newName = requested.trim();
      if (!newName) {
        this._setPhysicalKeyStatus("Имя ключа не может быть пустым", "error");
        return;
      }
      if (newName === currentName) {
        this._setPhysicalKeyStatus("Имя ключа не изменилось", "info");
        return;
      }

      const confirmed = window.confirm(
        `Переименовать физический ключ «${currentName || "без имени"}» в «${newName}»?`
      );
      if (!confirmed) return;

      this._physicalKeysLoading = true;
      this._setPhysicalKeyButtonsDisabled(true);
      this._setPhysicalKeyStatus(`Переименовываю ключ в «${newName}»…`, "info");

      try {
        const response = await this._callResponseService("rename_physical_key", {
          device_id: this._deviceId,
          key_ref: item.key_ref,
          new_name: newName,
        });
        if (response?.verified !== true || response?.name !== newName) {
          throw new Error("Home Assistant не подтвердил новое имя ключа");
        }

        this._physicalKeysSnapshot = null;
        this._setPhysicalKeyStatus(
          response.renamed === false
            ? "Имя ключа уже совпадало с выбранным"
            : `Ключ переименован в «${newName}». Обновляю список…`,
          "ok"
        );
      } catch (err) {
        this._setPhysicalKeyStatus(this._errorText(err), "error");
        this._physicalKeysLoading = false;
        this._setPhysicalKeyButtonsDisabled(false);
        return;
      }

      this._physicalKeysLoading = false;
      this._setPhysicalKeyButtonsDisabled(false);
      await this._refreshPhysicalKeys(true);
    };

    proto._updatePhysicalKeyEnrollmentCountdown = function () {
      const status = this.shadowRoot?.getElementById("physical-key-enrollment-status");
      if (!status || !this._physicalKeyEnrollmentDeadline) return;

      const remaining = Math.max(
        0,
        Math.ceil((this._physicalKeyEnrollmentDeadline - Date.now()) / 1000)
      );
      if (remaining > 0) {
        status.hidden = false;
        status.textContent =
          `Режим регистрации активен: ${remaining} с. Приложите новый ключ к считывателю.`;
        status.dataset.type = "warning";
        return;
      }

      status.hidden = false;
      status.textContent = "Окно регистрации завершилось. Проверяю список ключей…";
      status.dataset.type = "info";
      this._physicalKeyEnrollmentDeadline = null;
      if (this._physicalKeyEnrollmentTimer) {
        clearInterval(this._physicalKeyEnrollmentTimer);
        this._physicalKeyEnrollmentTimer = null;
      }
      void this._refreshPhysicalKeys(true);
    };

    proto._startPhysicalKeyEnrollment = async function () {
      if (!this._deviceId || !this._hass || this._physicalKeysLoading) return;

      await this._resolvePhysicalKeyEnrollmentEntity();
      if (
        !this._physicalKeyEnrollmentEntityId ||
        !this._entityAvailable(this._physicalKeyEnrollmentEntityId)
      ) {
        this._setPhysicalKeyStatus(
          "Кнопка регистрации физического ключа недоступна для этого домофона",
          "error"
        );
        return;
      }

      const confirmed = window.confirm(
        "Включить режим регистрации нового физического ключа на 60 секунд?\n\n" +
          "После подтверждения приложите НОВЫЙ незарегистрированный ключ к считывателю домофона."
      );
      if (!confirmed) return;

      const add = this.shadowRoot?.getElementById("add-physical-key");
      if (add) add.disabled = true;
      this._setPhysicalKeyStatus("Включаю режим регистрации ключа…", "info");

      try {
        await this._hass.callWS({
          type: "call_service",
          domain: "button",
          service: "press",
          service_data: { entity_id: this._physicalKeyEnrollmentEntityId },
        });
      } catch (err) {
        this._setPhysicalKeyStatus(this._errorText(err), "error");
        this._setPhysicalKeyButtonsDisabled(false);
        return;
      }

      this._physicalKeyEnrollmentDeadline = Date.now() + ENROLLMENT_SECONDS * 1000;
      if (this._physicalKeyEnrollmentTimer) {
        clearInterval(this._physicalKeyEnrollmentTimer);
      }
      this._physicalKeyEnrollmentTimer = setInterval(
        () => this._updatePhysicalKeyEnrollmentCountdown(),
        1000
      );
      this._updatePhysicalKeyEnrollmentCountdown();
      this._setPhysicalKeyStatus(
        "Ufanet принял команду запуска регистрации. Это ещё не подтверждает, что новый ключ сохранён.",
        "ok"
      );
      this._setPhysicalKeyButtonsDisabled(false);
    };

    proto._installPhysicalKeyPanel = function () {
      if (!this.shadowRoot || !this._config) return;

      const tabs = this.shadowRoot.querySelector(".tabs");
      if (tabs && !this.shadowRoot.getElementById("tab-keys")) {
        const tab = document.createElement("button");
        tab.id = "tab-keys";
        tab.className = "tab-button";
        tab.type = "button";
        tab.setAttribute("role", "tab");
        tab.textContent = "КЛЮЧИ";
        const diagnostics = this.shadowRoot.getElementById("tab-diagnostics");
        tabs.insertBefore(tab, diagnostics || null);
        tab.addEventListener("click", () => this._setActiveTab(KEY_TAB));
      }

      if (!this.shadowRoot.getElementById("panel-keys")) {
        const panel = document.createElement("section");
        panel.id = "panel-keys";
        panel.className = "panel";
        panel.setAttribute("role", "tabpanel");
        panel.hidden = true;
        panel.innerHTML = `
          <div class="physical-key-toolbar">
            <div class="physical-key-toolbar-main">
              <div class="physical-key-toolbar-title">Физические ключи</div>
              <div id="physical-key-summary" class="physical-key-summary">Список ещё не загружен</div>
            </div>
            <div class="physical-key-toolbar-actions">
              <button id="refresh-physical-keys" class="small-button" type="button">Обновить</button>
              <button id="add-physical-key" class="small-button primary-button" type="button" disabled>Добавить ключ</button>
            </div>
          </div>
          <div class="physical-key-note">
            В список не выводятся provider key ID и external ID. Переименование использует только непрозрачный key_ref.
          </div>
          <div id="physical-key-enrollment-status" class="physical-key-enrollment-status" hidden></div>
          <div id="physical-key-list" class="physical-key-list"></div>
          <div id="physical-key-status" class="physical-key-status">Готово</div>
        `;
        const diagnosticsPanel = this.shadowRoot.getElementById("panel-diagnostics");
        diagnosticsPanel?.parentNode?.insertBefore(panel, diagnosticsPanel);
        if (!panel.parentNode) this.shadowRoot.appendChild(panel);

        panel
          .querySelector("#refresh-physical-keys")
          ?.addEventListener("click", () => void this._refreshPhysicalKeys(true));
        panel
          .querySelector("#add-physical-key")
          ?.addEventListener("click", () => void this._startPhysicalKeyEnrollment());
      }

      if (!this.shadowRoot.getElementById("physical-key-extension-style")) {
        const style = document.createElement("style");
        style.id = "physical-key-extension-style";
        style.textContent = `
          .physical-key-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 12px;
          }
          .physical-key-toolbar-main { min-width: 0; }
          .physical-key-toolbar-title {
            font-size: 16px;
            font-weight: 600;
          }
          .physical-key-summary,
          .physical-key-meta,
          .physical-key-note {
            color: var(--secondary-text-color);
            font-size: 12px;
          }
          .physical-key-toolbar-actions,
          .physical-key-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
          }
          .physical-key-note {
            margin: 0 0 12px;
            line-height: 1.45;
          }
          .physical-key-list {
            display: grid;
            gap: 8px;
          }
          .physical-key-row {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto;
            align-items: center;
            gap: 12px;
            padding: 12px;
            border: 1px solid var(--divider-color);
            border-radius: 10px;
            background: var(--card-background-color);
          }
          .physical-key-icon {
            color: var(--primary-color);
          }
          .physical-key-main { min-width: 0; }
          .physical-key-name {
            font-weight: 600;
            overflow-wrap: anywhere;
          }
          .physical-key-meta { margin-top: 3px; }
          .physical-key-empty {
            padding: 18px 12px;
            text-align: center;
            color: var(--secondary-text-color);
            border: 1px dashed var(--divider-color);
            border-radius: 10px;
          }
          .physical-key-status,
          .physical-key-enrollment-status {
            margin-top: 12px;
            padding: 9px 11px;
            border-radius: 8px;
            font-size: 12px;
          }
          .physical-key-status[data-type="ok"],
          .physical-key-enrollment-status[data-type="ok"] {
            background: color-mix(in srgb, var(--success-color, #43a047) 12%, transparent);
          }
          .physical-key-status[data-type="error"] {
            background: color-mix(in srgb, var(--error-color) 12%, transparent);
          }
          .physical-key-status[data-type="warning"],
          .physical-key-enrollment-status[data-type="warning"] {
            background: color-mix(in srgb, var(--warning-color, #ffa000) 15%, transparent);
          }
          .physical-key-status[data-type="info"],
          .physical-key-enrollment-status[data-type="info"] {
            background: color-mix(in srgb, var(--primary-color) 10%, transparent);
          }
          @media (max-width: 600px) {
            .physical-key-row {
              grid-template-columns: auto minmax(0, 1fr);
            }
            .physical-key-actions {
              grid-column: 1 / -1;
              justify-content: flex-end;
            }
          }
        `;
        this.shadowRoot.appendChild(style);
      }

      this._renderPhysicalKeys();
      void this._resolvePhysicalKeyEnrollmentEntity();
    };

    proto._renderSkeleton = function (...args) {
      const result = originalRenderSkeleton.apply(this, args);
      this._installPhysicalKeyPanel();
      return result;
    };

    proto._setActiveTab = function (tab, updateStatus = true) {
      if (tab !== KEY_TAB) {
        const result = originalSetActiveTab.call(this, tab, updateStatus);
        const panel = this.shadowRoot?.getElementById("panel-keys");
        const button = this.shadowRoot?.getElementById("tab-keys");
        if (panel) panel.hidden = true;
        if (button) {
          button.classList.remove("active");
          button.setAttribute("aria-selected", "false");
        }
        return result;
      }

      this._activeTab = KEY_TAB;
      for (const name of ORIGINAL_TABS) {
        const panel = this.shadowRoot?.getElementById(`panel-${name}`);
        const button = this.shadowRoot?.getElementById(`tab-${name}`);
        if (panel) panel.hidden = true;
        if (button) {
          button.classList.remove("active");
          button.setAttribute("aria-selected", "false");
        }
      }

      const panel = this.shadowRoot?.getElementById("panel-keys");
      const button = this.shadowRoot?.getElementById("tab-keys");
      if (panel) panel.hidden = false;
      if (button) {
        button.classList.add("active");
        button.setAttribute("aria-selected", "true");
      }
      void this._refreshPhysicalKeys(false);
      if (updateStatus) this._setStatus("Раздел: Ключи", "info");
    };

    proto.setConfig = function (config) {
      const result = originalSetConfig.call(this, config);
      if (config?.default_tab === KEY_TAB) {
        this._activeTab = KEY_TAB;
      }
      return result;
    };

    proto.disconnectedCallback = function (...args) {
      if (this._physicalKeyEnrollmentTimer) {
        clearInterval(this._physicalKeyEnrollmentTimer);
        this._physicalKeyEnrollmentTimer = null;
      }
      this._physicalKeyEnrollmentDeadline = null;
      return originalDisconnectedCallback?.apply(this, args);
    };

    if (originalGetConfigForm) {
      CardClass.getConfigForm = function () {
        const form = originalGetConfigForm();
        const schema = Array.isArray(form?.schema) ? form.schema : [];
        const defaultTab = schema.find((item) => item?.name === "default_tab");
        const options = defaultTab?.selector?.select?.options;
        if (
          Array.isArray(options) &&
          !options.some((item) => item?.value === KEY_TAB)
        ) {
          const diagnosticsIndex = options.findIndex(
            (item) => item?.value === "diagnostics"
          );
          const keyOption = { value: KEY_TAB, label: "Ключи" };
          if (diagnosticsIndex >= 0) options.splice(diagnosticsIndex, 0, keyOption);
          else options.push(keyOption);
        }
        return form;
      };
    }

    function installOnExistingCards(root) {
      if (!root?.querySelectorAll) return;
      for (const element of root.querySelectorAll("*")) {
        if (element.localName === CARD_TAG) {
          element._installPhysicalKeyPanel?.();
          if (element._activeTab === KEY_TAB) {
            element._setActiveTab(KEY_TAB, false);
          }
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
      installPhysicalKeyExtension(CardClass);
    } catch (err) {
      console.error("Ufanet physical-key card extension failed to initialize", err);
    }
  }

  void boot();
})();
