from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARD = ROOT / "custom_components" / "ufanet_intercom" / "frontend" / "ufanet-archive-card.js"
TEST = ROOT / "tests" / "test_frontend_privacy.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


source = CARD.read_text(encoding="utf-8")

source = replace_once(
    source,
    '    this._guestInviteUrl = null;\n    this._runtimeStatus = null;',
    '    this._guestInviteUrl = null;\n'
    '    this._fcmSessions = null;\n'
    '    this._fcmSessionsLoading = false;\n'
    '    this._runtimeStatus = null;',
    "constructor state",
)

source = replace_once(
    source,
    '                { value: "guests", label: "Гости" },\n'
    '                { value: "diagnostics", label: "Диагностика" },',
    '                { value: "guests", label: "Гости" },\n'
    '                { value: "sessions", label: "Устройства" },\n'
    '                { value: "diagnostics", label: "Диагностика" },',
    "config form sessions option",
)

old_tabs = '["live", "archive", "guests", "diagnostics"]'
new_tabs = '["live", "archive", "guests", "sessions", "diagnostics"]'
if source.count(old_tabs) < 2:
    raise RuntimeError("tab arrays: expected at least two matches")
source = source.replace(old_tabs, new_tabs)

source = replace_once(
    source,
    '    } else if (normalized === "guests") {\n'
    '      void this._refreshGuestAccess(false);\n'
    '    } else if (normalized === "diagnostics") {',
    '    } else if (normalized === "guests") {\n'
    '      void this._refreshGuestAccess(false);\n'
    '    } else if (normalized === "sessions") {\n'
    '      void this._refreshFcmSessions(false);\n'
    '    } else if (normalized === "diagnostics") {',
    "sessions tab activation",
)

source = replace_once(
    source,
    '        guests: "Гости",\n        diagnostics: "Диагностика",',
    '        guests: "Гости",\n        sessions: "Устройства",\n        diagnostics: "Диагностика",',
    "sessions status name",
)

