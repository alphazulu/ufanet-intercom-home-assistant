# Физические ключи и журнал проходов

[English version](keys.md)

Этот раздел описывает API физических ключей и событий прохода, который используют
официальный Android-клиент и интеграция Home Assistant.

## Статус

Read-only формы запросов успешно проверены на реальной учётной записи. Аккаунт
вернул feature `keys`, один домофон подтвердил поддержку записи ключей, а список
ключей и история проходов вернули корректные пустые коллекции с HTTP 200. Поэтому
envelope пустых ответов и pagination имеют статус **Confirmed**. Поля непустой
записи ключа или прохода пока остаются **Observed** из Android-клиента до получения
реального нового ключа.

В validation-ветке также подготовлены штатный запуск 60-секундного режима
регистрации физического ключа и обработка асинхронного `reason=key_add`. Их wire
контракты восстановлены из официального Android-клиента и имеют статус
**Observed**, пока не выполнен end-to-end тест новым незарегистрированным ключом.

На реальной установке Home Assistant уже подтверждено пустое состояние inventory:
сенсор **«Физические ключи»** имеет числовое состояние `0`, а его read-only атрибут
возвращает `keys: []`.

## Возможности аккаунта

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed**

```json
{
  "status": "ok",
  "data": {
    "features": ["keys"]
  }
}
```

В live-ответе присутствовал `keys`. Клиенту также известны `share_access`,
`temporary_access`, `frsi` и `ble`.

## Capability конкретного домофона

```http
POST /api/v0/intercoms/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

**Confirmed**

```json
{
  "page": 1,
  "page_size": 10,
  "filters": {
    "has_key_recording_support": true
  }
}
```

Массив `result.intercoms` содержит `id` и булево поле
`has_key_recording_support`. И запрос, и значение `true` подтверждены live-тестом.
Нумерация страниц этого endpoint начинается с `1`. Интеграция не создаёт кнопку
регистрации ключа и не опрашивает историю для домофона, отсутствующего в
отфильтрованном результате.

## Список физических ключей

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed для пустого envelope; поля непустой записи Observed**

```json
{
  "data": {
    "keys": [
      {
        "id": 1,
        "external_id": "<redacted>",
        "name": "<redacted>",
        "create_date": 1700000000,
        "devices": ["<redacted-skud-id>"]
      }
    ]
  }
}
```

`external_id` рассматривается как приватный идентификатор доступа и отбрасывается
сразу при нормализации ответа. Он не хранится в runtime inventory и не должен
попадать в журнал Home Assistant, диагностику, состояние сущностей или события.

Внутренний `id` ключа сохраняется только в памяти интеграции, поскольку он может
понадобиться для будущих операций переименования/удаления. В состояние сущностей,
события и diagnostics он не публикуется.

## Read-only inventory в Home Assistant

Сенсор **«Физические ключи»** сохраняет числовое состояние — количество ключей,
привязанных к конкретному домофону. В validation-ветке у этого же сенсора есть
read-only атрибут `keys`:

```yaml
state: 2
attributes:
  keys:
    - name: "Папа"
      created_at: "2025-06-27T06:03:36+00:00"
    - name: "Запасной"
      created_at: "2025-06-20T10:11:12+00:00"
```

Для каждого элемента публикуются только:

- `name` — имя ключа из Ufanet;
- `created_at` — `create_date`, преобразованный в ISO timestamp UTC.

Список фильтруется по `devices`, поэтому на сущности одного домофона не показываются
ключи, связанные только с другим домофоном. Сортировка — от более новых к старым.
Provider `key_id` и `external_id` в атрибут `keys` не попадают.

На тестовой установке с нулём зарегистрированных ключей live-проверены:

```yaml
state: 0
attributes:
  keys: []
