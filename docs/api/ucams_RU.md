# UCAMS и live-видео

[English version](ucams.md)

UCAMS — видеоплатформа, которую использует протестированный аккаунт Ufanet.

## Получение метаданных камеры

**Статус: Confirmed**

После обмена JWT Ufanet на bearer-токен UCAMS выполняется запрос:

```http
POST https://cloud.ucams.ru/api/v0/cameras/this/
Authorization: Bearer <UCAMS_JWT>
Content-Type: application/json
```

Проверенное тело запроса:

```json
{
  "fields": [
    "number",
    "token_l",
    "token_r",
    "is_llhls_enabled",
    "permission",
    "address",
    "title",
    "timezone",
    "is_fav",
    "is_public",
    "inactivity_period",
    "server",
    "analytics",
    "tariff",
    "is_sounding",
    "streams_count"
  ],
  "token_l_ttl": 20800,
  "token_r_ttl": 20800,
  "numbers": ["<CAMERA_NUMBER>"]
}
```

В ответе наблюдаются:

- `number` камеры;
- `token_l` — токен для live/media;
- `token_r` — токен архива;
- timezone;
- поддержка LL-HLS;
- количество потоков;
- домен/производитель медиасервера;
- домен сервиса снимков;
- объявленные `analytics` capabilities; `motion_alarm` live-подтверждён на проверенной камере, а `perimeter_security` остаётся только Observed;
- данные тарифа, включая глубину архива (`dvr_hours`).

Полная структура ответа намеренно не объявляется стабильной схемой: это закрытый API, и вложенность может отличаться.

Для production capability discovery аналитики полный media-metadata запрос выше не требуется. Ufanet Intercom v0.28.0 использует отдельный минимальный `cameras/this/` только с `number` и `analytics`. Подтверждённый контракт отчёта `motion_alarm` и privacy boundary описаны на странице [аналитики камер UCAMS](analytics_RU.md).

## Live HLS

**Статус: Confirmed**

```text
https://<MEDIA_SERVER>/<CAMERA_NUMBER>/index.m3u8?token=<TOKEN_L>&tracks=v1a1
```

Проверенный URL вернул HTTP 200 и HLS-поток.

`tracks=v1a1` — проверенная комбинация видео/аудио. Другие селекторы потоков системно не исследовались.

## Снимок камеры

**Статус: Confirmed**

```text
https://<SCREENSHOT_DOMAIN>/api/v0/screenshots/<CAMERA_NUMBER>.jpg?token=<TOKEN_L>
```

Домен снимков лучше брать из метаданных камеры/сервера, а не жёстко прописывать.

## Назначение токенов

| Токен | Назначение |
|---|---|
| Ufanet access JWT | Ufanet API и обмен на UCAMS |
| UCAMS JWT | управляющий API UCAMS (`Bearer`), включая metadata камеры и analytics reports |
| `token_l` | live HLS и снимки |
| `token_r` | архив и диапазоны записи |

**Статус: Confirmed для описанных операций.**

## Наблюдения по кодекам

Протестированная камера отдавала H.264 + AAC в разрешении 1920×1080.

**Статус: Observed; нельзя считать это гарантией для всех камер.**
