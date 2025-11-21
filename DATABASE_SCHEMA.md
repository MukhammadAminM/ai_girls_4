# Схема базы данных

Полное описание всех таблиц в базе данных проекта.

## Таблицы

### 1. `girls` - Персонажи
Хранит информацию о персонажах (девушках).

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER (PK, AUTO_INCREMENT) | Уникальный идентификатор персонажа |
| `name` | VARCHAR(100) (UNIQUE, NOT NULL) | Имя персонажа (уникальное) |
| `system_prompt` | TEXT (NOT NULL) | Системный промпт для AI модели |
| `greeting` | TEXT (NOT NULL) | Приветственное сообщение персонажа |
| `clothing_description` | TEXT (NULLABLE) | Описание постоянной одежды персонажа |

**Модель:** `Girl`

---

### 2. `dialogs` - Диалоги
Хранит информацию о диалогах между пользователями и персонажами.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | BIGINT (PK, AUTO_INCREMENT) | Уникальный идентификатор диалога |
| `user_id` | BIGINT (INDEX, NOT NULL) | ID пользователя Telegram |
| `girl_id` | INTEGER (FK → girls.id, INDEX, NOT NULL) | ID персонажа |
| `title` | VARCHAR(200) (NULLABLE) | Название диалога |
| `nsfw_enabled` | BOOLEAN (DEFAULT: false, NOT NULL) | Флаг включения 18+ контента |
| `created_at` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), NOT NULL) | Дата создания |
| `updated_at` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), ON UPDATE: now(), NOT NULL) | Дата последнего обновления |

**Модель:** `Dialog`

**Связи:**
- `girl_id` → `girls.id` (CASCADE DELETE)

---

### 3. `chat_messages` - Сообщения в диалогах
Хранит все сообщения в диалогах (от пользователя и от персонажа).

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | BIGINT (PK, AUTO_INCREMENT) | Уникальный идентификатор сообщения |
| `dialog_id` | BIGINT (FK → dialogs.id, INDEX, NOT NULL) | ID диалога |
| `role` | VARCHAR(16) (NOT NULL) | Роль отправителя: "user" или "assistant" |
| `content` | TEXT (NOT NULL) | Текст сообщения |
| `created_at` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), NOT NULL) | Дата создания сообщения |

**Модель:** `ChatMessage`

**Связи:**
- `dialog_id` → `dialogs.id` (CASCADE DELETE)

---

### 4. `user_selected_girls` - Выбранные персонажи пользователями
Хранит информацию о том, какой персонаж выбран у каждого пользователя.

| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | BIGINT (PK, NOT NULL) | ID пользователя Telegram |
| `girl_id` | INTEGER (FK → girls.id, NOT NULL) | ID выбранного персонажа |
| `active_dialog_id` | BIGINT (FK → dialogs.id, NULLABLE) | ID активного диалога (если есть) |
| `photos_used` | INTEGER (DEFAULT: 0, NOT NULL) | Количество использованных фото |
| `updated_at` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), ON UPDATE: now(), NOT NULL) | Дата последнего обновления |

**Модель:** `UserSelectedGirl`

**Связи:**
- `girl_id` → `girls.id` (CASCADE DELETE)
- `active_dialog_id` → `dialogs.id` (SET NULL ON DELETE)

---

### 5. `user_retention` - Retention метрики пользователей
Хранит агрегированные данные о retention пользователей.

| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | BIGINT (PK, NOT NULL) | ID пользователя Telegram |
| `first_seen` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), NOT NULL) | Дата первого визита |
| `last_seen` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), ON UPDATE: now(), NOT NULL) | Дата последнего визита |
| `total_sessions` | INTEGER (DEFAULT: 1, NOT NULL) | Общее количество сессий |
| `total_messages` | INTEGER (DEFAULT: 0, NOT NULL) | Общее количество сообщений |
| `total_photos` | INTEGER (DEFAULT: 0, NOT NULL) | Общее количество сгенерированных фото |
| `days_active` | INTEGER (DEFAULT: 1, NOT NULL) | Количество уникальных дней активности |

**Модель:** `UserRetention`

---

