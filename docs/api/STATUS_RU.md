# Матрица проверки API

[English version](STATUS.md)

Эта таблица — компактный индекс того, что проект действительно проверял. Все оговорки и детали находятся на соответствующих страницах документации.

| Раздел | Метод / endpoint | Статус | Примечание |
|---|---|---|---|
| Auth | `POST /api/v1/auth/auth_by_contract/` | **Confirmed** | Договор/пароль -> access + refresh JWT |
| Auth | `POST /api/v1/auth/refresh/` | **Confirmed** | Обновление токена |
| Auth | `POST cloud.ucams.ru/api/v0/auth/?ttl=20800` | **Confirmed** | JWT Ufanet -> токен UCAMS |
| Account | `GET /api/v0/contract/` | **Confirmed** | Доступность подтверждена; схема ещё не описана |
| Account | `GET /api/v0/object/` | **Confirmed** | Доступность подтверждена; схема ещё не описана |
| FCM | `POST /api/v0/fcm/` | **Confirmed** | Тело регистрации из Android 4.0.14 успешно использовано headless Windows/Python client |
| FCM | Headless FIS/GCM/MCS receive | **Confirmed** | Без Android/Google Play Services получен реальный Ufanet push через `mtalk.google.com:5228` |
| FCM | `DELETE /api/v0/fcm/` | **Confirmed** | Probe удалил только собственную виртуальную регистрацию с HTTP 200 и восстановил её через POST HTTP 200 |
| FCM | `POST /api/v4/fcm_device/authorized_devices/` | **Observed** | Android-клиент получает список устройств и metadata доступа к звонкам |
| FCM | `POST /api/v4/fcm_device/logout_device/` | **Observed** | Android-клиент отправляет `{device_id}` для отзыва другого устройства/сессии |
| Push | `data.reason = "sip"` | **Confirmed** | Реальный payload содержит `username`, `password`, `server`, `skud_id`, `transport`, `contract`, `house_id`, `flat`, `time`, `uuid`; `from=<sender-id>`, priority `normal` |
| SKUD | `GET /api/v0/skud/shared/` | **Confirmed** | Возвращает протестированный домофон |
| SKUD | `GET /api/v0/skud/` | **Observed** | На тестируемом аккаунте вернул `[]` |
| Дверь | `GET /api/v0/skud/shared/<id>/open/?door=1` | **Confirmed** | Физическое действие; успешный `{"result":true}` |
| UCAMS | `POST /api/v0/cameras/this/` | **Confirmed** | Метаданные камеры/сервера/токенов |
| Live | `.../<camera>/index.m3u8?...` | **Confirmed** | HTTP 200 |
| Snapshot | `/api/v0/screenshots/<camera>.jpg?...` | **Confirmed** | Снимок работает |
| Архив | `recording_status.json?...request=ranges...` | **Confirmed** | Диапазоны `{from,duration}` |
| Архив | `archive-<start>-<duration>.m3u8` | **Confirmed** | HTTP 200 |
| Архив | `archive-<start>-<duration>.mp4` с `token_r` | **Not supported** | HTTP 403 в проверенной форме |
| Звонки | `GET /api/v1/skuds/call-history/` | **Confirmed** | История с offset-aware `called_at` |
| Звонки | `POST /api/v1/cctv/history/` | **Confirmed** | URL preview/archive MP4 с токенами |
| Shared access | `GET /api/v4/token/shared/users/` | **Confirmed** | Пользователи с принятым доступом |
| Shared access | `POST /api/v4/token/shared/create_token/` | **Confirmed** | Создание invitation token |
| Shared access | `POST /api/v4/token/shared_device/` | **Confirmed** | Получатель принимает токен |
| Shared access | `POST /api/v4/token/delete/` | **Confirmed** | Отзыв принятого доступа |
| Временный гость | `GET /api/v1/skuds/skud_share_open/` | **Confirmed** | Список ссылок |
| Временный гость | `POST /api/v1/skuds/skud_share_open/` | **Confirmed** | `time` в минутах; проверено 3 часа |
| Временный гость | `DELETE /api/v1/skuds/skud_share_open/` | **Confirmed** | Отзыв проверен |

## Правило обновления

При новом результате:

- обновляйте эту матрицу и подробную страницу одним commit;
- не ставьте **Confirmed** только на основании декомпилированного кода клиента;
- статус **Not supported** относится только к точно проверенной форме запроса;
- не публикуйте данные конкретного аккаунта и credentials.
