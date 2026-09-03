from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:80]!r}")
    write(path, text.replace(old, new, 1))


def replace_all_exact(path: str, old: str, new: str, expected: int) -> None:
    text = read(path)
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} matches, found {count}: {old!r}")
    write(path, text.replace(old, new))


# Release version alignment checked by scripts/release_check.py.
replace_once(
    "custom_components/ufanet_intercom/manifest.json",
    '  "version": "0.29.0"',
    '  "version": "0.30.0"',
)
replace_once(
    "custom_components/ufanet_intercom/const.py",
    'INTEGRATION_VERSION = "0.29.0"',
    'INTEGRATION_VERSION = "0.30.0"',
)
replace_once(
    "custom_components/ufanet_intercom/__init__.py",
    '_ARCHIVE_CARD_MODULE_URL = f"{_ARCHIVE_CARD_URL}?v=0.29.0"',
    '_ARCHIVE_CARD_MODULE_URL = f"{_ARCHIVE_CARD_URL}?v=0.30.0"',
)
replace_once(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    'const CARD_VERSION = "0.29.0";',
    'const CARD_VERSION = "0.30.0";',
)

# Finish the previously approved UI cleanup: the shield + badge already communicate protection.
replace_once(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    '''      if (session.protected === true) {\n        const protectedText = document.createElement("span");\n        protectedText.className = "fcm-session-protected-note";\n        protectedText.textContent = "Защищено";\n        actions.appendChild(protectedText);\n      } else {\n        const revoke = document.createElement("button");''',
    '''      if (session.protected !== true) {\n        const revoke = document.createElement("button");''',
)
replace_once(
    "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js",
    '''        .fcm-session-protected-note {\n          color: var(--success-color, #43a047);\n          font-size: 11px;\n          font-weight: 600;\n          text-align: right;\n          white-space: nowrap;\n        }\n''',
    "",
)

