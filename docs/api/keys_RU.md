# Физические ключи и журнал проходов

[English version](keys.md)

Этот раздел описывает API физических ключей и событий прохода, который используют официальный Android-клиент и интеграция Home Assistant.

## Статус

Read-only формы запросов успешно проверены на реальной учётной записи. Аккаунт вернул feature `keys`, один домофон подтвердил поддержку записи ключей, а список ключей и история проходов вернули корректные пустые коллекции с HTTP 200. Поэтому envelope пустых ответов и pagination имеют статус **Confirmed**. Поля непустой записи ключа или прохода пока остаются **Observed** из Android-клиента до получения реального нового ключа.

В validation-ветке подготовлены:

- 60-секундная регистрация физического ключа;
- обработка FCM `reason=key_add`;
- read-only inventory ключей;
- privacy-safe сервисы `list_physical_keys` и `rename_physical_key`;
- Lovelace-вкладка **КЛЮЧИ** поверх этих privacy-safe HA surface.

Wire-контракты регистрации, `key_add`, непустого key item и переименования остаются **Observed**, пока не выполнен end-to-end тест реальным новым ключом. На реальной установке Home Assistant уже подтверждены пустые пути: числовой state сенсора **«Физические ключи»** равен `0`, `keys` равен `[]`, а `ufanet_intercom.list_physical_keys` вернул `count: 0`, `keys: []`.

## Возможности аккаунта

```http
GET /api/v4/skud/features/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed.** Live-ответ содержал account feature `keys`.

## Capability конкретного домофона

```http
POST /api/v0/intercoms/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

```json
{
  "page": 1,
  "page_size": 10,
  "filters": {"has_key_recording_support": true}
}
```

**Confirmed.** В `result.intercoms` подтверждены `id` и `has_key_recording_support=true`. Нумерация страниц начинается с `1`. Интеграция не создаёт enrollment/management поверхность для домофона, отсутствующего в этом capability-result.

## Список физических ключей

```http
POST /api/v4/key/list/
Authorization: JWT <UFANET_ACCESS>
```

**Confirmed для пустого envelope; поля непустой записи Observed.** Android-observed item содержит внутренний provider ID, приватный `external_id`, `name`, `create_date` и `devices`.

`external_id` рассматривается как приватный идентификатор доступа и отбрасывается сразу при нормализации ответа. Provider ID сохраняется только во внутренней runtime-памяти, поскольку он требуется для операций над конкретным ключом. Эти provider identifiers не публикуются в entity state, событиях, diagnostics или публичных service responses.

## Read-only inventory в Home Assistant

Сенсор **«Физические ключи»** сохраняет числовое состояние — количество ключей, привязанных к конкретному домофону. Его атрибут `keys` содержит только:

```yaml
keys:
  - name: "Папа"
    created_at: "2025-06-27T06:03:36+00:00"
```

Список фильтруется по `devices`, сортируется от новых к старым и не содержит provider ID. На тестовой установке live-проверено:

```yaml
state: 0
attributes:
  keys: []
```

Непустой inventory требует проверки после регистрации реального ключа.

## Privacy-safe список для операций управления

Validation-ветка также предоставляет response-service:

```text
ufanet_intercom.list_physical_keys
```

Он сначала запрашивает свежий key coordinator/inventory и для выбранного домофона возвращает только:

```yaml
count: 1
keys:
  - key_ref: "<24-hex-opaque-ref>"
    name: "Папа"
    created_at: "<UTC ISO-8601>"
```

`key_ref` — локальная непрозрачная ссылка, зависящая от ConfigEntry, выбранного SKUD и внутреннего provider ID. Raw provider ID не принимается и не возвращается. Ссылка другого домофона не разрешается для выбранного устройства.

Пустой live-вызов этого сервиса уже подтверждён (`count: 0`, `keys: []`). Непустой результат пока не live-проверен.

## Запуск регистрации физического ключа

Официальный Android-клиент включает серверный режим автосбора запросом:

```http
POST /api/v4/key/skud/<skud_id>/auto_collect/enable/
Authorization: JWT <UFANET_ACCESS>
```

**Observed из Android-клиента; live-проверка ожидается.** После успешного ответа приложение открывает окно **60 секунд**, в течение которого новый ключ нужно приложить к считывателю. Успешный HTTP-ответ означает только, что режим регистрации включён.

В HA flow представлен кнопкой **«Добавить физический ключ»** (`mdi:key-plus`) с атрибутом `enrollment_window_seconds: 60`. Кнопка создаётся только для capability-supported домофона и недоступна для заблокированного/недоступного устройства.

## Асинхронное завершение регистрации через FCM

Android-клиент знает completion `reason=key_add` вместе со status и внутренним идентификатором ключа. **Observed; live-проверка ожидается.** Нативная логика успеха требует status `0` и корректный идентификатор.

Validation runtime немедленно обновляет key coordinator и публикует только privacy-minimized account-level событие:

```yaml
event_type: ufanet_intercom_key_enrollment
data:
  type: key_enrollment
  source: fcm
  result: success
  received_at: "<UTC ISO-8601>"
  inventory_refresh_succeeded: true
```

