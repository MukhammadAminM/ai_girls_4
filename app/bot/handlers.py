import logging
import math
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.db import get_session
from app.repositories.girls import ensure_default_girl, get_all_girls, get_default_girl, get_girl_by_id
from app.repositories.dialogs import (
    create_dialog,
    get_active_dialog,
    get_all_user_dialogs,
    get_dialog_by_id,
    get_user_dialogs_with_girl,
)
from app.repositories.messages import (
    add_message,
    clear_dialog,
    get_all_messages,
    get_girls_with_history,
    get_message_count,
    get_recent_messages,
)
from app.repositories.user_selected_girl import (
    get_active_dialog_id,
    get_selected_girl,
    set_active_dialog,
    set_selected_girl,
)
from app.repositories.user_profile import (
    add_diamonds,
    add_energy,
    get_user_diamonds,
    get_user_energy,
    spend_diamonds,
    spend_energy,
)
from app.config import settings
from app.services.image_client import ImageClient
from app.services.venice_client import VeniceClient
from app.bot.task_helpers import (
    enqueue_image_generation,
    enqueue_reply_generation,
    send_image_from_task_result,
    wait_for_task_result,
)

router = Router()

GIRLS_PER_PAGE = 2
DIALOGS_PER_PAGE = 5
MAX_PHOTOS_PER_DIALOG = 9999


async def safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    """
    Безопасно редактирует текст сообщения, игнорируя ошибку 'message is not modified'.
    
    Args:
        message: Сообщение для редактирования
        text: Новый текст
        reply_markup: Новая клавиатура (опционально)
    """
    from aiogram.exceptions import TelegramBadRequest
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        # Игнорируем ошибку "message is not modified" - это нормально при быстрых повторных нажатиях
        if "message is not modified" not in str(e).lower():
            raise


async def safe_edit_media(message: Message, media, reply_markup=None) -> None:
    """
    Безопасно редактирует медиа сообщения, игнорируя ошибку 'message is not modified'.
    
    Args:
        message: Сообщение для редактирования
        media: Новое медиа
        reply_markup: Новая клавиатура (опционально)
    """
    from aiogram.exceptions import TelegramBadRequest
    try:
        await message.edit_media(media, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        # Игнорируем ошибку "message is not modified" - это нормально при быстрых повторных нажатиях
        if "message is not modified" not in str(e).lower():
            raise

# Словарь для отслеживания состояния генерации изображений по user_id
# Хранит ссылку на сообщение-предупреждение, которое нужно удалить после генерации
_generating_images: dict[int, Message | None] = {}

# Путь к папке с изображениями девушек
GIRLS_IMAGES_DIR = Path("girls_images")


def get_girl_image_path(girl_name: str) -> Path | None:
    """Возвращает путь к изображению девушки или None, если файл не найден."""
    # Маппинг имен девушек к именам файлов
    name_mapping = {
        "Стейси": "staicy.png",
        "Аманда": "amanda.png",
        "Джейн": "jane.png",
    }
    
    filename = name_mapping.get(girl_name)
    if not filename:
        return None
    
    image_path = GIRLS_IMAGES_DIR / filename
    if image_path.exists():
        return image_path
    return None


def get_girl_description(girl) -> str:
    """Формирует описание девушки на основе её данных."""
    # Информация о девушках
    descriptions = {
        "Стейси": "👩‍🎓 19 лет\n📚 Одногруппница\n💬 Дружелюбная, умная, игривая",
        "Аманда": "👩 32 года\n🏠 Соседка\n💔 Разведёнка\n💋 Опытная милфа",
        "Джейн": "👩‍🌾 22 года\n🌾 Из деревни\n🧡 Рыжеволосая\n🏡 Хозяйственная",
    }
    
    return descriptions.get(girl.name, f"💬 {girl.name}")


def get_girl_story_intro(girl_name: str) -> str:
    """Возвращает введение в сюжет для персонажа."""
    story_intros = {
        "Стейси": "Стейси — твоя одногруппница, 19 лет. Дружелюбная, умная и игривая девушка, всегда готова помочь с учёбой. Ты зашёл к ней разобраться с домашним заданием.",
        "Аманда": "Аманда — твоя соседка, 32 года. Опытная и уверенная в себе разведёнка, знает чего хочет и не стесняется этого. Она пригласила тебя посидеть.",
        "Джейн": "Джейн — хозяйственная девушка из деревни, 22 года. Рыжеволосая, простая и искренняя, любит природу и животных. Ты случайно встретил её, заблудившись в деревне.",
    }
    
    return story_intros.get(girl_name, "Ты встречаешься с персонажем.")


def get_insufficient_balance_message(girl_name: str, resource_type: str, current: int, needed: int) -> str:
    """
    Генерирует сообщение от персонажа о недостатке баланса.
    
    Args:
        girl_name: Имя персонажа
        resource_type: Тип ресурса ("diamonds" или "energy")
        current: Текущее количество ресурса
        needed: Необходимое количество ресурса
    
    Returns:
        Сообщение от персонажа
    """
    if resource_type == "diamonds":
        messages = {
            "Стейси": (
                f"💎 Ой, у тебя недостаточно алмазов для фото... ⏰ Наше общение проходит так незаметно, "
                f"что я даже не заметила, как быстро пролетело время! ✨ Пополни баланс, чтобы мы могли "
                f"продолжить и я смогла показать тебе больше 😊💕"
            ),
            "Аманда": (
                f"💎 Дорогой, у тебя не хватает алмазов для фото... ⏰ Наше общение такое увлекательное, "
                f"что время пролетает незаметно! ✨ Пополни баланс, чтобы мы могли продолжить наше общение 💋🔥"
            ),
            "Джейн": (
                f"💎 Ой, у тебя маловато алмазов для фото... ⏰ Мы так хорошо общаемся, что я даже не заметила, "
                f"как быстро время прошло! ✨ Пополни баланс, пожалуйста, чтобы мы могли продолжить 🌾💚"
            ),
        }
    else:  # energy
        messages = {
            "Стейси": (
                f"⚡ Ой, у тебя закончилась энергия... ⏰ Наше общение проходит так незаметно, "
                f"что я даже не заметила, как быстро пролетело время! ✨ Пополни баланс, чтобы мы могли "
                f"продолжить наш разговор 😊💕"
            ),
            "Аманда": (
                f"⚡ Дорогой, у тебя не хватает энергии для сообщений... ⏰ Наше общение такое увлекательное, "
                f"что время пролетает незаметно! ✨ Пополни баланс, чтобы мы могли продолжить наше общение 💋🔥"
            ),
            "Джейн": (
                f"⚡ Ой, у тебя закончилась энергия... ⏰ Мы так хорошо общаемся, что я даже не заметила, "
                f"как быстро время прошло! ✨ Пополни баланс, пожалуйста, чтобы мы могли продолжить 🌾💚"
            ),
        }
    
    return messages.get(girl_name, f"❌ Недостаточно {'алмазов' if resource_type == 'diamonds' else 'энергии'}!")


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает основную клавиатуру (главное меню, история чатов)."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главное меню"), KeyboardButton(text="📜 История чатов")],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_dialogue_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру для диалога (все основные + завершить/начать заново)."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главное меню"), KeyboardButton(text="📜 История чатов")],
            [KeyboardButton(text="❌ Завершить диалог"), KeyboardButton(text="🔄 Начать диалог заново")],
        ],
        resize_keyboard=True,
    )
    return keyboard


def build_image_prompt(girl_name: str, clothing_description: str | None = None) -> str:
    """
    Формирует промпт для генерации изображения на основе персонажа.
    
    Args:
        girl_name: Имя персонажа
        clothing_description: Описание постоянной одежды персонажа
    """
    # Базовые характеристики персонажей: цвет волос, цвет глаз, размер груди, размер задницы
    base_characteristics = {
        "Стейси": "blonde hair, blue eyes, medium breasts, medium ass",
        "Аманда": "dark hair, brown eyes, large breasts, large ass",
        "Джейн": "red hair, green eyes, medium breasts, medium ass",
    }
    
    # Начинаем промпт с (masterpiece), best quality
    prompt = "(masterpiece), best quality"
    
    # Добавляем базовые характеристики персонажа
    characteristics = base_characteristics.get(girl_name, "1girl, solo")
    prompt = f"{prompt}, {characteristics}"
    
    # Добавляем описание одежды
    if clothing_description:
        prompt = f"{prompt}, {clothing_description}"
    
    return prompt


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return

    # Отслеживаем активность пользователя
    async with get_session() as session:
        from app.repositories.retention import track_user_activity, update_user_retention
        await update_user_retention(session, user_id=message.from_user.id, is_new_user=True)
        await track_user_activity(session, user_id=message.from_user.id)
        await session.commit()
    
    # Отправляем приветственное сообщение с встроенной клавиатурой
    await message.answer(
        "👋 Привет! Я бот ролевой игры с AI девушками.\n\n"
        "💕 Выбери девушку для начала диалога:",
        reply_markup=get_main_keyboard()
    )
    
    # Получаем информацию о профиле для главного меню
    async with get_session() as session:
        diamonds = await get_user_diamonds(session, user_id=message.from_user.id)
        energy = await get_user_energy(session, user_id=message.from_user.id)
    
    # Формируем текст главного меню с информацией о профиле
    menu_text = (
        f"🏠 Главное меню\n\n"
        f"💎 Алмазы: {diamonds}\n"
        f"   💰 Стоимость генерации изображения: {settings.image_generation_cost} алмазов\n\n"
        f"⚡ Энергия: {energy}\n"
        f"   💬 Стоимость сообщения: {settings.message_energy_cost} энергии"
    )
    
    # Отправляем главное меню с кнопками
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💕 Выбрать девушку", callback_data="choose_girl:0")],
            [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up_balance")]
        ]
    )
    
    await message.answer(menu_text, reply_markup=keyboard)


