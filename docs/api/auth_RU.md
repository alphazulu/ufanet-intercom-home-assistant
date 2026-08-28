# Авторизация

[English version](auth.md)

## Вход в Ufanet

**Статус: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/auth/auth_by_contract/
Content-Type: application/json

{
  "contract": "<LOGIN_OR_CONTRACT>",
  "password": "<PASSWORD>"
}
```

В наблюдаемом ответе присутствуют данные токенов, включая:

```json
{
  "token": {
    "access": "<UFANET_ACCESS_JWT>",
    "refresh": "<UFANET_REFRESH_JWT>"
  },
  "exp": "<...>"
}
```

Пример не является полной схемой ответа — здесь перечислены только поля, необходимые интеграции.

## Заголовок Authorization Ufanet

**Статус: Confirmed**

Авторизованные запросы к Ufanet используют:

```http
Authorization: JWT <UFANET_ACCESS_JWT>
```

Для проверенных Ufanet endpoint схема `Bearer` не используется.

## Обновление токена

**Статус: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/auth/refresh/
Content-Type: application/json

{
  "token": "<UFANET_REFRESH_JWT>"
}
```

Интеграция обновляет access token, а не держит бесконечную сессию, основанную на пароле.

## Обмен JWT Ufanet на токен UCAMS

**Статус: Confirmed**

```http
POST https://cloud.ucams.ru/api/v0/auth/?ttl=20800
Authorization: JWT <UFANET_ACCESS_JWT>
```

Наблюдаемый ответ:

```json
{
  "token": "<UCAMS_JWT>"
}
```

Значение `ttl=20800` использовалось и проверено в рамках проекта. Другие значения TTL системно не исследовались.

## Заголовок Authorization UCAMS

**Статус: Confirmed**

Дальнейшие запросы к управляющему API UCAMS используют:

```http
Authorization: Bearer <UCAMS_JWT>
```

## Дополнительные авторизованные endpoint Ufanet

Во время разработки успешно вызывались также:

```text
GET /api/v0/contract/
GET /api/v0/object/
POST /api/v0/fcm/
```

**Статус: Confirmed по доступности; семантика ответов пока полностью не описана.**

## Безопасность

- Не логируйте access/refresh JWT.
- Не добавляйте токены в примеры репозитория.
- URL медиаресурсов с токенами тоже являются временными учётными данными.
- UCAMS JWT и `token_l`/`token_r` — разные типы токенов с разным назначением.