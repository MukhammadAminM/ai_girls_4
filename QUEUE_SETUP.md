# Настройка очередей Redis

Проект использует Redis для асинхронной обработки задач генерации изображений и ответов AI.

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Убедитесь, что Redis запущен:
```bash
# Linux/Mac
redis-server

# Windows (через Docker)
docker run -d -p 6379:6379 redis:latest
```

## Конфигурация

Добавьте в `.env` файл:
```env
REDIS_URL=redis://localhost:6379/0
REDIS_QUEUE_PREFIX=ai_girls:queue:
REDIS_RESULT_PREFIX=ai_girls:result:
REDIS_RESULT_TTL=3600
```

## Запуск

### 1. Запуск бота
```bash
python main.py
```

### 2. Запуск воркера (в отдельном терминале)
```bash
python worker.py
```

Воркер обрабатывает задачи из очереди:
- Генерация изображений (`GENERATE_IMAGE`)
- Генерация ответов AI (`GENERATE_REPLY`)
- Генерация промптов для изображений (`GENERATE_IMAGE_PROMPT`)

## Архитектура

### Компоненты

1. **QueueService** (`app/services/queue_service.py`)
   - Управление очередями Redis
   - Добавление/извлечение задач
   - Отслеживание статуса задач

2. **QueueWorker** (`app/workers/queue_worker.py`)
   - Фоновый процесс для обработки задач
   - Обработка каждого типа задач
   - Сохранение результатов в Redis

3. **Task Helpers** (`app/bot/task_helpers.py`)
   - Вспомогательные функции для работы с очередями
   - Интеграция с handlers бота

### Типы задач

- `GENERATE_IMAGE` - Генерация изображения по промпту
- `GENERATE_REPLY` - Генерация ответа AI на сообщение
- `GENERATE_IMAGE_PROMPT` - Генерация промпта для изображения на основе диалога

### Статусы задач

- `PENDING` - Задача в очереди
- `PROCESSING` - Задача обрабатывается
- `COMPLETED` - Задача выполнена успешно
- `FAILED` - Задача завершилась с ошибкой

## Мониторинг

Проверить длину очереди:
```python
from app.services.queue_service import QueueService, TaskType

queue_service = QueueService()
await queue_service.connect()
length = await queue_service.get_queue_length(TaskType.GENERATE_IMAGE)
print(f"Задач в очереди: {length}")
```

## Отладка

Если задачи не обрабатываются:
1. Проверьте, что воркер запущен
2. Проверьте подключение к Redis
3. Проверьте логи воркера
4. Убедитесь, что все сервисы (Venice API, Image API) доступны

## Масштабирование

Для обработки большего количества задач можно запустить несколько воркеров:
```bash
# Терминал 1
python worker.py

# Терминал 2
python worker.py

# Терминал 3
python worker.py
```

Каждый воркер будет обрабатывать задачи из общей очереди.