@router.message(Command("girl"))
async def handle_girl_info(message: Message) -> None:
    async with get_session() as session:
        girl = await get_default_girl(session)
    if not girl:
        await message.answer("👥 Пока нет доступных персонажей.")
        return
    await message.answer(f"💬 Сейчас с тобой общается {girl.name}.")


async def _show_profile(user_id: int, message_or_callback) -> None:
    """Вспомогательная функция для показа профиля."""
    async with get_session() as session:
        diamonds = await get_user_diamonds(session, user_id=user_id)
        energy = await get_user_energy(session, user_id=user_id)
    
    text = (
        f"👤 Твой профиль\n\n"
        f"💎 Алмазы: {diamonds}\n"
        f"   💰 Стоимость генерации изображения: {settings.image_generation_cost} алмазов\n\n"
        f"⚡ Энергия: {energy}\n"
        f"   💬 Стоимость сообщения: {settings.message_energy_cost} энергии"
    )
    
    # Добавляем кнопку возврата в главное меню
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main_menu")]]
    )
    
    if hasattr(message_or_callback, 'answer'):  # Это callback
        await message_or_callback.message.answer(text, reply_markup=keyboard)
        await message_or_callback.answer()
    else:  # Это message
        await message_or_callback.answer(text, reply_markup=keyboard)


@router.message(Command("profile"))
async def handle_profile(message: Message) -> None:
    """Показывает профиль пользователя с алмазами и энергией."""
    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return
    
    await _show_profile(message.from_user.id, message)


@router.callback_query(lambda c: c.data and c.data == "show_profile")
async def handle_show_profile_callback(callback: CallbackQuery) -> None:
    """Обработчик инлайн кнопки для показа профиля."""
    if not callback.from_user:
        await callback.message.answer("⚠️ Не могу определить пользователя.")
        return
    
    await _show_profile(callback.from_user.id, callback)


@router.message(Command("image"))
async def handle_generate_image(message: Message) -> None:
    """Генерирует изображение текущего персонажа через очередь."""
    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return

    async with get_session() as session:
        # Проверяем наличие алмазов
        diamonds = await get_user_diamonds(session, user_id=message.from_user.id)
        girl = await get_selected_girl(session, user_id=message.from_user.id)
        if not girl:
            girl = await get_default_girl(session)
        
        if diamonds < settings.image_generation_cost:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up_balance")]
                ]
            )
            # Сообщение от персонажа о недостатке алмазов
            if girl:
                message_text = get_insufficient_balance_message(
                    girl_name=girl.name,
                    resource_type="diamonds",
                    current=diamonds,
                    needed=settings.image_generation_cost
                )
            else:
                message_text = (
                    f"❌ Недостаточно алмазов!\n\n"
                    f"💎 У тебя: {diamonds} алмазов\n"
                    f"💰 Нужно: {settings.image_generation_cost} алмазов"
                )
            await message.answer(message_text, reply_markup=keyboard)
            return
        
        if not girl:
            girl = await get_default_girl(session)
            if girl:
                await set_selected_girl(session, user_id=message.from_user.id, girl_id=girl.id)

        if not girl:
            await message.answer("⚠️ Персонажи пока не настроены. Попробуй позже.")
            return
        
        # Списываем алмазы
        await spend_diamonds(session, user_id=message.from_user.id, amount=settings.image_generation_cost)
        await session.commit()

    # Формируем промпт для генерации изображения на основе персонажа
    additional = None
    if message.text and len(message.text.split()) > 1:
        additional = " ".join(message.text.split()[1:])
    
    prompt = build_image_prompt(
        girl_name=girl.name,
        clothing_description=girl.clothing_description,
    )
    if additional:
        prompt = f"{prompt}, {additional}"

    # Устанавливаем флаг генерации
    if message.from_user:
        _generating_images[message.from_user.id] = None
    
    try:
        # Отправляем сообщение о начале генерации
        status_message = await message.answer(
            "🎨 Генерирую фото...\n"
            "⏱️ Генерация может занять обычно 20 секунд, пожалуйста, подождите."
        )
        
        # Добавляем задачу в очередь
        task_id = await enqueue_image_generation(
            user_id=message.from_user.id,
            prompt=prompt,
            girl_id=girl.id,
        )
        
        # Ожидаем результат (используем бот из контекста сообщения)
        from aiogram import Bot
        bot = message.bot
        task_result = await wait_for_task_result(bot, message, task_id)
        
        # Удаляем сообщение о генерации
        try:
            await status_message.delete()
        except Exception:
            pass
        
        if task_result:
            await send_image_from_task_result(bot, message, task_result, girl.name)
            # Показываем обновленный баланс
            async with get_session() as session:
                new_diamonds = await get_user_diamonds(session, user_id=message.from_user.id)
                await message.answer(f"💎 Алмазов осталось: {new_diamonds}")
        else:
            # Возвращаем алмазы, если генерация не удалась
            async with get_session() as session:
                await add_diamonds(session, user_id=message.from_user.id, amount=settings.image_generation_cost)
                await session.commit()
            await message.answer("❌ Не получилось сгенерировать изображение. Алмазы возвращены.")
    except Exception as exc:
        await message.answer("❌ Не получилось сгенерировать изображение. Проверь, что локальный API запущен.")
        logging.getLogger(__name__).exception("Ошибка при генерации изображения", exc_info=exc)
    finally:
        # Удаляем сообщение-предупреждение, если оно было отправлено
        if message.from_user:
            warning_msg = _generating_images.pop(message.from_user.id, None)
            if warning_msg:
                try:
                    await warning_msg.delete()
                except Exception:
                    pass


@router.message(lambda m: m.text and ("Главное меню" in m.text or m.text == "🏠 Главное меню"))
async def handle_main_menu(message: Message) -> None:
    """Обработчик кнопки 'Главное меню'."""
    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return

    async with get_session() as session:
        # НЕ завершаем диалог - просто показываем главное меню
        # Получаем информацию о профиле для главного меню
        diamonds = await get_user_diamonds(session, user_id=message.from_user.id)
        energy = await get_user_energy(session, user_id=message.from_user.id)
    
    # Формируем текст главного меню с информацией о профиле
    menu_text = (
        f"🏠 Главное меню\n\n"
        f"💎 Алмазы: {diamonds}\n"
        f"   💰 Стоимость генерации изображения: {settings.image_generation_cost} алмазов\n\n"
        f"⚡ Энергия: {energy}\n"
        f"   💬 Стоимость сообщения: {settings.message_energy_cost} энергии"
    )
    
    # Показываем главное меню с кнопками
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💕 Выбрать девушку", callback_data="choose_girl:0")],
            [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up_balance")]
        ]
    )
    
    await message.answer(menu_text, reply_markup=keyboard)


async def build_history_keyboard(
    dialogs_list: list[tuple],  # list of (girl, dialog) tuples
    page: int,
    session,
) -> tuple[str, InlineKeyboardMarkup]:
    """Создаёт клавиатуру со списком диалогов и пагинацией."""
    total_pages = math.ceil(len(dialogs_list) / DIALOGS_PER_PAGE) if dialogs_list else 1
    start_idx = page * DIALOGS_PER_PAGE
    end_idx = start_idx + DIALOGS_PER_PAGE
    page_dialogs = dialogs_list[start_idx:end_idx]

    text = "📜 История чатов\n\nВыбери диалог для просмотра:\n\n"
    keyboard_buttons = []
    
    for girl, dialog in page_dialogs:
        msg_count = await get_message_count(session, dialog_id=dialog.id)
        dialog_date = dialog.updated_at.strftime("%d.%m.%Y") if dialog.updated_at else ""
        title = dialog.title or f"Диалог от {dialog.created_at.strftime('%d.%m.%Y') if dialog.created_at else ''}"
        button_text = f"💬 {girl.name} - {title[:25]} ({msg_count}) - {dialog_date}"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_dialog:{dialog.id}"
            )
        ])
    
    # Кнопки пагинации
    nav_buttons = []
    if total_pages > 1:
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"history_page:{page - 1}")
            )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"history_page:{page + 1}")
            )
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        # Показываем номер страницы
        text += f"\n📄 Страница {page + 1} из {total_pages}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return text, keyboard


@router.message(lambda m: m.text and ("История чатов" in m.text or m.text == "📜 История чатов"))
async def handle_chat_history(message: Message) -> None:
    """Обработчик кнопки 'История чатов'."""
    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return

    async with get_session() as session:
        # НЕ завершаем диалог - просто показываем историю
        # Получаем все диалоги пользователя, сгруппированные по персонажам
        from app.repositories.dialogs import get_dialogs_by_girls
        dialogs_by_girls = await get_dialogs_by_girls(session, user_id=message.from_user.id)

        if not dialogs_by_girls:
            await message.answer(
                "📜 У тебя пока нет истории чатов с персонажами.\n"
                "💕 Начни диалог с любым персонажем!",
                reply_markup=get_main_keyboard(),
            )
            return

        # Преобразуем в плоский список (girl, dialog) для пагинации
        dialogs_list = []
        for girl, dialogs in dialogs_by_girls:
            for dialog in dialogs:
                dialogs_list.append((girl, dialog))
        
        # Сортируем по updated_at DESC (новые сначала)
        dialogs_list.sort(key=lambda x: x[1].updated_at, reverse=True)

        # Показываем первую страницу
        text, keyboard = await build_history_keyboard(dialogs_list, 0, session)
        await message.answer(text, reply_markup=keyboard)


