from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace(path: str, old: str, new: str, *, required: bool = True) -> None:
    text = read(path)
    if old not in text:
        if required:
            raise SystemExit(f"expected text not found in {path}: {old[:140]!r}")
        return
    write(path, text.replace(old, new))


def replace_regex(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, flags=re.S)
    if count != 1:
        raise SystemExit(f"expected one regex match in {path}, got {count}: {pattern}")
    write(path, updated)


# Root README: current release status and shipped physical-key semantics.
replace_regex(
    "README.md",
    r"## Current validation / 0\.31\.0 release candidate\n.*?\n## Unofficial API documentation",
    """## Current release: v0.31.0

Version **v0.31.0** was published on 2026-09-09 after the release candidate was merged and the final release state passed Tests, HACS/Hassfest and the repository release self-check. The `v0.31.0` tag points to that published `main` state.

Live-confirmed release evidence includes:

- Android actionable incoming-call notifications from real Ufanet calls;
- guarded **Open door** physically opening the configured door and **View camera** opening the selected same-device camera;
- timeout, post-open replacement and second-call supersession without stale door actions;
- privacy-safe authorized-device management and the separately warned advanced FCM unregister path, including target refresh-chain behavior;
- physical-key capability, non-empty inventory, selected-key passage history and backend-verified rename;
- end-to-end enrollment of a genuinely unregistered physical key during the real 60-second `auto_collect/enable` window;
- real headless-FCM `reason=key_add` completion with the tested success rule (`key_status == 0` plus a parseable `key_id`), followed by healthy registered-key inventory;
- a separate no-key 60-second timeout in which no additional `reason=key_add` completion push was observed;
- repeated Lovelace reload/switch tests without reproducing the former **Configuration error**.

There are no remaining hard functional blockers under the published 0.31.0 scope. iOS actionable-notification delivery is not live-tested and is not claimed as Confirmed; physical-key deletion is deliberately unimplemented/out of scope; provider-specific enrollment failure payloads that were not observed are not inferred. Sanitized enrollment evidence is in `docs/api/key_enrollment_live_2026-09-09.md`; the former pre-release audit is retained as a historical snapshot in `docs/releases/0.31.0-pre-release-audit.md`.

## Unofficial API documentation""",
)
replace("README.md", "Add the main resource as a JavaScript module. On this 0.31.0 RC branch the matching cache-bust URL is:", "Add the main resource as a JavaScript module. For v0.31.0 the matching cache-bust URL is:")
replace("README.md", "The `?v=` value must match the installed integration/card version. The currently published release remains v0.30.0 until separate merge/tag/GitHub Release approval.", "The `?v=` value must match the installed integration/card version.")
replace("README.md", "The validation card contains six tabs:", "The card contains six tabs:")
replace("README.md", "The KEYS tab and the validation authorized-device behavior are provided by packaged frontend extensions.", "The KEYS tab and the authorized-device behavior are provided by packaged frontend extensions.")
replace("README.md", "complete current release-validation action lifecycle", "complete v0.31.0 validation action lifecycle")
replace("README.md", "- **Physical keys** — numeric count; the validation branch also exposes read-only `keys` rows containing only `name` and UTC `created_at`;", "- **Physical keys** — numeric count plus read-only `keys` rows containing only `name` and UTC `created_at`;")
replace("README.md", "The validation branch also adds **Add physical key** (`mdi:key-plus`) only for supported intercoms. It mirrors the Android-observed 60-second `auto_collect/enable` flow. A successful button request means only that enrollment mode was armed; the new key still has to be presented to the reader within 60 seconds. The real new-key side effect remains pending live validation.", "The integration exposes **Add physical key** (`mdi:key-plus`) only for supported intercoms. It mirrors the Android-observed 60-second `auto_collect/enable` flow. A successful button request means only that enrollment mode was armed; the new key still has to be presented to the reader within 60 seconds. End-to-end live testing confirmed that a genuinely unregistered key can then be registered successfully through this flow.")
replace("README.md", "The FCM listener recognizes the Android-observed `reason=key_add` completion path. It refreshes the key inventory immediately and emits the account-level, privacy-minimized `ufanet_intercom_key_enrollment` event. Private provider identifiers, raw message text and push payload are not published. The real `key_add` path remains **Observed/pending live validation**.", "The FCM listener recognizes `reason=key_add`, refreshes the key inventory immediately and emits the account-level, privacy-minimized `ufanet_intercom_key_enrollment` event. The tested success path is **Confirmed** by a real new-key enrollment and headless-FCM completion. Private provider identifiers, raw message text and push payload are not published; unobserved provider-specific error payloads are not inferred.")

