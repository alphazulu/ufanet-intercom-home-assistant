# Headless FCM для Ufanet

Цель: получать push Ufanet непосредственно на Linux/Home Assistant без Android-эмулятора и Google Play Services, не распространяя Firebase client configuration стороннего приложения в репозитории.

## Источник Firebase configuration

В packaged resources официального Android-клиента присутствуют необходимые client-side Firebase параметры. Репозиторий намеренно не фиксирует их конкретные значения.

Для headless receiver нужны:

- Android package/application id;
- Firebase project id;
- sender/project number;
- Firebase app id;
- Firebase client API key.

Пользователь извлекает их **локально из собственной копии официального приложения** с помощью:

```text
tools/research/fcm_probe_py/extract_firebase_config.py
```

Extractor создаёт локальный `firebase_config.json`, который находится в `.gitignore`.

Realtime Database URL и Storage bucket для FCM receiver не нужны и по умолчанию extractor их не сохраняет.

## Почему Android не обязателен

Существуют client-side реализации FCM protocol, которые выполняют Firebase Installation registration, Android/GCM check-in и получают сообщения через постоянное Google MCS соединение (`mtalk.google.com:5228`).

Практически полезные reference implementations:

- `github.com/morhaviv/go-fcm-receiver` — Go, MIT;
- `github.com/agusibrahim/fcm_receiver.rs` — Rust;
- `push-receiver-v2` — Node.js;
- Python package `firebase-messaging`, используемый research PoC и интеграцией.

## Подтверждённый PoC

```text
local user-owned app resources
        |
        v
extract_firebase_config.py
        |
        v
firebase_config.json (local, gitignored)
        |
        v
virtual FCM registration
        |
        +--> FCM token
        +--> AndroidId/securityToken
        +--> local crypto keys
        |
        | POST /api/v0/fcm/ через Ufanet JWT
        v
Ufanet backend associates virtual installation
        |
        v
mtalk.google.com:5228 TLS/MCS
        |
        v
incoming Ufanet data message
        |
        v
sanitize + dispatch supported reason
```

Headless Windows/Python flow подтверждён реальным `reason=sip` push. После первого успешного получения сообщения credentials виртуального FCM device должны сохраняться и переиспользоваться, а не генерироваться при каждом старте.

## Реализованная архитектура Home Assistant

Начиная с интеграционного FCM flow, production Home Assistant уже реализует основные элементы первоначально исследованной архитектуры:

1. загрузку Firebase client config из локальной пользовательской конфигурации;
2. Firebase Installations/FCM registration;
3. Android/GCM check-in;
4. хранение runtime FCM credentials только в private HA storage;
5. TLS connection к MCS (`mtalk.google.com:5228`);
6. protobuf framing/heartbeat/login через используемую receiver library;
7. обработку защищённого transport payload библиотекой;
8. reconnect/backoff и watchdog;
9. persistent-id deduplication;
10. callback в call coordinator при `reason=sip`, после чего authoritative `call-history` обновляется немедленно.

Polling остаётся safety path: до подтверждения здорового MCS используется обычный polling, при исправном FCM сохраняется 300-секундный контрольный опрос, а после disconnect обычный polling автоматически возвращается.

Текущая интеграция распознаёт `reason=key_add`, немедленно refresh physical-key inventory и создаёт privacy-minimized `ufanet_intercom_key_enrollment`. 9 сентября 2026 года реальный `key_add` от действительно нового ключа был live-подтверждён через headless FCM; provider `key_id`, title/body и raw push наружу по-прежнему не публикуются. Отдельный no-key timeout не дал completion push, поэтому не наблюдавшиеся provider-specific error semantics не додумываются.

Конкретная Firebase configuration официального приложения не является частью исходного кода интеграции: пользователь импортирует/извлекает её локально.

## Подтверждённые свойства SIP push

Практически подтверждено:

- selector находится в `data.reason` и равен `sip`;
- push содержит временные SIP credentials и intercom context;
- для одного и того же звонка `push.data.time` совпал с `call-history.called_at` до секунды;
- `push.data.uuid` при этом отличался от durable `call-history.uuid`.

Поэтому push используется как low-latency trigger, а `call-history.uuid` — как канонический durable ID звонка.

Android notification action lifecycle поверх подтверждённого Home Assistant call event также прошёл текущую live-validation: реальный звонок, Open door, View camera, timeout replacement, post-open replacement и supersession вторым звонком подтверждены. Недоступный отрицательный test со вторым Ufanet device отдельно waived после security review без отмены cross-device runtime guards. Это относится к Home Assistant Companion notification layer, а не к wire-семантике FCM transport.

## Сеть

Для headless push нужен исходящий доступ как минимум к:

```text
mtalk.google.com:5228/TCP
```

а также HTTPS к Firebase/Google registration endpoints и Ufanet API.

## Безопасность и границы распространения

Не коммитить и не публиковать:

- `firebase_config.json` пользователя;
- FCM token;
- Firebase Installation auth/refresh credentials;
- Android/GCM security token;
- private WebPush keys/auth secret;
- Ufanet JWT;
- реальные SIP username/password/server;
- provider physical-key identifiers из `key_add`;
- account-specific device/account/location identifiers.

Firebase Android client parameters технически распространяются внутри клиентского APK, однако этот open-source проект сознательно получает их локально из пользовательской копии и не распространяет конфигурацию чужого Firebase project как часть интеграции.