@router.message(lambda m: m.text and ("Завершить диалог" in m.text or m.text == "❌ Завершить диалог"))
async def handle_end_dialogue(message: Message) -> None:
    """Обработчик кнопки 'Завершить диалог'."""
    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return

    async with get_session() as session:
        # Просто сбрасываем активный диалог, но не удаляем сам диалог
        # Диалог останется в истории чатов
        await set_active_dialog(session, user_id=message.from_user.id, dialog_id=None)
        await session.commit()
        
        girl = await get_selected_girl(session, user_id=message.from_user.id)
        girl_name = girl.name if girl else "персонажем"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👤 Выбрать девушку", callback_data="choose_girl:0")]]
    )
    
    await message.answer(
        f"✅ Диалог с {girl_name} завершён.\n\n"
        "💾 Диалог сохранён в истории чатов. "
        "Используй кнопку '👤 Выбрать девушку' для начала нового диалога или "
        "'📜 История чатов' для продолжения предыдущего.",
        reply_markup=keyboard,
    )
    await message.answer(reply_markup=get_main_keyboard())


@router.message(lambda m: m.text and ("Начать диалог заново" in m.text or m.text == "🔄 Начать диалог заново"))
async def handle_restart_dialogue(message: Message) -> None:
    """Обработчик кнопки 'Начать диалог заново'."""
    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return

    async with get_session() as session:
        # Сначала завершаем текущий диалог
        await set_active_dialog(session, user_id=message.from_user.id, dialog_id=None)
        
        girl = await get_selected_girl(session, user_id=message.from_user.id)
        if not girl:
            girl = await get_default_girl(session)

        if not girl:
            await message.answer("Персонажи пока не настроены.")
            return

        # Создаём новый диалог (начинаем заново)
        dialog = await create_dialog(
            session,
            user_id=message.from_user.id,
            girl_id=girl.id,
        )
        await set_active_dialog(session, user_id=message.from_user.id, dialog_id=dialog.id)
        await set_selected_girl(session, user_id=message.from_user.id, girl_id=girl.id, active_dialog_id=dialog.id)

        # Добавляем приветствие в историю
        await add_message(
            session,
            dialog_id=dialog.id,
            role="assistant",
            content=girl.greeting,
        )
        
        # Отслеживаем создание диалога
        from app.repositories.retention import track_user_activity, update_user_retention
        await update_user_retention(session, user_id=message.from_user.id)
        await track_user_activity(session, user_id=message.from_user.id, dialogs_created=1)
        
        await session.commit()

    # Отправляем введение в сюжет и приветствие
    story_intro = get_girl_story_intro(girl.name)
    image_path = get_girl_image_path(girl.name)
    
    if image_path:
        try:
            photo = FSInputFile(image_path)
            await message.answer_photo(
                photo,
                caption=story_intro,
                reply_markup=get_dialogue_keyboard()
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Не удалось отправить фото: {exc}")
            await message.answer(
                story_intro,
                reply_markup=get_dialogue_keyboard()
            )
    else:
        await message.answer(
            story_intro,
            reply_markup=get_dialogue_keyboard()
        )
    
    # Отправляем приветственное сообщение от персонажа
    await message.answer(
        f"👋 {girl.greeting}",
        reply_markup=get_dialogue_keyboard()
    )


@router.message(lambda m: m.successful_payment is None)  # Исключаем сообщения с платежами
async def handle_dialogue(message: Message) -> None:
    if not message.text:
        await message.answer("📝 Я понимаю только текстовые сообщения.")
        return

    if not message.from_user:
        await message.answer("⚠️ Не могу определить пользователя.")
        return
    
    # Проверяем, идет ли генерация изображения для этого пользователя
    if message.from_user.id in _generating_images:
        # Отправляем короткое уведомление
        # Примечание: всплывающие окна (alerts) доступны только для callback queries,
        # для обычных сообщений отправляем короткое уведомление
        warning_msg = await message.answer(
            "⏸️ Во время генерации изображения нельзя отправлять сообщения.\n"
            "⏱️ Пожалуйста, подождите завершения генерации."
        )
        # Сохраняем ссылку на сообщение-предупреждение, если его еще нет
        if _generating_images.get(message.from_user.id) is None:
            _generating_images[message.from_user.id] = warning_msg
        return

    reply_text: str | None = None
    girl_name: str | None = None
    active_dialog_id: int | None = None
    
    async with get_session() as session:
        # Получаем выбранного персонажа
        girl = await get_selected_girl(session, user_id=message.from_user.id)
        if not girl:
            girl = await get_default_girl(session)
            if girl:
                await set_selected_girl(session, user_id=message.from_user.id, girl_id=girl.id)

        if not girl:
            await message.answer("⚠️ Персонажи пока не настроены. Попробуй позже.")
            return
        
        girl_name = girl.name

        # Получаем активный диалог
        active_dialog_id = await get_active_dialog_id(session, user_id=message.from_user.id)
        if not active_dialog_id:
            # Если нет активного диалога, значит пользователь в главном меню
            # Не создаем новый диалог автоматически - нужно явно выбрать девушку
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="👤 Выбрать девушку", callback_data="choose_girl:0")]]
            )
            await message.answer(
                "💬 Для начала диалога выбери девушку через кнопку '👤 Выбрать девушку' или используй кнопки меню.",
                reply_markup=keyboard,
            )
            return
        else:
            # Проверяем, что диалог принадлежит текущему персонажу
            dialog = await get_dialog_by_id(session, active_dialog_id)
            if not dialog or dialog.girl_id != girl.id:
                # Создаём новый диалог, если активный диалог не соответствует персонажу
                dialog = await create_dialog(
                    session,
                    user_id=message.from_user.id,
                    girl_id=girl.id,
                )
                active_dialog_id = dialog.id
                await set_active_dialog(session, user_id=message.from_user.id, dialog_id=dialog.id)
                await set_selected_girl(session, user_id=message.from_user.id, girl_id=girl.id, active_dialog_id=dialog.id)
                
                # Добавляем приветствие в историю при создании нового диалога
                await add_message(
                    session,
                    dialog_id=dialog.id,
                    role="assistant",
                    content=girl.greeting,
                )

        # Списываем энергию перед генерацией ответа
        energy_spent = await spend_energy(session, user_id=message.from_user.id, amount=settings.message_energy_cost)
        if not energy_spent:
            # Получаем текущую энергию и информацию о персонаже
            current_energy = await get_user_energy(session, user_id=message.from_user.id)
            girl = await get_selected_girl(session, user_id=message.from_user.id)
            if not girl:
                girl = await get_default_girl(session)
            
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up_balance")]
                ]
            )
            
            # Сообщение от персонажа о недостатке энергии
            if girl:
                message_text = get_insufficient_balance_message(
                    girl_name=girl.name,
                    resource_type="energy",
                    current=current_energy,
                    needed=settings.message_energy_cost
                )
            else:
                message_text = (
                    f"❌ Недостаточно энергии!\n\n"
                    f"⚡ У тебя: {current_energy} энергии\n"
                    f"💰 Нужно: {settings.message_energy_cost} энергии"
                )
            await message.answer(message_text, reply_markup=keyboard)
            return
        
        # Добавляем сообщение пользователя
        await add_message(
            session,
            dialog_id=active_dialog_id,
            role="user",
            content=message.text,
        )
        
        # Отслеживаем активность
        from app.repositories.retention import (
            increment_user_messages,
            track_user_activity,
            update_user_retention,
        )
        await update_user_retention(session, user_id=message.from_user.id)
        await increment_user_messages(session, user_id=message.from_user.id)
        await track_user_activity(session, user_id=message.from_user.id, messages_count=1)

        # Получаем историю из активного диалога
        history = await get_recent_messages(
            session,
            dialog_id=active_dialog_id,
            limit=30,
        )

        history_payload = [
            {"role": msg.role, "content": msg.content}
            for msg in history
        ]
        
        # Проверяем наличие 18+ контента и обновляем флаг
        from app.services.nsfw_detector import detect_nsfw_in_messages
        from app.repositories.messages import get_all_messages
        from app.repositories.dialogs import set_dialog_nsfw_enabled, get_dialog_nsfw_enabled
        
        all_dialog_messages = await get_all_messages(session, dialog_id=active_dialog_id)
        nsfw_detected = detect_nsfw_in_messages(all_dialog_messages)
        
        # Если обнаружен 18+ контент, включаем флаг (он остается включенным навсегда)
        current_nsfw_flag = await get_dialog_nsfw_enabled(session, dialog_id=active_dialog_id)
        if nsfw_detected and not current_nsfw_flag:
            await set_dialog_nsfw_enabled(session, dialog_id=active_dialog_id, enabled=True)
        
        await session.commit()  # Сохраняем сообщение пользователя

    # Генерируем ответ через очередь
    try:
        # Показываем индикатор загрузки
        status_message = await message.answer("💭 Думаю...")
        
        # Добавляем задачу в очередь
        task_id = await enqueue_reply_generation(
            user_id=message.from_user.id,
            system_prompt=girl.system_prompt,
            history=history_payload,
            dialog_id=active_dialog_id,
            user_message=message.text,
        )
        
        # Ожидаем результат
        bot = message.bot
        task_result = await wait_for_task_result(bot, message, task_id, timeout=60.0)
        
        # Удаляем индикатор загрузки
        try:
            await status_message.delete()
        except Exception:
            pass
        
        if task_result and "reply" in task_result:
            reply_text = task_result["reply"]
        else:
            # Fallback: генерируем напрямую, если очередь не работает
            client = VeniceClient()
            try:
                reply_text = await client.generate_reply(girl.system_prompt, history_payload)
                async with get_session() as session:
                    await add_message(
                        session,
                        dialog_id=active_dialog_id,
                        role="assistant",
                        content=reply_text,
                    )
                    await session.commit()
            except Exception as exc:
                # Возвращаем энергию, если генерация не удалась
                async with get_session() as session:
                    from app.repositories.user_profile import add_energy
                    await add_energy(session, user_id=message.from_user.id, amount=settings.message_energy_cost)
                    await session.commit()
                await message.answer("⚠️ Не получилось получить ответ от модели. Энергия возвращена.")
                logging.getLogger(__name__).exception("Ошибка при обращении к Venice API", exc_info=exc)
                return
            finally:
                await client.close()
    
    except Exception as exc:
        logging.getLogger(__name__).exception("Ошибка при генерации ответа через очередь", exc_info=exc)
        # Fallback: генерируем напрямую
        client = VeniceClient()
        try:
            reply_text = await client.generate_reply(girl.system_prompt, history_payload)
            async with get_session() as session:
                await add_message(
                    session,
                    dialog_id=active_dialog_id,
                    role="assistant",
                    content=reply_text,
                )
                await session.commit()
        except Exception as exc2:
            # Возвращаем энергию, если генерация не удалась
            async with get_session() as session:
                from app.repositories.user_profile import add_energy
                await add_energy(session, user_id=message.from_user.id, amount=settings.message_energy_cost)
                await session.commit()
            await message.answer("⚠️ Не получилось получить ответ от модели. Энергия возвращена.")
            logging.getLogger(__name__).exception("Ошибка при обращении к Venice API", exc_info=exc2)
            return
        finally:
            await client.close()
    
    # Получаем информацию о пользователе для счётчика фото
    async with get_session() as session:
        from app.repositories.user_selected_girl import get_user_photos_used
        photos_used = await get_user_photos_used(session, user_id=message.from_user.id)

    if reply_text and girl_name:
        # Создаём клавиатуру с кнопкой "Получить фото" и стоимостью
        keyboard_buttons = []
        if photos_used < MAX_PHOTOS_PER_DIALOG:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📷 Получить фото ({settings.image_generation_cost} алмазов)",
                    callback_data=f"get_photo:{active_dialog_id}"
                )
            ])
        else:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📷 Лимит фото исчерпан ({photos_used}/{MAX_PHOTOS_PER_DIALOG})",
                    callback_data="photo_limit_reached"
                )
            ])
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Отправляем только текстовое сообщение с кнопкой
        await message.answer(reply_text, reply_markup=inline_keyboard)