# Russian README equivalent.
replace_regex(
    "README_RU.md",
    r"## Текущая validation-разработка / release candidate 0\.31\.0\n.*?\n## Неофициальная документация API",
    """## Текущий релиз: v0.31.0

Версия **v0.31.0** опубликована 9 сентября 2026 года после merge release candidate и успешных Tests, HACS/Hassfest и repository release self-check на финальном release state. Тег `v0.31.0` указывает на это опубликованное состояние `main`.

Для релиза live-подтверждены:

- Android actionable notifications на реальных звонках Ufanet;
- защищённое **«Открыть дверь»** с фактическим открытием настроенной двери и **«Открыть камеру»** для выбранной same-device камеры;
- timeout, post-open replacement и supersession вторым звонком без устаревших door actions;
- privacy-safe управление авторизованными устройствами и отдельно предупреждённый advanced FCM unregister, включая проверенное влияние на refresh-chain target;
- capability, непустой inventory, selected-key история и backend-verified rename физических ключей;
- end-to-end регистрация действительно нового физического ключа в реальном 60-секундном окне `auto_collect/enable`;
- настоящий headless-FCM `reason=key_add` с подтверждённым success rule (`key_status == 0` и parseable `key_id`) и последующим корректным inventory;
- отдельный 60-секундный no-key timeout без дополнительного `reason=key_add` completion push;
- повторные Lovelace reload/switch проверки без воспроизведения прежней **Configuration error**.

В опубликованном scope 0.31.0 не осталось hard functional blockers. iOS actionable-notification delivery не проверялся live и не заявляется Confirmed; удаление физического ключа намеренно не реализовано и остаётся вне scope; не наблюдавшиеся provider-specific enrollment error payloads не додумываются. Обезличенное подтверждение enrollment находится в `docs/api/key_enrollment_live_2026-09-09.md`; прежний pre-release audit сохранён как исторический snapshot в `docs/releases/0.31.0-pre-release-audit.md`.

## Неофициальная документация API""",
)
replace("README_RU.md", "Добавьте основной ресурс как JavaScript module. На текущей RC-ветке 0.31.0 правильный cache-bust URL:", "Добавьте основной ресурс как JavaScript module. Для v0.31.0 правильный cache-bust URL:")
replace("README_RU.md", "`?v=` должен совпадать с реально установленной версией интеграции/карточки. Текущий опубликованный релиз остаётся v0.30.0 до отдельного разрешения на merge/tag/GitHub Release.", "`?v=` должен совпадать с реально установленной версией интеграции/карточки.")
replace("README_RU.md", "В validation-ветке карточка содержит шесть вкладок:", "Карточка содержит шесть вкладок:")
replace("README_RU.md", "Вкладка **КЛЮЧИ** и validation-логика управления устройствами реализованы packaged frontend extensions.", "Вкладка **КЛЮЧИ** и логика управления устройствами реализованы packaged frontend extensions.")
replace("README_RU.md", "полном текущем release-validation action lifecycle", "полном validation lifecycle v0.31.0")
replace("README_RU.md", "- **«Физические ключи»** — числовое количество; validation-ветка также публикует read-only `keys` только с `name` и UTC `created_at`;", "- **«Физические ключи»** — числовое количество и read-only `keys` только с `name` и UTC `created_at`;")
replace("README_RU.md", "Validation-ветка добавляет **«Добавить физический ключ»** (`mdi:key-plus`) только для поддерживаемых домофонов. Кнопка повторяет Android-observed 60-секундный `auto_collect/enable` flow. Успешный HTTP означает только включение enrollment mode; новый ключ нужно физически приложить к считывателю в течение 60 секунд. Реальный new-key side effect пока ожидает live-проверки.", "Интеграция предоставляет **«Добавить физический ключ»** (`mdi:key-plus`) только для поддерживаемых домофонов. Кнопка повторяет Android-observed 60-секундный `auto_collect/enable` flow. Успешный HTTP означает только включение enrollment mode; новый ключ нужно физически приложить к считывателю в течение 60 секунд. End-to-end live-тест подтвердил успешную регистрацию действительно нового ключа через этот flow.")
replace("README_RU.md", "FCM listener распознаёт Android-observed completion `reason=key_add`, немедленно обновляет key inventory и отправляет account-level privacy-minimized событие `ufanet_intercom_key_enrollment`. Private provider identifiers, raw message text и push payload не публикуются. Реальный `key_add` остаётся **Observed / pending live validation**.", "FCM listener распознаёт `reason=key_add`, немедленно обновляет key inventory и отправляет account-level privacy-minimized событие `ufanet_intercom_key_enrollment`. Проверенный success path имеет статус **Confirmed** после реальной регистрации нового ключа и headless-FCM completion. Private provider identifiers, raw message text и push payload не публикуются; не наблюдавшиеся provider-specific error payloads не додумываются.")