Observed completion payload не содержит `skud_id`, поэтому интеграция его не угадывает. Привязка ключа определяется последующим `/api/v4/key/list/` через `devices`.

FCM diagnostics хранят только `received_key_add_push_count`, `last_key_add_push_at`, `last_key_add_result`; provider identifiers, `title`, `body` и raw push не сохраняются.

## Переименование физического ключа

Официальный Android-клиент использует `POST /api/v4/key/edit/` с внутренним provider identifier и новым именем. **Observed из Android-клиента; реальный endpoint ещё не live-проверен.**

Validation-ветка реализует этот контракт через response-service:

```text
ufanet_intercom.rename_physical_key
```

Публичный input:

```yaml
device_id: <HA device id>
key_ref: <opaque ref from list_physical_keys>
new_name: "Новое имя"
```

Безопасная последовательность:

1. перед изменением перечитывается свежий inventory;
2. `key_ref` разрешается только внутри выбранного домофона;
3. пустое имя и control characters отклоняются; локально установлен консервативный предел 128 символов — это **не** утверждение о server limit;
4. только после разрешения ref внутренняя runtime-логика вызывает observed edit endpoint с приватным provider identifier;
5. после POST inventory перечитывается ещё раз;
6. операция считается подтверждённой сервисом только если тот же ключ виден с новым именем;
7. если новое имя совпадает с текущим, provider POST не выполняется.

Provider identifier не попадает в service input/output. Если POST мог изменить серверное состояние, но post-write refresh не удался, HA сообщает неопределённый результат, а не объявляет переименование успешным.

До появления реального ключа этот runtime path считается **validation-only**, а endpoint остаётся **Observed**.

## Lovelace-вкладка КЛЮЧИ

Validation-ветка автоматически загружает packaged frontend extension `ufanet-physical-keys-card.js`. Он ждёт регистрации `custom:ufanet-intercom-card` и добавляет вкладку **КЛЮЧИ**, не меняя основной исходник карточки.

Frontend использует только Home Assistant surface: `list_physical_keys`, `rename_physical_key` и same-device HA enrollment button. В строке списка выводятся только имя и дата добавления; opaque `key_ref` передаётся обратно в HA service, но не показывается пользователю. **Добавить ключ** требует подтверждения, показывает 60-секундный countdown и после завершения окна перечитывает список. **Переименовать** требует подтверждения и отображает успех только после `verified: true` от backend. Delete action отсутствует.

Provider identifiers не используются extension. Пустое состояние и интеграция extension с реальной Lovelace-карточкой требуют отдельного live visual test до релиза.

## Удаление ключа

Android-клиент содержит destructive delete-запрос для выбранного физического ключа. **Observed.** Удаление в текущем runtime **не реализовано** и остаётся вне release scope до отдельного дизайна защиты/подтверждения и live-теста.

## Журнал проходов

```http
POST /api/v4/key/skud/<skud_id>/key/pass_history/
Authorization: JWT <UFANET_ACCESS>
Content-Type: application/json
```

Минимальный запрос:

```json
{"page": 0, "page_size": 5}
```

**Confirmed для envelope/pagination; поля непустой записи Observed.** Android-observed result содержит ссылку на ключ, имя ключа и время прохода; время трактуется как Unix seconds. Стартовая страница `0`, штатный Android page size `25`.

Первый успешный poll устанавливает baseline и не воспроизводит старые события. Приватный cursor предотвращает дубли после reload/restart. Публичное событие прохода не содержит provider IDs.

## Модель Home Assistant в validation-ветке

Текущая ветка включает:

- capability discovery;
- **Физические ключи**: count + read-only `keys`;
- **Последний проход по ключу**;
- passage EventEntity / `ufanet_intercom_key_passage` / device trigger;
- 60-секундный key coordinator;
- **Добавить физический ключ**;
- FCM `key_add` + немедленный inventory refresh;
- `ufanet_intercom_key_enrollment`;
- `list_physical_keys` с opaque `key_ref`;
- validation-only `rename_physical_key` с fresh-resolution и post-write verification;
- validation-only Lovelace-вкладку **КЛЮЧИ** без delete action.

Diagnostics не содержат имён ключей, времени проходов, provider identifiers или полной истории.

## Обязательная live-проверка до релиза

Релиз блока остаётся заблокирован, пока не подтверждены:

1. вкладка **КЛЮЧИ** реально загружается в существующей Lovelace-карточке и на zero-key аккаунте показывает корректное пустое состояние без ошибок;
2. запуск auto-collect кнопкой HA/карточки;
3. приложение нового ключа в пределах 60 секунд;
4. реальный `reason=key_add` и его wire-схема;
5. быстрое обновление числового Physical keys state;
6. появление непустого `keys` с ожидаемыми `name`/`created_at`;
7. отсутствие provider identifiers в публичных surface;
8. корректный `ufanet_intercom_key_enrollment`;
9. `list_physical_keys` выдаёт opaque `key_ref` без provider IDs;
10. `rename_physical_key` реально меняет имя через observed edit endpoint, post-write refresh подтверждает новое имя, а вкладка **КЛЮЧИ** отображает обновлённое значение.

Удаление и BLE-ключи остаются вне текущего release scope.
