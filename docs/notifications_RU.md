# Полноценные уведомления Home Assistant

Ufanet Intercom передаёт подтверждённый входящий звонок в Home Assistant, не публикуя токенизированные provider URL preview/archive. Уведомление строится только на сущностях Home Assistant и защищённом соединении официального Companion App.

## Рекомендуемый blueprint

Импортируйте `blueprints/automation/ufanet_intercom/incoming_call_notification.yaml` и выберите:

- устройство домофона Ufanet;
- телефон с официальным Home Assistant Companion App;
- соответствующий сенсор **«Последний вызов»**;
- соответствующую сущность **«Снимок последнего звонка»**;
- при необходимости соответствующую **live camera** домофона;
- при необходимости точную кнопку/реле **«Открыть дверь»**;
- URI панели Home Assistant для обычного открытия уведомления и fallback-навигации;
- при необходимости Android notification channel;
- при необходимости timeout ожидания изображения и action открытия двери.

Для совместимости blueprint сохраняет device trigger `incoming_call`. Дополнительно интеграция создаёт нативную doorbell EventEntity, представляющую тот же подтверждённый звонок стандартным событием Home Assistant `ring`.

## Содержимое native push

Уведомление реального звонка строится только из безопасных данных Home Assistant. В заголовке указывается имя выбранного устройства домофона. В теле могут выводиться:

- адрес;
- подъезд;
- квартира;
- локальное время звонка.

Отсутствующие поля не выводятся. При ручном запуске данные берутся из выбранного сенсора **«Последний вызов»**, а уведомление явно помечается как тестовое.

`called_at` преобразуется в локальный часовой пояс Home Assistant.

## Последовательность доставки

1. Новый звонок подтверждается coordinator истории звонков — polling либо FCM-assisted refresh.
2. Blueprint сразу отправляет текстовый push; создание JPEG не задерживает первое уведомление.
3. Интеграция приватно загружает provider preview и извлекает JPEG в **«Снимок последнего звонка»**.
4. Если JPEG готов в заданном окне, уведомление заменяется под тем же `tag` через `/api/image_proxy/image.entity_id`.
5. Исходные Ufanet `preview_url`/`archive_url` не попадают в automation/push payload.

Ручной тест использует отдельный tag и не заменяет активный real-call push.

Для Android первоначальный push использует `ttl: 0`, `priority: high`, настраиваемый `channel` и `importance: high`. Обновления картинки/статуса используют `alert_once: true`.

## Android и iOS actions

Blueprint использует inline actions Companion App:

- **«Открыть дверь»** — уникальный локальный Home Assistant action ID, без provider API/ID в телефоне;
- **«Открыть камеру»** — стандартный `URI`, открывающий выбранную same-device live `camera.*` через `more-info-entity-id`, иначе используется fallback URI панели.

Выбранная камера принимается только если принадлежит тому же Home Assistant device, что и домофон.

Для door action запрашивается authentication там, где она поддерживается. Android live-тест показал, что FCM data channel требует строковые action values, поэтому `authenticationRequired` передаётся как `"true"`. Apple-only `destructive` не включается.

**Android Companion проверен live. iOS action delivery на реальном устройстве не проверялся.**

## Кнопки и модель безопасности

Device trigger входящего звонка привязан к точному Home Assistant `device_id`: событие другого устройства эту автоматизацию не запускает.

В обычной настройке selector предлагает только `button` сущности интеграции `ufanet_intercom`. Но runtime-проверка является отдельным обязательным слоем: **«Открыть дверь»** показывается только если выбранная button entity находится в `device_entities(intercom_device_id)` выбранного домофона.

Та же проверка `button.*` + принадлежность тому же device повторяется непосредственно перед `button.press` в обоих execution paths — как до, так и после обновления изображения. Если сущность перестала принадлежать выбранному устройству, операция завершается fail-closed без физического вызова.

Сама Home Assistant button entity уже привязана к конкретным `skud_id`/relay внутри интеграции. Телефон не передаёт provider SKUD ID или номер двери в physical-action path.

Blueprint работает в `mode: restart`; новый звонок отменяет старый listener. Каждый звонок имеет отдельный action ID из context события. Сценарий двух последовательных реальных звонков live-проверен: старый action больше не принимается.

