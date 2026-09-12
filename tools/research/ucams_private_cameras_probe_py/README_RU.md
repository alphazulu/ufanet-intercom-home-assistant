# UCAMS private cameras probe

Read-only probe для проверки полного списка пользовательских камер UCAMS, который официальный клиент использует в разделе **«Умности → Видеонаблюдение»**.

## Что подтверждено по официальному клиенту

Официальный Android-клиент загружает личные камеры через:

```text
POST /api/v0/cameras/my/
```

Для обычного списка клиент отправляет:

```json
{
  "page": 1,
  "order_by": "addr_asc",
  "page_size": 50,
  "fields": [
    "number",
    "address",
    "title",
    "timezone",
    "analytics",
    "blocking_lvl",
    "streams_count",
    "is_public",
    "inactivity_period",
    "server",
    "tariff",
    "token_l",
    "token_r",
    "permission",
    "is_fav"
  ]
}
```

При выборе групп дополнительно используется `camera_group_ids`.

Ответ читается как пагинированный объект с `results` и `page.next/page.previous`.

## Назначение probe

Probe проверяет только read-only путь:

1. Ufanet JWT authentication;
2. `/api/v0/skud/shared/` — чтобы определить, какие камеры уже известны как домофонные;
3. UCAMS authentication;
4. все страницы `/api/v0/cameras/my/`;
5. privacy-safe capability summary для каждой камеры.

Никакие write/delete/favorite/rename/configure endpoint'ы не вызываются.

## Конфиденциальность

Probe **не печатает**:

- номера камер;
- названия камер;
- адреса;
- Ufanet/UCAMS токены;
- `token_l` / `token_r`;
- серверные домены;
- пароль.

Номера камер используются только в памяти процесса для сопоставления с камерой домофона и дедупликации страниц.

## Запуск

Из каталога probe:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python probe.py
```

Probe запросит contract/login и пароль. Пароль вводится через `getpass` и не выводится на экран.

Можно передать login отдельно:

```cmd
python probe.py --username YOUR_CONTRACT
```

Пароль специально нельзя передать аргументом командной строки.

## Ожидаемый безопасный вывод

Пример структуры вывода:

```text
[OK] Ufanet authentication: HTTP 200
[OK] GET /api/v0/skud/shared/: HTTP 200
[RESULT] known intercom cameras: total=1
[OK] UCAMS authentication: HTTP 200
[OK] POST /api/v0/cameras/my/ page 1: HTTP 200
[RESULT] private cameras: total=6 pages=1 known_intercom_cameras=1 intercom_matches=1 non_intercom_cameras=5 with_archive=4 with_analytics=3 favorites=2 marked_public=0
[RESULT] camera[1]: intercom_match=true title_present=true address_present=true timezone_present=true streams_count=1 analytics_count=1 motion_alarm=true perimeter_security=false tariff_present=true archive_hours=120 server_vendor_present=true permission_present=true is_fav=false is_public=false blocking_lvl_present=true inactivity_period_present=true
...
[OK] Read-only UCAMS private camera inventory audit completed
[PRIVACY] Camera numbers, titles, addresses, tokens and server domains were not printed
```

Значения выше являются только примером формата, а не ожидаемыми значениями конкретного аккаунта.

## Что нужно прислать после запуска

Можно прислать весь stdout probe. Он специально спроектирован так, чтобы не содержать provider camera IDs, адресов, названий, токенов или доменов.

По результату live-test мы сможем решить следующий этап интеграции:

- отдельный inventory coordinator всех пользовательских камер;
- создание HA `camera` entities для камер вне домофона;
- повторное использование live/archive/analytics capabilities по каждой доступной камере;
- сохранение домофонных функций только у камеры, связанной со SKUD.