# Publishing guide: turn 0.31.0 RC state into a published baseline while keeping the evergreen approval policy.
replace("PUBLISHING.md", "This broader check is important for 0.31.0: validation introduced packaged KEYS/history and authorized-device extensions, so a stale extension cache-bust must fail release preparation rather than silently shipping an older browser resource.", "This broader check was introduced for 0.31.0 because that release added packaged KEYS/history and authorized-device extensions; a stale extension cache-bust must fail release preparation rather than silently shipping an older browser resource.")
replace_regex(
    "PUBLISHING.md",
    r"## Current 0\.31\.0 preparation state\n.*?\n## Live-validation gate",
    """## Published 0.31.0 baseline

Version **v0.31.0** was published on 2026-09-09 after the release candidate passed the required live-validation gates, privacy/documentation review and exact-head CI. The published scope includes actionable Android call notifications, authorized-device/advanced-FCM management, physical-key inventory/history/rename, and live-confirmed physical-key enrollment with real `reason=key_add` completion.

The release retained the documented boundaries: iOS actionable notification delivery is not claimed as live-confirmed; physical-key deletion is outside the 0.31.0 scope; unobserved provider-specific enrollment failure payloads are not inferred. Existing release tags remain immutable.

This baseline is historical context only. Future releases must repeat the same evidence, version-synchronization and explicit-approval process for their own target version and exact release SHA.

## Live-validation gate""",
)
replace("PUBLISHING.md", "The planned next minor version is **0.31.0**, subject to final confirmation at release time. Use a SemVer tag matching `manifest.json`, for example `v0.31.0`, and publish a GitHub Release rather than only creating a tag. An Unreleased planning heading or draft release notes are not authorization to publish.", "For every release, use a SemVer tag matching `manifest.json` (for example `v0.31.1` for a future patch release) and publish a GitHub Release rather than only creating a tag. The current published baseline is **v0.31.0**. An Unreleased planning heading or draft release notes are not authorization to publish.")

# Changelog should describe what actually shipped.
replace("CHANGELOG.md", "- Added validation-only `list_physical_keys` and `rename_physical_key` response services.", "- Added `list_physical_keys` and `rename_physical_key` response services.")
replace("CHANGELOG.md", "- Added a validation-only **КЛЮЧИ / KEYS** Lovelace tab as separate packaged frontend extensions.", "- Added a **КЛЮЧИ / KEYS** Lovelace tab as separate packaged frontend extensions.")

# API overview pages.
for path in ("docs/api/README.md", "docs/api/README_RU.md"):
    text = read(path)
    text = text.replace("validation-only enrollment/real FCM completion", "live-confirmed enrollment/real FCM completion")
    text = text.replace("validation-only enrollment/real FCM completion remains the release gate", "live-confirmed enrollment/real FCM completion")
    text = text.replace("enrollment/real `reason=key_add` and delete remain unconfirmed or out of scope", "enrollment/real `reason=key_add` is live-confirmed for the tested success path, while delete remains unimplemented/out of scope")
    text = text.replace("Observed `reason=key_add` as physical-key enrollment completion", "Confirmed `reason=key_add` for the tested physical-key enrollment success path")
    write(path, text)

