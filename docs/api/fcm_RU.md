# FCM / push-уведомления

[English version](fcm.md)

Эта страница фиксирует reverse engineering push-цепочки официального Android-клиента Ufanet, подтверждённый headless FCM flow и live-подтверждённую связь device registration с авторизацией Ufanet.

> Конкретная Firebase client configuration официального приложения намеренно не распространяется в репозитории. Пользователь извлекает её локально из собственной копии приложения через `tools/research/fcm_probe_py/extract_firebase_config.py`.

## Статус

29 августа 2026 года отдельный Windows/Python headless client успешно:

1. создал virtual Firebase/GCM installation;
2. зарегистрировал FCM token в Ufanet;
3. подключился к Google MCS;
4. получил реальный `reason=sip` push без Android/Google Play Services;
5. сопоставил тот же физический звонок с `/api/v1/skuds/call-history/`.

Headless FCM transport и путь `reason=sip` имеют статус **Confirmed**.

Официальный Android-клиент также содержит completion flow регистрации физического ключа с `data.reason=key_add`, `key_status` и `key_id`. 9 сентября 2026 года этот success path был проверен end-to-end с действительно новым ключом и реальным headless-FCM completion, поэтому `reason=key_add` имеет статус **Confirmed для проверенного success path**.

8 сентября 2026 года controlled probes дополнительно подтвердили, что device-registration endpoints связаны с состоянием авторизации: и штатный `logout_device`, и прямой FCM unregister удалили проверенную строку устройства и инвалидировали refresh JWT target, тогда как уже выданный access JWT временно продолжал работать.

## Режим интеграции Home Assistant

Начиная с версии 0.20.0 в настройках интеграции доступны `polling` и экспериментальный `fcm`. FCM регистрирует приватную virtual installation, слушает `data.reason=sip` и сразу запрашивает обновление `call-history` через существующий call coordinator. Polling остаётся включённым с минимальным интервалом 300 секунд, чтобы пропущенный push или разрыв MCS-соединения не отключил события звонков незаметно.

Текущая интеграция распознаёт `data.reason=key_add`. Этот путь не меняет проверенный SIP/call flow: он классифицирует результат регистрации ключа, немедленно обновляет physical-key coordinator и отправляет privacy-minimized событие Home Assistant `ufanet_intercom_key_enrollment`. Provider key ID и raw notification text не публикуются.

По умолчанию JSON читается из `ufanet_intercom/firebase_config.json` внутри каталога конфигурации Home Assistant. В ConfigEntry сохраняется только этот относительный путь. Firebase-значения и runtime FCM credentials остаются в локальных config/storage Home Assistant и исключены из диагностики.

Компонент намеренно не разбирает и не хранит APK. Извлечение остаётся отдельным проверяемым локальным шагом и не добавляет в Home Assistant Android resource parsers и поверхность загрузки APK.

## Firebase client configuration

Для receiver нужны значения, присутствующие в packaged resources официального Android-клиента:

```text
project_id
sender_id
app_id
package_name
api_key
```

В исходном коде интеграции/PoC нет встроенных значений этих полей.

Локальный extractor:

```cmd
py tools\research\fcm_probe_py\extract_firebase_config.py "C:\path\to\decompiled-app"
```

создаёт gitignored `firebase_config.json`:

```json
{
  "schema_version": 1,
  "firebase": {
    "project_id": "<extracted>",
    "sender_id": "<extracted>",
    "app_id": "<extracted>",
    "package_name": "<extracted>",
    "api_key": "<extracted>"
  }
}
```

Realtime Database URL и Storage bucket receiver не использует и по умолчанию extractor их не сохраняет.

## Регистрация устройства

### Android-клиент

**Observed**

При наличии Google Play Services приложение получает token через:

```text
FirebaseMessaging.getInstance().getToken()
```

и передаёт его в device-registration flow. `onNewToken()` повторяет регистрацию при ротации token.

### Ufanet FCM registration

**Confirmed**

```http
POST /api/v0/fcm/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "token": "<push-provider-token>",
  "device_id": "<device-id>",
  "title": "<device-title>",
  "application": "<package-name-from-local-config>",
  "os": 0,
  "token_type": 0
}
```

В Android-клиенте также **Observed** `token_type = 2` для HMS.

### `device_id`

**Observed**

`device_id` — installation-scoped идентификатор, а не Android hardware ID. Клиент сохраняет стабильное значение формата:

```text
<device-title>_<random UUID>
```

и использует повторно. Headless PoC делает эквивалентный локальный installation ID.

### Unregister / advanced FCM cleanup

**Confirmed**

```http
DELETE /api/v0/fcm/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "device_id": "<device-id>"
}
```

Первый probe подтвердил HTTP 200 удаления/восстановления собственной virtual registration. Более точный `fcm_delete_jwt_probe.py` проверил authorization side effect: независимый observer удалил disposable subject registration только через `DELETE /api/v0/fcm/`; `logout_device` ни разу не вызывался. После DELETE:

