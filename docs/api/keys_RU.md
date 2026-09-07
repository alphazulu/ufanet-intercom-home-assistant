# Физические ключи и журнал проходов

[English version](keys.md)

Этот раздел описывает API физических ключей и событий прохода, который используют официальный Android-клиент и интеграция Home Assistant.

## Статус

Read-only контракты физических ключей и истории проходов проверены на реальной учётной записи с непустыми данными. Подтверждены:

- account feature `keys`;
- `has_key_recording_support=true` для реального домофона;
- непустой `/api/v4/key/list/` с одним зарегистрированным ключом;
- непустой `/api/v4/key/skud/<id>/key/pass_history/` с двумя проходами;
- live-схема passage item: `key:str`, `key_name:str`, `time_passage:int`;
- фильтрация истории выбранного ключа через `filters.key=<external_id>`;
- Home Assistant/Lovelace: один реальный ключ отображается, выбор строки загружает его passage timestamps.

7 сентября 2026 также выполнено прямое сравнение с физическим ключом. Номер, нанесённый на проверенный брелок, **не совпал** с кандидатами-идентификаторами из ответа списка ключей. При этом использование `external_id` этого ключа продолжило возвращать корректную и обновляющуюся историю именно этого физического ключа. Поэтому:

- `external_id` **Confirmed** как серверный per-key идентификатор для фильтрации истории проходов;
- `external_id` **не является** номером, нанесённым на проверенный физический ключ;
- ранее экспериментальное публичное поле `number` удалено из validation-ветки, чтобы не выпускать вводящую в заблуждение интерпретацию.

Wire-контракты регистрации нового ключа, `reason=key_add` и переименования остаются **Observed**, пока не выполнены соответствующие state-changing live-тесты.

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

**Confirmed.** В `result.intercoms` подтверждены `id` и `has_key_recording_support=true`. Нумерация страниц начинается с `1`. Интеграция не создаёт enrollment/management surface для домофона, отсутствующего в этом capability-result.

## Список физических ключей

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed на непустом live-ответе.** Item содержит:

- внутренний provider `id`;
- строковый `external_id`;
- `name`;
- `create_date`;
- `devices`.

И provider `id`, и `external_id` остаются внутренними runtime-данными. Live-сравнение показало, что номер, нанесённый на физический ключ, не представлен проверенными значениями идентификаторов из этого ответа.

У `external_id` при этом подтверждена важная runtime-роль: официальный Android-клиент использует его в `filters.key` при запросе истории одного выбранного ключа, а live-тест показал, что возвращаемая история относится к ожидаемому физическому ключу и корректно обновляется.

## Read-only inventory в Home Assistant

Сенсор **«Физические ключи»** сохраняет числовое состояние — количество ключей, привязанных к конкретному домофону. Атрибут `keys` остаётся минимальным:

```yaml
keys:
  - name: "Папа"
    created_at: "2025-06-27T06:03:36+00:00"
```

Список фильтруется по `devices`, сортируется от новых к старым и не содержит provider identifiers. Пустой путь (`0`, `[]`) и непустой путь с одним реальным ключом live-проверены.

## Список для Lovelace и операций управления

Validation-ветка предоставляет response-service:

```text
ufanet_intercom.list_physical_keys
```

Он сначала обновляет key coordinator/inventory и для выбранного домофона возвращает:

```yaml
count: 1
keys:
  - key_ref: "<24-hex-opaque-ref>"
    name: "Папа"
    created_at: "<UTC ISO-8601>"
```

Provider `id`, `external_id` и предполагаемый номер физического ключа наружу не возвращаются.

`key_ref` — локальная непрозрачная ссылка, зависящая от ConfigEntry, выбранного SKUD и внутреннего provider ID. Ссылка другого домофона не разрешается для выбранного устройства.

Пустой response-service path (`count: 0`, `keys: []`) и непустой inventory path уже live-проверены.

## Запуск регистрации физического ключа

Официальный Android-клиент включает серверный режим автосбора запросом:

```http
POST /api/v4/key/skud/<skud_id>/auto_collect/enable/
Authorization: JWT <UFANET_ACCESS>
```

**Observed из Android-клиента; state-changing live-проверка ожидается.** После успешного ответа приложение открывает окно **60 секунд**, в течение которого новый ключ нужно приложить к считывателю. HTTP 200 означает только, что режим регистрации включён, а не что ключ уже зарегистрирован.

В HA flow представлен кнопкой **«Добавить физический ключ»** (`mdi:key-plus`) с `enrollment_window_seconds: 60`. Кнопка создаётся только для capability-supported домофона и недоступна для заблокированного/недоступного устройства.

## Асинхронное завершение регистрации через FCM

Android-клиент знает completion `reason=key_add` вместе со status и внутренним идентификатором ключа. **Observed; live-проверка ожидается.** Нативная логика успеха требует status `0` и корректный идентификатор.

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

Observed completion payload не содержит `skud_id`, поэтому интеграция его не угадывает. Привязка ключа определяется последующим `/api/v4/key/list/` через `devices`.

