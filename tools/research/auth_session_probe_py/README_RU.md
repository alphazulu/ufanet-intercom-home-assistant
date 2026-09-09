# Ufanet auth-session probe

Privacy-safe probe для проверки отношения между обычной JWT-авторизацией Ufanet и `/api/v4/fcm_device/authorized_devices/`.

## Что именно проверяется

Ufanet позволяет получить обычную пару `access`/`refresh` через:

```http
POST /api/v1/auth/auth_by_contract/
```

без обязательной регистрации FCM. Этот probe проверяет, меняется ли membership списка:

```http
POST /api/v4/fcm_device/authorized_devices/
```

после:

1. второй независимой авторизации по contract/password без `/api/v0/fcm/`;
2. обычных read-only/poll запросов с новым access JWT;
3. обновления JWT через `/api/v1/auth/refresh/` и повторных poll запросов.

Цель — получить live evidence, является ли `authorized_devices` полным списком JWT-сессий либо отдельным device/FCM-oriented inventory.

## Важная граница вывода

Если membership `authorized_devices` не изменится, это подтверждает только следующее:

> дополнительная рабочая JWT-авторизация и её refresh не создают видимую запись в `/api/v4/fcm_device/authorized_devices/` на проверенном аккаунте.

Это **не доказывает**, что Ufanet вообще не ведёт отдельный server-side реестр access/refresh JWT. Probe проверяет только доступный endpoint `authorized_devices`.

## Безопасность

Probe:

- выполняет две обычные JWT-авторизации;
- выполняет один JWT refresh;
- делает только обычные GET/poll запросы `/api/v0/contract/` и `/api/v0/skud/shared/`;
- читает `/api/v4/fcm_device/authorized_devices/`;
- **не вызывает** `POST /api/v0/fcm/`;
- **не вызывает** `DELETE /api/v0/fcm/`;
- **не вызывает** `/api/v4/fcm_device/logout_device/`;
- не отзывает существующие устройства или токены;
- не открывает дверь и не меняет настройки аккаунта;
- не пишет пароль/JWT/device IDs на диск;
- не печатает JWT, `device_id`, title, timestamps или raw response bodies.

Следует учитывать, что сама авторизация создаёт новую пару access/refresh JWT, которая может оставаться действительной до серверного expiry. Известного generic revoke endpoint для этой пары проект пока не подтвердил.

## Установка

```cmd
cd tools\research\auth_session_probe_py
py -m venv .venv
.venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

## Запуск

```cmd
py probe.py
```

или:

```cmd
py probe.py --contract <UFANET_CONTRACT>
```

Пароль всегда запрашивается через `getpass` и не отображается.

## Ожидаемый безопасный вывод

Пример, если обычная JWT-авторизация не влияет на `authorized_devices`:

```text
[INFO] This probe performs two JWT logins and one JWT refresh, but does not register FCM, unregister FCM, log out devices, or persist credentials.
[OK] baseline Ufanet authentication: HTTP 200
[OK] authorized_devices baseline: HTTP 200
[RESULT] baseline authorized-device count: 3
[OK] independent poll-only Ufanet authentication: HTTP 200
[OK] authorized_devices after second login: HTTP 200
[RESULT] second login vs baseline: before=3 after=3 membership_unchanged=true added=0 removed=0
[OK] poll-only GET /api/v0/contract/: HTTP 200
[OK] poll-only GET /api/v0/skud/shared/: HTTP 200
[OK] authorized_devices after poll-only requests: HTTP 200
[RESULT] poll-only requests vs post-login: before=3 after=3 membership_unchanged=true added=0 removed=0
[OK] Ufanet token refresh: HTTP 200
[RESULT] refresh token rotation: access_changed=true refresh_changed=true
[OK] poll-only GET /api/v0/contract/: HTTP 200
[OK] poll-only GET /api/v0/skud/shared/: HTTP 200
[OK] authorized_devices after JWT refresh: HTTP 200
[RESULT] JWT refresh vs pre-refresh: before=3 after=3 membership_unchanged=true added=0 removed=0
[SUMMARY]
  second_login_changed_authorized_device_membership=false
  poll_requests_changed_authorized_device_membership=false
  jwt_refresh_changed_authorized_device_membership=false
  fcm_registration_requests_sent=false
  logout_or_revoke_requests_sent=false
  secrets_persisted=false
[CONCLUSION] Additional poll-only JWT authentication and refresh did not change authorized_devices membership during this test.
```

Количество устройств в примере условное. В реальном выводе допустимо публиковать только агрегаты; raw device IDs и JWT публиковать не следует.

Если membership неожиданно изменится, не делайте немедленный вывод о причинности: возможна параллельная активность официального приложения/другого устройства. Повторите тест в спокойный период и сравните результат.