def build_girl_keyboard(girls: list, current_index: int, selected_girl_id: int | None = None, active_dialog_id: int | None = None) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для одной девушки с навигацией и выбором."""
    total_girls = len(girls)
    if total_girls == 0:
        return InlineKeyboardMarkup(inline_keyboard=[])
    
    # Нормализуем индекс
    if current_index < 0:
        current_index = 0
    elif current_index >= total_girls:
        current_index = total_girls - 1
    
    current_girl = girls[current_index]
    # Галочка показывается только если персонаж выбран И есть активный диалог
    is_selected = selected_girl_id is not None and current_girl.id == selected_girl_id and active_dialog_id is not None
    
    keyboard_buttons = []
    
    # Кнопки навигации с номером
    nav_buttons = []
    if total_girls > 1:
        if current_index > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"choose_girl:{current_index - 1}"))
        else:
            # Если первая девушка, кнопка "Назад" ведет к последней
            nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"choose_girl:{total_girls - 1}"))
        
        # Номер девушки в середине
        nav_buttons.append(InlineKeyboardButton(
            text=f"📄 {current_index + 1} / {total_girls}",
            callback_data="girl_info_dummy"  # Неактивная кнопка для отображения
        ))
        
        if current_index < total_girls - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"choose_girl:{current_index + 1}"))
        else:
            # Если последняя девушка, кнопка "Вперёд" ведет к первой
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"choose_girl:0"))
        
        keyboard_buttons.append(nav_buttons)
    
    # Кнопка выбора отдельной строкой
        select_text = "✅ Выбрать" if is_selected else "👤 Выбрать"
    keyboard_buttons.append([
        InlineKeyboardButton(text=select_text, callback_data=f"select_girl:{current_girl.id}")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


@router.callback_query(lambda c: c.data == "girl_info_dummy")
async def handle_girl_info_dummy(callback: CallbackQuery) -> None:
    """Обработчик для неактивной кнопки с номером девушки."""
    await callback.answer()  # Просто отвечаем на callback без действий


@router.callback_query(lambda c: c.data and c.data.startswith("choose_girl:"))
async def handle_choose_girl_callback(callback: CallbackQuery) -> None:
    """Обработчик для показа одной девушки с навигацией."""
    # Отвечаем сразу, чтобы убрать индикатор загрузки
    await callback.answer()
    
    if not callback.from_user:
        return

    try:
        girl_index = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        girl_index = 0

    async with get_session() as session:
        girls = await get_all_girls(session)
        selected_girl = await get_selected_girl(session, user_id=callback.from_user.id)
        selected_girl_id = selected_girl.id if selected_girl else None
        # Проверяем наличие активного диалога
        active_dialog_id = await get_active_dialog_id(session, user_id=callback.from_user.id)

    if not girls:
        await callback.message.answer("👥 Пока нет доступных персонажей.")
        return

    # Нормализуем индекс
    total_girls = len(girls)
    if girl_index < 0:
        girl_index = 0
    elif girl_index >= total_girls:
        girl_index = total_girls - 1

    current_girl = girls[girl_index]
    
    # Формируем текст с информацией о девушке
    # Галочка показывается только если персонаж выбран И есть активный диалог
    is_selected = selected_girl_id is not None and current_girl.id == selected_girl_id and active_dialog_id is not None
    marker = "✅ " if is_selected else ""
    
    # Получаем описание девушки
    description = get_girl_description(current_girl)
    
    text = f"{marker}{current_girl.name}\n\n{description}"

    keyboard = build_girl_keyboard(girls, girl_index, selected_girl_id, active_dialog_id)
    
    # Добавляем кнопку возврата в главное меню
    back_button = InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main_menu")
    # Добавляем кнопку в конец клавиатуры
    if keyboard.inline_keyboard:
        keyboard.inline_keyboard.append([back_button])
    else:
        keyboard.inline_keyboard = [[back_button]]
    
    # Получаем фото девушки
    image_path = get_girl_image_path(current_girl.name)
    
    if image_path:
        try:
            photo = FSInputFile(image_path)
            # Проверяем, есть ли уже фото в сообщении
            if callback.message.photo:
                # Если есть фото, редактируем его
                from aiogram.types import InputMediaPhoto
                media = InputMediaPhoto(media=photo, caption=text)
                await safe_edit_media(callback.message, media, reply_markup=keyboard)
            else:
                # Если нет фото, но есть текстовое сообщение - редактируем его на фото
                # Сначала удаляем старое сообщение, так как нельзя изменить текстовое на фото
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.message.answer_photo(photo, caption=text, reply_markup=keyboard)
            return
        except Exception as exc:
            # Игнорируем таймауты и другие ошибки при отправке фото - переходим к текстовому варианту
            error_str = str(exc).lower()
            if "timeout" not in error_str and "message is not modified" not in error_str:
                logging.getLogger(__name__).warning(f"Не удалось отправить фото: {exc}")
    
    # Если фото не удалось отправить, редактируем текстовое сообщение
    if callback.message.photo:
        # Если было фото, но нужно показать текстовое - удаляем и отправляем новое
        # (нельзя изменить фото на текст напрямую)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard)
    else:
        # Редактируем текстовое сообщение
        await safe_edit_text(callback.message, text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data.startswith("select_girl:"))
async def handle_select_girl_callback(callback: CallbackQuery) -> None:
    """Обработчик для выбора персонажа."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка: не могу определить пользователя.", show_alert=True)
        return

    try:
        girl_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("⚠️ Ошибка: неверный ID персонажа.", show_alert=True)
        return

    async with get_session() as session:
        girl = await get_girl_by_id(session, girl_id)
        if not girl:
            await callback.answer("👤 Персонаж не найден.", show_alert=True)
            return

        # Создаём новый диалог при выборе девушки
        dialog = await create_dialog(
            session,
            user_id=callback.from_user.id,
            girl_id=girl_id,
        )
        await set_selected_girl(session, user_id=callback.from_user.id, girl_id=girl_id, active_dialog_id=dialog.id)
        await set_active_dialog(session, user_id=callback.from_user.id, dialog_id=dialog.id)
        
        # Добавляем приветствие в историю
        from app.repositories.messages import add_message
        await add_message(
            session,
            dialog_id=dialog.id,
            role="assistant",
            content=girl.greeting,
        )
        
        # Отслеживаем создание диалога
        from app.repositories.retention import track_user_activity, update_user_retention
        await update_user_retention(session, user_id=callback.from_user.id)
        await track_user_activity(session, user_id=callback.from_user.id, dialogs_created=1)
        
        await session.commit()

    # Удаляем старое сообщение с выбором девушек
    try:
        await callback.message.delete()
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Не удалось удалить старое сообщение: {exc}")
    
    # Отправляем сообщение с введением в сюжет
    story_intro = get_girl_story_intro(girl.name)
    image_path = get_girl_image_path(girl.name)
    
    if image_path:
        try:
            photo = FSInputFile(image_path)
            await callback.message.answer_photo(
                photo,
                caption=story_intro,
                reply_markup=get_dialogue_keyboard()
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Не удалось отправить фото: {exc}")
            # Если не удалось отправить фото, отправляем текстовое сообщение
            await callback.message.answer(
                story_intro,
                reply_markup=get_dialogue_keyboard()
            )
    else:
        # Если фото не найдено, отправляем текстовое сообщение
        await callback.message.answer(
            story_intro,
            reply_markup=get_dialogue_keyboard()
        )
    
    # Отправляем приветственное сообщение от персонажа
    await callback.message.answer(
        f"👋 {girl.greeting}",
        reply_markup=get_dialogue_keyboard()
    )
    
    await callback.answer(f"✅ Выбрана {girl.name}!")


@router.callback_query(lambda c: c.data and c.data.startswith("view_dialog:"))
async def handle_view_history_callback(callback: CallbackQuery) -> None:
    """Обработчик для просмотра истории конкретного диалога."""
    # Отвечаем сразу
    await callback.answer()
    
    if not callback.from_user:
        return

    try:
        parts = callback.data.split(":")
        dialog_id = int(parts[1])
    except (ValueError, IndexError):
        await callback.answer("⚠️ Ошибка: неверный формат данных.", show_alert=True)
        return

    async with get_session() as session:
        from app.repositories.dialogs import get_dialog_by_id
        
        dialog = await get_dialog_by_id(session, dialog_id)
        if not dialog:
            await callback.message.answer("💬 Диалог не найден.")
            return
        
        # Проверяем, что диалог принадлежит пользователю
        if dialog.user_id != callback.from_user.id:
            await callback.message.answer("🔒 У тебя нет доступа к этому диалогу.")
            return
        
        girl = await get_girl_by_id(session, dialog.girl_id)
        if not girl:
            await callback.message.answer("👤 Персонаж не найден.")
            return

        # Получаем последние сообщения диалога (8 сообщений)
        recent_messages = await get_recent_messages(
            session,
            dialog_id=dialog_id,
            limit=8,
        )

        if not recent_messages:
            await callback.message.answer("📜 История пуста.")
            return

        # Формируем текст истории с датами
        dialog_title = dialog.title or f"Диалог от {dialog.created_at.strftime('%d.%m.%Y') if dialog.created_at else ''}"
        text = f"💬 {girl.name} - {dialog_title}\n\n"
        text += "─" * 30 + "\n\n"

        for msg in recent_messages:
            role_emoji = "👤 Ты" if msg.role == "user" else f"🤖 {girl.name}"
            
            # Форматируем дату
            msg_date = msg.created_at
            if msg_date:
                date_str = msg_date.strftime("%d.%m.%Y %H:%M")
            else:
                date_str = "Неизвестно"
            
            # Обрезаем длинные сообщения
            content = msg.content
            if len(content) > 150:
                content = content[:150] + "..."
            
            text += f"{role_emoji}\n"
            text += f"📅 {date_str}\n"
            text += f"{content}\n\n"
            text += "─" * 30 + "\n\n"

        # Формируем клавиатуру
        keyboard_buttons = [
            [InlineKeyboardButton(text="💬 Продолжить чат", callback_data=f"continue_dialog:{dialog_id}")],
            [InlineKeyboardButton(text="🔙 К списку чатов", callback_data="back_to_history_list")],
        ]

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await safe_edit_text(callback.message, text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data == "back_to_history_list")
async def handle_back_to_history_list(callback: CallbackQuery) -> None:
    """Обработчик для возврата к списку диалогов в истории."""
    # Отвечаем сразу
    await callback.answer()
    
    if not callback.from_user:
        return

    async with get_session() as session:
        from app.repositories.dialogs import get_dialogs_by_girls
        dialogs_by_girls = await get_dialogs_by_girls(session, user_id=callback.from_user.id)

        if not dialogs_by_girls:
            await callback.message.edit_text(
                "📜 У тебя пока нет истории чатов с персонажами.\n"
                "💕 Начни диалог с любым персонажем!",
            )
            return

        # Преобразуем в плоский список (girl, dialog) для пагинации
        dialogs_list = []
        for girl, dialogs in dialogs_by_girls:
            for dialog in dialogs:
                dialogs_list.append((girl, dialog))
        
        # Сортируем по updated_at DESC (новые сначала)
        dialogs_list.sort(key=lambda x: x[1].updated_at, reverse=True)

        # Показываем первую страницу
        text, keyboard = await build_history_keyboard(dialogs_list, 0, session)
        await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data.startswith("history_page:"))