methods = r'''
  _formatFcmSessionTime(value) {
    const epochMs = Date.parse(String(value || ""));
    if (!Number.isFinite(epochMs)) return "время неизвестно";
    try {
      const exact = new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "short",
        timeStyle: "medium",
      }).format(new Date(epochMs));
      return `${exact} • ${this._formatRelativeEpoch(epochMs / 1000)}`;
    } catch (_err) {
      return String(value || "время неизвестно");
    }
  }

  _fcmPlatformLabel(value) {
    const labels = {
      android: "Android",
      ios: "iOS",
      harmonyos: "HarmonyOS",
      other: "Другая платформа",
      unknown: "Платформа неизвестна",
    };
    return labels[String(value || "unknown")] || "Платформа неизвестна";
  }

  _setFcmSessionStatus(message, type = "info") {
    const status = this.shadowRoot.getElementById("fcm-session-status");
    if (!status) return;
    status.textContent = message || "";
    status.dataset.type = type;
  }

  _setFcmSessionButtonsDisabled(disabled) {
    const refresh = this.shadowRoot.getElementById("refresh-fcm-sessions");
    const revokeAll = this.shadowRoot.getElementById("revoke-other-fcm-sessions");
    if (refresh) refresh.disabled = disabled;
    if (revokeAll) {
      const count = Number(this._fcmSessions?.revocable_count || 0);
      revokeAll.disabled = disabled || count < 1;
    }
    for (const button of this.shadowRoot.querySelectorAll(".fcm-session-action")) {
      button.disabled = disabled;
    }
  }

  async _refreshFcmSessions(force = false) {
    if (!this._deviceId || !this._hass || this._fcmSessionsLoading) return;
    if (this._fcmSessions && !force) {
      this._renderFcmSessions();
      return;
    }

    this._fcmSessionsLoading = true;
    this._setFcmSessionButtonsDisabled(true);
    this._setFcmSessionStatus("Загрузка авторизованных устройств…", "info");

    try {
      const response = await this._callResponseService("list_fcm_sessions", {
        device_id: this._deviceId,
      });
      if (!response || !Array.isArray(response.sessions)) {
        throw new Error("Сервис не вернул список авторизованных устройств");
      }
      this._fcmSessions = response;
      this._renderFcmSessions();
      this._setFcmSessionStatus("Список авторизованных устройств обновлён", "ok");
    } catch (err) {
      this._setFcmSessionStatus(this._errorText(err), "error");
    } finally {
      this._fcmSessionsLoading = false;
      this._setFcmSessionButtonsDisabled(false);
    }
  }

  _renderFcmSessions() {
    const host = this.shadowRoot.getElementById("fcm-session-list");
    const summary = this.shadowRoot.getElementById("fcm-session-summary");
    const revokeAll = this.shadowRoot.getElementById("revoke-other-fcm-sessions");
    if (!host) return;

    host.textContent = "";
    const snapshot = this._fcmSessions;
    const sessions = Array.isArray(snapshot?.sessions) ? snapshot.sessions : [];

    if (summary) {
      if (!snapshot) {
        summary.textContent = "Список ещё не загружен";
      } else {
        summary.textContent =
          `Всего: ${Number(snapshot.count || sessions.length)} • ` +
          `защищено: ${Number(snapshot.protected_count || 0)} • ` +
          `можно отозвать: ${Number(snapshot.revocable_count || 0)}`;
      }
    }

    if (revokeAll) {
      revokeAll.disabled =
        this._fcmSessionsLoading || Number(snapshot?.revocable_count || 0) < 1;
    }

    if (!snapshot) {
      const empty = document.createElement("div");
      empty.className = "fcm-session-empty";
      empty.textContent = "Нажмите «Обновить», чтобы получить список устройств.";
      host.appendChild(empty);
      return;
    }

    if (!sessions.length) {
      const empty = document.createElement("div");
      empty.className = "fcm-session-empty";
      empty.textContent = "Авторизованных устройств не найдено.";
      host.appendChild(empty);
      return;
    }

    for (const session of sessions) {
      const row = document.createElement("div");
      row.className = "fcm-session-row";
      row.dataset.protected = session.protected === true ? "true" : "false";

      const icon = document.createElement("div");
      icon.className = "fcm-session-icon";
      icon.textContent = session.protected === true ? "🛡️" : "📱";

      const main = document.createElement("div");
      main.className = "fcm-session-main";

      const titleLine = document.createElement("div");
      titleLine.className = "fcm-session-title-line";
      const title = document.createElement("span");
      title.className = "fcm-session-title";
      title.textContent = String(session.title || "Неизвестное устройство");
      titleLine.appendChild(title);

      if (session.protected === true) {
        const badge = document.createElement("span");
        badge.className = "fcm-session-badge";
        badge.textContent = "Home Assistant • защищено";
        titleLine.appendChild(badge);
      }

      const meta = document.createElement("div");
      meta.className = "fcm-session-meta";
      const details = [
        this._fcmPlatformLabel(session.platform),
        this._formatFcmSessionTime(session.last_update),
        session.is_call_access === true ? "звонки разрешены" : "без доступа к звонкам",
      ];
      meta.textContent = details.join(" • ");

      main.append(titleLine, meta);

      const actions = document.createElement("div");
      actions.className = "fcm-session-actions";
      if (session.protected === true) {
        const protectedText = document.createElement("span");
        protectedText.className = "fcm-session-protected-note";
        protectedText.textContent = "Текущая HA-регистрация не может быть отозвана здесь";
        actions.appendChild(protectedText);
      } else {
        const revoke = document.createElement("button");
        revoke.type = "button";
        revoke.className = "small-button danger-button fcm-session-action";
        revoke.textContent = "Отозвать";
        revoke.title = "Завершить эту авторизованную сессию Ufanet";
        revoke.addEventListener("click", () => void this._revokeFcmSession(session));
        actions.appendChild(revoke);
      }

      row.append(icon, main, actions);
      host.appendChild(row);
    }
  }

  async _revokeFcmSession(session) {
    if (!session || session.protected === true || !this._deviceId || this._fcmSessionsLoading) {
      return;
    }

    const title = String(session.title || "Неизвестное устройство");
    const activity = this._formatFcmSessionTime(session.last_update);
    const confirmed = window.confirm(
      `Завершить авторизованную сессию «${title}»?\n\n` +
      `${this._fcmPlatformLabel(session.platform)}\n${activity}\n\n` +
      "Устройство будет разлогинено в Ufanet. Для повторного доступа потребуется новая авторизация."
    );
    if (!confirmed) return;

    this._fcmSessionsLoading = true;
    this._setFcmSessionButtonsDisabled(true);
    this._setFcmSessionStatus(`Отзываю сессию «${title}»…`, "warning");

    try {
      await this._callResponseService("revoke_fcm_session", {
        device_id: this._deviceId,
        session_ref: session.session_ref,
        confirm: true,
      });
      this._fcmSessions = null;
      this._setFcmSessionStatus(`Сессия «${title}» отозвана. Обновляю список…`, "ok");
    } catch (err) {
      this._setFcmSessionStatus(this._errorText(err), "error");
      this._fcmSessionsLoading = false;
      this._setFcmSessionButtonsDisabled(false);
      return;
    }

    this._fcmSessionsLoading = false;
    this._setFcmSessionButtonsDisabled(false);
    await this._refreshFcmSessions(true);
  }

  async _revokeOtherFcmSessions() {
    if (!this._deviceId || this._fcmSessionsLoading || !this._fcmSessions) return;
    const count = Number(this._fcmSessions.revocable_count || 0);
    if (!Number.isInteger(count) || count < 1) {
      this._setFcmSessionStatus("Нет сессий, доступных для массового отзыва", "info");
      return;
    }

    const confirmed = window.confirm(
      `Завершить ВСЕ остальные авторизованные сессии (${count})?\n\n` +
      "Защищённые регистрации Home Assistant останутся активными. Остальные телефоны, эмуляторы и старые сессии будут разлогинены."
    );
    if (!confirmed) return;

    const confirmedAgain = window.confirm(
      `Последнее подтверждение: отозвать именно ${count} незaщищённых сессий?\n\n` +
      "Если список изменился после его загрузки, серверная операция будет отменена без массового отзыва."
    );
    if (!confirmedAgain) return;

    this._fcmSessionsLoading = true;
    this._setFcmSessionButtonsDisabled(true);
    this._setFcmSessionStatus(`Отзываю ${count} остальных сессий…`, "warning");

    try {
      const response = await this._callResponseService("revoke_other_fcm_sessions", {
        device_id: this._deviceId,
        expected_count: count,
        confirm: true,
      });
      this._fcmSessions = null;
      this._setFcmSessionStatus(
        `Массовый отзыв завершён: ${Number(response?.revoked_count || count)} сессий. Обновляю список…`,
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
    await this._refreshFcmSessions(true);
  }

'''

