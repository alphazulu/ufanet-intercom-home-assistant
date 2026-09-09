# Авторизация

[English version](auth.md)

> Combined validation-ветка не меняет базовую цепочку входа Ufanet/UCAMS. При этом
> live-тесты добавили подтверждённые сведения об отзыве авторизации конкретного
> устройства и о побочном authorization-эффекте FCM unregister.

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

## Авторизация устройства и отзыв refresh-цепочки

**Статус: Confirmed для проверенных flow**

8 сентября 2026 года live-тесты разделили обычную JWT-аутентификацию и FCM transport:

- controller, созданный только через `auth_by_contract` и ни разу не зарегистрированный в FCM, успешно запросил `POST /api/v4/fcm_device/authorized_devices/`;
- тот же plain-JWT controller успешно отозвал другое тестовое устройство через `POST /api/v4/fcm_device/logout_device/`;
- после `logout_device` целевая строка исчезла, уже выданный access JWT целевого устройства продолжил возвращать HTTP 200, а его refresh JWT стал возвращать HTTP 401;
- независимая controller/observer JWT-сессия осталась рабочей.

Отдельный controlled probe затем зарегистрировал disposable probe-owned FCM device с собственной JWT-парой и удалил его только через `DELETE /api/v0/fcm/`, ни разу не вызывая `logout_device`. Строка исчезла, subject access JWT продолжил возвращать HTTP 200, а subject refresh JWT стал возвращать HTTP 401. Независимый observer остался авторизован.

Следовательно, это разные серверные операции, но обе имеют live-подтверждённый destructive authorization-эффект на refresh-цепочку проверенного target:

```text
POST /api/v4/fcm_device/logout_device/
    -> строка удаляется
    -> уже выданный access JWT может жить до expiry
    -> refresh JWT проверенного target отклоняется

DELETE /api/v0/fcm/
    -> FCM/device registration удаляется
    -> уже выданный access JWT может жить до expiry
    -> refresh JWT проверенного target отклоняется
```

`authorized_devices` нельзя считать исчерпывающим независимым списком всех JWT. Live-тест показал, что строка исчезает после FCM unregister, хотя уже выданный access JWT ещё временно работает.

Поэтому Home Assistant использует `logout_device` как каноническое действие **отзыва авторизации устройства**, а прямой FCM unregister оставляет отдельным расширенным destructive-функционалом. Raw provider `device_id` пользователю не раскрывается.

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

## Дополнительные authenticated endpoint

Во время разработки успешно использовались:

```text
GET /api/v0/contract/
GET /api/v0/object/
POST /api/v0/fcm/
DELETE /api/v0/fcm/
POST /api/v4/fcm_device/authorized_devices/
POST /api/v4/fcm_device/logout_device/
```

Подробная семантика device registration находится в разделе [FCM / push-уведомления](fcm_RU.md).

## Время жизни токенов

JWT-поля `exp` используются интеграцией только для планирования refresh. Проверка
действительной авторизации всегда выполняется сервером. Нельзя считать локально
прочитанный `exp` криптографической валидацией JWT.

## Безопасность

Пароль, access/refresh JWT Ufanet и bearer token UCAMS — credentials. Они не должны
попадать в entity state, diagnostics, публичные issue, документацию или логи. В
диагностике допустимы только признаки наличия и expiry timestamp, если они не
раскрывают само значение token.

Нельзя судить о безопасности авторизации только по title, platform, age или наличию
строки в `authorized_devices`. И штатный logout, и advanced FCM unregister требуют
явного подтверждения, поскольку live-тест показал invalidation refresh-авторизации
целевой регистрации.
