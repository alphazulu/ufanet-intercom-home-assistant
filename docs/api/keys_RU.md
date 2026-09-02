# Физические ключи и журнал проходов

[English version](keys.md)

Этот раздел описывает read-only API физических ключей и событий прохода, который
используют официальный Android-клиент и интеграция Home Assistant.

## Статус

Все четыре read-only формы запроса успешно проверены на реальной учётной записи.
Аккаунт вернул feature `keys`, один домофон подтвердил поддержку
журнала, а список ключей и история вернули корректные пустые коллекции с HTTP 200.
Поэтому envelope пустых ответов и pagination имеют статус **Confirmed**. Поля
непустой записи ключа или прохода остаются **Observed** из Android-клиента до
получения реальной записи. Probe не создаёт, не переименовывает и не удаляет ключи.

## Возможности аккаунта

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

Подтверждённая форма ответа:

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
Нумерация страниц этого endpoint начинается с `1`. Интеграция не опрашивает
историю домофона, отсутствующего в отфильтрованном результате.

## Список физических ключей

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

Подтверждённый envelope пустого ответа; поля непустой записи остаются Observed:

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

`external_id` рассматривается как приватный идентификатор доступа: он не должен
попадать в журнал Home Assistant, диагностику, состояние сущностей или события.

## Журнал проходов

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

Минимальное тело без фильтрации по конкретному ключу:

```json
{
  "page": 0,
  "page_size": 5
}
```

Подтверждённые envelope и pagination; поля непустой записи остаются Observed:

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

## Модель Home Assistant

В версии 0.27.0 функция реализована в read-only виде:

- определение capability перед polling;
- сенсор **«Количество физических ключей»**;
- сенсор времени **«Последний проход по ключу»**;
- `EventEntity`, событие `ufanet_intercom_key_passage` и device trigger;
- приватный cursor времени/внутреннего ID ключа для дедупликации после reload;
- отдельный coordinator с интервалом 60 секунд.

Первый успешный опрос используется как baseline и не генерирует старые события.
Имя ключа существует только в фактическом transient-событии. Диагностика не
содержит имён, времени событий, внутренних ID ключей, `external_id` и полной
истории.

Переименование, удаление, автоматический сбор и BLE-ключи в первый этап не входят.
