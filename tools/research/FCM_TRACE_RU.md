# Динамический захват FCM Ufanet на Android

Цель: поймать точный live payload входящего домофонного звонка и подтвердить runtime-поведение клиента 4.0.14 без MITM и без открытия двери.

## Что уже известно из статического анализа 4.0.14

Декомпилированный официальный Android-клиент версии 4.0.14 (419, `UfanetGoogle`) уже позволил восстановить:

- регистрацию через `POST /api/v0/fcm/`;
- `token_type=0` для FCM и `token_type=2` для HMS;
- logout через `DELETE /api/v0/fcm/`;
- входящий reason `sip`;
- обязательные SIP-поля `username`, `password`, `server`, `skud_id`;
- app-generated `device_id`.

`device_id` **не равен Android ID**. Клиент хранит в default SharedPreferences ключ `UUID`; при первом запуске создаётся:

```text
<device-title>_<random UUID>
```

Поэтому сравнивать его с `Settings.Secure.ANDROID_ID` больше не требуется.

## Подготовка Frida

На Windows:

```powershell
py -m pip install -U frida-tools
adb devices
adb shell getprop ro.product.cpu.abi
frida --version
```

Для текущего тестового окружения уже определено:

```text
ABI: x86_64
Frida: 17.17.0
```

Следовательно, нужен:

```text
frida-server-17.17.0-android-x86_64
```

Текущий AVD пока не даёт `adb root`: `adb shell id` возвращает `uid=2000(shell)`. Для `frida-server` проще использовать отдельный x86_64 AVD на system image `Google APIs`/debuggable, а не production `Google Play`, либо применять Frida Gadget.

Когда root доступен:

```powershell
adb root
adb shell id
adb push frida-server-17.17.0-android-x86_64 /data/local/tmp/frida-server
adb shell chmod 755 /data/local/tmp/frida-server
adb shell "/data/local/tmp/frida-server >/dev/null 2>&1 &"
frida-ps -U
```

`adb shell id` должен показать `uid=0(root)`.

## Запуск трассировки

Из корня репозитория используйте `package_name`, извлечённый только в локальный gitignored `firebase_config.json`:

```powershell
$firebaseConfig = Get-Content tools\research\fcm_probe_py\firebase_config.json | ConvertFrom-Json
$packageName = $firebaseConfig.firebase.package_name
frida -U -f $packageName -l tools\research\frida_ufanet_fcm.js
```

Точные package/class identifiers официального клиента намеренно не приводятся в документации. Трассировщик ориентирован на соответствующие классы текущего клиента и дополнительно оставляет generic Firebase hooks как fallback.

После загрузки ожидаем:

```text
[UFANET-FCM] hooked app NetworkHelper register/unregister
[UFANET-FCM] hooked app FCMService onNewToken/onMessageReceived
[UFANET-FCM] hooked PushBase.processMessage
[UFANET-FCM] tracer ready for <official-application-package> 4.0.14
```

## Проверка регистрации

При обычном login/перезапуске приложение вызывает Firebase `getToken()` и затем регистрацию Ufanet.

Трассировщик должен показать структуру, но скрыть чувствительные значения:

```text
[UFANET-FCM] NetworkHelper.registerDevice(...)
[UFANET-FCM]   auth = <redacted>
[UFANET-FCM]   provider_token = <redacted ...>
[UFANET-FCM]   device_id = <redacted ...>
[UFANET-FCM]   title = <redacted text ...>
[UFANET-FCM]   application = <official-application-package>
[UFANET-FCM]   os = 0
[UFANET-FCM]   token_type = 0 (FCM)
```

## Захват реального звонка

Не открывая дверь, инициируйте один обычный входящий звонок на домофоне.

Ищем блоки:

```text
[UFANET-FCM] FCMService.onMessageReceived
[UFANET-FCM]   RemoteMessage.data (... keys):
...
[UFANET-FCM] PushBase.processMessage
[UFANET-FCM]   dispatcher data (... keys):
...
```

Скрипт намеренно редактирует SIP credentials и приватные идентификаторы. Нам прежде всего нужны **имена ключей**, reason/event selector и несекретные значения протокольного типа.

Особенно важно выяснить:

1. точный ключ, значение которого равно `sip`;
2. полный набор ключей реального SIP data-message;
3. приходит ли `RemoteMessage.notification` или сообщение data-only;
4. присутствуют ли дополнительные call-state/event-type поля;
5. выполняется ли параллельно запрос к `call-history`;
6. поведение в foreground/background.

## Сохранение вывода

```powershell
frida -U -f $packageName -l tools\research\frida_ufanet_fcm.js | Tee-Object -FilePath ufanet_fcm_trace.txt
```

`ufanet_fcm_trace.txt` не добавлять в Git.

Перед передачей лога ещё раз убедитесь, что в нём нет:

- JWT/access/refresh token;
- FCM/HMS token;
- SIP username/password/server;
- contract/flat;
- реального `device_id`;
- частных адресов и иных account-specific данных.

Текущая версия tracer уже редактирует эти поля автоматически, но ручная проверка перед публикацией всё равно обязательна.

## Альтернативный путь без root: вытащить APK

Для дальнейшего статического анализа root обычно не нужен. Выполните:

```powershell
adb shell pm path $packageName
```

Команда вернёт пути `base.apk` и, возможно, split APK. Их можно скопировать:

```powershell
adb pull <путь-из-pm-path> C:\Temp\ufanet-base.apk
```

Если есть несколько split APK, полезно вытащить все. Из оригинального APK можно достать:

- Firebase resource values (`google_app_id`, sender id, project id и т. п.);
- полный `AndroidManifest.xml`;
- оригинальные `classes*.dex` для повторного decompile/smali и восстановления центрального `PushBase.processMessage()`.
