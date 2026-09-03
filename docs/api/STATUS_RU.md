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
| FCM | `POST /api/v4/fcm_device/authorized_devices/` | **Confirmed** | Live-проверенный POST без body возвращает `data.device_list`; подтверждены `device_id`, `title`, `last_update`, `is_call_access` и серверные metadata `os`/`os_display`. `devices_num_permission` наблюдается live, но его точная бизнес-семантика пока не подтверждена. |
| FCM | `POST /api/v4/fcm_device/logout_device/` | **Confirmed** | Controlled probe-owned сессия была видна до logout `{device_id}`, исчезла после HTTP 200, восстановлена через `/api/v0/fcm/` и снова появилась; targeted production revoke также live-проверен в Home Assistant. |
| Push | `data.reason = "sip"` | **Confirmed** | Реальный payload содержит `username`, `password`, `server`, `skud_id`, `transport`, `contract`, `house_id`, `flat`, `time`, `uuid`; `from=<sender-id>`, priority `normal` |
| SKUD | `GET /api/v0/skud/shared/` | **Confirmed** | Возвращает протестированный домофон |
| SKUD | `GET /api/v0/skud/` | **Observed** | На тестируемом аккаунте вернул `[]` |
| Возможности | `GET /api/v4/skud/features/` | **Confirmed** | Live-ответ содержал account feature `keys` |
| Домофоны | `POST /api/v0/intercoms/` | **Confirmed** | Фильтрованный запрос со страницей от `1` вернул `has_key_recording_support=true` |
| Ключи | `POST /api/v4/key/list/` | **Confirmed** | Подтверждены HTTP 200 и пустой `data.keys`; поля непустой записи остаются Observed |
| Проходы | `POST /api/v4/key/skud/<id>/key/pass_history/` | **Confirmed** | Подтверждены HTTP 200, страницы от `0` и пустой `results`; поля записи остаются Observed |
| Дверь | `GET /api/v0/skud/shared/<id>/open/?door=1` | **Confirmed** | Физическое действие; успешный `{"result":true}` |
| UCAMS | `POST /api/v0/cameras/this/` | **Confirmed** | Метаданные камеры/сервера/токенов; metadata capability `analytics` также live-подтверждена |
| Аналитика | `analytics` в metadata камеры: `motion_alarm` | **Confirmed** | Проверенная live-камера объявляет аналитику движения; используется production v0.28.0 |
| Аналитика | `analytics` в metadata камеры: `perimeter_security` | **Observed** | Capability есть в Android-клиенте, но проверенный тариф её не объявляет; production runtime её не использует |
| Аналитика | `POST /api/v0/analytics/motion_alarm/report/` | **Confirmed** | HTTP 200; envelope `count/page/results`; поля события `id/date/length`; `date` авторитетен, `id` используется только как приватный opaque cursor |
| Аналитика | `POST /api/v0/analytics/archive_events/` | **Observed** | Декомпилированный Android archive player умеет запрашивать все analytics за архивный интервал; live-подтверждения нет, production runtime endpoint не использует |
| Аналитика | пагинация motion report | **Confirmed** | `page` содержит `current/next/previous/all/page_size`; сервер вернул page size 60 при меньшем `limit`. Request-поле пагинации пока не live-подтверждено, поэтому v0.28.0 разрешает неполный report только делением подтверждённого окна `start`/`end` и не продвигает cursor за неразрешённый промежуток |
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
- не выводите непроверенные request-поля пагинации из одной только metadata ответа;
- не публикуйте данные конкретного аккаунта, credentials, camera/event identifiers, точную историю событий или raw private responses.