# Detailed FCM references: key_add success path is Confirmed; unknown error variants remain uncharacterized.
replace("docs/api/fcm.md", "The official Android client also contains a physical-key enrollment completion path using `data.reason=key_add`, `key_status`, and `key_id`. That payload contract is currently **Observed** from client code and remains a hard live-validation gate until a new unregistered physical key can be enrolled end to end.", "The official Android client also contains a physical-key enrollment completion path using `data.reason=key_add`, `key_status`, and `key_id`. On 2026-09-09 that success path was exercised end to end with a genuinely unregistered key and a real headless-FCM completion, so `reason=key_add` is **Confirmed for the tested success path**.")
replace("docs/api/fcm.md", "The current validation branch additionally recognizes `data.reason=key_add`.", "The current integration recognizes `data.reason=key_add`.")
replace("docs/api/fcm.md", "The validation branch separates normal device authorization from advanced FCM cleanup:", "The current integration separates normal device authorization from advanced FCM cleanup:")
replace("docs/api/fcm.md", "**Observed in the Android client; live validation pending**", "**Confirmed for the tested success path**")
replace("docs/api/fcm.md", "The validation branch handles this message without exposing provider identifiers:", "The integration handles this message without exposing provider identifiers:")
replace_regex(
    "docs/api/fcm.md",
    r"## Required key-add live validation\n.*?\n## Security",
    """## Physical-key completion live validation

On 2026-09-09 the physical-key completion path was confirmed end to end:

1. Home Assistant armed the real 60-second enrollment window through `auto_collect/enable`;
2. a genuinely unregistered key was presented and registered;
3. the active headless listener received real `reason=key_add` completion pushes;
4. the tested success matched `key_status == 0` plus a parseable `key_id`;
5. the immediate key-inventory refresh remained healthy and the registered key was present.

A separate no-key test allowed the complete 60-second window to expire and produced no additional `reason=key_add` completion push. No HTTP 400, `key_status != 0`, or separate FCM error completion was observed in that case, so those provider-specific error semantics remain uncharacterized rather than inferred.

Sanitized evidence is recorded in `key_enrollment_live_2026-09-09.md`.

## Security""",
)

replace("docs/api/fcm_RU.md", "Официальный Android-клиент также содержит completion flow регистрации физического ключа с `data.reason=key_add`, `key_status` и `key_id`. Этот контракт пока имеет статус **Observed** по коду клиента и остаётся обязательным live-gate до end-to-end регистрации нового незарегистрированного ключа.", "Официальный Android-клиент также содержит completion flow регистрации физического ключа с `data.reason=key_add`, `key_status` и `key_id`. 9 сентября 2026 года этот success path был проверен end-to-end с действительно новым ключом и реальным headless-FCM completion, поэтому `reason=key_add` имеет статус **Confirmed для проверенного success path**.")
replace("docs/api/fcm_RU.md", "Текущая validation-ветка дополнительно распознаёт `data.reason=key_add`.", "Текущая интеграция распознаёт `data.reason=key_add`.")
replace("docs/api/fcm_RU.md", "Validation-ветка разделяет обычный отзыв авторизации и advanced FCM cleanup:", "Текущая интеграция разделяет обычный отзыв авторизации и advanced FCM cleanup:")
replace("docs/api/fcm_RU.md", "**Observed в Android-клиенте; live-проверка ожидается**", "**Confirmed для проверенного success path**")
replace("docs/api/fcm_RU.md", "Validation-ветка обрабатывает сообщение без provider identifiers:", "Интеграция обрабатывает сообщение без provider identifiers:")
replace_regex(
    "docs/api/fcm_RU.md",
    r"## Обязательная live-проверка `key_add`\n.*?\n## Безопасность",
    """## Live-проверка completion физического ключа

9 сентября 2026 года physical-key completion path подтверждён end-to-end:

1. Home Assistant включил реальное 60-секундное окно enrollment через `auto_collect/enable`;
2. действительно новый ключ был приложен и зарегистрирован;
3. активный headless listener получил настоящие `reason=key_add` completion pushes;
4. проверенный success соответствовал `key_status == 0` и parseable `key_id`;
5. немедленный refresh key inventory остался healthy, зарегистрированный ключ присутствовал.

В отдельном no-key тесте полное 60-секундное окно истекло без дополнительного `reason=key_add` completion push. HTTP 400, `key_status != 0` и отдельный FCM error completion в этом случае не наблюдались, поэтому provider-specific error semantics остаются нехарактеризованными и не додумываются.

Обезличенное подтверждение находится в `key_enrollment_live_2026-09-09.md`.

## Безопасность""",
)

