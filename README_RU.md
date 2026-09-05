# Ufanet Intercom для Home Assistant

[English](README.md) | **Русский**

Пользовательская интеграция Home Assistant для домофонов Ufanet / «Умный дом», использующая облачные API официального мобильного приложения.

> Это независимая интеграция сообщества. Она не связана с Ufanet и не поддерживается компанией Ufanet.

## Возможности

- Настройка через интерфейс Home Assistant с использованием договора/логина Ufanet и пароля.
- Открытие двери через сущности Home Assistant `button`.
- LIVE-видео с камеры UCAMS и снимки.
- Просмотр видеоархива с диапазонами записи, масштабированием/перемещением таймлайна, метками звонков и read-only метками движения.
- История звонков, `ufanet_intercom_call`, нативные сущности **«Входящий звонок»** / **«Снимок последнего звонка»**, doorbell EventEntity и device trigger.
- Blueprint уведомлений Companion App: мгновенный текстовый push, приватное обновление картинкой Home Assistant, опциональная защищённая кнопка **«Открыть дверь»** и прямой переход **«Открыть камеру»**.
- Физические ключи для поддерживаемых домофонов: read-only счётчик/inventory, время последнего прохода, EventEntity/device trigger, validation-only **«Добавить физический ключ»** и privacy-safe сервисы списка/переименования через opaque `key_ref`.
- Read-only UCAMS `motion_alarm`: EventEntity **«Обнаружено движение»**, `ufanet_intercom_motion`, device trigger и метки на таймлайне архива.
- Выбор получения звонков: polling по умолчанию либо экспериментальный FCM с малой задержкой и резервным опросом.
- Privacy-safe инвентарь авторизованных Ufanet/FCM-сессий и защищённый явный отзыв сессий.
- Временные гостевые ключи и управление принятым совместным доступом.
- Ручной экспорт архива в MP4 через `ffmpeg -c copy` в Home Assistant Media.
- Постоянная медиатека экспортов с ограничением срока хранения и общего объёма.
- Опциональное автоматическое сохранение MP4 вокруг новых звонков.
- Options Flow и диагностика Home Assistant с учётом конфиденциальности.
- Единая Lovelace-карточка: `custom:ufanet-intercom-card`.

## Текущая validation-разработка

Ветка `codex/combined-validation` содержит ещё не выпущенные изменения уведомлений
и регистрации/управления физическими ключами. Она намеренно остаётся **validation-only** и не
должна тегироваться/публиковаться, пока не завершены live-gates в активном PR.
Версия установленной интеграции поэтому остаётся `0.30.0` до отдельного этапа
подготовки релиза.

Уже live-проверено на тестовой установке Home Assistant:

- Android actionable notification;
- реальный звонок Ufanet с push;
- action **«Открыть дверь»** физически открыл настроенную дверь;
- **«Открыть камеру»** открыл More Info выбранной live-камеры;
- timeout обновил существующее уведомление на месте и удалил устаревшую кнопку открытия;
- combined-сборка с уведомлениями и physical-key функциями загрузилась без замеченных регрессий;
- capability/coordinator физических ключей и пустой read-only inventory (`state=0`, `keys=[]`).

До релиза обязательны оставшиеся real-call проверки гонок/несовпадений/metadata и
полная регистрация **нового физического ключа**, включая реальный `reason=key_add`,
непустую запись inventory, privacy-safe `list_physical_keys` и реальное
переименование через validation-only `rename_physical_key`. Подробности:
[уведомления Home Assistant](docs/notifications_RU.md) и
[физические ключи/проходы](docs/api/keys_RU.md).

## Неофициальная документация API

В репозитории ведётся reverse-engineered документация интерфейсов Ufanet/UCAMS:

- [Документация API](docs/api/README_RU.md)
- [Матрица проверки API](docs/api/STATUS_RU.md)
- [Физические ключи и журнал проходов](docs/api/keys_RU.md)
- [FCM / push-уведомления](docs/api/fcm_RU.md)
- [Безопасность](docs/api/security_RU.md)
- [Примеры curl](docs/api/examples/curl.md)
- [Read-only пример на Python](docs/api/examples/python.md)

