# Настройка Replicate для генерации изображений

## Описание

Проект поддерживает генерацию изображений через Replicate.com вместо локального API. Это позволяет использовать облачные модели без необходимости запускать локальный сервер.

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Получите API токен Replicate:
   - Зарегистрируйтесь на [replicate.com](https://replicate.com)
   - Перейдите в настройки аккаунта
   - Скопируйте API токен

## Настройка

Добавьте в файл `.env`:

```env
# Replicate настройки
REPLICATE_API_TOKEN=r8_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
REPLICATE_MODEL=black-forest-labs/flux-dev
USE_REPLICATE=true
```

### Параметры:

- `REPLICATE_API_TOKEN` (обязательно) - API токен Replicate
- `REPLICATE_MODEL` (опционально) - Модель для генерации. По умолчанию: `black-forest-labs/flux-dev`
- `USE_REPLICATE` (опционально) - Включить использование Replicate вместо локального API. По умолчанию: `false`

## Доступные модели

Вы можете использовать любую модель Replicate, которая поддерживает генерацию изображений по промпту. Популярные модели:

- `black-forest-labs/flux-dev` - FLUX.1 [dev] (по умолчанию)
- `black-forest-labs/flux-schnell` - FLUX.1 [schnell] (быстрая версия)
- `aisha-ai-official/wai-nsfw-illustrious-v11:c1d5b02687df6081c7953c74bcc527858702e8c153c9382012ccc3906752d3ec` - **WAI NSFW Illustrious v11** (РЕКОМЕНДУЕТСЯ для NSFW контента)
- `cjwbw/animagine-xl-3.1:6afe2e6b27dad2d6f480b59195c221884b6acc589ff4d05ff0e5fc058690fbb9` - Animagine XL 3.1 (для аниме/NSFW контента)
- `stability-ai/stable-diffusion` - Stable Diffusion
- `stability-ai/sdxl` - Stable Diffusion XL

### Использование WAI NSFW Illustrious для NSFW контента

**WAI NSFW Illustrious v11** - специальная модель для NSFW контента, разработанная для генерации откровенных изображений. Рекомендуется для использования с NSFW промптами.

Для использования:

```env
REPLICATE_MODEL=aisha-ai-official/wai-nsfw-illustrious-v11:c1d5b02687df6081c7953c74bcc527858702e8c153c9382012ccc3906752d3ec
```

Эта модель автоматически поддерживает параметры:
- `num_inference_steps` (количество шагов)
- `guidance_scale` (CFG scale)
- `width`, `height` (размеры)
- `seed` (для воспроизводимости)
- `prompt` (текстовый промпт)
- `negative_prompt` (негативный промпт)

### Использование Animagine XL для NSFW контента

Animagine XL 3.1 специально разработана для аниме-стиля и более лояльна к NSFW контенту. Для использования:

```env
REPLICATE_MODEL=cjwbw/animagine-xl-3.1:6afe2e6b27dad2d6f480b59195c221884b6acc589ff4d05ff0e5fc058690fbb9
```

Эта модель автоматически поддерживает параметры:
- `num_inference_steps` (количество шагов)
- `guidance_scale` (CFG scale)
- `width`, `height` (размеры)
- `seed` (для воспроизводимости)

## Использование

После настройки просто запустите бота и воркер как обычно:

```bash
# Терминал 1: Запуск бота
python main.py

# Терминал 2: Запуск воркера
python worker.py
```

Воркер автоматически будет использовать Replicate для генерации изображений, если `USE_REPLICATE=true`.

## Переключение между локальным API и Replicate

Чтобы переключиться обратно на локальный API, установите в `.env`:

```env
USE_REPLICATE=false
```

Или просто удалите/закомментируйте эту строку.

## Особенности

1. **Асинхронная обработка**: Replicate клиент работает асинхронно, не блокируя воркер
2. **Автоматическая загрузка**: Изображения автоматически скачиваются с URL, возвращаемых Replicate
3. **Конвертация форматов**: Изображения автоматически конвертируются в PNG и оптимизируются для Telegram
4. **Сжатие**: Большие изображения автоматически сжимаются до 10MB (лимит Telegram)

## Обработка ошибок

Если Replicate API недоступен или произошла ошибка:
- Задача помечается как FAILED
- Ошибка логируется
- Пользователь получает сообщение об ошибке

## Стоимость

Replicate использует pay-as-you-go модель. Стоимость зависит от:
- Выбранной модели
- Размера изображения
- Количества шагов генерации

Проверьте актуальные цены на [replicate.com/pricing](https://replicate.com/pricing)

## Примеры промптов

Replicate поддерживает те же промпты, что и локальный API. Примеры:

```
1girl, 19 years old, blonde hair, blue eyes, student, cute, friendly, anime style
```

```
1girl, 32 years old, mature woman, milf, confident, elegant, anime style, dark hair
```

## Отладка

Для отладки проверьте логи воркера:

```bash
python worker.py
```

Логи покажут:
- Какой клиент используется (Replicate или локальный API)
- Параметры запроса
- Результаты генерации
- Ошибки, если они возникли