source = replace_once(
    source,
    '  _formatExpiry(value) {',
    methods + '  _formatExpiry(value) {',
    "FCM session UI methods",
)

source = replace_once(
    source,
    '          grid-template-columns: repeat(3, 1fr);',
    '          grid-template-columns: repeat(5, minmax(0, 1fr));',
    "tab grid",
)

css = r'''

        /* AUTHORIZED DEVICES */
        .fcm-session-toolbar {
          padding: 14px 16px 10px;
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
          border-bottom: 1px solid var(--divider-color);
        }
        .fcm-session-toolbar-main { flex: 1 1 240px; min-width: 0; }
        .fcm-session-toolbar-title { font-size: 13px; font-weight: 700; }
        .fcm-session-summary { margin-top: 3px; color: var(--secondary-text-color); font-size: 11px; }
        .fcm-session-warning {
          margin: 12px 16px 8px;
          padding: 10px 12px;
          border-radius: 10px;
          background: color-mix(in srgb, var(--warning-color, #f0a000) 10%, transparent);
          border: 1px solid color-mix(in srgb, var(--warning-color, #f0a000) 28%, transparent);
          color: var(--secondary-text-color);
          font-size: 11px;
          line-height: 1.45;
        }
        .fcm-session-list { display: grid; gap: 7px; padding: 4px 16px 12px; }
        .fcm-session-empty { color: var(--secondary-text-color); font-size: 12px; padding: 12px 0; }
        .fcm-session-row {
          display: grid;
          grid-template-columns: 34px minmax(0, 1fr) auto;
          gap: 9px;
          align-items: center;
          padding: 10px 11px;
          border-radius: 10px;
          background: var(--secondary-background-color);
          border: 1px solid transparent;
        }
        .fcm-session-row[data-protected="true"] {
          border-color: color-mix(in srgb, var(--success-color, #43a047) 35%, transparent);
        }
        .fcm-session-icon { font-size: 20px; text-align: center; }
        .fcm-session-main { min-width: 0; }
        .fcm-session-title-line { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
        .fcm-session-title {
          font-size: 13px;
          font-weight: 650;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 100%;
        }
        .fcm-session-badge {
          padding: 2px 6px;
          border-radius: 999px;
          font-size: 10px;
          color: var(--success-color, #43a047);
          background: color-mix(in srgb, var(--success-color, #43a047) 12%, transparent);
          white-space: nowrap;
        }
        .fcm-session-meta {
          color: var(--secondary-text-color);
          font-size: 11px;
          margin-top: 3px;
          overflow-wrap: anywhere;
        }
        .fcm-session-actions { display: flex; align-items: center; justify-content: flex-end; }
        .fcm-session-protected-note {
          max-width: 170px;
          color: var(--secondary-text-color);
          font-size: 10px;
          text-align: right;
          line-height: 1.3;
        }
        .fcm-session-status {
          padding: 0 16px 14px;
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        #fcm-session-status[data-type="error"] { color: var(--error-color); }
        #fcm-session-status[data-type="warning"] { color: var(--warning-color, #f0a000); }
        #fcm-session-status[data-type="ok"] { color: var(--success-color, #43a047); }
        #revoke-other-fcm-sessions { color: var(--error-color); }
'''