# Top-level English README.
replace_once(
    "README.md",
    "- Selectable call updates: polling by default or experimental low-latency FCM with safety polling.\n",
    "- Selectable call updates: polling by default or experimental low-latency FCM with safety polling.\n"
    "- Security review of authorized Ufanet/FCM sessions, with Home Assistant-owned registrations protected from revocation and explicit controls for unknown sessions.\n",
)
replace_once(
    "README.md",
    "Add the resource as a JavaScript module. For release v0.29.0 the cache-bust URL is:",
    "Add the resource as a JavaScript module. For release v0.30.0 the cache-bust URL is:",
)
replace_once(
    "README.md",
    "/ufanet_intercom/ufanet-archive-card.js?v=0.29.0",
    "/ufanet_intercom/ufanet-archive-card.js?v=0.30.0",
)
replace_once(
    "README.md",
    "The card contains four tabs:\n\n- **LIVE** — video, door button, latest call and jump-to-call recording.\n- **АРХИВ** — timeline, call markers, MP4 export and export media library.\n- **ГОСТИ** — shared invitations, accepted guest access, temporary keys and revoke actions.\n- **ДИАГНОСТИКА** — token-free runtime health, polling, UCAMS/archive status and autosave state.",
    "The card contains five tabs:\n\n- **LIVE** — video, door button, latest call and jump-to-call recording.\n- **АРХИВ** — timeline, call and motion markers, MP4 export and export media library.\n- **ГОСТИ** — shared invitations, accepted guest access, temporary keys and revoke actions.\n- **УСТРОЙСТВА** — authorized Ufanet sessions, Home Assistant ownership protection, targeted revocation and guarded bulk revocation.\n- **ДИАГНОСТИКА** — token-free runtime health, polling, FCM authorization state, UCAMS/archive status and autosave state.",
)
replace_once(
    "README.md",
    "The FCM watchdog distinguishes launched listener tasks from an established transport, lets the FCM library handle short reconnects, and recreates a terminal or stalled listener with exponential backoff. A Home Assistant Repair warning appears after a prolonged outage and closes automatically after recovery. Invalid or unreadable private FCM state is regenerated with a separate Repair notice; call-history polling remains active while the new listener connects. Disabling FCM or removing the ConfigEntry unregisters only the integration-owned `Home Assistant_<UUID>` virtual device; ordinary reloads and Home Assistant restarts retain it. Failed cleanup falls back to polling, opens a Repair and retries on the next setup. The diagnostics tab shows listener health, watchdog state, state-recovery and cleanup reasons, fallback polling, reconnects and connection timestamps without exposing push payloads, device IDs or credentials.\n",
    "The FCM watchdog distinguishes launched listener tasks from an established transport, lets the FCM library handle short reconnects, and recreates a terminal or stalled listener with exponential backoff. A Home Assistant Repair warning appears after a prolonged outage and closes automatically after recovery. Invalid or unreadable private FCM state is regenerated with a separate Repair notice; call-history polling remains active while the new listener connects. Disabling FCM or removing the ConfigEntry unregisters only the integration-owned `Home Assistant_<UUID>` virtual device; ordinary reloads and Home Assistant restarts retain it. Failed cleanup falls back to polling, opens a Repair and retries on the next setup. The diagnostics tab shows listener health, watchdog state, state-recovery and cleanup reasons, fallback polling, reconnects and connection timestamps without exposing push payloads, device IDs or credentials.\n\n### Authorized devices and FCM session security\n\nVersion 0.30.0 adds a live-confirmed check of the integration's own registration through `POST /api/v4/fcm_device/authorized_devices/`. The check runs after the MCS listener starts and does not block FCM transport startup. Diagnostics expose only whether the check succeeded, whether the Home Assistant registration is present, its call-access boolean and a coarse last-update age bucket; the provider `device_id`, exact timestamp, title and raw response remain private.\n\nThe **УСТРОЙСТВА** tab lists authorized Ufanet sessions by bounded title, normalized platform, last activity and call-access state. Home Assistant-owned registrations that can be proved from local private state are marked protected and have no revoke action. Other sessions can be revoked individually through an opaque `session_ref`; the integration refreshes the provider inventory before the request and verifies disappearance afterward. Bulk revocation requires two UI confirmations plus a backend `expected_count` guard against a fresh snapshot. No session is automatically revoked because of age, title or platform.\n",
)
replace_once(
    "README.md",
    "- Firebase values, FCM credentials and the local Firebase config path are never included in diagnostics. Do not commit `firebase_config.json`.\n",
    "- Firebase values, FCM credentials and the local Firebase config path are never included in diagnostics. Do not commit `firebase_config.json`.\n"
    "- Authorized-session management never exposes raw provider FCM `device_id` values in the card or public session responses. Home Assistant-owned registrations are protected from targeted and bulk revocation; destructive actions require explicit confirmation, and bulk revocation additionally requires an exact fresh revocable-session count.\n",
)