- target исчез из `authorized_devices`;
- уже выданный access JWT target продолжил возвращать HTTP 200;
- refresh JWT target стал возвращать HTTP 401;
- независимый observer access JWT остался рабочим;
- probe восстановил device свежим JWT login и повторной FCM registration.

Поэтому прямой FCM unregister **разрушает проверенную refresh-авторизацию** и не должен описываться как безобидная отписка от push.

Штатная cleanup-логика интеграции по-прежнему удаляет только строго проверенную собственную `Home Assistant_<UUID>` registration при отключении FCM или удалении ConfigEntry. Обычные reload/restart Home Assistant регистрацию сохраняют.

## Инвентарь авторизованных устройств / регистраций

**Confirmed**

```http
POST /api/v4/fcm_device/authorized_devices/
Authorization: JWT <UFANET_ACCESS>
```

Request body отсутствует. Plain JWT controller, который вообще не регистрировался в FCM, успешно читает этот endpoint. Live-confirmed ответ содержит `data.device_list`. Текущий Android DTO использует `device_id`, nullable `title`, `last_update` и `is_call_access`; сервер также вернул `os` и `os_display`.

Обезличенный структурный пример:

```json
{
  "data": {
    "device_list": [
      {
        "device_id": "<opaque-device-id>",
        "title": "<device-title>",
        "last_update": "<offset-aware ISO-8601>",
        "is_call_access": true,
        "os": 0,
        "os_display": "Android"
      }
    ],
    "devices_num_permission": false
  }
}
```

`last_update` трактуется как provider activity time, а не время входа. На проверенном аккаунте `os=0` коррелировал с `Android`, но это не универсальная подтверждённая enum-таблица. `devices_num_permission` наблюдается live, точная operational-семантика не подтверждена.

Главное ограничение: это **не исчерпывающий независимый список всех JWT**. Live-тест показал, что строка исчезает после прямого FCM unregister, хотя уже выданный access JWT ещё может работать. Endpoint следует считать provider device/registration inventory, который использует официальный UI активных устройств и связанные authorization actions.

## Отзыв авторизации устройства

**Confirmed**

```http
POST /api/v4/fcm_device/logout_device/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "device_id": "<device-id>"
}
```

Официальный Android UI вызывает endpoint для выбранного не-текущего устройства и реализует «завершить все остальные сессии» последовательными вызовами для других строк.

Controlled live-тест подтвердил cross-session effect без FCM у controller:

1. plain `auth_by_contract` controller без FCM registration запросил `authorized_devices`;
2. выбрал другое тестовое устройство;
3. `logout_device` вернул HTTP 200;
4. target исчез из inventory;
5. существующий access JWT target продолжил возвращать HTTP 200;
6. refresh JWT target стал возвращать HTTP 401;
7. controller/observer authorization осталась рабочей.

Поэтому `logout_device` является канонической Ufanet-операцией **отзыва авторизации устройства**, несмотря на namespace `fcm_device`.

## Home Assistant services управления устройствами

Текущая интеграция разделяет обычный отзыв авторизации и advanced FCM cleanup:

```text
list_authorized_devices
revoke_authorized_device
revoke_other_authorized_devices

list_fcm_registrations
unregister_fcm_registration
unregister_other_fcm_registrations
```

Обычные authorization services используют `logout_device`. Advanced FCM services используют `DELETE /api/v0/fcm/` и явно предупреждают, что проверенная refresh-авторизация target инвалидируется, хотя `logout_device` не вызывается.

Публичные строки используют opaque `authorization_ref` или `fcm_ref`. Raw provider `device_id` и FCM token никогда не возвращаются. Доказанно принадлежащие Home Assistant registrations защищены по private local state; при невозможности проверить ownership destructive-действия fail closed. Массовые операции требуют точного expected count из текущего snapshot и отменяются при изменении inventory.

Исторические сервисы:

```text
list_fcm_sessions
revoke_fcm_session
revoke_other_fcm_sessions
```

сохранены как compatibility aliases. Несмотря на названия, revoke-сервисы вызывают `logout_device`; для новых automations нужно использовать canonical authorized-device names.

Вкладка **УСТРОЙСТВА** использует canonical authorization services, а advanced FCM cleanup вынесен в отдельный сворачиваемый технический раздел. UI live-проверен: тестовые записи успешно удаляются, собственная Home Assistant registration остаётся protected.

## Headless transport

**Confirmed**

```text
local firebase_config.json
        |
        v
Firebase Installation registration
        |
        v
GCM/Android check-in + registration
        |
        v
FCM registration token
        |
        v
POST /api/v0/fcm/
        |
        v
TLS/MCS -> mtalk.google.com:5228
        |
        v
real Ufanet data push
```

Android, Frida и Google Play Services не нужны для получения push после успешной virtual registration.

## Входящий SIP push

