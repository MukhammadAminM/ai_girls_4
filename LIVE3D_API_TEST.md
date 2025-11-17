# Тестирование API live3d.io

## Проблема с Cloudflare

API защищено Cloudflare, который требует JavaScript challenge. Для успешного запроса нужен свежий cookie `cf_clearance`.

## Способ 1: Получение cookie из браузера

1. Откройте браузер и перейдите на https://animegenius.live3d.io/
2. Откройте DevTools (F12)
3. Перейдите в Application/Storage -> Cookies -> https://api.live3d.io
4. Скопируйте значение cookie `cf_clearance`
5. Используйте его в запросе

## Способ 2: Использование curl (PowerShell)

```powershell
# Замените YOUR_CF_CLEARANCE на свежий cookie из браузера
$headers = @{
    "accept" = "application/json"
    "accept-language" = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    "authorization" = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjM0NzI4MTEsInN1YiI6Imdvb2dsZSA0NDczNDM3IG11aGFtbWFkYW1pbm1hZGlldkBnbWFpbC5jb20ifQ.c2ce_v3L1KfeVH9MQqTHqsZYVDY3NbGHFXegR1D21-s"
    "content-type" = "application/json"
    "cookie" = "cf_clearance=YOUR_CF_CLEARANCE"
    "origin" = "https://animegenius.live3d.io"
    "referer" = "https://animegenius.live3d.io/"
    "user-agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
}

$body = '{"prompt":"beautiful girl"}'

Invoke-RestMethod -Uri "https://api.live3d.io/api/v1/generation/generate" -Method Post -Headers $headers -Body $body | ConvertTo-Json -Depth 10
```

## Способ 3: Использование Python скрипта

Запустите `test_live3d_api.py`:

```bash
python test_live3d_api.py
```

Скрипт попытается:
1. Автоматически получить cookie через Selenium (если установлен)
2. Использовать предоставленный cookie
3. Использовать cloudscraper для обхода Cloudflare

## Способ 4: Использование curl (если установлен)

```bash
curl -X POST "https://api.live3d.io/api/v1/generation/generate" \
  -H "accept: application/json" \
  -H "authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjM0NzI4MTEsInN1YiI6Imdvb2dsZSA0NDczNDM3IG11aGFtbWFkYW1pbm1hZGlldkBnbWFpbC5jb20ifQ.c2ce_v3L1KfeVH9MQqTHqsZYVDY3NbGHFXegR1D21-s" \
  -H "content-type: application/json" \
  -H "cookie: cf_clearance=YOUR_CF_CLEARANCE" \
  -H "origin: https://animegenius.live3d.io" \
  -H "referer: https://animegenius.live3d.io/" \
  -d '{"prompt":"beautiful girl"}'
```

## Важно

- Cookie `cf_clearance` имеет ограниченный срок действия (обычно несколько часов)
- Cookie привязан к IP-адресу и браузеру
- При получении ошибки 403 нужно обновить cookie