# Top-level Russian README.
replace_once(
    "README_RU.md",
    "- Выбор способа получения звонков: polling по умолчанию либо экспериментальный FCM с малой задержкой и резервным опросом.\n",
    "- Выбор способа получения звонков: polling по умолчанию либо экспериментальный FCM с малой задержкой и резервным опросом.\n"
    "- Проверка безопасности авторизованных Ufanet/FCM-сессий: регистрации Home Assistant защищены от отзыва, а неизвестные сессии можно явно завершить.\n",
)
replace_once(
    "README_RU.md",
    "Добавьте ресурс как JavaScript-модуль. Для релиза v0.29.0 cache-bust URL такой:",
    "Добавьте ресурс как JavaScript-модуль. Для релиза v0.30.0 cache-bust URL такой:",
)
replace_once(
    "README_RU.md",
    "/ufanet_intercom/ufanet-archive-card.js?v=0.29.0",
    "/ufanet_intercom/ufanet-archive-card.js?v=0.30.0",
)
replace_once(
    "README_RU.md",
    "Карточка содержит четыре вкладки:\n\n- **LIVE** — видео, кнопка открытия двери, последний звонок и переход к записи звонка.\n- **АРХИВ** — таймлайн, метки звонков, экспорт MP4 и медиатека экспортированных роликов.\n- **ГОСТИ** — приглашения для совместного доступа, принятые гостевые доступы, временные ключи и их отзыв.\n- **ДИАГНОСТИКА** — состояние интеграции без раскрытия токенов, polling, состояние UCAMS/архива и автосохранения.",
    "Карточка содержит пять вкладок:\n\n- **LIVE** — видео, кнопка открытия двери, последний звонок и переход к записи звонка.\n- **АРХИВ** — таймлайн, метки звонков и движения, экспорт MP4 и медиатека экспортированных роликов.\n- **ГОСТИ** — приглашения для совместного доступа, принятые гостевые доступы, временные ключи и их отзыв.\n- **УСТРОЙСТВА** — авторизованные сессии Ufanet, защита регистраций Home Assistant, точечный отзыв и защищённый массовый отзыв.\n- **ДИАГНОСТИКА** — состояние интеграции без раскрытия токенов, polling, статус FCM-авторизации, состояние UCAMS/архива и автосохранения.",
)
replace_once(
    "README_RU.md",
    "FCM watchdog отличает запуск задач listener от реального подключения, не мешает библиотеке самостоятельно обрабатывать короткие разрывы и пересоздаёт окончательно остановленный или зависший listener с экспоненциальной задержкой. После длительного сбоя Home Assistant создаёт предупреждение Repair и автоматически закрывает его после восстановления. Некорректное или нечитаемое приватное состояние FCM безопасно создаётся заново с отдельным уведомлением Repair; до подключения нового listener продолжает работать polling истории звонков. При отключении FCM или удалении ConfigEntry удаляется только принадлежащее интеграции виртуальное устройство `Home Assistant_<UUID>`; обычный reload и перезапуск Home Assistant сохраняют регистрацию. При ошибке очистки polling продолжает работать, создаётся Repair, а запрос повторяется при следующем setup. Вкладка диагностики показывает состояние listener и watchdog, причины восстановления state и очистки, резервный polling, переподключения и время соединений без раскрытия push payload, device ID или credentials.\n",
    "FCM watchdog отличает запуск задач listener от реального подключения, не мешает библиотеке самостоятельно обрабатывать короткие разрывы и пересоздаёт окончательно остановленный или зависший listener с экспоненциальной задержкой. После длительного сбоя Home Assistant создаёт предупреждение Repair и автоматически закрывает его после восстановления. Некорректное или нечитаемое приватное состояние FCM безопасно создаётся заново с отдельным уведомлением Repair; до подключения нового listener продолжает работать polling истории звонков. При отключении FCM или удалении ConfigEntry удаляется только принадлежащее интеграции виртуальное устройство `Home Assistant_<UUID>`; обычный reload и перезапуск Home Assistant сохраняют регистрацию. При ошибке очистки polling продолжает работать, создаётся Repair, а запрос повторяется при следующем setup. Вкладка диагностики показывает состояние listener и watchdog, причины восстановления state и очистки, резервный polling, переподключения и время соединений без раскрытия push payload, device ID или credentials.\n\n### Авторизованные устройства и безопасность FCM-сессий\n\nВ версии 0.30.0 добавлена live-confirmed проверка собственной регистрации интеграции через `POST /api/v4/fcm_device/authorized_devices/`. Проверка запускается уже после старта MCS listener и не блокирует запуск FCM-транспорта. Диагностика показывает только успешность проверки, наличие регистрации Home Assistant, булево состояние доступа к звонкам и грубую возрастную корзину `last_update`; provider `device_id`, точное время, title и raw response остаются приватными.\n\nВкладка **УСТРОЙСТВА** показывает авторизованные сессии Ufanet по ограниченному title, нормализованной платформе, времени последней активности и доступу к звонкам. Регистрации Home Assistant, принадлежность которых можно доказать из локального приватного state, помечаются как защищённые и не имеют действия отзыва. Остальные сессии можно отозвать по одной через непрозрачный `session_ref`: перед запросом интеграция заново получает список, а после `logout_device` проверяет фактическое исчезновение. Массовый отзыв требует двух подтверждений в UI и серверной проверки точного `expected_count` по свежему snapshot. Возраст, title или платформа сами по себе никогда не являются причиной автоматического отзыва.\n",
)
replace_once(
    "README_RU.md",
    "- Firebase values, FCM credentials and the local Firebase config path are never included in diagnostics. Do not commit `firebase_config.json`.\n",
    "- Firebase values, FCM credentials and the local Firebase config path are never included in diagnostics. Do not commit `firebase_config.json`.\n"
    "- Управление авторизованными FCM-сессиями не показывает raw provider `device_id` в карточке или публичных ответах списка. Регистрации Home Assistant защищены от одиночного и массового отзыва; destructive-действия требуют явного подтверждения, а массовый отзыв дополнительно требует точного свежего количества доступных для отзыва сессий.\n",
)