async def handle_history_page_callback(callback: CallbackQuery) -> None:
    """Обработчик для пагинации истории чатов."""
    # Отвечаем сразу
    await callback.answer()
    
    if not callback.from_user:
        return

    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("⚠️ Ошибка: неверный номер страницы.", show_alert=True)
        return

    async with get_session() as session:
        from app.repositories.dialogs import get_dialogs_by_girls
        dialogs_by_girls = await get_dialogs_by_girls(session, user_id=callback.from_user.id)

        if not dialogs_by_girls:
            await callback.answer("📜 История пуста.", show_alert=True)
            return

        # Преобразуем в плоский список (girl, dialog) для пагинации
        dialogs_list = []
        for girl, dialogs in dialogs_by_girls:
            for dialog in dialogs:
                dialogs_list.append((girl, dialog))
        
        # Сортируем по updated_at DESC (новые сначала)
        dialogs_list.sort(key=lambda x: x[1].updated_at, reverse=True)

        # Проверяем валидность страницы
        total_pages = math.ceil(len(dialogs_list) / DIALOGS_PER_PAGE) if dialogs_list else 1
        if page < 0 or page >= total_pages:
            await callback.answer("⚠️ Неверный номер страницы.", show_alert=True)
            return

        # Показываем запрошенную страницу
        text, keyboard = await build_history_keyboard(dialogs_list, page, session)
        await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data == "top_up_balance")
async def handle_top_up_balance_callback(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Пополнить баланс'."""
    if not callback.from_user:
        await callback.message.answer("⚠️ Не могу определить пользователя.")
        return
    
    await callback.answer()
    
    # Показываем выбор категории
    text = "💰 Пополнить баланс\n\nВыберите, что вы хотите пополнить:"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 Пакеты", callback_data="top_up_packages"),
                InlineKeyboardButton(text="💎 Алмазы", callback_data="top_up_diamonds"),
                InlineKeyboardButton(text="⚡ Энергия", callback_data="top_up_energy")
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main_menu")]
        ]
    )
    
    # Редактируем сообщение главного меню на сообщение пополнения баланса
    try:
        if callback.message.photo:
            # Если сообщение с фото, удаляем и отправляем текстовое
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=keyboard)
        else:
            # Если текстовое, редактируем
            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as exc:
        # Если редактирование не удалось, удаляем и отправляем новое
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data == "top_up_packages")
async def handle_top_up_packages_callback(callback: CallbackQuery) -> None:
    """Обработчик выбора категории 'Пакеты'."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    await callback.answer()
    
    text = (
        "📦 Пакеты\n\n"
        "Выберите пакет:\n\n"
        "🎁 Starter Pack\n"
        "   💰 350 ⭐ ($6.99)\n"
        "   Включает в себя:\n"
        "   ⚡ 300 энергии\n"
        "   💎 300 алмазов\n\n"
        "🎁 Premium Pack\n"
        "   💰 1 000 ⭐ ($19.99)\n"
        "   Включает в себя:\n"
        "   ⚡ 1 000 энергии\n"
        "   💎 1 000 алмазов\n\n"
        "🎁 Ultimate Pack\n"
        "   💰 2 500 ⭐ ($49.99)\n"
        "   Включает в себя:\n"
        "   ⚡ 3 000 энергии\n"
        "   💎 3 000 алмазов"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Starter Pack (350⭐)", callback_data="buy_pack:starter:300:300:350")],
            [InlineKeyboardButton(text="🎁 Premium Pack (1000⭐)", callback_data="buy_pack:premium:1000:1000:1000")],
            [InlineKeyboardButton(text="🎁 Ultimate Pack (2500⭐)", callback_data="buy_pack:ultimate:3000:3000:2500")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="top_up_balance")]
        ]
    )
    
    # Редактируем сообщение пополнения баланса на сообщение с пакетами
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=keyboard)
        else:
            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as exc:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data == "top_up_diamonds")
async def handle_top_up_diamonds_callback(callback: CallbackQuery) -> None:
    """Обработчик выбора категории 'Алмазы'."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    await callback.answer()
    
    text = (
        "💎 Алмазы\n\n"
        "Выберите количество:\n\n"
        "💎 50 алмазов\n"
        "   🎁 БЕСПЛАТНО (временно)\n\n"
        "💎 150 алмазов\n"
        "   💰 125 ⭐ ($2.49)\n\n"
        "💎 500 алмазов\n"
        "   💰 350 ⭐ ($6.99)\n\n"
        "💎 1 200 алмазов\n"
        "   💰 750 ⭐ ($14.99)\n\n"
        "💎 3 000 алмазов\n"
        "   💰 1 500 ⭐ ($29.99)"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 50 алмазов (БЕСПЛАТНО)", callback_data="buy_diamonds:50:1")],
            [InlineKeyboardButton(text="💎 150 алмазов (125⭐)", callback_data="buy_diamonds:150:125")],
            [InlineKeyboardButton(text="💎 500 алмазов (350⭐)", callback_data="buy_diamonds:500:350")],
            [InlineKeyboardButton(text="💎 1 200 алмазов (750⭐)", callback_data="buy_diamonds:1200:750")],
            [InlineKeyboardButton(text="💎 3 000 алмазов (1500⭐)", callback_data="buy_diamonds:3000:1500")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="top_up_balance")]
        ]
    )
    
    # Редактируем сообщение пополнения баланса на сообщение с алмазами
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=keyboard)
        else:
            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as exc:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data == "top_up_energy")