# Notifications no longer carry an overall release blocker.
replace("docs/notifications.md", "## Live validation on the combined validation branch", "## Live validation for v0.31.0")
replace("docs/notifications.md", "The overall 0.31.0 validation branch is still **not release-ready** because the new physical-key enrollment / real `reason=key_add` flow remains pending.", "This notification path shipped in v0.31.0. The former physical-key enrollment / real `reason=key_add` release gate was closed by end-to-end live validation before publication.")
replace("docs/notifications_RU.md", "## Live-проверка validation-ветки", "## Live-проверка для v0.31.0")
replace("docs/notifications_RU.md", "Вся ветка 0.31.0 всё ещё **не готова к релизу**, потому что остаётся live-validation нового физического ключа: `auto_collect/enable` → новый незарегистрированный ключ → настоящий `reason=key_add` → inventory/event/error semantics.", "Этот notification path опубликован в v0.31.0. Бывший release gate физического ключа (`auto_collect/enable` → новый ключ → настоящий `reason=key_add`) был закрыт end-to-end live-проверкой до публикации.")

# Current API pages: remove branch-era labels while preserving historical evidence files separately.
for path in (
    "docs/api/analytics.md", "docs/api/archive.md", "docs/api/auth.md", "docs/api/calls.md",
    "docs/api/guests.md", "docs/api/intercom.md", "docs/api/keys.md", "docs/api/security.md", "docs/api/ucams.md",
):
    text = read(path)
    for old, new in (
        ("The current combined notification/physical-key validation branch", "The v0.31.0 release"),
        ("The combined notification/physical-key validation branch", "The v0.31.0 release"),
        ("The combined validation branch", "The v0.31.0 release"),
        ("the combined validation branch", "the v0.31.0 release"),
        ("The validation branch", "The current integration"),
        ("the validation branch", "the current integration"),
        ("validation-branch", "v0.31.0"),
    ):
        text = text.replace(old, new)
    write(path, text)

for path in (
    "docs/api/analytics_RU.md", "docs/api/archive_RU.md", "docs/api/auth_RU.md", "docs/api/calls_RU.md",
    "docs/api/guests_RU.md", "docs/api/intercom_RU.md", "docs/api/keys_RU.md", "docs/api/security_RU.md", "docs/api/ucams_RU.md",
):
    text = read(path)
    for old, new in (
        ("Текущая combined validation-ветка уведомлений/физических ключей", "Релиз v0.31.0"),
        ("Combined validation-ветка уведомлений/физических ключей", "Релиз v0.31.0"),
        ("Combined validation-ветка", "Релиз v0.31.0"),
        ("Validation-ветка", "Текущая интеграция"),
        ("validation-ветка", "текущая интеграция"),
    ):
        text = text.replace(old, new)
    write(path, text)

replace("docs/api/keys.md", "the previously experimental public `number` field was removed from the current integration rather than shipping a misleading interpretation.", "the previously experimental public `number` field was removed before v0.31.0 publication rather than shipping a misleading interpretation.", required=False)
replace("docs/api/keys.md", "## Home Assistant model on the current integration", "## Home Assistant model", required=False)
replace("docs/api/models.md", "Validation management surfaces expose a local opaque `key_ref` rather than any provider identifier.", "Home Assistant management surfaces expose a local opaque `key_ref` rather than any provider identifier.", required=False)
replace("docs/api/models_RU.md", "Validation management surfaces", "Home Assistant management surfaces", required=False)
replace("docs/api/key_enrollment_live_2026-09-09.md", "implemented on the 0.31.0 validation branch", "implemented for v0.31.0 before publication")

# Research guide: update the result that is no longer pending.
replace("tools/research/FCM_HEADLESS_RU.md", "Текущая combined validation-ветка дополнительно распознаёт Android-observed `reason=key_add`, немедленно refresh physical-key inventory и создаёт privacy-minimized `ufanet_intercom_key_enrollment`. Сам реальный `key_add` от нового незарегистрированного ключа ещё не live-подтверждён и остаётся hard validation gate; provider `key_id`, title/body и raw push наружу не публикуются.", "Текущая интеграция распознаёт `reason=key_add`, немедленно refresh physical-key inventory и создаёт privacy-minimized `ufanet_intercom_key_enrollment`. 9 сентября 2026 года реальный `key_add` от действительно нового ключа был live-подтверждён через headless FCM; provider `key_id`, title/body и raw push наружу по-прежнему не публикуются. Отдельный no-key timeout не дал completion push, поэтому не наблюдавшиеся provider-specific error semantics не додумываются.")

