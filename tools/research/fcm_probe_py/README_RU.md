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

### Read-only аудит активных авторизаций

Для live-проверки наблюдаемого в Android-клиенте endpoint:

```cmd
py probe.py --audit-authorized-devices
```

Этот режим **не требует `firebase_config.json`**, не выполняет Firebase/GCM check-in,
не регистрирует и не удаляет FCM device, не изменяет `fcm_state.json` и не запускает
MCS listener. Он только авторизуется в Ufanet и делает read-only по смыслу запрос
`POST /api/v4/fcm_device/authorized_devices/` без request body.

Endpoint **live-confirmed** 2 сентября 2026 года. Probe намеренно не печатает
`device_id`, title, точные `last_update`, response body или неизвестные значения.
Вывод содержит только агрегаты: количество записей, наличие ожидаемых полей, число
уникальных/дублирующихся `device_id`, распределение `is_call_access`, возрастные корзины
`last_update` без точных дат, имена неизвестных schema-полей без их значений и
тип/булево состояние `devices_num_permission`.

Имена неизвестных полей считаются schema metadata: probe может показать сам ключ,
например `application`, но никогда не показывает соответствующее ему значение.
Возраст `last_update` выводится только корзинами `<=24h`, `1-7d`, `7-30d`, `30-90d`,
`>90d`; отдельный `future`-счётчик позволяет заметить рассинхронизацию часов без
публикации точной даты.

Live-аудит 2 сентября 2026 года также подтвердил наличие полей `os` и
`os_display`. Числовая семантика `os` пока не считается подтверждённой: probe
выводит его только как ограниченный непрозрачный код `0..255`. `os_display`
сводится к фиксированным категориям `android`, `ios`, `harmonyos`, `other`.
Исходная строка `os_display` не печатается; допустимы только агрегированные
счётчики и корреляция `код -> категория`. `devices_num_permission` также
наблюдается live, но его точная бизнес-семантика пока не утверждается. Финальная
live-проверка подтвердила наблюдаемую корреляцию `0 -> android` для всех строк
проверенного ответа, однако это не считается универсальной enum-таблицей. Наличие
давно не обновлявшейся авторизованной строки также показывает, что inventory нельзя
приравнивать к списку устройств, активных прямо сейчас.

Пример безопасного вывода:

```text
[OK] POST /api/v4/fcm_device/authorized_devices/: HTTP 200
[RESULT] authorized devices audit
  total: 3
  valid_objects: 3
  invalid_entries: 0
  with_device_id: 3
  unique_device_ids: 3
  duplicate_device_ids: 0
  with_title: 3
  with_last_update: 3
  parseable_last_update: 3
  last_update_age_le_24h: 1
  last_update_age_1_7d: 1
  last_update_age_7_30d: 0
  last_update_age_30_90d: 0
  last_update_age_gt_90d: 1
  last_update_age_future: 0
  with_call_access: 3
  call_access_true: 2
  call_access_false: 1
  call_access_invalid: 0
  with_os: 3
  os_code_invalid: 0
  with_os_display: 3
  os_display_invalid: 0
  unknown_field_count: 0
  os_code_counts: 0=2, 1=1
  os_display_counts: android=2, ios=1
  os_code_display_pairs: 0->android=2, 1->ios=1
  unknown_field_names: (none)
  devices_num_permission: true
[OK] Read-only authorized devices audit completed
```

### Безопасная проверка unregister

Контракт удаления FCM-регистрации подтверждён реальным запросом. Для его повторной
безопасной проверки:

```cmd
py probe.py --verify-unregister
```

После обычной регистрации probe удалит **только свою виртуальную регистрацию** через
`DELETE /api/v0/fcm/` и сразу зарегистрирует тот же локальный `device_id` и FCM token
заново, после чего завершится без запуска listener. Флаг не удаляет другие устройства
и не выводит `device_id` или token. Если
повторная регистрация не удалась, достаточно снова запустить `py probe.py` без флага.

Компонент Home Assistant использует подтверждённый DELETE только для собственного
`Home Assistant_<UUID>` при отключении FCM или полном удалении ConfigEntry. При
обычной перезагрузке интеграции либо Home Assistant регистрация сохраняется.

### Безопасная проверка logout_device

Официальный Android-клиент завершает авторизованный сеанс запросом
`POST /api/v4/fcm_device/logout_device/` с JSON `device_id`. Для controlled live-проверки
этого destructive-контракта используется только собственная виртуальная регистрация probe:

```cmd
py probe.py --verify-logout-device
```

Probe сначала регистрирует свой обычный `ufanet_device_id`, проверяет, что именно он
присутствует в `authorized_devices`, вызывает `logout_device` только для этого ID,
проверяет его исчезновение и сразу восстанавливает ту же FCM-регистрацию. Existing
телефоны, официальные приложения и Home Assistant registrations этим режимом не
выбираются и не удаляются. Raw `device_id`, FCM token и response body не печатаются.

Этот флаг остаётся ограниченным contract-test для probe-owned регистрации. Подтверждённый
`logout_device` теперь используется в production-интеграции v0.30.0 через защищённые
`list_fcm_sessions` / `revoke_fcm_session` / `revoke_other_fcm_sessions`; probe по-прежнему
не принимает произвольный чужой `device_id` и не выбирает существующие телефоны.

## Что делает probe

1. Загружает локальную Firebase client configuration.
2. Регистрирует/проверяет virtual Firebase/GCM client.
3. Сохраняет sensitive runtime credentials в локальный `fcm_state.json`.
4. Регистрирует FCM token через Ufanet `/api/v0/fcm/`.
5. При явном `--verify-unregister` удаляет только эту регистрацию и сразу восстанавливает её.
6. При явном `--verify-logout-device` завершает только probe-owned авторизованный сеанс, проверяет исчезновение и восстанавливает его.
7. Подключается к MCS `mtalk.google.com:5228`.
8. Получает и санитизирует push.
9. Для `reason=sip` автоматически проверяет `/api/v1/skuds/call-history/` на offsets `0, 0.25, 0.5, 1, 2, 5` секунд.
10. Коррелирует запись по `called_at` относительно push `time` с дополнительной проверкой house/flat context.
11. Печатает задержку появления history record и накопительную статистику.

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
