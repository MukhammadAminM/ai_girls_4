"""Репозиторий для работы с платежами."""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment


async def create_payment(
    session: AsyncSession,
    user_id: int,
    payment_type: str,
    amount_stars: int,
    diamonds_received: int = 0,
    energy_received: int = 0,
    pack_name: str | None = None,
    amount_usd: float | None = None,
    telegram_payment_charge_id: str | None = None,
    telegram_provider_payment_charge_id: str | None = None,
) -> Payment:
    """
    Создает запись о платеже.
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        payment_type: Тип платежа (diamonds, energy, pack, combo)
        amount_stars: Сумма в Telegram Stars
        diamonds_received: Получено алмазов
        energy_received: Получено энергии
        pack_name: Название пакета (если применимо)
        amount_usd: Сумма в USD
        telegram_payment_charge_id: ID платежа от Telegram
        telegram_provider_payment_charge_id: ID платежа от провайдера
    
    Returns:
        Созданная запись о платеже
    """
    payment = Payment(
        user_id=user_id,
        payment_type=payment_type,
        amount_stars=amount_stars,
        diamonds_received=diamonds_received,
        energy_received=energy_received,
        pack_name=pack_name,
        amount_usd=amount_usd,
        telegram_payment_charge_id=telegram_payment_charge_id,
        telegram_provider_payment_charge_id=telegram_provider_payment_charge_id,
    )
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    return payment


async def get_payments_stats(session: AsyncSession) -> dict[str, Any]:
    """
    Получает общую статистику по платежам.
    
    Returns:
        Словарь со статистикой
    """
    # Общее количество платежей
    total_payments_stmt = select(func.count(Payment.id))
    total_payments_result = await session.execute(total_payments_stmt)
    total_payments = total_payments_result.scalar() or 0
    
    # Общая сумма в Stars
    total_stars_stmt = select(func.sum(Payment.amount_stars))
    total_stars_result = await session.execute(total_stars_stmt)
    total_stars = total_stars_result.scalar() or 0
    
    # Общая сумма в USD (если есть данные)
    total_usd_stmt = select(func.sum(Payment.amount_usd))
    total_usd_result = await session.execute(total_usd_stmt)
    total_usd = total_usd_result.scalar() or 0.0
    
    # Количество уникальных донатеров
    unique_donors_stmt = select(func.count(func.distinct(Payment.user_id)))
    unique_donors_result = await session.execute(unique_donors_stmt)
    unique_donors = unique_donors_result.scalar() or 0
    
    # Статистика по типам платежей
    payments_by_type_stmt = (
        select(Payment.payment_type, func.count(Payment.id), func.sum(Payment.amount_stars))
        .group_by(Payment.payment_type)
    )
    payments_by_type_result = await session.execute(payments_by_type_stmt)
    payments_by_type = {
        row[0]: {"count": row[1], "total_stars": row[2] or 0}
        for row in payments_by_type_result.all()
    }
    
    # Статистика за последние 24 часа
    yesterday = datetime.now() - timedelta(days=1)
    recent_payments_stmt = select(func.count(Payment.id)).where(Payment.created_at >= yesterday)
    recent_payments_result = await session.execute(recent_payments_stmt)
    recent_payments = recent_payments_result.scalar() or 0
    
    recent_stars_stmt = select(func.sum(Payment.amount_stars)).where(Payment.created_at >= yesterday)
    recent_stars_result = await session.execute(recent_stars_stmt)
    recent_stars = recent_stars_result.scalar() or 0
    
    # Статистика за последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    week_payments_stmt = select(func.count(Payment.id)).where(Payment.created_at >= week_ago)
    week_payments_result = await session.execute(week_payments_stmt)
    week_payments = week_payments_result.scalar() or 0
    
    week_stars_stmt = select(func.sum(Payment.amount_stars)).where(Payment.created_at >= week_ago)
    week_stars_result = await session.execute(week_stars_stmt)
    week_stars = week_stars_result.scalar() or 0
    
    return {
        "total_payments": total_payments,
        "total_stars": total_stars,
        "total_usd": total_usd,
        "unique_donors": unique_donors,
        "payments_by_type": payments_by_type,
        "recent_24h": {
            "payments": recent_payments,
            "stars": recent_stars,
        },
        "recent_7d": {
            "payments": week_payments,
            "stars": week_stars,
        },
    }


async def get_user_payments(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[Payment]:
    """
    Получает последние платежи пользователя.
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        limit: Максимальное количество записей
    
    Returns:
        Список платежей пользователя
    """
    stmt = (
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_top_donors(session: AsyncSession, limit: int = 10) -> list[tuple[int, int, int]]:
    """
    Получает топ донатеров по общей сумме платежей.
    
    Args:
        session: Сессия БД
        limit: Максимальное количество записей
    
    Returns:
        Список кортежей (user_id, total_stars, total_payments)
    """
    stmt = (
        select(
            Payment.user_id,
            func.sum(Payment.amount_stars).label("total_stars"),
            func.count(Payment.id).label("total_payments"),
        )
        .group_by(Payment.user_id)
        .order_by(func.sum(Payment.amount_stars).desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1] or 0, row[2]) for row in result.all()]

