# FCM / push-уведомления

[English version](fcm.md)

Эта страница фиксирует reverse engineering push-цепочки официального Android-клиента Ufanet и подтверждённый headless FCM flow.

> Конкретная Firebase client configuration официального приложения намеренно не распространяется в репозитории. Пользователь извлекает её локально из собственной копии приложения через `tools/research/fcm_probe_py/extract_firebase_config.py`.

## Статус

29 августа 2026 года отдельный Windows/Python headless client успешно:

1. создал virtual Firebase/GCM installation;
2. зарегистрировал FCM token в Ufanet;
3. подключился к Google MCS;
4. получил реальный `reason=sip` push без Android/Google Play Services;
5. сопоставил тот же физический звонок с `/api/v1/skuds/call-history/`.

Headless FCM path имеет статус **Confirmed**.

## Режим интеграции Home Assistant

Начиная с версии 0.20.0 в настройках интеграции доступны `polling` и экспериментальный `fcm`. FCM регистрирует приватную virtual installation, слушает `data.reason=sip` и сразу запрашивает обновление `call-history` через существующий call coordinator. Polling остаётся включённым с минимальным интервалом 300 секунд, чтобы пропущенный push или разрыв MCS-соединения не отключил события звонков незаметно.

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

в SharedPreferences и использует повторно.

Headless PoC делает эквивалентный локальный installation ID.

### Unregister

**Observed**

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

Также в Android-клиенте наблюдаются endpoints управления авторизованными push-устройствами семейства `/api/v4/fcm_device/`; они ещё не являются live-confirmed частью проекта.

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

Динамически подтверждено, что selector находится в `data.reason` и для входящего звонка равен `sip`.

Android call path использует как минимум:

```text
username
password
server
skud_id
```

для немедленного SIP flow. UUID истории звонков для live-start не требуется.

## Связь push и call-history

**Confirmed**

Для одного и того же физического вызова:

```text
push.data.time == call-history.called_at   (совпало до секунды)
push.data.uuid != call-history.uuid
```

Следовательно:

- `push.data.uuid` — не durable UUID записи истории;
- `fcmMessageId` — отдельный идентификатор FCM delivery/message;
- канонический устойчивый ID завершённого/архивного события берётся из `call-history.uuid`.

Предыдущие два SIP push с интервалом около 12 секунд были двумя отдельными сделанными тестовыми вызовами, а не доказанными retries одного звонка.

## Целевая архитектура Home Assistant

```text
FCM reason=sip
   |
   +--> immediate transient incoming/ringing event
   |
   +--> immediate UfanetCallCoordinator refresh
              |
              v
       call-history UUID
              |
       durable event + media/archive
```

Push — low-latency wake-up signal. `call-history` остаётся authoritative source для durable identity и media. Периодический polling сохраняется как fallback и после стабилизации push может выполняться существенно реже.

## Research latency probe

Windows/Python PoC после каждого SIP push проверяет `call-history` на offsets:

```text
0, 0.25, 0.5, 1, 2, 5 seconds
```

и измеряет верхнюю границу времени появления записи. Это используется для выбора production retry/backoff.

В четырёх последовательных live-тестах 29 августа 2026 года совпадающая запись каждый раз находилась уже первым запросом. Запрос завершался через 0,446–0,916 секунды после push (медиана 0,613 секунды), разница timestamp push/history составляла 0–1 секунду. Во всех четырёх образцах UUID push отличался от устойчивого UUID истории. Интеграция всё равно выполняет короткие повторные refresh, чтобы учесть сетевой jitter и более медленную публикацию call-history.

## Безопасность

Не публиковать и не коммитить:

- `firebase_config.json`;
- `fcm_state.json`;
- FCM/GCM registration tokens;
- Firebase Installation auth/refresh credentials;
- Android/GCM security token;
- WebPush private key/auth secret;
- Ufanet JWT;
- реальные SIP username/password/server;
- private account/location identifiers.

Хотя Firebase Android client config по своей природе поставляется внутри клиентского APK, проект сознательно не распространяет конфигурацию чужого Firebase project и получает её только локально из пользовательской копии приложения.