Документация явно разделяет **Confirmed**, **Observed**, **Inferred** и
**Not supported**. State-changing поведение не переводится в Confirmed только по
декомпилированному коду клиента.

## Требования

- Home Assistant **2026.8.0 или новее**.
- Сетевой доступ к `dom.ufanet.ru`, `cloud.ucams.ru` и медиасерверам UCAMS, возвращаемым API.
- Для экспериментального FCM — исходящий HTTPS к endpoint Firebase/GCM и TLS к `mtalk.google.com:5228`.
- Для MP4-экспорта и JPEG последнего звонка — доступный `ffmpeg` в runtime Home Assistant.
- Учётная запись/договор Ufanet с уже имеющимся доступом к домофону в официальном приложении.

## Установка

### Вручную

1. Скопируйте `custom_components/ufanet_intercom` в `config/custom_components/ufanet_intercom`.
2. Перезапустите Home Assistant.
3. Откройте **Настройки → Устройства и службы → Добавить интеграцию**.
4. Найдите **Ufanet Intercom** и укажите тот же договор/логин и пароль, что используются в официальном приложении.

### Через HACS как пользовательский репозиторий

1. HACS → **Custom repositories / Пользовательские репозитории**.
2. Добавьте этот GitHub-репозиторий с категорией **Integration**.
3. Установите **Ufanet Intercom**.
4. Перезапустите Home Assistant и добавьте интеграцию через **Настройки → Устройства и службы**.

## Lovelace-карточка

Текущий опубликованный релиз — v0.30.0, поэтому его cache-bust URL:

```text
/ufanet_intercom/ufanet-archive-card.js?v=0.30.0
```

`?v=` должен совпадать с реально установленным релизом. На validation-ветках это
значение не меняется до фактического bump версии интеграции/карточки при подготовке
релиза.

Минимальная конфигурация:

```yaml
type: custom:ufanet-intercom-card
entity: camera.YOUR_UFANET_CAMERA
default_tab: live
```

Карточка содержит пять вкладок:

- **LIVE** — видео, управление дверью, последний звонок и переход к записи звонка.
- **АРХИВ** — таймлайн, метки звонков/движения, экспорт MP4 и медиатека экспортов.
- **ГОСТИ** — приглашения, принятый shared access, временные ключи и отзыв.
- **УСТРОЙСТВА** — авторизованные Ufanet-сессии, защита регистраций Home Assistant, точечный и защищённый массовый отзыв.
- **ДИАГНОСТИКА** — token-free runtime health, polling, FCM authorization, UCAMS/archive и autosave.

## Настройки

Откройте **Настройки → Устройства и службы → Ufanet Intercom → Настроить**.

Основные параметры: режим получения звонков, polling interval, сколько секунд брать
до звонка, длительность/шаг архива, ограничения хранения MP4 и автоматическое
сохранение видео звонков. YAML конкретной карточки остаётся локальным override там,
где это поддерживается.

### Режимы получения звонков

- **`polling` (по умолчанию)** читает `call-history` с выбранным интервалом и не требует дополнительной настройки.
- **`fcm` (экспериментально)** использует локальный headless FCM receiver как low-latency сигнал. `call-history` остаётся authoritative. До подтверждения MCS работает обычный polling; при исправном FCM сохраняется контрольный опрос раз в 300 секунд, а при разрыве нормальный polling восстанавливается автоматически.

FCM watchdog отличает запуск задачи от установленного транспорта, позволяет библиотеке
обрабатывать короткие reconnect и пересоздаёт окончательно остановленный/зависший
listener с backoff. Repairs покрывает длительный сбой listener, восстановление
повреждённого private state и отложенную очистку регистрации без публикации
credentials/push payload.

FCM-значения не распространяются в репозитории. Продвинутый пользователь извлекает
их локально из своей декомпилированной копии официального Android-приложения:

```bash
python tools/research/fcm_probe_py/extract_firebase_config.py /путь/к/decompiled-app -o firebase_config.json
```