FCM diagnostics хранят только `received_key_add_push_count`, `last_key_add_push_at`, `last_key_add_result`; provider identifiers, `title`, `body` и raw push не сохраняются.

## Переименование физического ключа

Официальный Android-клиент использует:

```http
POST /api/v4/key/edit/
```

с внутренним provider identifier и новым именем. **Observed из Android-клиента; реальный state-changing endpoint ещё не live-проверен.**

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
3. пустое имя/control characters отклоняются; локально установлен консервативный предел 128 символов — это не утверждение о provider limit;
4. runtime вызывает observed edit endpoint с внутренним provider ID;
5. после POST inventory перечитывается ещё раз;
6. операция считается подтверждённой только если тот же ключ виден с новым именем;
7. если новое имя совпадает с текущим, provider POST не выполняется.

Внутренний provider ID не попадает в service input/output. Если POST мог изменить серверное состояние, но post-write refresh не удался, HA сообщает неопределённый результат, а не объявляет переименование успешным.

## Lovelace-вкладка КЛЮЧИ

Validation-ветка автоматически загружает packaged physical-key extensions и добавляет вкладку **КЛЮЧИ** к существующей карточке.

Строка физического ключа показывает только:

- пользовательское имя;
- дату добавления;
- действие **Переименовать**.

Provider identifiers и опровергнутый кандидат на физический номер ключа не отображаются. Opaque `key_ref` используется только внутри вызовов HA service и пользователю не выводится.

**Добавить ключ** требует подтверждения, показывает 60-секундный countdown и после завершения окна перечитывает список. **Переименовать** требует подтверждения и отображает успех только после `verified: true` от backend. Delete action отсутствует.

Клик по строке ключа выбирает его и в нижней части вкладки загружает **Историю проходов** выбранного ключа.

## История проходов конкретного ключа

Validation-ветка предоставляет response-service:

```text
ufanet_intercom.get_physical_key_passages
```

Публичный input содержит только HA `device_id`, opaque `key_ref` и страницу. Перед запросом сервис перечитывает inventory, разрешает ключ внутри выбранного домофона и затем внутренне использует его `external_id`:

```json
{
  "page": 0,
  "page_size": 25,
  "filters": {
    "key": "<private external_id>"
  }
}
```

Наружу возвращаются только нормализованные времена проходов:

```yaml
page: 0
page_size: 25
total: 2
has_more: false
passages:
  - occurred_at: "<UTC ISO-8601>"
  - occurred_at: "<UTC ISO-8601>"
```

На live API подтверждено, что `filters.key=<external_id>` возвращает проходы выбранного физического ключа. Frontend end-to-end также live-проверен: при выборе реального ключа карточка отображает его passage timestamps, а последующие обновления истории продолжают корректно относиться к тому же ключу.

## Wire-контракт журнала проходов

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

Минимальный запрос:

```json
{"page": 0, "page_size": 5}
```

**Confirmed на непустом live-ответе.** Envelope:

```text
count: int
current_page: int
page_count: int
page_size: int
results: list
```

Live passage item:

```text
key: str
key_name: str
time_passage: int
```

Важное отличие от decompiled Android DTO: DTO объявляет `key` как integer, а реальный backend отдаёт JSON string. Gson в Android принимает numeric string для integer field; Home Assistant явно зеркалирует это поведение.

Первый coordinator poll устанавливает baseline и не воспроизводит старые события. Приватный cursor предотвращает дубли после reload/restart. Публичное событие прохода не содержит provider IDs.

## Удаление ключа

Android-клиент содержит destructive delete-запрос для выбранного физического ключа. **Observed.** Удаление в текущем runtime **не реализовано** и остаётся вне release scope до отдельного дизайна защиты/подтверждения и live-теста.

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
- `list_physical_keys` только с `key_ref`, `name`, `created_at`;
- validation-only `rename_physical_key` с fresh-resolution и post-write verification;
- `get_physical_key_passages` с per-key фильтрацией по приватному `external_id`;
- validation-only Lovelace-вкладку **КЛЮЧИ** с историей выбранного ключа, без delete action.

Diagnostics не содержат имён ключей, provider identifiers, времени проходов или полной истории.

## Обязательная live-проверка до релиза

Read-only key/history path и отрицательный тест физического номера теперь live-confirmed. Вопрос с номером закрыт и больше не является release blocker: интеграция не публикует предполагаемый номер.

Релиз по-прежнему блокируют state-changing и safety tests:

1. запустить auto-collection из HA/card;
2. приложить новый незарегистрированный ключ в течение 60 секунд;
3. получить реальный `reason=key_add` и зафиксировать обезличенную wire-схему;
4. проверить быстрое обновление числового **Физические ключи** после FCM completion;
5. проверить появление нового ключа на всех read-only surfaces;
6. проверить privacy-safe результат `ufanet_intercom_key_enrollment`;
7. live-проверить `rename_physical_key` и post-write verification;
8. проверить реальные enrollment/rename error semantics;
9. завершить оставшиеся notification safety gates из PR #15.

Delete и BLE keys остаются вне текущего release scope.