# Changelog for the release being prepared.
replace_once(
    "CHANGELOG.md",
    "# Changelog\n\n## 0.29.0",
    """# Changelog\n\n## 0.30.0\n\n- Added a live-confirmed, privacy-safe authorized-device inventory based on `POST /api/v4/fcm_device/authorized_devices/`, including non-blocking verification that the Home Assistant FCM registration is present and has call access.\n- Added coarse FCM authorization diagnostics (`registered`, `call_access`, last-update age bucket and bounded error type) without exposing provider device IDs, titles, exact timestamps, FCM tokens or raw responses.\n- Live-confirmed `POST /api/v4/fcm_device/logout_device/` end-to-end against a disposable probe-owned registration: present before logout, absent after HTTP 200, then restored and visible again.\n- Added `list_fcm_sessions`, targeted `revoke_fcm_session` and guarded `revoke_other_fcm_sessions` Home Assistant response services. Public session rows use opaque entry-scoped `session_ref` values; raw provider `device_id` values stay internal.\n- Protected every locally provable Home Assistant-owned FCM registration for the same account from both targeted and bulk revocation. Ownership verification fails closed before destructive actions.\n- Added fresh-inventory resolution and post-revoke disappearance checks for targeted revocation; bulk revocation requires `confirm=true` plus an exact `expected_count` and aborts if the revocable inventory changed. No session is removed automatically by age, title or platform.\n- Added the **УСТРОЙСТВА** card tab with authorized-session summary, HA/MDI platform icons, last activity, call-access state, protected Home Assistant rows, explicit targeted revoke, and double-confirmed bulk revoke. Raw provider identifiers are never rendered.\n- Live-tested the production targeted-revoke path in Home Assistant using only a disposable probe registration, then verified that the protected Home Assistant registration remained present. The final card layout was also visually smoke-tested on a real Home Assistant dashboard.\n- Extended the standalone FCM research probe with privacy-safe authorized-device auditing and a controlled `--verify-logout-device` lifecycle check restricted to the probe-owned registration.\n- Updated EN/RU user, API, security and research documentation for the new FCM authorization/session-security model and bumped integration/card/cache-bust documentation to v0.30.0.\n- Added regression coverage for inventory privacy, stable opaque refs, HA ownership protection, fresh targeted revoke verification, bulk count-race protection and card privacy/safety wiring.\n\n## 0.29.0""",
)