```

Непустой `keys` всё ещё требует проверки после регистрации реального нового ключа.

## Запуск регистрации физического ключа

Официальный Android-клиент включает серверный режим автосбора отдельным запросом:

```http
POST /api/v4/key/skud/<skud_id>/auto_collect/enable/
Authorization: JWT <UFANET_ACCESS>
```

**Observed из Android-клиента; live-проверка ожидается**

После успешного ответа приложение открывает окно **60 секунд**, в течение которого
новый физический ключ нужно приложить к считывателю домофона. Успешный HTTP-ответ
означает только, что режим регистрации включён; он не доказывает, что ключ был
приложен или сохранён.

В Home Assistant этот flow представлен кнопкой **«Добавить физический ключ»**
(`mdi:key-plus`). Кнопка создаётся только для домофона с подтверждённым
`has_key_recording_support` и имеет атрибут:

```yaml
enrollment_window_seconds: 60
```

Если основной coordinator недоступен или домофон помечен `is_blocked`, кнопка
недоступна. Ошибка Ufanet преобразуется в ошибку действия Home Assistant; сама
интеграция не считает нажатие подтверждением регистрации.

## Асинхронное завершение регистрации через FCM

Официальный Android-клиент знает push со следующими полями:

```text
data.reason = key_add
data.key_status
data.key_id
```

**Observed из Android-клиента; live-проверка ожидается**

Нативная логика успеха:

```text
key_status == 0
AND
key_id присутствует и разбирается как integer
```

Отсутствующий/некорректный `key_status` трактуется как ошибка. В validation-ветке
Home Assistant повторяет эту семантику, но не публикует provider `key_id`, `title`
или `body`.

После `reason=key_add` интеграция немедленно вызывает refresh key coordinator. Тот
же refresh перечитывает `/api/v4/key/list/`, поэтому после будущего реального теста
новый ключ должен появиться одновременно с изменением числового состояния сенсора.

На шину Home Assistant отправляется только privacy-minimized account-level событие:

```yaml
event_type: ufanet_intercom_key_enrollment
data:
  type: key_enrollment
  source: fcm
  result: success
  received_at: "<UTC ISO-8601>"
  inventory_refresh_succeeded: true
```

Проверенный Android payload `key_add` не содержит `skud_id`, поэтому интеграция
намеренно не угадывает конкретный домофон в этом событии. Привязка нового ключа к
домофону определяется последующим `/api/v4/key/list/` через поле `devices`.

Диагностика FCM хранит только:

```text
received_key_add_push_count
last_key_add_push_at
last_key_add_result
```

Provider `key_id`, `title`, `body` и исходный push payload не сохраняются.

## Журнал проходов

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

**Confirmed для envelope/pagination; поля непустой записи Observed**

Минимальное тело без фильтрации по конкретному ключу:

```json
{
  "page": 0,
  "page_size": 5
}
```

```json
{
  "count": 1,
  "current_page": 0,
  "page_count": 1,
  "page_size": 5,
  "results": [
    {
      "key": 1,
      "key_name": "<redacted>",
      "time_passage": 1700000000
    }
  ]
}
```

`time_passage` интерпретируется Android-клиентом как Unix-время в секундах.
Начальная страница имеет номер `0`, а штатный размер страницы клиента равен `25`.

Первый успешный poll истории используется как baseline и не генерирует старые
события. Приватный cursor предотвращает повторную выдачу одинаковых проходов после
reload/перезапуска Home Assistant.

## Наблюдаемые операции управления ключом

Официальный Android-клиент также содержит следующие state-changing операции. Они
**не реализованы** в текущем Home Assistant runtime и не должны считаться
live-confirmed.

### Переименование

**Observed**

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

### Удаление

**Observed**

```http
POST /api/v4/key/skud/<skud_id>/delete/key/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "key_id": 1
}
```

Удаление является destructive-операцией и не должно добавляться в production UI
без отдельной проверки endpoint, защиты от выбора не того домофона/ключа и явного
подтверждения пользователя.

## Модель Home Assistant в validation-ветке

Текущая validation-ветка включает:

- определение capability перед polling;
- сенсор **«Физические ключи»**: количество + read-only `keys` inventory;
- сенсор времени **«Последний проход по ключу»**;
- `EventEntity`, событие `ufanet_intercom_key_passage` и device trigger;
- приватный cursor времени/внутреннего ID ключа для дедупликации после reload;
- отдельный coordinator с интервалом 60 секунд;
- кнопку **«Добавить физический ключ»**, запускающую 60-секундный auto-collect;
- FCM completion handler `reason=key_add` с немедленным refresh списка ключей;
- privacy-safe событие `ufanet_intercom_key_enrollment` и агрегированные FCM diagnostics.

Diagnostics не содержат имён ключей, времени проходов, внутренних ID,
`external_id` или полной истории.

## Обязательная live-проверка до релиза

Релиз этого блока остаётся заблокирован, пока реальным новым ключом не подтверждены:

1. запуск auto-collect кнопкой Home Assistant;
2. приложение ключа к выбранному домофону в пределах 60 секунд;
3. реальный `reason=key_add` и его фактическая wire-схема;
4. изменение числового состояния **«Физические ключи»** без ожидания следующего
   штатного poll;
5. появление нового элемента в `keys` с ожидаемыми `name` и `created_at`;
6. отсутствие `key_id`/`external_id` в публичных state/event/diagnostics;
7. корректный `ufanet_intercom_key_enrollment` result.

Переименование, удаление и BLE-ключи в текущий release scope не входят.