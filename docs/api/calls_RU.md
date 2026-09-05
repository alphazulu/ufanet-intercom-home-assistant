# Звонки и история

[English version](calls.md)

## История звонков

**Статус: Confirmed**

```http
GET https://dom.ufanet.ru/api/v1/skuds/call-history/?page=1&page_size=25
Authorization: JWT <UFANET_ACCESS_JWT>
```

Наблюдаемые поля звонка:

```json
{
  "uuid": "<CALL_UUID>",
  "called_at": "<OFFSET_AWARE_DATETIME>",
  "timezone": "<TIMEZONE_NAME>",
  "camera_number": "<CAMERA_NUMBER>",
  "address": "<ADDRESS>",
  "porch": "<PORCH>",
  "flat": "<FLAT>"
}
```

Это не полная схема — перечислены поля, которые реально использует интеграция.

## Медиа звонка

**Статус: Confirmed**

```http
POST https://dom.ufanet.ru/api/v1/cctv/history/
Authorization: JWT <UFANET_ACCESS_JWT>
Content-Type: application/json

{
  "uuid": "<CALL_UUID>"
}
```

Наблюдаемый ответ содержит URL с временными токенами для:

- `preview` MP4;
- архивного/media `url` MP4.

Эти URL содержат временные права доступа и не должны попадать в логи, диагностику,
Recorder-backed attributes или automation payload.

## Семантика времени

**Статус: Confirmed по реальным данным звонков**

`called_at` содержит timezone offset и задаёт авторитетный абсолютный момент звонка. Отдельное поле `timezone` может не совпадать с ожидаемой клиентом зоной/offset.

Правильная обработка:

1. распарсить `called_at` как aware datetime;
2. сохранить представленный абсолютный момент;
3. конвертировать его в нужную timezone для отображения;
4. не заменять timezone/offset без преобразования времени.

Простая подмена timezone у уже распарсенного datetime может сдвинуть событие на другой реальный момент.

## Идентификатор события

Интеграция использует `uuid` звонка для дедупликации. В имени автоматически сохранённого MP4 хранится только сокращённый SHA-256 reference, а не исходный UUID.

**Статус: поведение интеграции, не требование API.**

## Представление в Home Assistant

Подтверждённая запись `call-history` является authoritative source для устойчивого
события Home Assistant даже в FCM-режиме. `reason=sip` используется как low-latency
сигнал на refresh, но push UUID не заменяет `call-history.uuid`.

Публичное `ufanet_intercom_call` и doorbell EventEntity намеренно не содержат
`preview_url`/`archive_url`. Через Home Assistant наружу передаются безопасные
metadata звонка и признаки `has_preview` / `has_archive`; токенизированные media URL
остаются runtime-данными.

Validation-ветка также использует то же подтверждённое событие в Companion
notification blueprint. Картинка берётся из приватной HA ImageEntity через
`/api/image_proxy/`, а action открытия двери вызывает выбранную Home Assistant
button entity, а не вставляет provider endpoint/credential в notification payload.

Подробная последовательность, Android live-validation и оставшиеся release gates:
[../notifications_RU.md](../notifications_RU.md).