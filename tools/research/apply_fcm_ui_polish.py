from pathlib import Path

CARD = Path("custom_components/ufanet_intercom/frontend/ufanet-archive-card.js")
text = CARD.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    text = text.replace(old, new, 1)


replace_once(
'''      const icon = document.createElement("div");
      icon.className = "fcm-session-icon";
      icon.textContent = session.protected === true ? "🛡️" : "📱";
''',
'''      const icon = document.createElement("ha-icon");
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
        session.protected === true
          ? "mdi:shield-check"
          : platformIcons[String(session.platform || "unknown")] || "mdi:cellphone"
      );
''',
"session icon",
)

replace_once(
'      main.append(titleLine, meta);\n',
'      main.append(titleLine);\n',
"session main layout",
)

replace_once(
'        protectedText.textContent = "Текущая HA-регистрация не может быть отозвана здесь";\n',
'        protectedText.textContent = "Защищено";\n',
"protected action text",
)

replace_once(
'      row.append(icon, main, actions);\n',
'      row.append(icon, main, meta, actions);\n',
"session row columns",
)

replace_once(
'''            <button id="refresh-fcm-sessions" type="button" class="small-button">Обновить</button>
            <button id="revoke-other-fcm-sessions" type="button" class="small-button" disabled>
              Отозвать все остальные
            </button>
''',
'''            <div class="fcm-session-toolbar-actions">
              <button id="refresh-fcm-sessions" type="button" class="small-button">Обновить</button>
              <button id="revoke-other-fcm-sessions" type="button" class="small-button danger-button fcm-session-bulk-action" disabled>
                Отозвать все остальные
              </button>
            </div>
''',
"session toolbar actions",
)

replace_once(
'''          <div class="fcm-session-warning">
            Здесь показаны активные авторизованные сессии аккаунта Ufanet. Регистрации,
            которые Home Assistant может доказанно распознать как свои, помечены щитом и
            защищены от одиночного и массового отзыва. Остальные устройства удаляются
            только после явного подтверждения пользователя.
          </div>
''',
'''          <div class="fcm-session-warning">
            Home Assistant защищает только те регистрации, принадлежность которых может
            доказать локально. Отзыв остальных сессий выполняется только после явного подтверждения.
          </div>
''',
"session warning copy",
)

