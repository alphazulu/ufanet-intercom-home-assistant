# Аналитические события камер UCAMS

[English version](analytics.md)

Здесь зафиксирован read-only контракт аналитики камер UCAMS, наблюдавшийся в
официальном Android-клиенте, подтверждённые live-части этого контракта и
privacy-safe production-поведение, реализованное в Ufanet Intercom v0.28.0.

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
или `offset`, поэтому v0.28.0 намеренно их не выдумывает. Production runtime:

1. проверяет `count`/`page`, чтобы определить полноту возвращённого временного
   окна;
2. сразу нормализует полное окно;
3. если после baseline окно неполное, рекурсивно делит только уже подтверждённый
   интервал `start`/`end` и запрашивает более узкие окна;
4. не продвигает cursor, если окно остаётся слишком плотным и его нельзя
   безопасно разрешить.

Таким образом переполнение обрабатывается fail-closed: отдельный poll может
завершиться ошибкой, но невиденные события не будут молча потеряны из-за
продвижения cursor за необработанный промежуток.

## Replay cursor и baseline первого poll

Provider `id` никогда не публикуется как пользовательские данные Home Assistant.
Production хранит только приватный cursor для каждой камеры: точное последнее
UTC `date` и множество ID, уже увиденных на этой же временной отметке.

Важное поведение v0.28.0:

- дробная точность timestamp сохраняется в private storage, поэтому reload не
  сдвигает cursor назад и не повторяет уже обработанное событие;
- ID с одинаковым timestamp сохраняются для детерминированной дедупликации;
- первый успешный poll устанавливает baseline и не воспроизводит существующую
  историю;
- если первый poll пустой, baseline устанавливается на время poll, а не Unix
  epoch;
- последующие запросы используют небольшой overlap вокруг приватного cursor, а
  повторы удаляются самим cursor;
- lookback аналитики ограничен и не превращается в неограниченный replay
  истории.

Обновление cursors транзакционно для всех камер. Если запрос одной камеры или
запись private storage завершается ошибкой, transient events очищаются, а cursor
state всего poll откатывается.

## Поверхность Home Assistant в v0.28.0

Для домофона, камера которого объявляет `motion_alarm`, интеграция создаёт:

- Home Assistant `EventEntity` **«Обнаружено движение»**;
- событие шины Home Assistant `ufanet_intercom_motion`;
- device trigger `motion_detected` для визуального редактора автоматизаций.

EventEntity публикует только `occurred_at`. Внутреннее bus-событие может
содержать ссылку на домофон/HA device, необходимую для маршрутизации
автоматизации, но не раскрывает номер камеры UCAMS, provider event/cursor ID,
`length`, raw history, media, screenshots, recognition output или произвольные
поля ответа.

Обнаружение Motion entity восстанавливается динамически: если UCAMS analytics
недоступна при первоначальном setup, последующий успешный capability refresh
может добавить сущность без reload ConfigEntry.

Analytics coordinator работает с низкой частотой опроса — обычно раз в 60
секунд. Это источник событий для автоматизаций, а не мгновенный security-alarm
transport.

## Модель событий таймлайна в Android-клиенте

**Статус: Observed**

В декомпилированном Android-клиенте для архивного timebar ведётся отдельный список точечных событий. Каждый `EventDataExistTimeSegment` хранит timestamp события, цвет и тип; timebar рисует timestamp узкой меткой поверх полосы наличия записи. Player запрашивает аналитику для доступного архивного интервала и не смешивает timestamps событий с диапазонами записи.

В клиенте также присутствует `POST /api/v0/analytics/archive_events/` для общего запроса архивной аналитики. Этот endpoint имеет статус только **Observed**: проект не подтверждал его live-запросом, поэтому production-код Home Assistant его не вызывает. Метки движения в архиве повторно используют уже Confirmed endpoint `POST /api/v0/analytics/motion_alarm/report/` с ограниченными окнами `start`/`end`.

При открытии analytics event официальный клиент использует playback offset примерно 18 секунд до события. Timestamp самого события не изменяется. Таймлайн Home Assistant повторяет эту UI-семантику: точечная метка остаётся на авторитетном `date`, а клик запускает запись примерно за 18 секунд до события, если этот участок архива доступен.

Авторизованный response-service Home Assistant `get_motion_events` возвращает только выбранную camera-local дату, признак поддержки, количество и нормализованные времена событий, необходимые Lovelace timeline. Номера камер UCAMS, provider event IDs, `length`, raw results, media, screenshots и recognition data не возвращаются.

## Ошибки, диагностика и граница приватности

Production-поддержка намеренно ограничена `motion_alarm`. Проект не запрашивает
распознавание лиц/номеров, thermal data, crowd analysis, helmet detection,
screenshots, свободный текст или analytics media URL.

Исследовательский probe выводит только HTTP-статусы, количества, наличие
capability, форму envelope, известные имена полей и поведение пагинации. Номера
камер, ID/timestamps событий, токены, media URL, изображения, recognition
results и raw JSON не печатаются.

На production-границе raw result немедленно сокращается до приватного cursor ID
и авторитетного `date`; лишние поля отбрасываются. Ошибки UCAMS API преобразуются
в фиксированную безопасную coordinator error без текста response body.
Диагностика содержит только агрегированные счётчики/health и тип исключения, но
не message исключения, raw events, camera identifiers или cursor values.
