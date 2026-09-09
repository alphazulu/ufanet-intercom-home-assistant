(() => {
  "use strict";

  const CARD_TAG = "ufanet-intercom-card";
  const EXTENSION_MARK = Symbol.for("ufanet_intercom.physical_key_history_card");
  const HISTORY_PAGE_SIZE = 25;

  function formatPassageAt(value) {
    const timestamp = Date.parse(String(value || ""));
    if (!Number.isFinite(timestamp)) return String(value || "время неизвестно");
    try {
      return new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "medium",
      }).format(new Date(timestamp));
    } catch (_err) {
      return String(value || "время неизвестно");
    }
  }

  function installHistoryExtension(CardClass) {
    if (!CardClass?.prototype || CardClass.prototype[EXTENSION_MARK]) return false;

    const proto = CardClass.prototype;
    if (
      typeof proto._renderPhysicalKeys !== "function" ||
      typeof proto._installPhysicalKeyPanel !== "function"
    ) {
      return false;
    }

    Object.defineProperty(proto, EXTENSION_MARK, {
      configurable: false,
      enumerable: false,
      value: true,
      writable: false,
    });

    const originalRenderPhysicalKeys = proto._renderPhysicalKeys;
    const originalInstallPhysicalKeyPanel = proto._installPhysicalKeyPanel;
    const originalDisconnectedCallback = proto.disconnectedCallback;

    proto._physicalKeyHistorySelection = null;
    proto._physicalKeyHistoryRows = [];
    proto._physicalKeyHistoryPage = 0;
    proto._physicalKeyHistoryHasMore = false;
    proto._physicalKeyHistoryLoading = false;

    proto._setPhysicalKeyHistoryStatus = function (message, type = "info") {
      const status = this.shadowRoot?.getElementById("physical-key-history-status");
      if (!status) return;
      status.textContent = message || "";
      status.dataset.type = type;
    };

    proto._setPhysicalKeyHistoryButtons = function () {
      const refresh = this.shadowRoot?.getElementById("refresh-physical-key-history");
      const more = this.shadowRoot?.getElementById("more-physical-key-history");
      if (refresh) {
        refresh.disabled =
          this._physicalKeyHistoryLoading || !this._physicalKeyHistorySelection;
      }
      if (more) {
        more.disabled =
          this._physicalKeyHistoryLoading ||
          !this._physicalKeyHistorySelection ||
          !this._physicalKeyHistoryHasMore;
        more.hidden = !this._physicalKeyHistoryHasMore;
      }
    };

    proto._clearPhysicalKeyHistory = function (hide = true) {
      this._physicalKeyHistorySelection = null;
      this._physicalKeyHistoryRows = [];
      this._physicalKeyHistoryPage = 0;
      this._physicalKeyHistoryHasMore = false;
      this._physicalKeyHistoryLoading = false;

      const section = this.shadowRoot?.getElementById("physical-key-history-section");
      const list = this.shadowRoot?.getElementById("physical-key-history-list");
      const title = this.shadowRoot?.getElementById("physical-key-history-title");
      const summary = this.shadowRoot?.getElementById("physical-key-history-summary");
      if (section) section.hidden = hide;
      if (list) list.textContent = "";
      if (title) title.textContent = "История проходов";
      if (summary) summary.textContent = "Выберите физический ключ выше.";
      this._setPhysicalKeyHistoryStatus("Готово", "info");
      this._setPhysicalKeyHistoryButtons();
    };

    proto._renderPhysicalKeyHistory = function () {
      const section = this.shadowRoot?.getElementById("physical-key-history-section");
      const list = this.shadowRoot?.getElementById("physical-key-history-list");
      const title = this.shadowRoot?.getElementById("physical-key-history-title");
      const summary = this.shadowRoot?.getElementById("physical-key-history-summary");
      if (!section || !list) return;

      const selected = this._physicalKeyHistorySelection;
      if (!selected) {
        section.hidden = true;
        return;
      }

      section.hidden = false;
      if (title) title.textContent = `История проходов — ${selected.name || "Физический ключ"}`;
      if (summary) {
        const count = this._physicalKeyHistoryRows.length;
        summary.textContent = count
          ? `Загружено проходов: ${count}`
          : "Проходы ещё не загружены";
      }

      list.textContent = "";
      if (!this._physicalKeyHistoryRows.length && !this._physicalKeyHistoryLoading) {
        const empty = document.createElement("div");
        empty.className = "physical-key-history-empty";
        empty.textContent = "Проходов для выбранного ключа нет.";
        list.appendChild(empty);
      } else {
        for (const item of this._physicalKeyHistoryRows) {
          if (!item || typeof item.occurred_at !== "string") continue;
          const row = document.createElement("div");
          row.className = "physical-key-history-row";

          const icon = document.createElement("ha-icon");
          icon.className = "physical-key-history-icon";
          icon.setAttribute("icon", "mdi:door-open");

          const text = document.createElement("div");
          text.className = "physical-key-history-time";
          text.textContent = formatPassageAt(item.occurred_at);
          text.title = item.occurred_at;

          row.append(icon, text);
          list.appendChild(row);
        }
      }

      this._setPhysicalKeyHistoryButtons();
    };

    proto._loadPhysicalKeyHistory = async function (reset = true) {
      const selected = this._physicalKeyHistorySelection;
      if (
        !selected?.key_ref ||
        !this._deviceId ||
        !this._hass ||
        this._physicalKeyHistoryLoading
      ) {
        return;
      }

      const page = reset ? 0 : this._physicalKeyHistoryPage + 1;
      this._physicalKeyHistoryLoading = true;
      if (reset) {
        this._physicalKeyHistoryRows = [];
        this._physicalKeyHistoryPage = 0;
        this._physicalKeyHistoryHasMore = false;
      }
      this._renderPhysicalKeyHistory();
      this._setPhysicalKeyHistoryStatus(
        reset ? "Загрузка истории проходов…" : "Загрузка следующей страницы…",
        "info"
      );
      this._setPhysicalKeyHistoryButtons();

      try {
        const response = await this._callResponseService("get_physical_key_passages", {
          device_id: this._deviceId,
          key_ref: selected.key_ref,
          page,
        });
        if (
          !response ||
          response.key_ref !== selected.key_ref ||
          !Array.isArray(response.passages)
        ) {
          throw new Error("Сервис не вернул историю выбранного ключа");
        }

        const rows = response.passages.filter(
          (item) => item && typeof item.occurred_at === "string"
        );
        if (rows.length !== response.passages.length) {
          throw new Error("Сервис вернул некорректную запись истории проходов");
        }

        this._physicalKeyHistoryRows = reset
          ? rows
          : [...this._physicalKeyHistoryRows, ...rows];
        this._physicalKeyHistoryPage = Number(response.page ?? page);
        this._physicalKeyHistoryHasMore = response.has_more === true;
        if (typeof response.name === "string" && response.name) {
          this._physicalKeyHistorySelection = {
            ...selected,
            name: response.name,
          };
        }

        this._renderPhysicalKeyHistory();
        this._setPhysicalKeyHistoryStatus(
          rows.length
            ? "История проходов обновлена"
            : reset
              ? "Для выбранного ключа проходы не найдены"
              : "Дополнительных проходов нет",
          "ok"
        );
      } catch (err) {
        this._physicalKeyHistoryHasMore = false;
        this._setPhysicalKeyHistoryStatus(this._errorText(err), "error");
      } finally {
        this._physicalKeyHistoryLoading = false;
        this._renderPhysicalKeyHistory();
      }
    };

    proto._selectPhysicalKeyForHistory = function (item) {
      if (!item?.key_ref) return;
      const same = this._physicalKeyHistorySelection?.key_ref === item.key_ref;
      this._physicalKeyHistorySelection = {
        key_ref: item.key_ref,
        name: String(item.name || "Физический ключ"),
      };
      this._physicalKeyHistoryRows = [];
      this._physicalKeyHistoryPage = 0;
      this._physicalKeyHistoryHasMore = false;
      this._renderPhysicalKeys();
      this._renderPhysicalKeyHistory();
      if (!same || !this._physicalKeyHistoryRows.length) {
        void this._loadPhysicalKeyHistory(true);
      }
    };

    proto._decoratePhysicalKeyRowsForHistory = function () {
      const snapshot = this._physicalKeysSnapshot;
      const keys = Array.isArray(snapshot?.keys) ? snapshot.keys : [];
      const rows = Array.from(
        this.shadowRoot?.querySelectorAll("#physical-key-list .physical-key-row") || []
      );

      if (
        this._physicalKeyHistorySelection &&
        !keys.some(
          (item) => item?.key_ref === this._physicalKeyHistorySelection.key_ref
        )
      ) {
        this._clearPhysicalKeyHistory(true);
      }

      rows.forEach((row, index) => {
        const item = keys[index];
        if (!item?.key_ref) return;
        row.classList.add("physical-key-history-selectable");
        row.dataset.historySelected = String(
          this._physicalKeyHistorySelection?.key_ref === item.key_ref
        );
        row.title = "Нажмите, чтобы показать историю проходов этого ключа";
        row.addEventListener("click", (event) => {
          if (event.target?.closest?.(".physical-key-rename")) return;
          this._selectPhysicalKeyForHistory(item);
        });
      });

      if (this._physicalKeyHistorySelection) {
        const current = keys.find(
          (item) => item?.key_ref === this._physicalKeyHistorySelection.key_ref
        );
        if (current && current.name !== this._physicalKeyHistorySelection.name) {
          this._physicalKeyHistorySelection = {
            ...this._physicalKeyHistorySelection,
            name: current.name,
          };
          this._renderPhysicalKeyHistory();
        }
      }
    };

    proto._installPhysicalKeyHistoryPanel = function () {
      const panel = this.shadowRoot?.getElementById("panel-keys");
      if (!panel || this.shadowRoot.getElementById("physical-key-history-section")) {
        return;
      }

      const section = document.createElement("section");
      section.id = "physical-key-history-section";
      section.className = "physical-key-history-section";
      section.hidden = true;
      section.innerHTML = `
        <div class="physical-key-history-toolbar">
          <div class="physical-key-history-toolbar-main">
            <div id="physical-key-history-title" class="physical-key-history-title">История проходов</div>
            <div id="physical-key-history-summary" class="physical-key-history-summary">Выберите физический ключ выше.</div>
          </div>
          <div class="physical-key-history-actions">
            <button id="refresh-physical-key-history" class="small-button" type="button">Обновить историю</button>
            <button id="more-physical-key-history" class="small-button" type="button" hidden>Показать ещё</button>
          </div>
        </div>
        <div class="physical-key-history-note">
          Показывается только время прохода выбранного ключа. Служебные идентификаторы Ufanet не выводятся.
        </div>
        <div id="physical-key-history-list" class="physical-key-history-list"></div>
        <div id="physical-key-history-status" class="physical-key-history-status">Готово</div>
      `;

      const status = panel.querySelector("#physical-key-status");
      if (status?.parentNode) status.parentNode.insertBefore(section, status);
      else panel.appendChild(section);

      section
        .querySelector("#refresh-physical-key-history")
        ?.addEventListener("click", () => void this._loadPhysicalKeyHistory(true));
      section
        .querySelector("#more-physical-key-history")
        ?.addEventListener("click", () => void this._loadPhysicalKeyHistory(false));

      if (!this.shadowRoot.getElementById("physical-key-history-extension-style")) {
        const style = document.createElement("style");
        style.id = "physical-key-history-extension-style";
        style.textContent = `
          .physical-key-history-selectable { cursor: pointer; }
          .physical-key-history-selectable:hover {
            border-color: color-mix(in srgb, var(--primary-color) 55%, var(--divider-color));
          }
          .physical-key-row[data-history-selected="true"] {
            border-color: var(--primary-color);
            box-shadow: 0 0 0 1px var(--primary-color) inset;
          }
          .physical-key-history-section {
            margin-top: 18px;
            padding-top: 16px;
            border-top: 1px solid var(--divider-color);
          }
          .physical-key-history-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 8px;
          }
          .physical-key-history-toolbar-main { min-width: 0; }
          .physical-key-history-title {
            font-size: 15px;
            font-weight: 600;
          }
          .physical-key-history-summary,
          .physical-key-history-note {
            color: var(--secondary-text-color);
            font-size: 12px;
          }
          .physical-key-history-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
          }
          .physical-key-history-note {
            margin-bottom: 10px;
            line-height: 1.45;
          }
          .physical-key-history-list {
            display: grid;
            gap: 6px;
          }
          .physical-key-history-row {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 12px;
            border: 1px solid var(--divider-color);
            border-radius: 8px;
          }
          .physical-key-history-icon { color: var(--primary-color); }
          .physical-key-history-time { font-variant-numeric: tabular-nums; }
          .physical-key-history-empty {
            padding: 16px 12px;
            text-align: center;
            color: var(--secondary-text-color);
            border: 1px dashed var(--divider-color);
            border-radius: 8px;
          }
          .physical-key-history-status {
            margin-top: 10px;
            padding: 9px 11px;
            border-radius: 8px;
            font-size: 12px;
          }
          .physical-key-history-status[data-type="ok"] {
            background: color-mix(in srgb, var(--success-color, #43a047) 12%, transparent);
          }
          .physical-key-history-status[data-type="error"] {
            background: color-mix(in srgb, var(--error-color) 12%, transparent);
          }
          .physical-key-history-status[data-type="info"] {
            background: color-mix(in srgb, var(--primary-color) 10%, transparent);
          }
        `;
        this.shadowRoot.appendChild(style);
      }

      this._setPhysicalKeyHistoryButtons();
    };

    proto._installPhysicalKeyPanel = function (...args) {
      const result = originalInstallPhysicalKeyPanel.apply(this, args);
      this._installPhysicalKeyHistoryPanel();
      this._decoratePhysicalKeyRowsForHistory();
      return result;
    };

    proto._renderPhysicalKeys = function (...args) {
      const result = originalRenderPhysicalKeys.apply(this, args);
      this._installPhysicalKeyHistoryPanel();
      this._decoratePhysicalKeyRowsForHistory();
      return result;
    };

    proto.disconnectedCallback = function (...args) {
      this._physicalKeyHistoryLoading = false;
      return originalDisconnectedCallback?.apply(this, args);
    };

    queueMicrotask(() => {
      for (const element of document.querySelectorAll(CARD_TAG)) {
        element._installPhysicalKeyHistoryPanel?.();
        element._decoratePhysicalKeyRowsForHistory?.();
      }
    });
    return true;
  }

  async function boot() {
    try {
      await customElements.whenDefined(CARD_TAG);
      const CardClass = customElements.get(CARD_TAG);
      for (let attempt = 0; attempt < 100; attempt += 1) {
        if (installHistoryExtension(CardClass)) return;
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      throw new Error("physical-key extension was not ready in time");
    } catch (err) {
      console.error("Ufanet key-history card extension failed to initialize", err);
    }
  }

  void boot();
})();
