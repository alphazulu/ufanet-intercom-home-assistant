# Гостевой и совместный доступ

[English version](guests.md)

Проект наблюдает два разных механизма предоставления доступа: постоянный/принятый shared access и временные гостевые ссылки.

> Combined validation-ветка уведомлений/физических ключей не меняет guest/shared
> access contracts или их evidence status. Этот раздел повторно проверен при
> обновлении документации и остаётся без функциональных изменений.

## Список временных гостевых ссылок

**Статус: Confirmed**

```http
GET https://dom.ufanet.ru/api/v1/skuds/skud_share_open/
Authorization: JWT <UFANET_ACCESS_JWT>
```

Полная схема ответа ещё документируется. Возвращаемые токены/URL являются средствами доступа и должны считаться секретами.

## Список пользователей с принятым shared access

**Статус: Confirmed**

```http
GET https://dom.ufanet.ru/api/v4/token/shared/users/?skud_id=<SKUD_ID>
Authorization: JWT <UFANET_ACCESS_JWT>
```

Используется для получения пользователей, которые уже приняли доступ к выбранному SKUD.

## Создание приглашения shared access

**Статус: Confirmed**

```http
POST https://dom.ufanet.ru/api/v4/token/shared/create_token/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "skud_id": <SKUD_ID>
}
```

Ответ содержит share token для получателя. Реальный токен нельзя публиковать в логах, issue, скриншотах и документации.

## Принятие shared access

**Статус: Confirmed по приложению/API тестам**

```http
POST https://dom.ufanet.ru/api/v4/token/shared_device/
Authorization: JWT <RECIPIENT_UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "token": "<SHARE_TOKEN>"
}
```

Операцию выполняет аккаунт получателя.

## Отзыв принятого shared access

**Статус: Confirmed — изменяет состояние**

```http
POST https://dom.ufanet.ru/api/v4/token/delete/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "contract_object_id": <ACCESS_ID>
}
```

Удаляет предоставленный доступ. В UI перед отзывом рекомендуется явное подтверждение пользователя.

## Создание временного гостевого доступа

**Статус: Confirmed — изменяет состояние**

```http
POST https://dom.ufanet.ru/api/v1/skuds/skud_share_open/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "time": "180",
  "id": <SKUD_ID>
}
```

### Семантика `time`

**Статус: Confirmed по APK и live-тесту**

`time` — строка с количеством **минут**. Мобильное приложение переводит выбранные часы в минуты (`hours × 60`).

| Время доступа | `time` |
|---|---:|
| 1 час | `"60"` |
| 3 часа | `"180"` |
| 6 часов | `"360"` |

Трёхчасовая ссылка была реально создана и успешно отозвана при тестировании.

## Удаление временного гостевого доступа

**Статус: Confirmed — изменяет состояние**

```http
DELETE https://dom.ufanet.ru/api/v1/skuds/skud_share_open/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "token": "<TEMP_GUEST_TOKEN>",
  "id": <SKUD_ID>
}
```

## Модель безопасности

Guest/share token фактически является bearer-capability: само владение токеном может быть достаточным для использования выданного доступа. Относитесь к нему как к временному credential.