Door action ограничен timeout. После timeout или успешной отправки `button.press` то же уведомление заменяется без door action. Post-open replacement также live-проверен.

Ручной запуск не имеет real event trigger, поэтому физическая кнопка открытия не отображается. Автоматического открытия двери нет — требуется явный tap пользователя.

## Live-проверка для v0.31.0

На реальной установке Home Assistant с Android Companion App подтверждены:

- ручная доставка уведомления со снимком последнего звонка;
- synthetic `ufanet_intercom_call` через device trigger;
- Android actionable notification;
- реальный входящий звонок Ufanet;
- физическое открытие двери через выбранный Ufanet `button.press`;
- **«Открыть камеру»** открывает More Info выбранной live camera;
- timeout обновляет то же уведомление, не создаёт второе и удаляет **«Открыть дверь»**;
- после успешного **«Открыть дверь»** то же уведомление заменяется версией без door action со статусом отправки команды;
- второй реальный звонок заменяет первый pending notification/action и инвалидирует старый action;
- fresh real-call push отображает ожидаемые device/location metadata и локальное время.

Во время live-теста исправлены Android payload-проблемы: `trigger.event.context.id` вместо отсутствующего bare `context.id` и строковый формат action values, необходимый FCM data channel.

## Security review cross-device защиты и waiver live-теста

Второго Ufanet device сейчас нет, поэтому буквальный отрицательный live-тест — выбрать door button другого Ufanet device и доказать, что она не появляется/не выполняется — физически недоступен.

Проведён отдельный targeted security/code review, зафиксированный в [`notification_cross_device_security_review_2026-09-07.md`](notification_cross_device_security_review_2026-09-07.md).

Проверены независимые уровни защиты:

1. incoming-call device trigger фильтрует точный HA `device_id`;
2. selector ограничен Ufanet `button` entities;
3. до отображения action проверяется `open_door_button_entity in device_entities(intercom_device_id)`;
4. та же membership-проверка выполняется снова непосредственно перед `button.press` в обоих путях;
5. каждый звонок получает уникальный action ID, а `mode: restart` инвалидирует предыдущий listener;
6. manual run не создаёт physical action;
7. provider target ID не приходит с телефона — выполняется уже зарегистрированная same-device Home Assistant button entity.

**Решение: waived только отсутствующий live multi-device test; сам safety invariant не waived.** Мы не утверждаем, что реальный тест с двумя Ufanet-устройствами был выполнен. Waiver основан на независимых runtime guards, automated device-filter tests, live-проверке окружающего action lifecycle и объективном отсутствии второго устройства для отрицательного hardware test.

Waiver действует в обычной trust model Home Assistant, где администратор HA является доверенным. Он не означает live-подтверждение iOS и не превращает malformed/ambiguous provider call routing в подтверждённую multi-device семантику.

## Статус notification-блока для релиза

Все Android notification release gates теперь либо live-confirmed, либо закрыты явно задокументированным waiver выше. У notification functionality больше нет собственного hard release blocker.

Этот notification path опубликован в v0.31.0. Бывший release gate физического ключа (`auto_collect/enable` → новый ключ → настоящий `reason=key_add`) был закрыт end-to-end live-проверкой до публикации.

## Диагностика

Если при реальном звонке push не приходит:

1. Запустите blueprint вручную. Если test push приходит, Companion delivery работает; дальше смотрите trace real incoming-call trigger.
2. Если текстовый push приходит, но JPEG нет, проверьте **«Снимок последнего звонка»**, Ufanet diagnostics и наличие `ffmpeg`.
3. Если door action отсутствует, проверьте, что выбрана **«Открыть дверь»** того же Ufanet device и запуск был реальным, а не manual.
4. Если **«Открыть камеру»** открывает только dashboard, выберите соответствующую live `camera.*`; mismatched camera намеренно использует fallback URI.
5. URL картинки должен быть `/api/image_proxy/image.entity_id`; вручную добавлять `access_token` не нужно.
6. Ошибка Android FCM вида `data must only contain string values` означает некорректный actionable-notification payload, а не проблему Ufanet call trigger.

Интеграция не использует critical/alarm-stream уведомления по умолчанию и не пытается обходить Do Not Disturb.
