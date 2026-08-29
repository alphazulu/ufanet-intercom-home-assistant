# Python headless FCM probe для Windows

Отдельный research-PoC для проверки Ufanet FCM/MCS без Android и Google Play Services.

## Принцип конфигурации

Репозиторий **не содержит Firebase-конфигурацию приложения Ufanet**. Project ID, sender ID, app ID, package name и Firebase client API key пользователь извлекает локально из своей копии официального приложения.

Для этого используется:

```text
extract_firebase_config.py
```

Результат сохраняется локально в:

```text
firebase_config.json
```

Файл добавлен в `.gitignore` и не должен попадать в git, issue или чат.

## Что извлекается

Обязательные для headless receiver поля:

```text
project_id
sender_id
app_id
package_name
api_key
```

`database_url` и `storage_bucket` receiver не использует. При необходимости extractor может сохранить их только с `--include-unused`.

## Подготовка исходников

Extractor принимает:

- каталог после JADX/apktool/decompile;
- `strings.xml`/`resources.xml`;
- `BuildConfig.java`.

Для надёжного автоматического определения `package_name` лучше передавать корневой каталог декомпилированного приложения, где доступны и resources XML, и app-level `BuildConfig.java`/manifest.

Пример:

```cmd
cd tools\research\fcm_probe_py
py extract_firebase_config.py "C:\Temp\ufanet-decompiled"
```

Ожидаемый результат:

```text
[OK] Firebase config written to: ...\firebase_config.json
[OK] package_name: ...
[OK] project_id: ...
[OK] sender_id: ...
[OK] app_id present: yes (sha256=...)
[OK] api_key present: yes (sha256=...)
[INFO] The API key value is intentionally not printed.
```

Если передан только resources XML и package name из него определить невозможно:

```cmd
py extract_firebase_config.py "C:\Temp\resources.xml" --package-name <package>
```

Если декомпиляция содержит несколько flavors/modules и extractor видит несколько разных кандидатов, он завершится с ошибкой вместо того, чтобы угадывать. Нужное значение можно явно задать параметрами `--project-id`, `--sender-id`, `--app-id`, `--package-name` или `--api-key`.

## Формат локального файла

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

Значения в примере намеренно отсутствуют.

## Установка PoC

```cmd
cd tools\research\fcm_probe_py
py -m venv .venv
.venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

## Запуск

После создания `firebase_config.json`:

```cmd
py probe.py
```

или с явным путём:

```cmd
py probe.py --firebase-config "C:\Private\firebase_config.json"
```

Probe запросит Ufanet contract/login и password. Пароль вводится через `getpass`.

## Что делает probe

1. Загружает локальную Firebase client configuration.
2. Регистрирует/проверяет virtual Firebase/GCM client.
3. Сохраняет sensitive runtime credentials в локальный `fcm_state.json`.
4. Регистрирует FCM token через Ufanet `/api/v0/fcm/`.
5. Подключается к MCS `mtalk.google.com:5228`.
6. Получает и санитизирует push.
7. Для `reason=sip` автоматически проверяет `/api/v1/skuds/call-history/` на offsets `0, 0.25, 0.5, 1, 2, 5` секунд.
8. Коррелирует запись по `called_at` относительно push `time` с дополнительной проверкой house/flat context.
9. Печатает задержку появления history record и накопительную статистику.

Probe не содержит кода открытия двери.

## State file

`fcm_state.json` содержит чувствительные runtime credentials:

- FCM/GCM tokens;
- Android check-in ID/security token;
- Firebase Installation credentials;
- WebPush private key/auth secret;
- generated installation ID;
- MCS persistent IDs.

Этот файл также находится в `.gitignore`.

При первом запуске после перехода на `firebase_config.json` существующий state автоматически привязывается к fingerprint Firebase application identity. Если затем подменить конфиг на другую Firebase application, probe откажется использовать старые credentials вместо неявного смешивания двух приложений.

## Подтверждённые результаты исследования

На реальном тесте headless Windows/Python client получил Ufanet `reason=sip` push без Android. Для одного и того же вызова также подтверждено:

```text
push.data.time == call-history.called_at  (до секунды)
push.data.uuid != call-history.uuid
```

Поэтому push используется как low-latency trigger, а UUID из `call-history` — как durable identity звонка.

## Безопасность

Не публикуйте:

- `firebase_config.json`;
- `fcm_state.json`;
- FCM/FIS/GCM runtime credentials;
- WebPush private keys;
- Ufanet JWT;
- SIP credentials из push;
- private account/location identifiers.

Хотя Firebase Android client configuration технически предназначена для поставки внутри клиентского приложения, проект сознательно не распространяет конфигурацию чужого Firebase project и получает её только локально из пользовательской копии приложения.
