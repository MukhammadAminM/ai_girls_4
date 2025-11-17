"""Админ-панель для анализа данных и retention."""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.db import get_session
from app.repositories.retention import get_daily_activity, get_retention_stats
from app.repositories.payments import get_payments_stats, get_top_donors

logger = logging.getLogger(__name__)

admin_router = Router()


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    if not settings.admin_user_ids or not settings.admin_user_ids.strip():
        logger.warning("Admin user IDs not configured")
        return False
    try:
        admin_ids = [int(uid.strip()) for uid in settings.admin_user_ids.split(",") if uid.strip()]
        return user_id in admin_ids
    except ValueError as e:
        logger.error(f"Error parsing admin_user_ids: {e}")
        return False


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру админ-панели."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin:stats"),
                InlineKeyboardButton(text="📈 Retention", callback_data="admin:retention"),
            ],
            [
                InlineKeyboardButton(text="📅 Ежедневная активность", callback_data="admin:daily"),
                InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users"),
            ],
            [
                InlineKeyboardButton(text="💰 Донаты", callback_data="admin:payments"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:refresh"),
            ],
        ]
    )
    return keyboard


@admin_router.message(Command("admin"))
async def handle_admin_command(message: Message) -> None:
    """Обработчик команды /admin."""
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    
    # Логируем попытку доступа
    logger.info(f"User {user_id} attempted to access admin panel")
    
    if not is_admin(user_id):
        logger.warning(f"User {user_id} is not in admin list. Current admins: {settings.admin_user_ids}")
        await message.answer(
            "❌ У вас нет доступа к админ-панели.\n\n"
            f"Ваш ID: {user_id}\n"
            "Обратитесь к администратору для получения доступа."
        )
        return
    
    logger.info(f"User {user_id} accessed admin panel successfully")
    await message.answer(
        "🔐 Админ-панель\n\n"
        "Выберите раздел для просмотра статистики:",
        reply_markup=get_admin_keyboard()
    )


@admin_router.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def handle_admin_callback(callback) -> None:
    """Обработчик callback для админ-панели."""
    if not callback.from_user:
        await callback.answer("⚠️ Ошибка")
        return
    
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    action = callback.data.split(":")[1]
    
    if action == "stats":
        await show_general_stats(callback)
    elif action == "retention":
        await show_retention_stats(callback)
    elif action == "daily":
        await show_daily_activity(callback)
    elif action == "users":
        await show_users_stats(callback)
    elif action == "payments":
        await show_payments_stats(callback)
    elif action == "refresh":
        await callback.message.edit_text(
            "🔐 Админ-панель\n\n"
            "Выберите раздел для просмотра статистики:",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer("✅ Обновлено")
    
    await callback.answer()


async def show_general_stats(callback) -> None:
    """Показывает общую статистику."""
    async with get_session() as session:
        stats = await get_retention_stats(session, days=30)
    
    text = (
        "📊 Общая статистика (за 30 дней)\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"🆕 Новых пользователей: {stats['new_users']}\n"
        f"✅ Активных пользователей: {stats['active_users']}\n\n"
        f"💬 Среднее сообщений на пользователя: {stats['avg_messages']}\n"
        f"📷 Среднее фото на пользователя: {stats['avg_photos']}\n"
        f"📅 Среднее дней активности: {stats['avg_days_active']}\n"
    )
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard())


async def show_retention_stats(callback) -> None:
    """Показывает статистику retention."""
    async with get_session() as session:
        stats = await get_retention_stats(session, days=30)
    
    text = (
        "📈 Retention метрики\n\n"
        f"D1 Retention: {stats['d1_retention']}%\n"
        f"D4 Retention: {stats['d4_retention']}%\n"
        f"D7 Retention: {stats['d7_retention']}%\n"
        f"D30 Retention: {stats['d30_retention']}%\n\n"
        f"📊 Общая статистика:\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"🆕 Новых за 30 дней: {stats['new_users']}\n"
        f"✅ Активных за 30 дней: {stats['active_users']}\n"
    )
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard())


async def show_daily_activity(callback) -> None:
    """Показывает ежедневную активность."""
    async with get_session() as session:
        daily = await get_daily_activity(session, days=7)
    
    if not daily:
        text = "📅 Ежедневная активность\n\nНет данных за последние 7 дней."
    else:
        text = "📅 Ежедневная активность (последние 7 дней)\n\n"
        for day in daily[:7]:  # Показываем последние 7 дней
            date_str = day["date"].strftime("%d.%m.%Y") if isinstance(day["date"], datetime) else str(day["date"])
            text += (
                f"📆 {date_str}\n"
                f"  👥 Пользователей: {day['unique_users']}\n"
                f"  💬 Сообщений: {day['total_messages']}\n"
                f"  📷 Фото: {day['total_photos']}\n"
                f"  💬 Диалогов: {day['total_dialogs']}\n\n"
            )
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard())


async def show_users_stats(callback) -> None:
    """Показывает статистику по пользователям."""
    async with get_session() as session:
        stats = await get_retention_stats(session, days=30)
    
    text = (
        "👥 Статистика пользователей\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"🆕 Новых за 30 дней: {stats['new_users']}\n"
        f"✅ Активных за 30 дней: {stats['active_users']}\n\n"
        f"📊 Средние показатели:\n"
        f"💬 Сообщений: {stats['avg_messages']}\n"
        f"📷 Фото: {stats['avg_photos']}\n"
        f"📅 Дней активности: {stats['avg_days_active']}\n"
    )
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard())


async def show_payments_stats(callback) -> None:
    """Показывает статистику по донатам."""
    async with get_session() as session:
        stats = await get_payments_stats(session)
        top_donors = await get_top_donors(session, limit=10)
    
    # Формируем статистику по типам платежей
    payments_by_type_text = ""
    if stats['payments_by_type']:
        type_names = {
            "diamonds": "💎 Алмазы",
            "energy": "⚡ Энергия",
            "pack": "📦 Пакеты",
            "combo": "💎⚡ Комбо"
        }
        for ptype, data in stats['payments_by_type'].items():
            type_name = type_names.get(ptype, ptype)
            payments_by_type_text += f"  {type_name}: {data['count']} платежей ({data['total_stars']} ⭐)\n"
    else:
        payments_by_type_text = "  Нет данных\n"
    
    # Формируем топ донатеров
    top_donors_text = ""
    if top_donors:
        for idx, (user_id, total_stars, total_payments) in enumerate(top_donors, 1):
            top_donors_text += f"{idx}. ID {user_id}: {total_stars} ⭐ ({total_payments} платежей)\n"
    else:
        top_donors_text = "Нет данных\n"
    
    text = (
        "💰 Статистика донатов\n\n"
        f"📊 Общая статистика:\n"
        f"  💰 Всего платежей: {stats['total_payments']}\n"
        f"  ⭐ Всего Stars: {stats['total_stars']:,}\n"
        f"  💵 Всего USD: ${stats['total_usd']:.2f}\n"
        f"  👥 Уникальных донатеров: {stats['unique_donors']}\n\n"
        f"📈 За последние 24 часа:\n"
        f"  💰 Платежей: {stats['recent_24h']['payments']}\n"
        f"  ⭐ Stars: {stats['recent_24h']['stars']:,}\n\n"
        f"📈 За последние 7 дней:\n"
        f"  💰 Платежей: {stats['recent_7d']['payments']}\n"
        f"  ⭐ Stars: {stats['recent_7d']['stars']:,}\n\n"
        f"📦 По типам платежей:\n"
        f"{payments_by_type_text}\n"
        f"🏆 Топ донатеров:\n"
        f"{top_donors_text}"
    )
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard())