source = replace_once(
    source,
    '        #guest-status[data-type="ok"] { color: var(--success-color, #43a047); }\n\n        .footer {',
    '        #guest-status[data-type="ok"] { color: var(--success-color, #43a047); }' + css + '\n\n        .footer {',
    "FCM session CSS",
)

source = replace_once(
    source,
    '          .controls { grid-template-columns: 1fr 1fr; }',
    '          .tabs { grid-template-columns: repeat(3, minmax(0, 1fr)); }\n'
    '          .controls { grid-template-columns: 1fr 1fr; }',
    "mobile tab grid",
)

source = replace_once(
    source,
    '          <button id="tab-guests" class="tab-button" type="button" role="tab">ГОСТИ</button>\n'
    '          <button id="tab-diagnostics" class="tab-button" type="button" role="tab">ДИАГНОСТИКА</button>',
    '          <button id="tab-guests" class="tab-button" type="button" role="tab">ГОСТИ</button>\n'
    '          <button id="tab-sessions" class="tab-button" type="button" role="tab">УСТРОЙСТВА</button>\n'
    '          <button id="tab-diagnostics" class="tab-button" type="button" role="tab">ДИАГНОСТИКА</button>',
    "sessions tab button",
)

panel = r'''

        <section id="panel-sessions" class="panel" role="tabpanel" hidden>
          <div class="fcm-session-toolbar">
            <div class="fcm-session-toolbar-main">
              <div class="fcm-session-toolbar-title">Авторизованные устройства Ufanet</div>
              <div id="fcm-session-summary" class="fcm-session-summary">Список ещё не загружен</div>
            </div>
            <button id="refresh-fcm-sessions" type="button" class="small-button">Обновить</button>
            <button id="revoke-other-fcm-sessions" type="button" class="small-button" disabled>
              Отозвать все остальные
            </button>
          </div>

          <div class="fcm-session-warning">
            Здесь показаны активные авторизованные сессии аккаунта Ufanet. Регистрации,
            которые Home Assistant может доказанно распознать как свои, помечены щитом и
            защищены от одиночного и массового отзыва. Остальные устройства удаляются
            только после явного подтверждения пользователя.
          </div>

          <div id="fcm-session-list" class="fcm-session-list">
            <div class="fcm-session-empty">Нажмите «Обновить», чтобы получить список устройств.</div>
          </div>
          <div id="fcm-session-status" class="fcm-session-status">Готово</div>
        </section>
'''