async def handle_top_up_energy_callback(callback: CallbackQuery) -> None:
    """Обработчик выбора категории 'Энергия'."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    await callback.answer()
    
    text = (
        "⚡ Энергия\n\n"
        "Выберите количество:\n\n"
        "⚡ 50 энергии\n"
        "   💰 1 ⭐ (временно)\n\n"
        "⚡ 150 энергии\n"
        "   💰 125 ⭐ ($2.49)\n\n"
        "⚡ 500 энергии\n"
        "   💰 350 ⭐ ($6.99)\n\n"
        "⚡ 1 200 энергии\n"
        "   💰 750 ⭐ ($14.99)\n\n"
        "⚡ 3 000 энергии\n"
        "   💰 1 500 ⭐ ($29.99)"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ 50 энергии (1⭐)", callback_data="buy_energy:50:1")],
            [InlineKeyboardButton(text="⚡ 150 энергии (125⭐)", callback_data="buy_energy:150:125")],
            [InlineKeyboardButton(text="⚡ 500 энергии (350⭐)", callback_data="buy_energy:500:350")],
            [InlineKeyboardButton(text="⚡ 1 200 энергии (750⭐)", callback_data="buy_energy:1200:750")],
            [InlineKeyboardButton(text="⚡ 3 000 энергии (1500⭐)", callback_data="buy_energy:3000:1500")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="top_up_balance")]
        ]
    )
    
    # Редактируем сообщение пополнения баланса на сообщение с энергией
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=keyboard)
        else:
            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as exc:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data.startswith("buy_diamonds:"))
async def handle_buy_diamonds_callback(callback: CallbackQuery) -> None:
    """Обработчик покупки алмазов."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    try:
        parts = callback.data.split(":")
        amount = int(parts[1])  # Количество алмазов
        stars = int(parts[2])  # Стоимость в Stars
    except (ValueError, IndexError):
        await callback.answer("⚠️ Ошибка в данных", show_alert=True)
        return
    
    await callback.answer()
    
    # Временно: 50 алмазов бесплатно (начисляем напрямую без инвойса)
    if amount == 50 and stars == 1:
        async with get_session() as session:
            from app.repositories.user_profile import add_diamonds
            from app.repositories.payments import create_payment
            
            # Начисляем алмазы
            await add_diamonds(session, user_id=callback.from_user.id, amount=amount)
            
            # Записываем "бесплатную" покупку в базу (0 stars, но с amount=50)
            await create_payment(
                session,
                user_id=callback.from_user.id,
                payment_type="diamonds",
                amount_stars=0,  # Бесплатно
                amount_usd=0.0,
                diamonds_received=amount,
                energy_received=0,
            )
            
            await session.commit()
            
            # Получаем обновленное количество алмазов
            from app.repositories.user_profile import get_user_diamonds
            new_diamonds = await get_user_diamonds(session, user_id=callback.from_user.id)
        
        # Редактируем сообщение с ценами на сообщение об успешном пополнении
        success_text = (
            f"✅ Вы успешно пополнили баланс!\n\n"
            f"💎 Получено: {amount} алмазов (бесплатно)\n"
            f"💎 Теперь у тебя: {new_diamonds} алмазов"
        )
        try:
            await callback.message.edit_text(success_text)
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Не удалось отредактировать сообщение: {exc}")
            await callback.message.answer(success_text)
        return
    
    # Для остальных сумм создаем инвойс
    # Сохраняем message_id сообщения с ценами в payload для последующего редактирования
    price_message_id = callback.message.message_id
    title = f"Покупка {amount} алмазов"
    description = f"Вы получите {amount} алмазов за {stars} Telegram Stars"
    payload = f"diamonds_{amount}_{callback.from_user.id}_msg_{price_message_id}"
    currency = "XTR"  # Telegram Stars currency code
    prices = [LabeledPrice(label=f"{amount} алмазов", amount=stars)]
    
    await callback.message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Для Telegram Stars не нужен
        currency=currency,
        prices=prices,
        start_parameter=f"diamonds_{amount}",
    )


@router.callback_query(lambda c: c.data and c.data.startswith("buy_energy:"))
async def handle_buy_energy_callback(callback: CallbackQuery) -> None:
    """Обработчик покупки энергии."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    try:
        parts = callback.data.split(":")
        amount = int(parts[1])  # Количество энергии
        stars = int(parts[2])  # Стоимость в Stars
    except (ValueError, IndexError):
        await callback.answer("⚠️ Ошибка в данных", show_alert=True)
        return
    
    await callback.answer()
    
    # Сохраняем message_id сообщения с ценами в payload для последующего редактирования
    price_message_id = callback.message.message_id
    # Создаем инвойс для Telegram Stars
    title = f"Покупка {amount} энергии"
    description = f"Вы получите {amount} энергии за {stars} Telegram Stars"
    payload = f"energy_{amount}_{callback.from_user.id}_msg_{price_message_id}"
    currency = "XTR"  # Telegram Stars currency code
    prices = [LabeledPrice(label=f"{amount} энергии", amount=stars)]
    
    await callback.message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Для Telegram Stars не нужен
        currency=currency,
        prices=prices,
        start_parameter=f"energy_{amount}",
    )


@router.callback_query(lambda c: c.data and c.data.startswith("buy_pack:"))
async def handle_buy_pack_callback(callback: CallbackQuery) -> None:
    """Обработчик покупки пакета."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    try:
        parts = callback.data.split(":")
        pack_type = parts[1]  # starter, premium, ultimate
        energy = int(parts[2])  # Количество энергии
        diamonds = int(parts[3])  # Количество алмазов
        stars = int(parts[4])  # Стоимость в Stars
    except (ValueError, IndexError):
        await callback.answer("⚠️ Ошибка в данных", show_alert=True)
        return
    
    await callback.answer()
    
    # Названия пакетов
    pack_names = {
        "starter": "Starter Pack",
        "premium": "Premium Pack",
        "ultimate": "Ultimate Pack"
    }
    pack_name = pack_names.get(pack_type, "Пакет")
    
    # Сохраняем message_id сообщения с ценами в payload для последующего редактирования
    price_message_id = callback.message.message_id
    # Создаем инвойс для Telegram Stars
    title = f"{pack_name}"
    description = f"Включает в себя: {energy} энергии ⚡ и {diamonds} алмазов 💎"
    payload = f"pack_{pack_type}_{energy}_{diamonds}_{callback.from_user.id}_msg_{price_message_id}"
    currency = "XTR"  # Telegram Stars currency code
    prices = [LabeledPrice(label=f"{pack_name} ({energy}⚡ + {diamonds}💎)", amount=stars)]
    
    await callback.message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Для Telegram Stars не нужен
        currency=currency,
        prices=prices,
        start_parameter=f"pack_{pack_type}",
    )


@router.callback_query(lambda c: c.data and c.data.startswith("buy_combo:"))
async def handle_buy_combo_callback(callback: CallbackQuery) -> None:
    """Обработчик покупки комбо (алмазы + энергия)."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    try:
        parts = callback.data.split(":")
        diamonds = int(parts[1])  # Количество алмазов
        energy = int(parts[2])  # Количество энергии
        stars = int(parts[3])  # Стоимость в Stars
    except (ValueError, IndexError):
        await callback.answer("⚠️ Ошибка в данных", show_alert=True)
        return
    
    await callback.answer()
    
    # Сохраняем message_id сообщения с ценами в payload для последующего редактирования
    price_message_id = callback.message.message_id
    # Создаем инвойс для Telegram Stars
    title = f"Комбо: {diamonds} алмазов + {energy} энергии"
    description = f"Вы получите {diamonds} алмазов и {energy} энергии за {stars} Telegram Stars"
    payload = f"combo_{diamonds}_{energy}_{callback.from_user.id}_msg_{price_message_id}"
    currency = "XTR"  # Telegram Stars currency code
    prices = [LabeledPrice(label=f"Комбо {diamonds}💎 + {energy}⚡", amount=stars)]
    
    await callback.message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Для Telegram Stars не нужен
        currency=currency,
        prices=prices,
        start_parameter=f"combo_{diamonds}_{energy}",
    )


@router.pre_checkout_query()
async def handle_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    """Обработчик предварительной проверки платежа."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Pre-checkout query received: user_id={pre_checkout_query.from_user.id if pre_checkout_query.from_user else None}, payload={pre_checkout_query.invoice_payload}")
    # Подтверждаем платеж
    await pre_checkout_query.answer(ok=True)