# API reference indexes.
replace_once(
    "docs/api/README.md",
    "   - guest/shared-access management.\n",
    "   - guest/shared-access management;\n   - FCM registration and authorized-session security management.\n",
)
replace_once(
    "docs/api/README.md",
    "State-changing examples (door opening, guest creation/revocation) are intentionally kept on the relevant reference pages rather than in the copy/paste examples collection.",
    "State-changing examples (door opening, guest creation/revocation, FCM session logout) are intentionally kept on the relevant reference pages rather than in the copy/paste examples collection.",
)
replace_once(
    "docs/api/README_RU.md",
    "   - гостевой и совместный доступ.\n",
    "   - гостевой и совместный доступ;\n   - регистрация FCM и управление безопасностью авторизованных сессий.\n",
)
replace_once(
    "docs/api/README_RU.md",
    "Примеры операций, изменяющих состояние (открытие двери, создание/отзыв гостевого доступа), намеренно находятся только на соответствующих страницах reference, а не в каталоге copy/paste примеров.",
    "Примеры операций, изменяющих состояние (открытие двери, создание/отзыв гостевого доступа, завершение FCM-сессии), намеренно находятся только на соответствующих страницах reference, а не в каталоге copy/paste примеров.",
)

# Verification matrices: promote the two /api/v4/fcm_device contracts only after live tests.
replace_once(
    "docs/api/STATUS.md",
    '| FCM | `POST /api/v4/fcm_device/authorized_devices/` | **Observed** | Android client consumes device list / call-access metadata |\n| FCM | `POST /api/v4/fcm_device/logout_device/` | **Observed** | Android client sends `{device_id}` to revoke another device/session |',
    '| FCM | `POST /api/v4/fcm_device/authorized_devices/` | **Confirmed** | Live-tested no-body POST returns `data.device_list`; confirmed fields include `device_id`, `title`, `last_update`, `is_call_access`, plus server metadata `os`/`os_display`. `devices_num_permission` is live-observed; exact business semantics remain unconfirmed. |\n| FCM | `POST /api/v4/fcm_device/logout_device/` | **Confirmed** | Controlled probe-owned session was present before `{device_id}` logout, absent after HTTP 200, restored through `/api/v0/fcm/`, and present again; targeted production revoke was also live-tested in Home Assistant. |',
)
replace_once(
    "docs/api/STATUS_RU.md",
    '| FCM | `POST /api/v4/fcm_device/authorized_devices/` | **Observed** | Android-клиент получает список устройств и metadata доступа к звонкам |\n| FCM | `POST /api/v4/fcm_device/logout_device/` | **Observed** | Android-клиент отправляет `{device_id}` для отзыва другого устройства/сессии |',
    '| FCM | `POST /api/v4/fcm_device/authorized_devices/` | **Confirmed** | Live-проверенный POST без body возвращает `data.device_list`; подтверждены `device_id`, `title`, `last_update`, `is_call_access` и серверные metadata `os`/`os_display`. `devices_num_permission` наблюдается live, но его точная бизнес-семантика пока не подтверждена. |\n| FCM | `POST /api/v4/fcm_device/logout_device/` | **Confirmed** | Controlled probe-owned сессия была видна до logout `{device_id}`, исчезла после HTTP 200, восстановлена через `/api/v0/fcm/` и снова появилась; targeted production revoke также live-проверен в Home Assistant. |',
)