source = replace_once(
    source,
    '        <section id="panel-diagnostics" class="panel" role="tabpanel" hidden>',
    panel + '\n        <section id="panel-diagnostics" class="panel" role="tabpanel" hidden>',
    "sessions panel",
)

source = replace_once(
    source,
    '    this.shadowRoot.getElementById("tab-guests")?.addEventListener("click", () => this._setActiveTab("guests"));\n'
    '    this.shadowRoot.getElementById("tab-diagnostics")?.addEventListener("click", () => this._setActiveTab("diagnostics"));',
    '    this.shadowRoot.getElementById("tab-guests")?.addEventListener("click", () => this._setActiveTab("guests"));\n'
    '    this.shadowRoot.getElementById("tab-sessions")?.addEventListener("click", () => this._setActiveTab("sessions"));\n'
    '    this.shadowRoot.getElementById("tab-diagnostics")?.addEventListener("click", () => this._setActiveTab("diagnostics"));',
    "sessions tab listener",
)

source = replace_once(
    source,
    '    this.shadowRoot.getElementById("diagnostics-refresh")?.addEventListener(\n'
    '      "click",\n'
    '      () => void this._refreshRuntimeStatus(true)\n'
    '    );',
    '    this.shadowRoot.getElementById("refresh-fcm-sessions")?.addEventListener(\n'
    '      "click",\n'
    '      () => void this._refreshFcmSessions(true)\n'
    '    );\n'
    '    this.shadowRoot.getElementById("revoke-other-fcm-sessions")?.addEventListener(\n'
    '      "click",\n'
    '      () => void this._revokeOtherFcmSessions()\n'
    '    );\n'
    '    this.shadowRoot.getElementById("diagnostics-refresh")?.addEventListener(\n'
    '      "click",\n'
    '      () => void this._refreshRuntimeStatus(true)\n'
    '    );',
    "sessions toolbar listeners",
)

source = replace_once(
    source,
    '    this._renderArchiveExports();\n    this._renderRuntimeStatus();',
    '    this._renderArchiveExports();\n    this._renderFcmSessions();\n    this._renderRuntimeStatus();',
    "initial sessions render",
)

source = replace_once(
    source,
    '    description: "LIVE, архив, звонки и гостевые доступы Ufanet",',
    '    description: "LIVE, архив, звонки, гостевые доступы и безопасность Ufanet",',
    "custom card description",
)

CARD.write_text(source, encoding="utf-8")

test_source = TEST.read_text(encoding="utf-8")
addition = r'''


def test_fcm_session_ui_uses_safe_refs_and_protection_guards() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")

    assert 'id="tab-sessions"' in source
    assert '"list_fcm_sessions"' in source
    assert '"revoke_fcm_session"' in source
    assert '"revoke_other_fcm_sessions"' in source
    assert "session_ref: session.session_ref" in source
    assert "expected_count: count" in source
    assert "confirm: true" in source
    assert "session.protected === true" in source
    assert "Home Assistant • защищено" in source
    assert "Отозвать все остальные" in source

    render = source.split("  _renderFcmSessions() {", 1)[1].split(
        "  async _revokeFcmSession", 1
    )[0]
    assert "session_ref" not in render
    assert "device_id" not in render
    assert "textContent = String(session.title" in render
'''
if "test_fcm_session_ui_uses_safe_refs_and_protection_guards" not in test_source:
    test_source += addition
TEST.write_text(test_source, encoding="utf-8")