@router.message(lambda m: m.successful_payment is not None)
async def handle_successful_payment(message: Message) -> None:
    """Обработчик успешного платежа."""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"=== PAYMENT RECEIVED === user_id={message.from_user.id if message.from_user else None}, has_payment={message.successful_payment is not None}")
    
    if not message.from_user or not message.successful_payment:
        logger.warning("handle_successful_payment: missing user or payment")
        return
    
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    logger.info(f"handle_successful_payment: user_id={message.from_user.id}, payload={payload}, amount={payment.total_amount}, charge_id={payment.telegram_payment_charge_id}")
    
    # Парсим payload: diamonds_10_123456789_msg_12345 или energy_25_123456789_msg_12345 или combo_20_20_123456789_msg_12345 или pack_starter_300_300_123456789_msg_12345
    # Извлекаем message_id из payload (если есть)
    price_message_id = None
    if "_msg_" in payload:
        try:
            msg_index = payload.rfind("_msg_")
            if msg_index != -1:
                price_message_id = int(payload[msg_index + 5:])  # +5 для "_msg_"
                # Убираем _msg_XXX из payload для корректного парсинга
                payload = payload[:msg_index]
        except (ValueError, IndexError):
            pass
    
    parts = payload.split("_")
    
    try:
        async with get_session() as session:
            from app.repositories.payments import create_payment
            
            if parts[0] == "diamonds":
                # Покупка алмазов
                amount = int(parts[1])
                amount_stars = payment.total_amount  # Сумма в Stars
                
                await add_diamonds(session, user_id=message.from_user.id, amount=amount)
                
                # Сохраняем информацию о платеже
                await create_payment(
                    session=session,
                    user_id=message.from_user.id,
                    payment_type="diamonds",
                    amount_stars=amount_stars,
                    diamonds_received=amount,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    telegram_provider_payment_charge_id=payment.provider_payment_charge_id,
                )
                
                await session.commit()
                logger.info(f"Payment saved: user_id={message.from_user.id}, type=diamonds, stars={amount_stars}, amount={amount}")
                
                # Редактируем сообщение с ценами на сообщение об успешном пополнении
                success_text = f"✅ Вы успешно пополнили баланс!\n\n💎 Получено: {amount} алмазов"
                if price_message_id:
                    try:
                        await message.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=price_message_id,
                            text=success_text
                        )
                    except Exception as exc:
                        logger.warning(f"Не удалось отредактировать сообщение с ценами: {exc}")
                        await message.answer(success_text)
                else:
                    await message.answer(success_text)
            elif parts[0] == "energy":
                # Покупка энергии
                amount = int(parts[1])
                amount_stars = payment.total_amount
                
                await add_energy(session, user_id=message.from_user.id, amount=amount)
                
                # Сохраняем информацию о платеже
                await create_payment(
                    session=session,
                    user_id=message.from_user.id,
                    payment_type="energy",
                    amount_stars=amount_stars,
                    energy_received=amount,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    telegram_provider_payment_charge_id=payment.provider_payment_charge_id,
                )
                
                await session.commit()
                logger.info(f"Payment saved: user_id={message.from_user.id}, type=energy, stars={amount_stars}, amount={amount}")
                
                # Редактируем сообщение с ценами на сообщение об успешном пополнении
                success_text = f"✅ Вы успешно пополнили баланс!\n\n⚡ Получено: {amount} энергии"
                if price_message_id:
                    try:
                        await message.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=price_message_id,
                            text=success_text
                        )
                    except Exception as exc:
                        logger.warning(f"Не удалось отредактировать сообщение с ценами: {exc}")
                        await message.answer(success_text)
                else:
                    await message.answer(success_text)
            elif parts[0] == "combo":
                # Покупка комбо
                diamonds = int(parts[1])
                energy = int(parts[2])
                amount_stars = payment.total_amount
                
                await add_diamonds(session, user_id=message.from_user.id, amount=diamonds)
                await add_energy(session, user_id=message.from_user.id, amount=energy)
                
                # Сохраняем информацию о платеже
                await create_payment(
                    session=session,
                    user_id=message.from_user.id,
                    payment_type="combo",
                    amount_stars=amount_stars,
                    diamonds_received=diamonds,
                    energy_received=energy,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    telegram_provider_payment_charge_id=payment.provider_payment_charge_id,
                )
                
                await session.commit()
                logger.info(f"Payment saved: user_id={message.from_user.id}, type=combo, stars={amount_stars}, diamonds={diamonds}, energy={energy}")
                
                # Редактируем сообщение с ценами на сообщение об успешном пополнении
                success_text = f"✅ Вы успешно пополнили баланс!\n\n💎 Получено: {diamonds} алмазов\n⚡ Получено: {energy} энергии"
                if price_message_id:
                    try:
                        await message.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=price_message_id,
                            text=success_text
                        )
                    except Exception as exc:
                        logger.warning(f"Не удалось отредактировать сообщение с ценами: {exc}")
                        await message.answer(success_text)
                else:
                    await message.answer(success_text)
            elif parts[0] == "pack":
                # Покупка пакета
                pack_type = parts[1]  # starter, premium, ultimate
                energy = int(parts[2])
                diamonds = int(parts[3])
                amount_stars = payment.total_amount
                
                pack_names = {
                    "starter": "Starter Pack",
                    "premium": "Premium Pack",
                    "ultimate": "Ultimate Pack"
                }
                pack_name = pack_names.get(pack_type, "Пакет")
                
                await add_diamonds(session, user_id=message.from_user.id, amount=diamonds)
                await add_energy(session, user_id=message.from_user.id, amount=energy)
                
                # Сохраняем информацию о платеже
                await create_payment(
                    session=session,
                    user_id=message.from_user.id,
                    payment_type="pack",
                    amount_stars=amount_stars,
                    diamonds_received=diamonds,
                    energy_received=energy,
                    pack_name=pack_name,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    telegram_provider_payment_charge_id=payment.provider_payment_charge_id,
                )
                
                await session.commit()
                logger.info(f"Payment saved: user_id={message.from_user.id}, type=pack, stars={amount_stars}")
                
                # Редактируем сообщение с ценами на сообщение об успешном пополнении
                success_text = (
                    f"✅ Вы успешно пополнили баланс!\n\n"
                    f"🎁 Получен пакет: {pack_name}\n"
                    f"💎 Алмазов: {diamonds}\n"
                    f"⚡ Энергии: {energy}"
                )
                if price_message_id:
                    try:
                        await message.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=price_message_id,
                            text=success_text
                        )
                    except Exception as exc:
                        logger.warning(f"Не удалось отредактировать сообщение с ценами: {exc}")
                        await message.answer(success_text)
                else:
                    await message.answer(success_text)
    except Exception as e:
        logger.error(f"Error processing payment: {e}", exc_info=True)
        await message.answer(f"⚠️ Произошла ошибка при обработке платежа. Пожалуйста, обратитесь к администратору.")


@router.callback_query(lambda c: c.data and c.data == "back_to_main_menu")
async def handle_back_to_main_menu_callback(callback: CallbackQuery) -> None:
    """Обработчик для возврата в главное меню."""
    if not callback.from_user:
        await callback.message.answer("⚠️ Не могу определить пользователя.")
        return
    
    await callback.answer()
    
    async with get_session() as session:
        # Проверяем, есть ли активный диалог, и завершаем его
        active_dialog_id = await get_active_dialog_id(session, user_id=callback.from_user.id)
        if active_dialog_id:
            # Завершаем диалог (устанавливаем active_dialog_id в None)
            await set_active_dialog(session, user_id=callback.from_user.id, dialog_id=None)
            await session.commit()
        
        # Получаем информацию о профиле для главного меню
        diamonds = await get_user_diamonds(session, user_id=callback.from_user.id)
        energy = await get_user_energy(session, user_id=callback.from_user.id)
    
    # Формируем текст главного меню с информацией о профиле
    menu_text = (
        f"🏠 Главное меню\n\n"
        f"💎 Алмазы: {diamonds}\n"
        f"   💰 Стоимость генерации изображения: {settings.image_generation_cost} алмазов\n\n"
        f"⚡ Энергия: {energy}\n"
        f"   💬 Стоимость сообщения: {settings.message_energy_cost} энергии"
    )
    
    # Показываем главное меню с кнопками (такие же, как в обработчике встроенной кнопки)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💕 Выбрать девушку", callback_data="choose_girl:0")],
            [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up_balance")]
        ]
    )
    
    # Пытаемся отредактировать сообщение, если не получается - удаляем и отправляем новое
    try:
        if callback.message.photo:
            # Если сообщение с фото, удаляем и отправляем текстовое
            await callback.message.delete()
            await callback.message.answer(menu_text, reply_markup=keyboard)
        else:
            # Если текстовое, редактируем
            await callback.message.edit_text(menu_text, reply_markup=keyboard)
    except Exception as exc:
        # Если редактирование не удалось, удаляем и отправляем новое
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(menu_text, reply_markup=keyboard)


