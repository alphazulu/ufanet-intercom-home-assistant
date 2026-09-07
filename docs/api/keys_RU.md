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
- Home Assistant/Lovelace: один реальный ключ отображается, выбор строки загружает два passage timestamp.

В validation-ветке подготовлены:

- 60-секундная регистрация физического ключа;
- обработка FCM `reason=key_add`;
- read-only inventory ключей;
- privacy-safe сервисы `list_physical_keys`, `rename_physical_key` и `get_physical_key_passages`;
- Lovelace-вкладка **КЛЮЧИ** с Experimental полем номера, переименованием и историей выбранного ключа.

Wire-контракты регистрации нового ключа, `reason=key_add` и переименования остаются **Observed**, пока не выполнены соответствующие state-changing live-тесты. Read-only inventory/history теперь **Confirmed** на непустом реальном наборе данных. Интерпретация `external_id` как номера, нанесённого на физический ключ, остаётся **Experimental**; 7 сентября 2026 пользователь явно решил оставить это предварительное поле в текущей release-разработке, не объявляя непроверенный mapping Confirmed.

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

Внутренний provider `id` остаётся служебным и не публикуется в entity state, событиях, diagnostics или публичных service responses.

У `external_id` подтверждена runtime-роль: официальный Android-клиент использует его в `filters.key` при запросе истории проходов одного выбранного ключа. Validation-ветка также выводит **значение** этого поля как Experimental пользовательский `number`. Проект не утверждает, что `external_id` совпадает с цифрами, нанесёнными на физический ключ. Wire-имя `external_id` через публичный service/UI не выводится.

## Read-only inventory в Home Assistant

Сенсор **«Физические ключи»** сохраняет числовое состояние — количество ключей, привязанных к конкретному домофону. Его существующий атрибут `keys` остаётся минимальным:

```yaml
keys:
  - name: "Папа"
    created_at: "2025-06-27T06:03:36+00:00"
```

Список фильтруется по `devices`, сортируется от новых к старым и не содержит внутреннего provider ID. Пустой путь (`0`, `[]`) и непустой путь с одним реальным ключом live-проверены.

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
    number: "<experimental key identifier>"
    name: "Папа"
    created_at: "<UTC ISO-8601>"
```

`number` является Experimental-представлением значения provider `external_id`. Оно намеренно не документируется как номер, нанесённый на брелок. Внутренний provider `id` не принимается и не возвращается.

`key_ref` — локальная непрозрачная ссылка, зависящая от ConfigEntry, выбранного SKUD и внутреннего provider ID. Ссылка другого домофона не разрешается для выбранного устройства.

Пустой response-service path (`count: 0`, `keys: []`) и непустой inventory path с одним ключом уже live-проверены. Будущее сравнение с заведомо известным физическим ключом может уточнить или повысить Experimental-интерпретацию, не меняя уже подтверждённую роль `external_id` для фильтрации истории.

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

Строка физического ключа показывает:

- пользовательское имя;
- **«Номер ключа (эксп.)»** — Experimental `number`, полученный из provider `external_id`, но не объявляемый физической маркировкой ключа;
- дату добавления;
- действие **Переименовать**.

UI прямо поясняет, что совпадение с маркировкой физического ключа не подтверждено. Внутренний provider ID не показывается. Opaque `key_ref` используется только внутри вызовов HA service и пользователю не выводится.

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

На live API подтверждено, что `filters.key=<external_id>` возвращает два прохода выбранного ключа. Frontend end-to-end также live-проверен: при выборе реального ключа внизу карточки отобразились два времени прохода.

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
- `list_physical_keys` с `key_ref`, Experimental `number`, `name`, `created_at`;
- validation-only `rename_physical_key` с fresh-resolution и post-write verification;
- `get_physical_key_passages` с per-key фильтрацией по приватному `external_id`;
- Lovelace-вкладку **КЛЮЧИ** с Experimental номером и историей проходов, без delete action.

Diagnostics не содержат имён ключей, значений number/`external_id`, времени проходов, внутренних provider IDs или полной истории.

## Обязательная live-проверка до релиза

Read-only key/history path уже live-подтверждён. Experimental-интерпретация номера явно рассмотрена и принята как Experimental для текущего candidate; она должна оставаться заметно маркированной и не должна описываться как Confirmed.

Релиз блока всё ещё заблокирован state-changing и safety-проверками, включая:

1. smoke-test, что UI КЛЮЧИ явно показывает Experimental status поля `number` и не раскрывает internal provider IDs;
2. запуск auto-collect кнопкой HA/карточки;
3. приложение нового незарегистрированного ключа в пределах 60 секунд;
4. реальный `reason=key_add` и его wire-схема;
5. быстрое обновление numeric Physical keys после FCM-triggered refresh;
6. подтверждение регистрации именно нового ключа и его появления во всех read-only surfaces;
7. корректный `ufanet_intercom_key_enrollment` без внутренних идентификаторов;
8. live-проверка `rename_physical_key` и post-write verification;
9. проверка ошибок enrollment/rename;
10. оставшиеся notification safety gates из PR #15.

Удаление и BLE-ключи остаются вне текущего release scope.
