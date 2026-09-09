# Проверка `logout_device` против JWT-сессии

Этот probe отвечает на узкий вопрос: влияет ли
`POST /api/v4/fcm_device/logout_device/` на JWT access/refresh-пару, которой была
зарегистрирована конкретная виртуальная запись устройства.

Файл:

```text
logout_jwt_probe.py
```

## Что делает тест

Probe использует только уже существующее виртуальное устройство из
`fcm_probe_py/fcm_state.json` и локальную `firebase_config.json`.

Последовательность:

1. получает/проверяет FCM token для probe-owned virtual device;
2. создаёт независимую poll-only JWT-пару `observer`;
3. создаёт отдельную JWT-пару `subject`;
4. регистрирует **только probe-owned device** через `/api/v0/fcm/`, используя `subject` access token;
5. через независимый `observer` проверяет, что probe-owned device появился в `authorized_devices`;
6. проверяет, что `subject` access token работает до logout;
7. вызывает `/api/v4/fcm_device/logout_device/` только для probe-owned `device_id`;
8. через `observer` проверяет исчезновение этого device из `authorized_devices`;
9. проверяет старый `subject` access token обычным `GET /api/v0/contract/`;
10. проверяет старый `subject` refresh token через `/api/v1/auth/refresh/`;
11. если refresh принят, проверяет новый access token;
12. отдельно проверяет, что независимый `observer` JWT продолжает работать;
13. делает свежий login и восстанавливает ту же probe-owned FCM/device registration.

## Ограничения безопасности

Probe:

- не принимает произвольный `device_id` из CLI;
- не печатает `device_id`;
- не печатает access/refresh JWT;
- не печатает FCM token;
- не печатает raw provider responses;
- не вызывает `logout_device` для телефона, Home Assistant или другой существующей записи;
- не вызывает `DELETE /api/v0/fcm/`;
- не запускает MCS listener;
- после `logout_device` пытается автоматически восстановить исходную probe-owned регистрацию через свежий login.

Это state-changing research test, но его единственная целевая серверная сущность —
виртуальное устройство, принадлежащее `fcm_probe_py`.

## Запуск

Используется то же окружение, что и у обычного FCM probe:

```cmd
cd C:\Project\ufanet\ufanet-intercom-home-assistant\tools\research\fcm_probe_py
.venv\Scripts\activate
python logout_jwt_probe.py
```

Если окружение ещё не создано:

```cmd
py -m venv .venv
.venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
python logout_jwt_probe.py
```

`firebase_config.json` и `fcm_state.json` должны находиться в том же каталоге, как
для обычного `probe.py`.

## Как читать результат

Наиболее важные строки:

```text
[RESULT] subject access after logout: ...
[RESULT] subject refresh after logout: ...
[RESULT] refreshed subject access after logout: ...
[RESULT] independent observer access after logout: ...
[SUMMARY]
  subject_access_survived_logout=...
  subject_refresh_survived_logout=...
  refreshed_subject_access_usable=...
  independent_observer_access_survived_logout=...
```

Если получим:

```text
subject_access_survived_logout=true
subject_refresh_survived_logout=true
refreshed_subject_access_usable=true
independent_observer_access_survived_logout=true
```

то это будет live-доказательством для проверенного сценария, что `logout_device`
удаляет authorized-device запись, но не отзывает JWT chain, использованную для её
регистрации.

Если старый access и refresh оба станут недействительны, а независимый observer
останется рабочим, это будет свидетельством связи `logout_device` с конкретной JWT
цепочкой, но не со всем аккаунтом.

Смешанный результат (например access работает, refresh отклонён) считается
неразрешённым до дополнительного анализа.

## Что этот тест не доказывает

Даже при полном сохранении JWT после `logout_device` тест не доказывает, что у Ufanet
вообще отсутствует отдельный серверный реестр JWT-сессий. Он проверяет только связь
известного `fcm_device/logout_device` с конкретной access/refresh-парой в контролируемом
probe-owned сценарии.