### 6. `user_activity` - Ежедневная активность пользователей
Хранит ежедневную статистику активности пользователей.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | BIGINT (PK, AUTO_INCREMENT) | Уникальный идентификатор записи |
| `user_id` | BIGINT (INDEX, NOT NULL) | ID пользователя Telegram |
| `activity_date` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), INDEX, NOT NULL) | Дата активности |
| `messages_count` | INTEGER (DEFAULT: 0, NOT NULL) | Количество сообщений за день |
| `photos_generated` | INTEGER (DEFAULT: 0, NOT NULL) | Количество сгенерированных фото за день |
| `dialogs_created` | INTEGER (DEFAULT: 0, NOT NULL) | Количество созданных диалогов за день |
| `created_at` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), NOT NULL) | Дата создания записи |

**Модель:** `UserActivity`

**Индексы:**
- Уникальный индекс: `(user_id, activity_date)` - одна запись на пользователя в день

---

### 7. `user_profiles` - Профили пользователей
Хранит информацию о ресурсах пользователей (алмазы, энергия).

| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | BIGINT (PK, NOT NULL) | ID пользователя Telegram |
| `diamonds` | INTEGER (DEFAULT: 5, NOT NULL) | Количество алмазов |
| `energy` | INTEGER (DEFAULT: 25, NOT NULL) | Текущая энергия |
| `max_energy` | INTEGER (DEFAULT: 25, NOT NULL) | Максимальная энергия |
| `updated_at` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), ON UPDATE: now(), NOT NULL) | Дата последнего обновления |

**Модель:** `UserProfile`

**Начальные значения:**
- `diamonds`: 5
- `energy`: 25
- `max_energy`: 25

---

### 8. `payments` - Платежи (донаты)
Хранит информацию о всех платежах пользователей.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | BIGINT (PK, AUTO_INCREMENT) | Уникальный идентификатор платежа |
| `user_id` | BIGINT (INDEX, NOT NULL) | ID пользователя Telegram |
| `payment_type` | VARCHAR(50) (NOT NULL) | Тип платежа: "diamonds", "energy", "pack", "combo" |
| `amount_stars` | INTEGER (NOT NULL) | Сумма в Telegram Stars |
| `amount_usd` | DOUBLE PRECISION (NULLABLE) | Сумма в USD (если известна) |
| `diamonds_received` | INTEGER (DEFAULT: 0, NOT NULL) | Получено алмазов |
| `energy_received` | INTEGER (DEFAULT: 0, NOT NULL) | Получено энергии |
| `pack_name` | VARCHAR(100) (NULLABLE) | Название пакета (если применимо) |
| `telegram_payment_charge_id` | VARCHAR(255) (NULLABLE) | ID платежа от Telegram |
| `telegram_provider_payment_charge_id` | VARCHAR(255) (NULLABLE) | ID платежа от провайдера |
| `created_at` | TIMESTAMP WITH TIME ZONE (DEFAULT: now(), INDEX, NOT NULL) | Дата создания платежа |

**Модель:** `Payment`

**Типы платежей:**
- `diamonds` - Покупка алмазов
- `energy` - Покупка энергии
- `pack` - Покупка пакета (Starter, Premium, Ultimate)
- `combo` - Комбо-пакет

---

## Связи между таблицами

```
girls (1) ──< (N) dialogs
              │
              └──< (N) chat_messages

girls (1) ──< (N) user_selected_girls

dialogs (1) ──< (N) user_selected_girls (active_dialog_id)
```

## Индексы

### Основные индексы:
- `dialogs.user_id` - для быстрого поиска диалогов пользователя
- `dialogs.girl_id` - для быстрого поиска диалогов с персонажем
- `chat_messages.dialog_id` - для быстрого поиска сообщений в диалоге
- `user_activity.user_id` - для быстрого поиска активности пользователя
- `user_activity.activity_date` - для быстрого поиска по дате
- `payments.user_id` - для быстрого поиска платежей пользователя
- `payments.created_at` - для быстрого поиска платежей по дате

### Уникальные ограничения:
- `girls.name` - имя персонажа должно быть уникальным
- `user_activity(user_id, activity_date)` - одна запись активности на пользователя в день
- `user_selected_girls.user_id` - один выбранный персонаж на пользователя (PK)

## Каскадные удаления

- При удалении `girls` → удаляются все связанные `dialogs` и `user_selected_girls`
- При удалении `dialogs` → удаляются все связанные `chat_messages`
- При удалении `dialogs` → `user_selected_girls.active_dialog_id` устанавливается в NULL