@router.callback_query(lambda c: c.data and c.data.startswith("get_photo:"))
async def handle_get_photo_callback(callback: CallbackQuery) -> None:
    """Обработчик для кнопки 'Получить фото'."""
    # Отвечаем на callback СРАЗУ, чтобы избежать таймаута
    await callback.answer()
    
    if not callback.from_user:
        await callback.message.answer("⚠️ Ошибка: не могу определить пользователя.")
        return

    try:
        dialog_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.message.answer("⚠️ Ошибка: неверный ID диалога.")
        return

    async with get_session() as session:
        # Проверяем наличие алмазов
        diamonds = await get_user_diamonds(session, user_id=callback.from_user.id)
        from app.repositories.dialogs import get_dialog_by_id
        from app.repositories.user_selected_girl import get_user_photos_used, increment_user_photos_used
        
        dialog = await get_dialog_by_id(session, dialog_id)
        if not dialog:
            await callback.message.answer("💬 Диалог не найден.")
            return
        
        # Проверяем, что диалог принадлежит пользователю
        if dialog.user_id != callback.from_user.id:
            await callback.message.answer("🔒 У тебя нет доступа к этому диалогу.")
            return
        
        # Получаем информацию о персонаже
        girl = await get_girl_by_id(session, dialog.girl_id)
        if not girl:
            await callback.message.answer("👤 Персонаж не найден.")
            return
        
        # Проверяем баланс алмазов
        if diamonds < settings.image_generation_cost:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up_balance")]
                ]
            )
            # Сообщение от персонажа о недостатке алмазов
            message_text = get_insufficient_balance_message(
                girl_name=girl.name,
                resource_type="diamonds",
                current=diamonds,
                needed=settings.image_generation_cost
            )
            await callback.message.answer(message_text, reply_markup=keyboard)
            return
        
        # Проверяем общий лимит фото для пользователя (для всех девушек)
        photos_used = await get_user_photos_used(session, user_id=callback.from_user.id)
        if photos_used >= MAX_PHOTOS_PER_DIALOG:
            await callback.message.answer(f"📷 Лимит фото исчерпан ({photos_used}/{MAX_PHOTOS_PER_DIALOG})")
            return
        
        # Списываем алмазы перед генерацией
        diamonds_spent = await spend_diamonds(session, user_id=callback.from_user.id, amount=settings.image_generation_cost)
        if not diamonds_spent:
            # Получаем текущее количество алмазов для отображения
            current_diamonds = await get_user_diamonds(session, user_id=callback.from_user.id)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up_balance")]
                ]
            )
            # Сообщение от персонажа о недостатке алмазов
            message_text = get_insufficient_balance_message(
                girl_name=girl.name,
                resource_type="diamonds",
                current=current_diamonds,
                needed=settings.image_generation_cost
            )
            await callback.message.answer(message_text, reply_markup=keyboard)
            return
        
        await session.commit()
        
        # Получаем все сообщения для анализа контекста
        all_messages = await get_all_messages(session, dialog_id=dialog_id)
        
        # Используем базовый промпт с характеристиками персонажа и одеждой
        base_prompt = build_image_prompt(
            girl_name=girl.name,
            clothing_description=girl.clothing_description,
        )
        
        # Формируем контекст из диалога (только эмоции и уровень обнажения)
        if all_messages:
            # Берем последние сообщения для анализа
            recent_messages = list(all_messages[-15:]) if len(all_messages) >= 15 else all_messages
            
            # Формируем диалог из последних сообщений
            recent_dialogue = [
                {"role": msg.role, "content": msg.content}
                for msg in recent_messages
            ]
            
            venice_client = VeniceClient()
            try:
                girl_description = f"{girl.name}, {girl.system_prompt[:200]}"
                
                # Определяем, какую одежду снимает персонаж при раздевании
                undressing_clothing = {
                    "Стейси": "shirt",  # рубашка
                    "Аманда": "dress",  # платье
                    "Джейн": "dress",   # платье
                }
                clothing_item = undressing_clothing.get(girl.name, "clothes")
                
                dialogue_context = await venice_client.generate_image_prompt(
                    girl_name=girl.name,
                    girl_description=girl_description,
                    recent_dialogue=recent_dialogue,
                    full_dialogue=None,  # Не нужен полный диалог
                    undressing_clothing=clothing_item,
                )
                # Добавляем контекст к базовому промпту
                if dialogue_context and len(dialogue_context.strip()) > 5:
                    image_prompt = f"{base_prompt}, {dialogue_context}"
                else:
                    image_prompt = base_prompt
            except Exception as exc:
                logging.getLogger(__name__).warning(f"Не удалось добавить контекст через ИИ: {exc}")
                image_prompt = base_prompt
            finally:
                await venice_client.close()
        else:
            # Если нет истории, используем только базовый промпт
            image_prompt = base_prompt
        
        # Генерируем и отправляем изображение через очередь
        # Устанавливаем флаг генерации
        if callback.from_user:
            _generating_images[callback.from_user.id] = None
        
        try:
            # Отправляем сообщение о начале генерации
            status_message = await callback.message.answer(
                "🎨 Генерирую фото...\n"
                "⏱️ Генерация может занять обычно 20 секунд, пожалуйста, подождите."
            )
            
            # Добавляем задачу в очередь
            task_id = await enqueue_image_generation(
                user_id=callback.from_user.id,
                prompt=image_prompt,
                dialog_id=dialog_id,
                girl_id=girl.id,
            )
            
            # Ожидаем результат
            bot = callback.message.bot
            task_result = await wait_for_task_result(bot, callback.message, task_id)
            
            # Удаляем сообщение о генерации
            try:
                await status_message.delete()
            except Exception:
                pass
            
            if task_result:
                await send_image_from_task_result(bot, callback.message, task_result, girl.name)
                
                # Показываем обновленный баланс
                async with get_session() as session:
                    new_diamonds = await get_user_diamonds(session, user_id=callback.from_user.id)
                    await callback.message.answer(f"💎 Алмазов осталось: {new_diamonds}")
                
                # Обновляем общий счётчик фото для пользователя
                async with get_session() as session:
                    await increment_user_photos_used(session, user_id=callback.from_user.id)
                    new_photos_used = await get_user_photos_used(session, user_id=callback.from_user.id)
                    
                    # Отслеживаем генерацию фото
                    from app.repositories.retention import (
                        increment_user_photos,
                        track_user_activity,
                        update_user_retention,
                    )
                    await update_user_retention(session, user_id=callback.from_user.id)
                    await increment_user_photos(session, user_id=callback.from_user.id)
                    await track_user_activity(session, user_id=callback.from_user.id, photos_generated=1)
                    
                    await session.commit()
            else:
                # Возвращаем алмазы, если генерация не удалась
                async with get_session() as session:
                    await add_diamonds(session, user_id=callback.from_user.id, amount=settings.image_generation_cost)
                    await session.commit()
                await callback.message.answer("❌ Не получилось сгенерировать изображение. Алмазы возвращены.")
        except ValueError as exc:
            error_msg = str(exc)
            logging.getLogger(__name__).warning(f"Не удалось сгенерировать изображение: {error_msg}")
            await callback.message.answer(f"❌ Ошибка генерации изображения: {error_msg}")
        except Exception as exc:
            logging.getLogger(__name__).exception("Ошибка при генерации изображения", exc_info=exc)
            await callback.message.answer("❌ Ошибка при генерации изображения")
        finally:
            # Удаляем сообщение-предупреждение, если оно было отправлено
            if callback.from_user:
                warning_msg = _generating_images.pop(callback.from_user.id, None)
                if warning_msg:
                    try:
                        await warning_msg.delete()
                    except Exception:
                        pass


@router.callback_query(lambda c: c.data and c.data == "photo_limit_reached")
async def handle_photo_limit_reached(callback: CallbackQuery) -> None:
    """Обработчик для кнопки с исчерпанным лимитом фото."""
    await callback.answer(f"📷 Лимит фото исчерпан ({MAX_PHOTOS_PER_DIALOG}/{MAX_PHOTOS_PER_DIALOG})", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("continue_dialog:"))
async def handle_continue_chat_callback(callback: CallbackQuery) -> None:
    """Обработчик для продолжения конкретного диалога."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка: не могу определить пользователя.", show_alert=True)
        return
    
    # Отвечаем сразу для быстрого отклика
    await callback.answer()

    try:
        dialog_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка: неверный ID диалога.", show_alert=True)
        return

    async with get_session() as session:
        from app.repositories.dialogs import get_dialog_by_id
        
        dialog = await get_dialog_by_id(session, dialog_id)
        if not dialog:
            await callback.answer("💬 Диалог не найден.", show_alert=True)
            return
        
        # Проверяем, что диалог принадлежит пользователю
        if dialog.user_id != callback.from_user.id:
            await callback.answer("🔒 У тебя нет доступа к этому диалогу.", show_alert=True)
            return
        
        girl = await get_girl_by_id(session, dialog.girl_id)
        if not girl:
            await callback.answer("👤 Персонаж не найден.", show_alert=True)
            return

        # Переключаемся на этого персонажа и устанавливаем активный диалог
        # Важно: сначала устанавливаем активный диалог, потом персонажа, чтобы они были синхронизированы
        await set_selected_girl(session, user_id=callback.from_user.id, girl_id=girl.id, active_dialog_id=dialog_id)
        
        # Обновляем updated_at диалога, чтобы он считался активным
        from datetime import datetime, timezone
        dialog.updated_at = datetime.now(timezone.utc)
        await session.commit()

        # Получаем все сообщения для поиска последнего сообщения персонажа
        all_messages = await get_all_messages(session, dialog_id=dialog_id)
        
        # Ищем последнее сообщение от персонажа (assistant)
        last_assistant_msg = None
        if all_messages:
            for msg in reversed(all_messages):
                if msg.role == "assistant":
                    last_assistant_msg = msg
                    break

    # Первое сообщение - уведомление о продолжении чата
    await callback.message.edit_text(f"💬 Продолжаем чат с {girl.name}! ✨")
    
    # Второе сообщение - последнее сообщение персонажа с клавиатурой диалога
    if last_assistant_msg:
        # Если есть последнее сообщение от персонажа, показываем его с клавиатурой
        await callback.message.answer(
            last_assistant_msg.content,
            reply_markup=get_dialogue_keyboard()
        )
    else:
        # Если нет сообщений от персонажа, показываем приветствие
        await callback.message.answer(
            girl.greeting,
            reply_markup=get_dialogue_keyboard()
        )