# Preserve pre-release documents as explicitly historical snapshots instead of deleting useful evidence.
replace("docs/releases/0.31.0-draft.md", "# Ufanet Intercom 0.31.0 — draft release notes", "# Ufanet Intercom 0.31.0 — historical draft release notes")
replace("docs/releases/0.31.0-draft.md", "> **DRAFT / NOT FOR PUBLICATION YET.** This document prepares the future release text for the 0.31.0 RC. It does not authorize merge, tag or GitHub Release. PR #15 remains the authoritative release review.", "> **Historical pre-release draft.** v0.31.0 was subsequently merged, tagged and published on 2026-09-09. This file is retained as release-preparation history; current release status is defined by `CHANGELOG.md` and the published GitHub Release.")
replace("docs/releases/0.31.0-draft.md", "The validation branch now separates", "v0.31.0 separates")
replace("docs/releases/0.31.0-draft.md", "For intercoms advertising physical-key recording support, the validation branch adds:", "For intercoms advertising physical-key recording support, v0.31.0 adds:")
replace("docs/releases/0.31.0-draft.md", "- validation-only **Add physical key** and **Rename** workflows;", "- **Add physical key** and **Rename** workflows;")
replace("docs/releases/0.31.0-draft.md", "The validation service therefore issues", "The integration service therefore issues")
replace_regex(
    "docs/releases/0.31.0-draft.md",
    r"## Still required before publication\n.*\Z",
    """## Publication outcome

The release-preparation gates described in this historical draft were completed. PR #15 was merged, the final documentation state was validated, and **v0.31.0** was published on 2026-09-09 as a normal non-prerelease GitHub Release.

The published tag points to the final v0.31.0 `main` commit. Tests, HACS/Hassfest and Release self-check all succeeded on that final release state before publication.

The documented scope boundaries remain unchanged: iOS actionable-notification delivery is not claimed as live-confirmed; physical-key deletion is unimplemented/out of scope; unobserved provider-specific enrollment failure payloads are not inferred.
""",
)

replace("docs/releases/0.31.0-pre-release-audit.md", "> **Validation document only.** This audit does not authorize a version bump, merge, tag, GitHub Release, or publication. Explicit user approval remains required for each release action.", "> **Historical pre-release snapshot.** At the time of this audit, separate approval was still required for merge/tag/publication. Those approvals were subsequently given and v0.31.0 was published on 2026-09-09. The evidence below is retained as the pre-release record.")
replace("docs/releases/0.31.0-pre-release-audit.md", "The currently published release remains v0.30.0 until separate merge/tag/GitHub Release approval. `release_check.py` enforces the synchronized RC values, parses every packaged frontend JavaScript file, and validates frontend response-service references.", "At the time of this audit, the published release was still v0.30.0 pending merge/tag/GitHub Release approval. v0.31.0 was subsequently published after those approvals. `release_check.py` enforces synchronized release values, parses every packaged frontend JavaScript file, and validates frontend response-service references.")
replace("docs/releases/0.31.0-pre-release-audit.md", "The validation branch packages the base card plus extensions for physical keys, key history, and authorized-device/advanced-FCM management.", "v0.31.0 packages the base card plus extensions for physical keys, key history, and authorized-device/advanced-FCM management.")
replace_regex(
    "docs/releases/0.31.0-pre-release-audit.md",
    r"## Release-candidate procedure\n.*\Z",
    """## Publication outcome

The release-candidate procedure recorded above was completed after this audit:

1. the release candidate was merged through PR #15;
2. the final documentation state was synchronized on `main`;
3. Tests, HACS/Hassfest and Release self-check succeeded on the final release state;
4. explicit merge/tag/GitHub Release approval was received;
5. tag **v0.31.0** and the normal GitHub Release were published on 2026-09-09.

Existing release tags remain immutable and must not be moved.
""",
)

# The final audit commit must not carry one-shot tooling.
for path in (
    ".github/workflows/post-release-audit-v0310.yml",
    ".github/workflows/post-release-doc-fix-v0310.yml",
    "scripts/post_release_doc_sync_v0310.py",
):
    target = ROOT / path
    if target.exists():
        target.unlink()
