(() => {
  "use strict";

  const CARD_TAG = "ufanet-intercom-card";
  const EXTENSION_MARK = Symbol.for("ufanet_intercom.authorized_devices_card");

  function installAuthorizedDevicesExtension(CardClass) {
    if (!CardClass?.prototype || CardClass.prototype[EXTENSION_MARK]) return false;

    const proto = CardClass.prototype;
    if (
      typeof proto._callResponseService !== "function" ||
      typeof proto._formatFcmSessionTime !== "function" ||
      typeof proto._fcmPlatformLabel !== "function" ||
      typeof proto._renderFcmSessions !== "function"
    ) {
      return false;
    }

    Object.defineProperty(proto, EXTENSION_MARK, {
      configurable: false,
      enumerable: false,
      value: true,
      writable: false,
    });

    const originalSetButtonsDisabled = proto._setFcmSessionButtonsDisabled;
    const originalRenderFcmSessions = proto._renderFcmSessions;

    proto._ensureAuthorizedDeviceState = function () {
      if (!Object.prototype.hasOwnProperty.call(this, "_advancedFcmSnapshot")) {
        this._advancedFcmSnapshot = null;
      }
      if (!Object.prototype.hasOwnProperty.call(this, "_advancedFcmLoading")) {
        this._advancedFcmLoading = false;
      }
    };

    proto._setFcmSessionButtonsDisabled = function (disabled) {
      originalSetButtonsDisabled?.call(this, disabled);
      this._ensureAuthorizedDeviceState();
      const advancedRefresh = this.shadowRoot?.getElementById("refresh-advanced-fcm");
      const advancedRemoveAll = this.shadowRoot?.getElementById("remove-other-advanced-fcm");
      if (advancedRefresh) {
        advancedRefresh.disabled = disabled || this._advancedFcmLoading;
      }
      if (advancedRemoveAll) {
        const count = Number(this._advancedFcmSnapshot?.removable_count || 0);
        advancedRemoveAll.disabled = disabled || this._advancedFcmLoading || count < 1;
      }
      for (const button of this.shadowRoot?.querySelectorAll(".advanced-fcm-action") || []) {
        button.disabled = disabled || this._advancedFcmLoading;
      }
    };

    proto._setAdvancedFcmStatus = function (message, type = "info") {
      const status = this.shadowRoot?.getElementById("advanced-fcm-status");
      if (!status) return;
      status.textContent = message || "";
      status.dataset.type = type;
    };

    proto._installAdvancedFcmPanel = function () {
      this._ensureAuthorizedDeviceState();
      const panel = this.shadowRoot?.getElementById("panel-sessions");
      if (!panel || this.shadowRoot.getElementById("advanced-fcm-management")) return;

      const details = document.createElement("details");
      details.id = "advanced-fcm-management";
      details.className = "advanced-fcm-management";
      details.innerHTML = `
        <summary class="advanced-fcm-summary-toggle">
          <span>Расширенное управление FCM</span>
          <span class="advanced-fcm-summary-hint">технический режим</span>
        </summary>
        <div class="advanced-fcm-body">
          <div class="advanced-fcm-warning">
            Прямое удаление FCM-регистрации использует DELETE /api/v0/fcm/ и не вызывает logout_device.
            Live-проверка показала, что при этом запись устройства исчезает и связанная refresh JWT-цепочка
            становится недействительной; уже выданный access JWT может работать до истечения срока.
          </div>
          <div class="advanced-fcm-toolbar">
            <div>
              <div class="advanced-fcm-title">FCM-регистрации</div>
              <div id="advanced-fcm-summary" class="advanced-fcm-subtitle">Список ещё не загружен</div>
            </div>
            <div class="advanced-fcm-toolbar-actions">
              <button id="refresh-advanced-fcm" type="button" class="small-button">Загрузить FCM</button>
              <button id="remove-other-advanced-fcm" type="button" class="small-button danger-button" disabled>
                Удалить остальные FCM
              </button>
            </div>
          </div>
          <div id="advanced-fcm-list" class="fcm-session-list advanced-fcm-list">
            <div class="fcm-session-empty">Нажмите «Загрузить FCM», чтобы получить технический список.</div>
          </div>
          <div id="advanced-fcm-status" class="fcm-session-status">Готово</div>
        </div>
      `;

      const normalStatus = panel.querySelector("#fcm-session-status");
      if (normalStatus?.parentNode) {
        normalStatus.parentNode.insertBefore(details, normalStatus.nextSibling);
      } else {
        panel.appendChild(details);
      }

      details
        .querySelector("#refresh-advanced-fcm")
        ?.addEventListener("click", () => void this._refreshAdvancedFcmRegistrations(true));
      details
        .querySelector("#remove-other-advanced-fcm")
        ?.addEventListener("click", () => void this._unregisterOtherAdvancedFcmRegistrations());

      if (!this.shadowRoot.getElementById("authorized-device-extension-style")) {
        const style = document.createElement("style");
        style.id = "authorized-device-extension-style";
        style.textContent = `
          .advanced-fcm-management {
            width: min(100%, 1240px);
            box-sizing: border-box;
            margin: 12px auto 4px;
            border: 1px solid var(--divider-color);
            border-radius: 10px;
            overflow: hidden;
          }
          .advanced-fcm-summary-toggle {
            cursor: pointer;
            padding: 12px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            font-weight: 600;
            user-select: none;
          }
          .advanced-fcm-summary-hint {
            color: var(--secondary-text-color);
            font-size: 11px;
            font-weight: 400;
          }
          .advanced-fcm-body {
            border-top: 1px solid var(--divider-color);
            padding: 12px;
          }
          .advanced-fcm-warning {
            padding: 10px 12px;
            border-radius: 8px;
            background: color-mix(in srgb, var(--warning-color, #f0a000) 12%, transparent);
            border: 1px solid color-mix(in srgb, var(--warning-color, #f0a000) 30%, transparent);
            color: var(--secondary-text-color);
            font-size: 12px;
            line-height: 1.5;
            margin-bottom: 12px;
          }
          .advanced-fcm-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 10px;
          }
          .advanced-fcm-title { font-weight: 600; }
          .advanced-fcm-subtitle {
            color: var(--secondary-text-color);
            font-size: 12px;
            margin-top: 2px;
          }
          .advanced-fcm-toolbar-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
          }
          .advanced-fcm-list { padding: 0; }
          .advanced-fcm-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 2px 7px;
            margin-left: 6px;
            font-size: 10px;
            color: var(--secondary-text-color);
            background: color-mix(in srgb, var(--primary-color) 10%, transparent);
          }
          @media (max-width: 600px) {
            .advanced-fcm-management { width: calc(100% - 24px); }
            .advanced-fcm-toolbar-actions { width: 100%; display: grid; grid-template-columns: 1fr 1fr; }
            .advanced-fcm-toolbar-actions button { width: 100%; }
          }
        `;
        this.shadowRoot.appendChild(style);
      }

      this._renderAdvancedFcmRegistrations();
    };

    proto._refreshFcmSessions = async function (force = false) {
      if (!this._deviceId || !this._hass || this._fcmSessionsLoading) return;
      if (this._fcmSessions && !force) {
        this._renderFcmSessions();
        return;
      }

      this._fcmSessionsLoading = true;
      this._setFcmSessionButtonsDisabled(true);
      this._setFcmSessionStatus("Загрузка авторизованных устройств…", "info");
      try {
        const response = await this._callResponseService("list_authorized_devices", {
          device_id: this._deviceId,
        });
        if (!response || !Array.isArray(response.authorizations)) {
          throw new Error("Сервис не вернул список авторизованных устройств");
        }
        this._fcmSessions = response;
        this._renderFcmSessions();
        this._setFcmSessionStatus("Список устройств обновлён", "ok");
      } catch (err) {
        this._setFcmSessionStatus(this._errorText(err), "error");
      } finally {
        this._fcmSessionsLoading = false;
        this._setFcmSessionButtonsDisabled(false);
      }
    };

    proto._renderFcmSessions = function () {
      this._installAdvancedFcmPanel();
      const host = this.shadowRoot?.getElementById("fcm-session-list");
      const summary = this.shadowRoot?.getElementById("fcm-session-summary");
      const revokeAll = this.shadowRoot?.getElementById("revoke-other-fcm-sessions");
      if (!host) return;

      host.textContent = "";
      const snapshot = this._fcmSessions;
      const authorizations = Array.isArray(snapshot?.authorizations)
        ? snapshot.authorizations
        : [];

      if (summary) {
        summary.textContent = !snapshot
          ? "Список ещё не загружен"
          : `Всего: ${Number(snapshot.count || authorizations.length)} • ` +
            `защищено: ${Number(snapshot.protected_count || 0)} • ` +
            `можно отозвать: ${Number(snapshot.revocable_count || 0)}`;
      }
      if (revokeAll) {
        revokeAll.textContent = "Отозвать остальные";
        revokeAll.disabled = this._fcmSessionsLoading || Number(snapshot?.revocable_count || 0) < 1;
      }

      if (!snapshot) {
        const empty = document.createElement("div");
        empty.className = "fcm-session-empty";
        empty.textContent = "Нажмите «Обновить», чтобы получить список устройств.";
        host.appendChild(empty);
        return;
      }
      if (!authorizations.length) {
        const empty = document.createElement("div");
        empty.className = "fcm-session-empty";
        empty.textContent = "Зарегистрированных устройств не найдено.";
        host.appendChild(empty);
        return;
      }

      for (const authorization of authorizations) {
        const row = document.createElement("div");
        row.className = "fcm-session-row";
        row.dataset.protected = authorization.protected === true ? "true" : "false";

        const icon = document.createElement("ha-icon");
        icon.className = "fcm-session-icon";
        const platformIcons = {
          android: "mdi:android",
          ios: "mdi:apple-ios",
          harmonyos: "mdi:cellphone",
          other: "mdi:cellphone",
          unknown: "mdi:cellphone",
        };
        icon.setAttribute(
          "icon",
          authorization.protected === true
            ? "mdi:shield-check"
            : platformIcons[String(authorization.platform || "unknown")] || "mdi:cellphone"
        );

        const main = document.createElement("div");
        main.className = "fcm-session-main";
        const titleLine = document.createElement("div");
        titleLine.className = "fcm-session-title-line";
        const title = document.createElement("span");
        title.className = "fcm-session-title";
        title.textContent = String(authorization.title || "Неизвестное устройство");
        titleLine.appendChild(title);
        if (authorization.protected === true) {
          const badge = document.createElement("span");
          badge.className = "fcm-session-badge";
          badge.textContent = "Home Assistant • защищено";
          titleLine.appendChild(badge);
        }
        main.appendChild(titleLine);

        const meta = document.createElement("div");
        meta.className = "fcm-session-meta";
        meta.textContent = [
          this._fcmPlatformLabel(authorization.platform),
          `Активность: ${this._formatFcmSessionTime(authorization.last_update)}`,
          authorization.is_call_access === true ? "звонки разрешены" : "без доступа к звонкам",
        ].join(" • ");

        const actions = document.createElement("div");
        actions.className = "fcm-session-actions";
        if (authorization.protected !== true) {
          const revoke = document.createElement("button");
          revoke.type = "button";
          revoke.className = "small-button danger-button fcm-session-action";
          revoke.textContent = "Отозвать авторизацию";
          revoke.title = "Выполнить штатный Ufanet logout_device для этого устройства";
          revoke.addEventListener("click", () => void this._revokeFcmSession(authorization));
          actions.appendChild(revoke);
        }

        row.append(icon, main, meta, actions);
        host.appendChild(row);
      }
    };

    proto._revokeFcmSession = async function (authorization) {
      if (
        !authorization?.authorization_ref ||
        authorization.protected === true ||
        !this._deviceId ||
        this._fcmSessionsLoading
      ) return;

      const title = String(authorization.title || "Неизвестное устройство");
      const confirmed = window.confirm(
        `Отозвать авторизацию устройства «${title}»?\n\n` +
        `${this._fcmPlatformLabel(authorization.platform)}\n` +
        `${this._formatFcmSessionTime(authorization.last_update)}\n\n` +
        "Будет вызван штатный Ufanet logout_device. Уже выданный access JWT может работать до истечения срока, но refresh-цепочка будет отозвана."
      );
      if (!confirmed) return;

      this._fcmSessionsLoading = true;
      this._setFcmSessionButtonsDisabled(true);
      this._setFcmSessionStatus(`Отзываю авторизацию «${title}»…`, "warning");
      try {
        await this._callResponseService("revoke_authorized_device", {
          device_id: this._deviceId,
          authorization_ref: authorization.authorization_ref,
          confirm: true,
        });
        this._fcmSessions = null;
        this._advancedFcmSnapshot = null;
        this._setFcmSessionStatus(`Авторизация «${title}» отозвана. Обновляю список…`, "ok");
      } catch (err) {
        this._setFcmSessionStatus(this._errorText(err), "error");
        this._fcmSessionsLoading = false;
        this._setFcmSessionButtonsDisabled(false);
        return;
      }
      this._fcmSessionsLoading = false;
      this._setFcmSessionButtonsDisabled(false);
      this._renderAdvancedFcmRegistrations();
      await this._refreshFcmSessions(true);
    };

    proto._revokeOtherFcmSessions = async function () {
      if (!this._deviceId || this._fcmSessionsLoading || !this._fcmSessions) return;
      const count = Number(this._fcmSessions.revocable_count || 0);
      if (!Number.isInteger(count) || count < 1) {
        this._setFcmSessionStatus("Нет устройств, доступных для массового отзыва", "info");
        return;
      }
      if (!window.confirm(
        `Отозвать авторизацию ВСЕХ остальных устройств (${count})?\n\n` +
        "Защищённые регистрации Home Assistant останутся активными. Для остальных будет вызван logout_device."
      )) return;
      if (!window.confirm(
        `Последнее подтверждение: отозвать именно ${count} устройств?\n\n` +
        "Если серверный список изменился, операция будет отменена."
      )) return;

      this._fcmSessionsLoading = true;
      this._setFcmSessionButtonsDisabled(true);
      this._setFcmSessionStatus(`Отзываю ${count} авторизаций…`, "warning");
      try {
        const response = await this._callResponseService("revoke_other_authorized_devices", {
          device_id: this._deviceId,
          expected_count: count,
          confirm: true,
        });
        this._fcmSessions = null;
        this._advancedFcmSnapshot = null;
        this._setFcmSessionStatus(
          `Отозвано: ${Number(response?.revoked_count || count)}. Обновляю список…`,
          "ok"
        );
      } catch (err) {
        this._setFcmSessionStatus(this._errorText(err), "error");
        this._fcmSessionsLoading = false;
        this._setFcmSessionButtonsDisabled(false);
        return;
      }
      this._fcmSessionsLoading = false;
      this._setFcmSessionButtonsDisabled(false);
      this._renderAdvancedFcmRegistrations();
      await this._refreshFcmSessions(true);
    };

    proto._refreshAdvancedFcmRegistrations = async function (force = false) {
      this._ensureAuthorizedDeviceState();
      if (!this._deviceId || !this._hass || this._advancedFcmLoading) return;
      if (this._advancedFcmSnapshot && !force) {
        this._renderAdvancedFcmRegistrations();
        return;
      }

      this._advancedFcmLoading = true;
      this._setFcmSessionButtonsDisabled(true);
      this._setAdvancedFcmStatus("Загрузка FCM-регистраций…", "info");
      try {
        const response = await this._callResponseService("list_fcm_registrations", {
          device_id: this._deviceId,
        });
        if (!response || !Array.isArray(response.registrations)) {
          throw new Error("Сервис не вернул список FCM-регистраций");
        }
        this._advancedFcmSnapshot = response;
        this._renderAdvancedFcmRegistrations();
        this._setAdvancedFcmStatus("FCM-регистрации обновлены", "ok");
      } catch (err) {
        this._setAdvancedFcmStatus(this._errorText(err), "error");
      } finally {
        this._advancedFcmLoading = false;
        this._setFcmSessionButtonsDisabled(false);
      }
    };

    proto._renderAdvancedFcmRegistrations = function () {
      this._ensureAuthorizedDeviceState();
      this._installAdvancedFcmPanel();
      const host = this.shadowRoot?.getElementById("advanced-fcm-list");
      const summary = this.shadowRoot?.getElementById("advanced-fcm-summary");
      const removeAll = this.shadowRoot?.getElementById("remove-other-advanced-fcm");
      if (!host) return;

      host.textContent = "";
      const snapshot = this._advancedFcmSnapshot;
      const registrations = Array.isArray(snapshot?.registrations) ? snapshot.registrations : [];
      if (summary) {
        summary.textContent = !snapshot
          ? "Список ещё не загружен"
          : `Всего: ${Number(snapshot.count || registrations.length)} • ` +
            `защищено: ${Number(snapshot.protected_count || 0)} • ` +
            `можно удалить: ${Number(snapshot.removable_count || 0)}`;
      }
      if (removeAll) {
        removeAll.disabled = this._advancedFcmLoading || Number(snapshot?.removable_count || 0) < 1;
      }

      if (!snapshot) {
        const empty = document.createElement("div");
        empty.className = "fcm-session-empty";
        empty.textContent = "Нажмите «Загрузить FCM», чтобы получить технический список.";
        host.appendChild(empty);
        return;
      }
      if (!registrations.length) {
        const empty = document.createElement("div");
        empty.className = "fcm-session-empty";
        empty.textContent = "FCM-регистрации не найдены.";
        host.appendChild(empty);
        return;
      }

      for (const registration of registrations) {
        const row = document.createElement("div");
        row.className = "fcm-session-row";
        row.dataset.protected = registration.protected === true ? "true" : "false";

        const icon = document.createElement("ha-icon");
        icon.className = "fcm-session-icon";
        icon.setAttribute("icon", registration.protected === true ? "mdi:shield-check" : "mdi:bell-ring");

        const main = document.createElement("div");
        main.className = "fcm-session-main";
        const titleLine = document.createElement("div");
        titleLine.className = "fcm-session-title-line";
        const title = document.createElement("span");
        title.className = "fcm-session-title";
        title.textContent = String(registration.title || "Неизвестное устройство");
        titleLine.appendChild(title);
        const fcmBadge = document.createElement("span");
        fcmBadge.className = "advanced-fcm-badge";
        fcmBadge.textContent = registration.protected === true ? "HA • защищено" : "FCM";
        titleLine.appendChild(fcmBadge);
        main.appendChild(titleLine);

        const meta = document.createElement("div");
        meta.className = "fcm-session-meta";
        meta.textContent = [
          this._fcmPlatformLabel(registration.platform),
          `Активность: ${this._formatFcmSessionTime(registration.last_update)}`,
          registration.is_call_access === true ? "звонки разрешены" : "без доступа к звонкам",
        ].join(" • ");

        const actions = document.createElement("div");
        actions.className = "fcm-session-actions";
        if (registration.protected !== true) {
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "small-button danger-button advanced-fcm-action";
          remove.textContent = "Удалить FCM";
          remove.title = "Прямой DELETE /api/v0/fcm/; refresh JWT этой регистрации будет инвалидирован";
          remove.addEventListener("click", () => void this._unregisterAdvancedFcmRegistration(registration));
          actions.appendChild(remove);
        }

        row.append(icon, main, meta, actions);
        host.appendChild(row);
      }
    };

    proto._unregisterAdvancedFcmRegistration = async function (registration) {
      if (
        !registration?.fcm_ref ||
        registration.protected === true ||
        !this._deviceId ||
        this._advancedFcmLoading
      ) return;

      const title = String(registration.title || "Неизвестное устройство");
      if (!window.confirm(
        `Удалить FCM-регистрацию «${title}» напрямую?\n\n` +
        "Будет вызван DELETE /api/v0/fcm/, а не logout_device. Live-тест показал, что запись устройства исчезнет, refresh JWT станет недействительным, но уже выданный access JWT может временно продолжить работать."
      )) return;

      this._advancedFcmLoading = true;
      this._setFcmSessionButtonsDisabled(true);
      this._setAdvancedFcmStatus(`Удаляю FCM-регистрацию «${title}»…`, "warning");
      try {
        const response = await this._callResponseService("unregister_fcm_registration", {
          device_id: this._deviceId,
          fcm_ref: registration.fcm_ref,
          confirm: true,
        });
        this._advancedFcmSnapshot = null;
        this._fcmSessions = null;
        this._setAdvancedFcmStatus(
          response?.authorized_device_still_visible === true
            ? "FCM удалён, но строка устройства всё ещё видна; обновляю списки…"
            : "FCM удалён; строка устройства исчезла. Обновляю списки…",
          "ok"
        );
      } catch (err) {
        this._setAdvancedFcmStatus(this._errorText(err), "error");
        this._advancedFcmLoading = false;
        this._setFcmSessionButtonsDisabled(false);
        return;
      }
      this._advancedFcmLoading = false;
      this._setFcmSessionButtonsDisabled(false);
      await this._refreshFcmSessions(true);
      await this._refreshAdvancedFcmRegistrations(true);
    };

    proto._unregisterOtherAdvancedFcmRegistrations = async function () {
      this._ensureAuthorizedDeviceState();
      if (!this._deviceId || this._advancedFcmLoading || !this._advancedFcmSnapshot) return;
      const count = Number(this._advancedFcmSnapshot.removable_count || 0);
      if (!Number.isInteger(count) || count < 1) {
        this._setAdvancedFcmStatus("Нет FCM-регистраций, доступных для удаления", "info");
        return;
      }
      if (!window.confirm(
        `Удалить ВСЕ остальные FCM-регистрации (${count})?\n\n` +
        "Это техническое действие через DELETE /api/v0/fcm/. Защищённая Home Assistant регистрация не удаляется."
      )) return;
      if (!window.confirm(
        `Последнее подтверждение: удалить именно ${count} FCM-регистраций?\n\n` +
        "Для удалённых регистраций refresh JWT-цепочки следует считать отозванными."
      )) return;

      this._advancedFcmLoading = true;
      this._setFcmSessionButtonsDisabled(true);
      this._setAdvancedFcmStatus(`Удаляю ${count} FCM-регистраций…`, "warning");
      try {
        const response = await this._callResponseService("unregister_other_fcm_registrations", {
          device_id: this._deviceId,
          expected_count: count,
          confirm: true,
        });
        this._advancedFcmSnapshot = null;
        this._fcmSessions = null;
        this._setAdvancedFcmStatus(
          `Удалено FCM-регистраций: ${Number(response?.unregistered_count || count)}. Обновляю списки…`,
          "ok"
        );
      } catch (err) {
        this._setAdvancedFcmStatus(this._errorText(err), "error");
        this._advancedFcmLoading = false;
        this._setFcmSessionButtonsDisabled(false);
        return;
      }
      this._advancedFcmLoading = false;
      this._setFcmSessionButtonsDisabled(false);
      await this._refreshFcmSessions(true);
      await this._refreshAdvancedFcmRegistrations(true);
    };

    queueMicrotask(() => {
      for (const element of document.querySelectorAll(CARD_TAG)) {
        element._ensureAuthorizedDeviceState?.();
        element._installAdvancedFcmPanel?.();
        if (element._fcmSessions) element._renderFcmSessions?.();
      }
    });

    // Keep a reference only to make intentional replacement explicit for reviewers.
    void originalRenderFcmSessions;
    return true;
  }

  async function boot() {
    try {
      await customElements.whenDefined(CARD_TAG);
      const CardClass = customElements.get(CARD_TAG);
      for (let attempt = 0; attempt < 100; attempt += 1) {
        if (installAuthorizedDevicesExtension(CardClass)) return;
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      throw new Error("authorized-device extension was not ready in time");
    } catch (err) {
      console.error("Ufanet authorized-device card extension failed to initialize", err);
    }
  }

  void boot();
})();