# Detailed FCM reference, English.
replace_once(
    "docs/api/fcm.md",
    "The Android client also contains `/api/v4/fcm_device/` device-management endpoints; these are not yet live-confirmed by this project.\n",
    '''## Authorized-device inventory\n\n**Confirmed**\n\n```http\nPOST /api/v4/fcm_device/authorized_devices/\nAuthorization: JWT <UFANET_ACCESS>\n```\n\nThe request has no body. The live-confirmed response contains `data.device_list`. The current Android DTO consumes `device_id`, nullable `title`, `last_update`, and `is_call_access`; the server also returned `os` and `os_display`, which the current Android DTO does not declare. A sanitized structural example is:\n\n```json\n{\n  "data": {\n    "device_list": [\n      {\n        "device_id": "<opaque-device-id>",\n        "title": "<device-title>",\n        "last_update": "<offset-aware ISO-8601>",\n        "is_call_access": true,\n        "os": 0,\n        "os_display": "Android"\n      }\n    ],\n    "devices_num_permission": false\n  }\n}\n```\n\nThe tested account returned unique `device_id` values and parseable timestamps. The live sample correlated opaque OS code `0` with normalized display `Android` for all returned rows, but this is only an observed correlation for that account and is not documented as a universal enum mapping. The Android response model names `devices_num_permission` as `isQuantityLimited`; the current active-devices screen does not use the flag, so its exact operational semantics remain unconfirmed.\n\nTreat this endpoint as an **authorized registration/session inventory**, not a guaranteed list of physical phones or distinct current raw FCM tokens. Re-registration/token refresh can update an existing installation-scoped `device_id`, and old authorized rows can remain for a long time.\n\n## Authorized-session logout\n\n**Confirmed**\n\n```http\nPOST /api/v4/fcm_device/logout_device/\nAuthorization: JWT <UFANET_ACCESS>\nContent-Type: application/json\n```\n\n```json\n{\n  "device_id": "<device-id>"\n}\n```\n\nThe official Android active-device UI uses this endpoint for one selected non-current device and implements "terminate all other sessions" by calling the same endpoint for each other row. On 2026-09-03 the project live-confirmed the destructive contract only against a disposable probe-owned virtual registration: the row was present before logout, the POST returned HTTP 200, the row disappeared from `authorized_devices`, and re-registering through `/api/v0/fcm/` restored it. No existing phone or Home Assistant registration was used for that provider-contract test.\n\nHome Assistant v0.30.0 exposes this capability through privacy/safety guards rather than raw provider IDs. `list_fcm_sessions` returns bounded user-facing metadata plus an opaque entry-scoped `session_ref`; HA-owned registrations proven from private local state are marked protected. `revoke_fcm_session` re-fetches the inventory, resolves exactly one non-protected ref, performs logout and verifies disappearance. `revoke_other_fcm_sessions` requires explicit confirmation plus an exact expected revocable count from a fresh snapshot and never removes sessions automatically by age/title/platform. The custom **УСТРОЙСТВА** tab uses the same services and never renders raw provider `device_id` values.\n''',
)