**Confirmed**

Обезличенная структура реального сообщения:

```json
{
  "data": {
    "contract": "<redacted>",
    "flat": "<redacted>",
    "house_id": "<redacted>",
    "password": "<redacted>",
    "reason": "sip",
    "server": "<redacted>",
    "skud_id": "<redacted>",
    "time": "<offset-aware ISO-8601>",
    "transport": "UDP",
    "username": "<redacted>",
    "uuid": "<push-event-uuid>"
  },
  "fcmMessageId": "<fcm-message-uuid>",
  "from": "<sender-id>",
  "priority": "normal"
}
```

Динамически подтверждено, что selector находится в `data.reason` и для входящего звонка равен `sip`. Android call path использует как минимум `username`, `password`, `server`, `skud_id`; UUID истории звонков для live-start не требуется.

## FCM completion регистрации физического ключа

**Confirmed для проверенного success path**

Клиент содержит completion path с `data.reason = key_add`. Наблюдаемая success-логика использует `key_status` и `key_id`: успех требует `key_status == 0` и корректного parseable `key_id`; в наблюдаемом payload нет `skud_id`.

Интеграция обрабатывает сообщение без provider identifiers:

```text
FCM reason=key_add
        |
        +--> классификация success/error
        |
        +--> немедленный UfanetKeyPassageCoordinator refresh
        |        |
        |        v
        |    POST /api/v4/key/list/
        |
        v
ufanet_intercom_key_enrollment
```

Публичное событие Home Assistant содержит только `type`, `source`, `result`, `received_at`, `inventory_refresh_succeeded`. Provider `key_id`, notification `title`/`body` и raw push не сохраняются в событии или diagnostics.

Так как в сообщении не наблюдался `skud_id`, событие намеренно остаётся account-level. Фактическая связь ключа с домофоном определяется после refresh по `devices` в inventory ключей.

## Связь push и call-history

**Confirmed для `reason=sip`**

Для одного физического вызова:

```text
push.data.time == call-history.called_at   (совпало до секунды)
push.data.uuid != call-history.uuid
```

Следовательно, `push.data.uuid` не является durable UUID записи истории, `fcmMessageId` — отдельный FCM delivery identifier, а `call-history.uuid` — канонический устойчивый ID завершённого/архивного события.

## Архитектура Home Assistant

Для звонков:

```text
FCM reason=sip
   |
   +--> immediate UfanetCallCoordinator refresh
              |
              v
       call-history UUID
              |
       durable event + media/archive
```

Для completion регистрации физического ключа:

```text
FCM reason=key_add
   |
   +--> immediate key inventory refresh
   |
   +--> privacy-minimized account-level completion event
```

Push — low-latency wake-up/completion signal. `call-history` остаётся authoritative source устойчивой идентичности и media звонка; `/api/v4/key/list/` является authoritative inventory после регистрации ключа. Периодический polling сохраняется как fallback.

## Research latency probe

Windows/Python PoC после каждого SIP push проверяет `call-history` на offsets `0, 0.25, 0.5, 1, 2, 5` seconds. В четырёх последовательных live-тестах 29 августа 2026 года совпадающая запись каждый раз находилась первым запросом. Запрос завершался через 0,446–0,916 секунды после push (медиана 0,613 секунды), разница timestamp push/history составляла 0–1 секунду. Интеграция всё равно выполняет короткие повторные refresh для network jitter и более медленной публикации.

## Live-проверка completion физического ключа

9 сентября 2026 года physical-key completion path подтверждён end-to-end:

1. Home Assistant включил реальное 60-секундное окно enrollment через `auto_collect/enable`;
2. действительно новый ключ был приложен и зарегистрирован;
3. активный headless listener получил настоящие `reason=key_add` completion pushes;
4. проверенный success соответствовал `key_status == 0` и parseable `key_id`;
5. немедленный refresh key inventory остался healthy, зарегистрированный ключ присутствовал.

В отдельном no-key тесте полное 60-секундное окно истекло без дополнительного `reason=key_add` completion push. HTTP 400, `key_status != 0` и отдельный FCM error completion в этом случае не наблюдались, поэтому provider-specific error semantics остаются нехарактеризованными и не додумываются.

Обезличенное подтверждение находится в `key_enrollment_live_2026-09-09.md`.

## Безопасность

Не публиковать и не коммитить:

- `firebase_config.json`;
- `fcm_state.json`;
- FCM/GCM registration tokens;
- Firebase Installation auth/refresh credentials;
- Android/GCM security token;
- WebPush private key/auth secret;
- Ufanet JWT;
- raw provider device IDs из account inventory;
- реальные SIP username/password/server;
- `external_id` физического ключа и provider `key_id`;
- private account/location identifiers.

Хотя Firebase Android client config поставляется внутри клиентского APK, проект сознательно не распространяет конфигурацию чужого Firebase project и получает её только локально из пользовательской копии приложения.