Скопируйте результат в `/config/ufanet_intercom/firebase_config.json`, выберите
`fcm` и оставьте относительный путь `ufanet_intercom/firebase_config.json`.
Интеграция читает JSON, но не копирует Firebase values в ConfigEntry/diagnostics.
Подробности: [FCM API](docs/api/fcm_RU.md).

## Автоматизации звонка и Companion notifications

Для каждого домофона с историей звонков создаётся бинарный сенсор
**«Входящий звонок»** и соответствующий device trigger. Нативный doorbell EventEntity
представляет тот же подтверждённый звонок стандартным типом `ring` Home Assistant.

Сущность **«Снимок последнего звонка»** приватно загружает tokenized provider
preview, извлекает JPEG через локальный `ffmpeg` с анонимным перематываемым
источником и хранит только JPEG. `preview_url`/`archive_url` не публикуются в
entity state или `ufanet_intercom_call`.

Рекомендуемый blueprint:
[`incoming_call_notification.yaml`](blueprints/automation/ufanet_intercom/incoming_call_notification.yaml).
Выберите домофон, Companion device, соответствующие **«Последний вызов»** /
**«Снимок последнего звонка»**, а при необходимости:

- matching live `camera.*`;
- точную кнопку **«Открыть дверь»** того же HA device;
- image delay, action timeout, fallback URI панели и Android notification channel.

Blueprint отправляет текст немедленно, затем при готовности JPEG заменяет то же
stable-tag уведомление картинкой через `/api/image_proxy/`. В реальном звонке
**«Открыть дверь»** работает только в пределах timeout и только для button того же
Home Assistant device. Принадлежность проверяется повторно непосредственно перед
`button.press`. **Ручной запуск blueprint физическую кнопку открытия не показывает.**

**«Открыть камеру»** открывает More Info выбранной live-камеры через
`more-info-entity-id`; при отсутствии/несовпадении selection используется fallback
URI панели. Одно Ufanet device может содержать live и archive camera, поэтому live
entity нужно выбирать явно.

Android live-проверен. Payload соответствует общей action-схеме Android/iOS
Companion, но iOS action delivery на реальном устройстве пока не проверялся и не
объявляется live-confirmed. Подробная модель безопасности и оставшиеся gates:
[docs/notifications_RU.md](docs/notifications_RU.md).

## Физические ключи и проходы

Для каждого домофона с `has_key_recording_support` создаются:

- **«Физические ключи»** — числовое количество; validation-ветка также публикует read-only `keys` только с `name` и UTC `created_at`;
- **«Последний проход по ключу»** — timestamp последнего прохода;
- EventEntity **«Проход по физическому ключу»** и соответствующий device trigger.

Отдельный coordinator опрашивает API раз в 60 секунд. Первый успешный poll истории
устанавливает baseline и не воспроизводит старые проходы; private cursor защищает
от дублей после reload. Публичный passage event содержит только `key_name` и
`occurred_at`; provider `external_id` и полная история не публикуются.

Validation-ветка добавляет **«Добавить физический ключ»** (`mdi:key-plus`) только
для поддерживаемых домофонов. Кнопка повторяет Android-observed 60-секундный
`auto_collect/enable` flow. Успешный HTTP означает только включение enrollment mode;
новый ключ нужно физически приложить к считывателю в течение 60 секунд.

FCM listener распознаёт Android-observed completion `reason=key_add`, немедленно
обновляет key inventory и отправляет account-level privacy-minimized событие
`ufanet_intercom_key_enrollment`. Provider `key_id`, `external_id`, raw message text
и push payload не публикуются. Реальный `key_add` и непустой inventory пока имеют
статус **Observed / pending live validation**.

Для будущего управления ключами validation-ветка предоставляет response-service
`ufanet_intercom.list_physical_keys`, который возвращает только `name`,
`created_at` и локальный непрозрачный `key_ref`. `ufanet_intercom.rename_physical_key`
принимает этот `key_ref`, перед изменением перечитывает свежий inventory, разрешает
ссылку только внутри выбранного домофона и после Android-observed `/api/v4/key/edit/`
обязательно перечитывает inventory ещё раз. Успех возвращается только если новое имя
реально видно после refresh. Raw provider `key_id` не принимается и не возвращается.
Сам rename endpoint остаётся **Observed / pending live validation** до появления
реального ключа. Удаление ключа не реализовано. Подробности:
[docs/api/keys_RU.md](docs/api/keys_RU.md).

