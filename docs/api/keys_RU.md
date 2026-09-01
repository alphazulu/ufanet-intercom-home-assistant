# Физические ключи и журнал проходов

[English version](keys.md)

Этот раздел описывает read-only API физических ключей и событий прохода, найденный
в официальном Android-клиенте.

## Статус

Все приведённые ниже контракты пока имеют статус **Observed**: HTTP-методы, пути,
тела запросов и DTO подтверждены кодом клиента, но ещё не проверены на реальной
учётной записи. Для live-проверки предназначен
`tools/research/key_passage_probe_py/probe.py`.

## Возможности аккаунта

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

Наблюдаемая форма ответа:

```json
{
  "status": "ok",
  "data": {
    "features": ["keys"]
  }
}
```

Известные клиенту значения feature: `share_access`, `temporary_access`, `keys`,
`frsi` и `ble`.

## Capability конкретного домофона

```http
POST /api/v0/intercoms/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "page": 0,
  "page_size": 100,
  "filters": {}
}
```

Массив `result.intercoms` содержит `id` и булево поле
`has_key_recording_support`. Интеграция не должна опрашивать историю для домофона,
который явно вернул `false`.

## Список физических ключей

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

Наблюдаемая форма:

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

Наблюдаемая модель ответа:

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

## Будущая модель Home Assistant

После live-подтверждения планируется read-only реализация:

- определение capability перед включением polling;
- сенсор количества физических ключей;
- сенсор времени последнего прохода;
- `EventEntity` прохода для автоматизаций;
- дедупликация событий после reload;
- отдельный coordinator с ограниченным интервалом опроса.

Переименование, удаление, автоматический сбор и BLE-ключи в первый этап не входят.
