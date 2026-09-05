# Физические ключи и журнал проходов

[English version](keys.md)

Этот раздел описывает API физических ключей и событий прохода, который используют официальный Android-клиент и интеграция Home Assistant.

## Статус

Read-only формы запросов успешно проверены на реальной учётной записи. Аккаунт вернул feature `keys`, один домофон подтвердил поддержку записи ключей, а список ключей и история проходов вернули корректные пустые коллекции с HTTP 200. Поэтому envelope пустых ответов и pagination имеют статус **Confirmed**. Поля непустой записи ключа или прохода пока остаются **Observed** из Android-клиента до получения реального нового ключа.

В validation-ветке подготовлены:

- 60-секундная регистрация физического ключа;
- обработка FCM `reason=key_add`;
- read-only inventory ключей;
- privacy-safe сервисы `list_physical_keys` и `rename_physical_key`.

Wire-контракты регистрации, `key_add`, непустого key item и переименования остаются **Observed**, пока не выполнен end-to-end тест реальным новым ключом. На реальной установке Home Assistant уже подтверждено пустое состояние inventory: числовой state сенсора **«Физические ключи»** равен `0`, а `keys` равен `[]`.

## Возможности аккаунта

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed.** Live-ответ содержал account feature `keys`.

## Capability конкретного домофона

```http
POST /api/v0/intercoms/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "page": 1,
  "page_size": 10,
  "filters": {"has_key_recording_support": true}
}
```

**Confirmed.** В `result.intercoms` подтверждены `id` и `has_key_recording_support=true`. Нумерация страниц начинается с `1`. Интеграция не создаёт enrollment/management поверхность для домофона, отсутствующего в этом capability-result.

## Список физических ключей

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed для пустого envelope; поля непустой записи Observed.** Android-observed item:

```json
{
  "id": 1,
  "external_id": "<redacted>",
  "name": "<redacted>",
  "create_date": 1700000000,
  "devices": ["<redacted-skud-id>"]
}
```

`external_id` рассматривается как приватный идентификатор доступа и отбрасывается сразу при нормализации ответа. Provider `id` сохраняется только во внутренней runtime-памяти, поскольку он требуется для операций над конкретным ключом. Ни `external_id`, ни provider `id` не публикуются в entity state, событиях, diagnostics или публичных service responses.

## Read-only inventory в Home Assistant

Сенсор **«Физические ключи»** сохраняет числовое состояние — количество ключей, привязанных к конкретному домофону. Его атрибут `keys` содержит только:

```yaml
keys:
  - name: "Папа"
    created_at: "2025-06-27T06:03:36+00:00"
```

Список фильтруется по `devices`, сортируется от новых к старым и не содержит provider ID. На тестовой установке live-проверено:

```yaml
state: 0
attributes:
  keys: []
```

Непустой inventory требует проверки после регистрации реального ключа.

## Privacy-safe список для операций управления

Validation-ветка также предоставляет response-service:

```text
ufanet_intercom.list_physical_keys
```

Он сначала запрашивает свежий key coordinator/inventory и для выбранного домофона возвращает только:

```yaml
count: 1
keys:
  - key_ref: "<24-hex-opaque-ref>"
    name: "Папа"
    created_at: "<UTC ISO-8601>"
```

`key_ref` — локальная непрозрачная ссылка, зависящая от ConfigEntry, выбранного SKUD и внутреннего provider key ID. Raw `key_id` не принимается и не возвращается. Это предотвращает использование публичного HA service API как интерфейса прямого ввода provider ID и не позволяет перенести `key_ref` на другой домофон.

Непустой результат этого сервиса пока не live-проверен.

## Запуск регистрации физического ключа

Официальный Android-клиент включает серверный режим автосбора запросом:

```http
POST /api/v4/key/skud/<skud_id>/auto_collect/enable/
Authorization: JWT <UFANET_ACCESS>
```

**Observed из Android-клиента; live-проверка ожидается.** После успешного ответа приложение открывает окно **60 секунд**, в течение которого новый ключ нужно приложить к считывателю. Успешный HTTP-ответ означает только, что режим регистрации включён.

В HA flow представлен кнопкой **«Добавить физический ключ»** (`mdi:key-plus`) с атрибутом:

```yaml
enrollment_window_seconds: 60
```

Кнопка создаётся только для capability-supported домофона и недоступна для заблокированного/недоступного устройства.

## Асинхронное завершение регистрации через FCM

Android-клиент знает push:

```text
data.reason = key_add
data.key_status
data.key_id
```