# Detailed FCM reference, Russian.
replace_once(
    "docs/api/fcm_RU.md",
    "Также в Android-клиенте наблюдаются endpoints управления авторизованными push-устройствами семейства `/api/v4/fcm_device/`; они ещё не являются live-confirmed частью проекта.\n",
    '''## Список авторизованных устройств/сессий\n\n**Confirmed**\n\n```http\nPOST /api/v4/fcm_device/authorized_devices/\nAuthorization: JWT <UFANET_ACCESS>\n```\n\nRequest body отсутствует. Live-confirmed ответ содержит `data.device_list`. Текущий Android DTO использует `device_id`, nullable `title`, `last_update` и `is_call_access`; сервер также вернул `os` и `os_display`, которых в текущем Android DTO нет. Обезличенный структурный пример:\n\n```json\n{\n  "data": {\n    "device_list": [\n      {\n        "device_id": "<opaque-device-id>",\n        "title": "<device-title>",\n        "last_update": "<offset-aware ISO-8601>",\n        "is_call_access": true,\n        "os": 0,\n        "os_display": "Android"\n      }\n    ],\n    "devices_num_permission": false\n  }\n}\n```\n\nНа проверенном аккаунте `device_id` были уникальны, а `last_update` корректно разбирались. В live-выборке непрозрачный код `os=0` коррелировал с нормализованным `Android` у всех возвращённых строк, но это только наблюдаемая корреляция на проверенном аккаунте, а не подтверждённая универсальная enum-таблица. Android response model называет `devices_num_permission` полем `isQuantityLimited`; текущий экран активных устройств этот флаг не использует, поэтому точная operational-семантика пока не подтверждена.\n\nEndpoint следует трактовать как **инвентарь авторизованных регистраций/сессий**, а не гарантированный список физических телефонов или уникальных текущих raw FCM tokens. Re-registration/token refresh может обновлять существующий installation-scoped `device_id`, а старые авторизованные строки могут сохраняться длительное время.\n\n## Завершение авторизованной сессии\n\n**Confirmed**\n\n```http\nPOST /api/v4/fcm_device/logout_device/\nAuthorization: JWT <UFANET_ACCESS>\nContent-Type: application/json\n```\n\n```json\n{\n  "device_id": "<device-id>"\n}\n```\n\nОфициальный Android UI активных устройств вызывает этот endpoint для выбранного не-текущего устройства, а действие «завершить все остальные сессии» реализует последовательными вызовами того же endpoint для остальных строк. 3 сентября 2026 года проект live-подтвердил destructive-контракт только на disposable probe-owned виртуальной регистрации: строка была видна до logout, POST вернул HTTP 200, строка исчезла из `authorized_devices`, а повторная регистрация через `/api/v0/fcm/` восстановила её. Ни существующий телефон, ни регистрация Home Assistant для provider-contract теста не использовались.\n\nHome Assistant v0.30.0 предоставляет эту возможность через privacy/safety guards вместо raw provider IDs. `list_fcm_sessions` возвращает ограниченную пользовательскую metadata и непрозрачный entry-scoped `session_ref`; регистрации HA, принадлежность которых доказана по приватному локальному state, помечаются protected. `revoke_fcm_session` заново получает inventory, однозначно разрешает один незащищённый ref, выполняет logout и проверяет исчезновение. `revoke_other_fcm_sessions` требует явного подтверждения и точного ожидаемого количества доступных для отзыва сессий по свежему snapshot и никогда не удаляет сессии автоматически по возрасту/title/platform. Карточка **УСТРОЙСТВА** использует те же сервисы и не рендерит raw provider `device_id`.\n''',
)

# API security references.
replace_once(
    "docs/api/security.md",
    "## Diagnostics and support bundles\n",
    '''## Authorized FCM sessions\n\nAuthorized-device inventory and logout are security-sensitive account operations. Raw provider FCM `device_id` values, FCM tokens and registration credentials should remain private even when a user is reviewing sessions. The Home Assistant integration exposes an opaque `session_ref` instead of the provider ID.\n\nA session must not be classified as safe/unsafe from title, platform or age alone. Home Assistant protects only registrations whose ownership can be proved from local private state; ownership verification fails closed before revocation. Targeted logout requires explicit confirmation and a fresh inventory lookup. Bulk logout additionally requires an exact expected revocable count from the fresh snapshot so a newly appeared session causes the operation to abort rather than being removed unexpectedly.\n\n## Diagnostics and support bundles\n''',
)
replace_once(
    "docs/api/security_RU.md",
    "## Диагностика и support bundles\n",
    '''## Авторизованные FCM-сессии\n\nИнвентарь авторизованных устройств и logout являются security-sensitive операциями аккаунта. Raw provider FCM `device_id`, FCM tokens и registration credentials должны оставаться приватными даже при просмотре списка пользователем. Интеграция Home Assistant выводит непрозрачный `session_ref` вместо provider ID.\n\nНельзя считать сессию безопасной/небезопасной только по title, платформе или возрасту. Home Assistant защищает только регистрации, принадлежность которых можно доказать из локального приватного state; если доказательство получить нельзя, отзыв блокируется fail-closed. Targeted logout требует явного подтверждения и свежего запроса inventory. Массовый logout дополнительно требует точного ожидаемого количества доступных для отзыва сессий по свежему snapshot: если появилась новая сессия, операция отменяется вместо неожиданного удаления.\n\n## Диагностика и support bundles\n''',
)

