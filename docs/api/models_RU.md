# Наблюдаемые модели данных

[English version](models.md)

Этот раздел фиксирует поля, которые реально наблюдались и используются интеграцией. Это **не** официальная схема поставщика.

## Объект SKUD/домофона

**Статус: Observed / частично Confirmed**

| Поле | Наблюдаемое назначение |
|---|---|
| `id` | идентификатор SKUD/домофона |
| `role` | роль устройства, например `Домофон` |
| `model` | числовой идентификатор модели |
| `camera` | на тестируемом устройстве может быть `null` |
| `cctv_number` | идентификатор камеры UCAMS, используемый интеграцией |
| `open_in_talk` | наблюдаемый режим открытия, например `http` |
| `open_type` | наблюдаемый режим открытия, например `http` |
| `relays` | информация о реле; на тестируемом устройстве пустой массив |
| `private_status` | числовой статус; точная семантика пока не установлена |
| `scope` | область доступа, например `owner` |
| поля адреса/названия | человекочитаемый адрес/имя; набор полей может отличаться |

Нельзя жёстко завязываться на `model == 39` или считать, что `camera` всегда `null`.

## Физический ключ

**Статус: пустой envelope Confirmed; поля непустой записи Observed из Android-клиента**

Android-модель содержит:

```text
id
external_id
name
create_date
devices
```

Production/validation parser сразу отбрасывает `external_id`. Provider `id` хранится только как private runtime identifier и не публикуется через entity state, events или diagnostics. Read-only `keys` attribute содержит только `name` и нормализованный UTC `created_at`, а связь с конкретным домофоном определяется через `devices`.

Для validation key-management публичный service API также не принимает raw provider `id`: `list_physical_keys` выдаёт локальный opaque `key_ref`, привязанный к ConfigEntry/домофону/внутреннему key ID. Перед rename этот ref повторно разрешается по свежему inventory выбранного домофона, а после write новое имя должно быть подтверждено повторным refresh.

## Метаданные камеры UCAMS

**Статус: Observed; capability `motion_alarm` Confirmed на live-проверенной камере**

Более широкий camera/media flow запрашивает поля:

```text
number
token_l
token_r
is_llhls_enabled
permission
address
title
timezone
is_fav
is_public
inactivity_period
server
analytics
tariff
is_sounding
streams_count
```

`analytics` — список capabilities. `motion_alarm` реально вернулся на live-проверенной камере и имеет статус Confirmed; `perimeter_security` известен из Android-клиента, но проверенный тариф его не объявил, поэтому статус остаётся Observed.

Production discovery аналитики в v0.28.0 запрашивает только `number` и `analytics`. Во вложенных данных `server`/`tariff` более широкого media-запроса наблюдались домен/производитель медиасервера, домен снимков и глубина архива (`dvr_hours`). Точную вложенность пока следует считать деталью реализации.

## Отчёт UCAMS `motion_alarm`

**Статус: Confirmed**

Подтверждённый ответ имеет следующую структурную модель:

```text
count
page
  current
  next
  previous
  all
  page_size
results[]
  id
  date
  length
```

Подтверждённая семантика элемента `results`:

| Поле | Значение |
|---|---|
| `id` | непрозрачный числовой provider event ID; только приватный cursor/дедупликация |
| `date` | авторитетный timestamp события в ISO-8601 UTC |
| `length` | длительность события, возвращаемая UCAMS |

Поле Android DTO `time` не используется как live wire timestamp; авторитетным является `date`. Сервер может вернуть `page_size` больше запрошенного `limit`: в live-тесте вернулось 60 при меньшем запросе.

Это **приватная wire-модель**, а не схема события Home Assistant. Production немедленно отбрасывает посторонние/неизвестные поля результата, хранит provider cursor только в private storage Home Assistant и публикует через EventEntity **«Обнаружено движение»** только грубое `occurred_at`. Подробности: [analytics_RU.md](analytics_RU.md).

## Диапазон архива

**Статус: Confirmed**

```json
{
  "from": 1700000000,
  "duration": 3600
}
```

- `from`: Unix timestamp в секундах;
- `duration`: секунды.

## Элемент истории звонков

**Статус: Observed / Confirmed для используемых полей**

```text
uuid
called_at
timezone
camera_number
address
porch
flat
```

`called_at` содержит offset и должен считаться авторитетным абсолютным временем звонка.

## Optional/null поля

Закрытый API может отличаться между аккаунтами, городами, тарифами, прошивками и моделями домофонов. Код должен:

- переносить отсутствие optional-полей;
- корректно обрабатывать явный `null`;
- не считать список enum-значений полным;
- проверять подтверждённые поля перед использованием;
- отбрасывать или редактировать неизвестные/private fields вместо публикации raw response через публичную диагностику.

## Правило добавления схем

Добавляйте поле в этот документ только если оно действительно наблюдалось в ответе API или коде клиента. Неясную семантику помечайте явно вместо догадки. Не публикуйте в примерах реальные provider key IDs/`external_id`, идентификаторы камер/событий или сырую историю конкретного аккаунта.