**Observed; live-проверка ожидается.** Нативная логика успеха: `key_status == 0` и присутствует корректный integer `key_id`.

Validation runtime немедленно обновляет key coordinator и публикует только privacy-minimized account-level событие:

```yaml
event_type: ufanet_intercom_key_enrollment
data:
  type: key_enrollment
  source: fcm
  result: success
  received_at: "<UTC ISO-8601>"
  inventory_refresh_succeeded: true
```

Observed `key_add` payload не содержит `skud_id`, поэтому интеграция его не угадывает. Привязка ключа определяется последующим `/api/v4/key/list/` через `devices`.

FCM diagnostics хранят только `received_key_add_push_count`, `last_key_add_push_at`, `last_key_add_result`; provider `key_id`, `title`, `body` и raw push не сохраняются.

## Переименование физического ключа

Официальный Android-клиент использует:

```http
POST /api/v4/key/edit/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "key_id": 1,
  "name": "<new-name>"
}
```

**Observed из Android-клиента; реальный endpoint ещё не live-проверен.**

Validation-ветка реализует этот контракт через response-service:

```text
ufanet_intercom.rename_physical_key
```

Публичный input:

```yaml
device_id: <HA device id>
key_ref: <opaque ref from list_physical_keys>
new_name: "Новое имя"
```

Безопасная последовательность:

1. перед изменением перечитывается свежий inventory;
2. `key_ref` разрешается только внутри выбранного домофона;
3. пустое имя и control characters отклоняются; локально установлен консервативный предел 128 символов — это **не** утверждение о server limit;
4. только после разрешения ref внутренняя runtime-логика вызывает `/api/v4/key/edit/` с provider `key_id`;
5. после POST inventory перечитывается ещё раз;
6. операция считается подтверждённой сервисом только если тот же ключ виден с новым именем;
7. если новое имя совпадает с текущим, provider POST не выполняется.

Provider `key_id` не попадает в service input/output. Если POST мог изменить серверное состояние, но post-write refresh не удался, HA сообщает неопределённый результат, а не объявляет переименование успешным.

До появления реального ключа этот runtime path считается **validation-only**, а endpoint остаётся **Observed**.

## Удаление ключа

Android-клиент также содержит:

```http
POST /api/v4/key/skud/<skud_id>/delete/key/
Content-Type: application/json

{"key_id": 1}
```

**Observed.** Удаление является destructive-операцией и в текущем runtime **не реализовано**. Оно не войдёт в release scope без отдельного дизайна подтверждения, защиты выбора ключа/домофона и live-теста.

## Журнал проходов

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

Минимальный запрос:

```json
{"page": 0, "page_size": 5}
```

**Confirmed для envelope/pagination; поля непустой записи Observed.** Android-observed result содержит `key`, `key_name`, `time_passage`; `time_passage` трактуется как Unix seconds. Стартовая страница `0`, штатный Android page size `25`.

Первый успешный poll устанавливает baseline и не воспроизводит старые события. Приватный cursor предотвращает дубли после reload/restart. Публичное событие прохода не содержит provider IDs.

## Модель Home Assistant в validation-ветке

Текущая ветка включает:

- capability discovery;
- **Физические ключи**: count + read-only `keys`;
- **Последний проход по ключу**;
- passage EventEntity / `ufanet_intercom_key_passage` / device trigger;
- 60-секундный key coordinator;
- **Добавить физический ключ**;
- FCM `key_add` + немедленный inventory refresh;
- `ufanet_intercom_key_enrollment`;
- `list_physical_keys` с opaque `key_ref`;
- validation-only `rename_physical_key` с fresh-resolution и post-write verification.

Diagnostics не содержат имён ключей, времени проходов, provider key IDs, `external_id` или полной истории.

## Обязательная live-проверка до релиза

Релиз блока остаётся заблокирован, пока реальным новым ключом не подтверждены:

1. запуск auto-collect кнопкой HA;
2. приложение нового ключа в пределах 60 секунд;
3. реальный `reason=key_add` и его wire-схема;
4. быстрое обновление числового Physical keys state;
5. появление непустого `keys` с ожидаемыми `name`/`created_at`;
6. отсутствие provider `key_id`/`external_id` в публичных surface;
7. корректный `ufanet_intercom_key_enrollment`;
8. `list_physical_keys` выдаёт opaque `key_ref` без provider ID;
9. `rename_physical_key` реально меняет имя через `/api/v4/key/edit/` и post-write refresh подтверждает новое имя.

Удаление и BLE-ключи остаются вне текущего release scope.
