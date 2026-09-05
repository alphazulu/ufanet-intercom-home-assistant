# Авторизация

[English version](auth.md)

> Combined validation-ветка уведомлений/физических ключей не меняет Ufanet/UCAMS
> authentication chain. Этот раздел повторно проверен при обновлении документации;
> существующие Confirmed claims сохраняются.

## Авторизация Ufanet по договору

**Статус: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/auth/auth_by_contract/
Content-Type: application/json
```

```json
{
  "contract": "<LOGIN_OR_CONTRACT>",
  "password": "<PASSWORD>"
}
```

Успешный ответ содержит пару JWT:

```text
token.access
token.refresh
```

Ufanet API использует access token в форме:

```http
Authorization: JWT <UFANET_ACCESS>
```

## Обновление Ufanet JWT

**Статус: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/auth/refresh/
Content-Type: application/json
```

```json
{
  "token": "<UFANET_REFRESH>"
}
```

Ответ возвращает новые `access` и `refresh` значения. Интеграция не должна
логировать старый или новый token.

## Авторизация UCAMS

**Статус: Confirmed**

После получения Ufanet JWT клиент обменивает его на UCAMS token:

```http
POST https://cloud.ucams.ru/api/v0/auth/?ttl=20800
Authorization: JWT <UFANET_ACCESS>
```

Успешный ответ содержит:

```json
{
  "token": "<UCAMS_TOKEN>"
}
```

Дальнейшие запросы управляющего UCAMS API используют:

```http
Authorization: Bearer <UCAMS_TOKEN>
```

## Время жизни токенов

JWT-поля `exp` используются интеграцией только для планирования refresh. Проверка
действительной авторизации всегда выполняется сервером. Нельзя считать локально
прочитанный `exp` криптографической валидацией JWT.

## Безопасность

Пароль, access/refresh JWT Ufanet и bearer token UCAMS — credentials. Они не должны
попадать в entity state, diagnostics, публичные issue, документацию или логи. В
диагностике допустимы только признаки наличия и expiry timestamp, если они не
раскрывают само значение token.