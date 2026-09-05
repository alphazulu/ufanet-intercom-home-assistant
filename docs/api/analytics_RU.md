# Аналитические события камер UCAMS

[English version](analytics.md)

Здесь зафиксирован read-only контракт аналитики камер UCAMS, наблюдавшийся в
официальном Android-клиенте, подтверждённые live-части этого контракта и
privacy-safe production-поведение, реализованное в Ufanet Intercom v0.28.0.

> Текущая combined validation-ветка уведомлений/физических ключей не меняет
> контракт `motion_alarm` или его evidence status. Этот раздел проверен при
> подготовке validation documentation и остаётся authoritative для аналитики.

## Метаданные возможностей камеры

**Статус: Confirmed для `motion_alarm`; Observed для `perimeter_security`**

`POST /api/v0/cameras/this/` может возвращать поле `analytics`. Проверенная
live-камера объявила `motion_alarm`. Android-клиент также знает capability
`perimeter_security`, но проверенный тариф её не объявил, поэтому endpoint
событий для неё не вызывался и production runtime её не использует.

Для production capability discovery v0.28.0 запрашивает только минимально
необходимые поля:

```json
{
  "fields": ["number", "analytics"],
  "numbers": ["<CAMERA_NUMBER>"]
}
```

Исследовательский probe может дополнительно запрашивать не-медийные metadata,
например `tariff`, чтобы классифицировать наблюдаемое поведение. Production
обнаружение capability не требует tariff, timezone, live/archive токенов,
screenshot или recognition data.

## Отчёт о событиях движения

**Статус: Confirmed для `motion_alarm`**

Подтверждённый live-endpoint:

```http
POST https://cloud.ucams.ru/api/v0/analytics/motion_alarm/report/
Authorization: Bearer <UCAMS_TOKEN>
Content-Type: application/json
```

Подтверждённые поля запроса:

```json
{
  "camera_number": "<CAMERA_NUMBER>",
  "start": "<ISO-8601 UTC>",
  "end": "<ISO-8601 UTC>",
  "limit": 25,
  "order_by_date": "desc"
}
```

`limit` следует считать advisory: сервер не соблюдал меньший проверенный limit,
поэтому клиент обязан проверять фактически полученную оболочку ответа.

Live-ответ представляет собой объект с полями `count`, `page` и `results`.
Каждый подтверждённый элемент `motion_alarm` содержит:

| Поле | Подтверждённая семантика |
|---|---|
| `id` | непрозрачный числовой ID события; используется только как приватный replay cursor |
| `date` | авторитетное время события в ISO-8601 UTC |
| `length` | длительность события, возвращаемая UCAMS |

В Android DTO присутствует поле `time`, однако подтверждённая wire-схема
использует `date`. Поэтому runtime считает `date` авторитетным временем события
и никогда не применяет к нему offset, используемый для старта архивного
воспроизведения до события.

## Пагинация и переполненные временные окна

Подтверждённый объект `page` содержит `current`, `next`, `previous`, `all` и
`page_size`. В live-проверке сервер вернул page size 60 при меньшем запрошенном
`limit`.

Для этого report endpoint не подтверждены request-поля пагинации вроде `page`
или `offset`. Production поэтому не придумывает pagination contract из одной
metadata ответа. Если временное окно возвращает больше событий, чем можно безопасно
обработать, runtime делит только подтверждённый интервал `start`/`end`; если даже
малое окно остаётся неполным, poll завершается ошибкой без продвижения cursor.

## Архивный offset

Android archive player стартует воспроизведение примерно за 18 секунд до выбранного
analytics event. Это UX-offset playback, а не изменение timestamp события.
Validation/production marker остаётся на авторитетном `date`.

## Home Assistant model

Для камеры с `motion_alarm` создаются:

- EventEntity **«Обнаружено движение»**;
- event bus `ufanet_intercom_motion`;
- device trigger **«Обнаружено движение»**;
- read-only markers на архивном timeline.

Публичное событие содержит только нормализованный `occurred_at`. Provider camera ID,
analytics cursor/event ID, `length`, raw history, screenshots, recognition/media
не публикуются. Cursor хранится только в private storage Home Assistant.

Первый успешный poll устанавливает baseline и не воспроизводит старую историю.
Дробная точность `date` сохраняется, чтобы одинаковые timestamp корректно
дедуплицировались после reload.

## Privacy/error boundary

Response считается private provider data. Runtime валидирует только необходимые
поля, неизвестные поля не прокидывает в entities/diagnostics, а server error text
не переносится как есть в публичные coordinator errors/logs.

Подробные модели также отражены в [models_RU.md](models_RU.md), а статус endpoints —
в [STATUS_RU.md](STATUS_RU.md).