# Аналитические события камер UCAMS

[English version](analytics.md)

Здесь зафиксированы read-only контракты аналитики камер, наблюдавшиеся в
официальном Android-клиенте и, где это указано, подтверждённые на live UCAMS.

## Метаданные возможностей камеры

**Статус: Confirmed для `motion_alarm`; Observed для `perimeter_security`**

Существующий запрос `POST /api/v0/cameras/this/` может включать поле
`analytics`. Проверенная live-камера вернула `motion_alarm`. Тот же контракт
Android-клиента содержит `perimeter_security`, но проверенный тариф эту
возможность не объявляет, поэтому endpoint событий для неё не вызывался.

Исследовательский probe запрашивает только:

```json
{
  "fields": ["number", "analytics", "tariff", "timezone"],
  "numbers": ["<CAMERA_NUMBER>"]
}
```

Для capability discovery не запрашиваются live-, archive- или screenshot-токены.

## Отчёт о событиях движения

**Статус: Confirmed для `motion_alarm`**

Подтверждённый live-запрос:

```http
POST https://cloud.ucams.ru/api/v0/analytics/motion_alarm/report/
Authorization: Bearer <UCAMS_TOKEN>
Content-Type: application/json
```

Поля запроса:

```json
{
  "camera_number": "<CAMERA_NUMBER>",
  "start": "<ISO-8601 UTC>",
  "end": "<ISO-8601 UTC>",
  "limit": 5,
  "order_by_date": "desc"
}
```

Live-ответ использует объект с полями `count`, `page` и `results`. Каждый
подтверждённый элемент `motion_alarm` содержит непрозрачный числовой `id`,
ISO-8601 UTC поле `date` и `length`.

В Android DTO присутствует поле `time`, однако подтверждённая wire-схема
использует `date`. Поэтому runtime должен считать `date` авторитетным временем
события и не применять к нему смещение, используемое для запуска архива.

`id` не является пользовательскими данными события. Он используется только как
приватный непрозрачный cursor для дедупликации.

## Пагинация и limit

Подтверждённый объект `page` содержит `current`, `next`, `previous`, `all` и
`page_size`. В live-проверке сервер вернул страницу размером 60, хотя был
запрошен меньший `limit`. Клиент не должен считать, что сервер соблюдает limit,
и обязан сам ограничивать число обрабатываемых записей.

## Scope и граница приватности

Production-поддержка намеренно ограничивается `motion_alarm`. Проект не
запрашивает распознавание лиц и номеров, тепловые данные, анализ толпы, каски,
screenshots, свободный текст или URL медиа.

Probe выводит только HTTP-статусы, количества, наличие capability, форму
оболочки, известные имена полей и поведение пагинации. Номера камер, ID и
timestamps событий, текст, токены, URL медиа, изображения, результаты
распознавания и сырой JSON не печатаются.

Production может хранить только приватный cursor, необходимый для подавления
повторов, и грубое время события для Home Assistant. Сырая история, media,
recognition data, camera identifiers и значения cursor не должны попадать в
entities, logs или diagnostics.