old_css = '''        /* AUTHORIZED DEVICES */
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

new_css = '''        /* AUTHORIZED DEVICES */
        .fcm-session-toolbar {
          width: min(100%, 1240px);
          box-sizing: border-box;
          margin: 0 auto;
          padding: 16px 16px 10px;
          display: flex;
          gap: 10px;
          align-items: center;
          flex-wrap: wrap;
        }
        .fcm-session-toolbar-main { flex: 1 1 280px; min-width: 0; }
        .fcm-session-toolbar-title { font-size: 14px; font-weight: 700; }
        .fcm-session-summary { margin-top: 4px; color: var(--secondary-text-color); font-size: 12px; }
        .fcm-session-toolbar-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 7px;
          flex-wrap: wrap;
        }
        .fcm-session-warning {
          width: calc(100% - 32px);
          max-width: 1208px;
          box-sizing: border-box;
          margin: 2px auto 10px;
          padding: 9px 11px;
          border-radius: 10px;
          background: color-mix(in srgb, var(--warning-color, #f0a000) 8%, transparent);
          border: 1px solid color-mix(in srgb, var(--warning-color, #f0a000) 24%, transparent);
          color: var(--secondary-text-color);
          font-size: 11px;
          line-height: 1.45;
        }
        .fcm-session-list {
          width: min(100%, 1240px);
          box-sizing: border-box;
          margin: 0 auto;
          display: grid;
          gap: 8px;
          padding: 4px 16px 12px;
        }
        .fcm-session-empty { color: var(--secondary-text-color); font-size: 12px; padding: 12px 0; }
        .fcm-session-row {
          display: grid;
          grid-template-columns: 36px minmax(180px, .9fr) minmax(280px, 1.5fr) auto;
          gap: 12px;
          align-items: center;
          padding: 11px 12px;
          border-radius: 11px;
          background: var(--secondary-background-color);
          border: 1px solid color-mix(in srgb, var(--divider-color) 78%, transparent);
        }
        .fcm-session-row[data-protected="true"] {
          border-color: color-mix(in srgb, var(--success-color, #43a047) 38%, transparent);
          background: color-mix(in srgb, var(--success-color, #43a047) 5%, var(--secondary-background-color));
        }
        .fcm-session-icon {
          --mdc-icon-size: 22px;
          justify-self: center;
          color: var(--secondary-text-color);
        }
        .fcm-session-row[data-protected="true"] .fcm-session-icon {
          color: var(--success-color, #43a047);
        }
        .fcm-session-main { min-width: 0; }
        .fcm-session-title-line { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
        .fcm-session-title {
          font-size: 14px;
          font-weight: 650;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 100%;
        }
        .fcm-session-badge {
          padding: 2px 7px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 600;
          color: var(--success-color, #43a047);
          background: color-mix(in srgb, var(--success-color, #43a047) 12%, transparent);
          white-space: nowrap;
        }
        .fcm-session-meta {
          min-width: 0;
          color: var(--secondary-text-color);
          font-size: 12px;
          line-height: 1.4;
          overflow-wrap: anywhere;
        }
        .fcm-session-actions {
          min-width: 86px;
          display: flex;
          align-items: center;
          justify-content: flex-end;
        }
        .fcm-session-protected-note {
          color: var(--success-color, #43a047);
          font-size: 11px;
          font-weight: 600;
          text-align: right;
          white-space: nowrap;
        }
        .fcm-session-action,
        .fcm-session-bulk-action {
          color: var(--error-color);
          background: transparent;
          border: 1px solid color-mix(in srgb, var(--error-color) 35%, transparent);
        }
        .fcm-session-action:hover,
        .fcm-session-bulk-action:hover {
          background: color-mix(in srgb, var(--error-color) 8%, transparent);
        }
        .fcm-session-status {
          width: min(100%, 1240px);
          box-sizing: border-box;
          margin: 0 auto;
          padding: 0 16px 14px;
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        #fcm-session-status[data-type="error"] { color: var(--error-color); }
        #fcm-session-status[data-type="warning"] { color: var(--warning-color, #f0a000); }
        #fcm-session-status[data-type="ok"] { color: var(--success-color, #43a047); }
'''
replace_once(old_css, new_css, "authorized devices CSS")

replace_once(
'''          .archive-library-actions { width: 100%; justify-content: flex-start; }
''',
'''          .archive-library-actions { width: 100%; justify-content: flex-start; }
          .fcm-session-toolbar { align-items: stretch; padding: 14px 12px 8px; }
          .fcm-session-toolbar-main { flex-basis: 100%; }
          .fcm-session-toolbar-actions {
            width: 100%;
            display: grid;
            grid-template-columns: 1fr 1fr;
          }
          .fcm-session-toolbar-actions button { width: 100%; }
          .fcm-session-warning { width: calc(100% - 24px); margin: 4px 12px 10px; }
          .fcm-session-list { padding: 4px 12px 12px; }
          .fcm-session-row {
            grid-template-columns: 32px minmax(0, 1fr) auto;
            gap: 6px 8px;
            padding: 10px;
          }
          .fcm-session-icon { grid-column: 1; grid-row: 1 / span 2; }
          .fcm-session-main { grid-column: 2; grid-row: 1; }
          .fcm-session-meta { grid-column: 2 / 4; grid-row: 2; }
          .fcm-session-actions { grid-column: 3; grid-row: 1; min-width: 0; }
          .fcm-session-status { padding: 0 12px 14px; }
''',
"mobile authorized devices layout",
)

if 'icon.textContent = session.protected === true ? "🛡️" : "📱";' in text:
    raise SystemExit("emoji session icon survived")
if 'row.append(icon, main, meta, actions);' not in text:
    raise SystemExit("four-column session row was not produced")
if 'session_ref: session.session_ref' not in text:
    raise SystemExit("targeted revoke plumbing disappeared")
if 'Home Assistant • защищено' not in text:
    raise SystemExit("explicit protected badge disappeared")

CARD.write_text(text, encoding="utf-8")