## Аналитика движения

Для камер с live-confirmed capability `motion_alarm` интеграция создаёт EventEntity
**«Обнаружено движение»** / device trigger и privacy-minimized
`ufanet_intercom_motion`. Архивный таймлайн может показывать read-only timestamps
движения. Provider camera/cursor IDs, screenshots, recognition data и raw history
не публикуются. Подробности: [docs/api/analytics_RU.md](docs/api/analytics_RU.md).

## Автоматическое сохранение звонков и локальная медиатека

Автосохранение по умолчанию отключено. После включения звонок экспортируется
асинхронно, когда нужный post-call интервал появился в UCAMS archive. Raw call UUID
хешируется перед использованием для локальной дедупликации имени файла.

Ручные и автоматические MP4 сохраняются в Home Assistant Media `ufanet_intercom/`.
Вкладка **АРХИВ** показывает ролики выбранной камеры, позволяет открыть/скачать/удалить
их и применяет настроенные ограничения срока/объёма.

## Безопасность

- JWT Ufanet/UCAMS и Firebase/FCM credentials намеренно не выводятся в diagnostics.
- Гостевые ссылки являются временными capabilities доступа.
- Открытие двери — реальное физическое действие; карточка/notification требуют явного действия пользователя, а notification добавляет same-device guards.
- Запуск physical-key enrollment изменяет состояние контроля доступа и не должен использоваться как health check или автоматическое действие.
- `external_id` физического ключа отбрасывается при нормализации; provider `key_id` остаётся только внутренним runtime ID и не попадает в sensor attributes/events/diagnostics.
- Публичное управление физическими ключами использует только intercom-scoped opaque `key_ref`; rename перечитывает inventory до изменения и проверяет результат повторным refresh после POST.
- Tokenized call-media URL остаются внутренними runtime-данными; image entity хранит только созданный JPEG.
- Управление FCM-сессиями использует opaque refs вместо raw provider device IDs и защищает доказанно принадлежащие HA регистрации.
- Motion provider cursor хранится только в private storage и наружу выводятся лишь нормализованные timestamps.

Подробности: [docs/api/security_RU.md](docs/api/security_RU.md).

## Диагностика проблем

Перед issue о packaging/frontend запустите:

```bash
python scripts/release_check.py
```

В Home Assistant используйте вкладку **ДИАГНОСТИКА** или **Скачать диагностику** на
странице интеграции/устройства.

Если `ffmpeg` недоступен или извлечение JPEG последнего звонка несколько раз
завершается ошибкой, Home Assistant создаёт Repairs warning. Звонки, архив и
управление дверью продолжают работать; после успешного JPEG warning закрывается.

## Разработка и проверка релиза

`python scripts/release_check.py --strict-hacs` вместе с GitHub CI проверяет
packaging, Python/JSON/JavaScript, ссылки методов/сервисов карточки, HACS/Hassfest и
согласованность release versions.

**Green CI не заменяет обязательный физический/live test.** Перед tag/release нужно
закрыть `REQUIRED VALIDATION BEFORE ANY RELEASE` в активном PR, обновить evidence
labels/docs/CHANGELOG, затем одним release-prep изменением поднять все версии и
cache-bust URL. См. [PUBLISHING.md](PUBLISHING.md).

## Лицензия

Проект распространяется по [MIT License](LICENSE).

Copyright © 2026 [alphazulu](https://github.com/alphazulu).

Разрешены коммерческое использование, изменение, распространение, сублицензирование
и включение в проприетарные продукты. В копиях или существенных частях ПО должны
сохраняться copyright notice и текст разрешения MIT License.

## Репозиторий

https://github.com/alphazulu/ufanet-intercom-home-assistant