# Root security policy: user-facing guidance for the new security feature.
replace_once(
    "SECURITY.md",
    "Use GitHub Private Vulnerability Reporting for security-sensitive reports when enabled for this repository. If a credential, token or guest link is exposed, revoke or rotate it immediately.\n",
    "Use GitHub Private Vulnerability Reporting for security-sensitive reports when enabled for this repository. If a credential, token or guest link is exposed, revoke or rotate it immediately.\n\nAuthorized FCM session data is also sensitive. Do not publish raw provider device IDs, FCM tokens, registration credentials, or full private session inventories. Ufanet Intercom v0.30.0 uses opaque session references in Home Assistant, protects locally provable Home Assistant registrations from revocation, and requires explicit confirmation for destructive session logout.\n",
)

# Research guide: reflect that the contract is now production-backed, while keeping the probe bounded.
replace_once(
    "tools/research/fcm_probe_py/README_RU.md",
    "Этот флаг предназначен только для подтверждения server contract перед добавлением\nуправления чужими/неизвестными сеансами в production-интеграцию.\n",
    "Этот флаг остаётся ограниченным contract-test для probe-owned регистрации. Подтверждённый\n`logout_device` теперь используется в production-интеграции v0.30.0 через защищённые\n`list_fcm_sessions` / `revoke_fcm_session` / `revoke_other_fcm_sessions`; probe по-прежнему\nне принимает произвольный чужой `device_id` и не выбирает существующие телефоны.\n",
)
replace_once(
    "tools/research/fcm_probe_py/README_RU.md",
    "`os_display`. Числовая семантика `os` пока не считается подтверждённой: probe\nвыводит его только как ограниченный непрозрачный код `0..255`. `os_display`\nсводится к фиксированным категориям `android`, `ios`, `harmonyos`, `other`.\nИсходная строка `os_display` не печатается; допустимы только агрегированные\nсчётчики и корреляция `код -> категория`. `devices_num_permission` также\nнаблюдается live, но его точная бизнес-семантика пока не утверждается.\n",
    "`os_display`. Числовая семантика `os` пока не считается подтверждённой: probe\nвыводит его только как ограниченный непрозрачный код `0..255`. `os_display`\nсводится к фиксированным категориям `android`, `ios`, `harmonyos`, `other`.\nИсходная строка `os_display` не печатается; допустимы только агрегированные\nсчётчики и корреляция `код -> категория`. `devices_num_permission` также\nнаблюдается live, но его точная бизнес-семантика пока не утверждается. Финальная\nlive-проверка подтвердила наблюдаемую корреляцию `0 -> android` для всех строк\nпроверенного ответа, однако это не считается универсальной enum-таблицей. Наличие\nдавно не обновлявшейся авторизованной строки также показывает, что inventory нельзя\nприравнивать к списку устройств, активных прямо сейчас.\n",
)
replace_once(
    "tools/research/fcm_probe_py/README_RU.md",
    "7. Подключается к MCS `mtalk.google.com:5228`.\n7. Получает и санитизирует push.\n8. Для `reason=sip` автоматически проверяет `/api/v1/skuds/call-history/` на offsets `0, 0.25, 0.5, 1, 2, 5` секунд.\n9. Коррелирует запись по `called_at` относительно push `time` с дополнительной проверкой house/flat context.\n10. Печатает задержку появления history record и накопительную статистику.",
    "7. Подключается к MCS `mtalk.google.com:5228`.\n8. Получает и санитизирует push.\n9. Для `reason=sip` автоматически проверяет `/api/v1/skuds/call-history/` на offsets `0, 0.25, 0.5, 1, 2, 5` секунд.\n10. Коррелирует запись по `called_at` относительно push `time` с дополнительной проверкой house/flat context.\n11. Печатает задержку появления history record и накопительную статистику.",
)

print("v0.30.0 release-prep patch applied")
