# Домофон / SKUD

[English version](intercom.md)

Ufanet представляет устройства контроля доступа/домофоны как объекты SKUD.

## Получение доступных домофонов

**Статус: Confirmed**

```http
GET https://dom.ufanet.ru/api/v0/skud/shared/
Authorization: JWT <UFANET_ACCESS_JWT>
```

Наблюдаемые поля SKUD, которые использует интеграция:

```json
{
  "id": 123456,
  "role": "Домофон",
  "model": 39,
  "camera": null,
  "cctv_number": "<CAMERA_NUMBER>",
  "open_in_talk": "http",
  "open_type": "http",
  "relays": [],
  "private_status": 1,
  "scope": "owner"
}
```

Наличие и значения полей могут отличаться в зависимости от модели устройства и аккаунта. См. [models_RU.md](models_RU.md).

## `/api/v0/skud/`

**Статус: Observed**

```http
GET https://dom.ufanet.ru/api/v0/skud/
Authorization: JWT <UFANET_ACCESS_JWT>
```

Для тестируемого аккаунта этот endpoint вернул пустой массив, тогда как `/api/v0/skud/shared/` вернул реальный домофон. Поэтому нельзя считать `/api/v0/skud/` основным endpoint обнаружения устройств.

## Открытие двери

**Статус: Confirmed — физическое действие**

```http
GET https://dom.ufanet.ru/api/v0/skud/shared/<SKUD_ID>/open/?door=1
Authorization: JWT <UFANET_ACCESS_JWT>
```

Наблюдаемый успешный ответ:

```json
{
  "result": true
}
```

> **Внимание:** endpoint выполняет реальное физическое действие. Нельзя использовать его как ping/health-check, фоновую проверку или безопасный пример против действующего устройства. Приложение должно требовать явного намерения пользователя открыть дверь.

### Параметр `door`

В рамках проекта проверялось только `door=1`.

**Статус: Confirmed для `door=1`; другие значения не исследованы.**

## Связь с камерой

На проверенном устройстве поле `camera` было `null`, а идентификатор UCAMS находился в `cctv_number`. Поэтому интеграция использует `cctv_number` для получения видеоданных.

**Статус: Confirmed для протестированной модели; поведение других моделей пока не описано.**