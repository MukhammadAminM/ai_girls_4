from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserActivity, UserRetention


async def track_user_activity(
    session: AsyncSession,
    user_id: int,
    messages_count: int = 0,
    photos_generated: int = 0,
    dialogs_created: int = 0,
) -> None:
    """Отслеживает активность пользователя за день."""
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Получаем или создаем запись активности за сегодня
    stmt = select(UserActivity).where(
        UserActivity.user_id == user_id,
        UserActivity.activity_date >= today_start,
        UserActivity.activity_date <= today_end
    )
    result = await session.execute(stmt)
    activity = result.scalar_one_or_none()
    
    if activity:
        activity.messages_count += messages_count
        activity.photos_generated += photos_generated
        activity.dialogs_created += dialogs_created
    else:
        activity = UserActivity(
            user_id=user_id,
            activity_date=datetime.now(timezone.utc),
            messages_count=messages_count,
            photos_generated=photos_generated,
            dialogs_created=dialogs_created,
        )
        session.add(activity)
    
    await session.flush()


async def update_user_retention(
    session: AsyncSession,
    user_id: int,
    is_new_user: bool = False,
) -> None:
    """Обновляет retention данные пользователя."""
    stmt = select(UserRetention).where(UserRetention.user_id == user_id)
    result = await session.execute(stmt)
    retention = result.scalar_one_or_none()
    
    now = datetime.now(timezone.utc)
    
    if retention:
        # Обновляем существующего пользователя
        retention.last_seen = now
        retention.total_sessions += 1
        
        # Проверяем, новый ли это день активности
        last_seen_date = retention.last_seen.date() if retention.last_seen else None
        today = now.date()
        
        if last_seen_date != today:
            retention.days_active += 1
    else:
        # Создаем нового пользователя
        retention = UserRetention(
            user_id=user_id,
            first_seen=now,
            last_seen=now,
            total_sessions=1,
            days_active=1,
        )
        session.add(retention)
    
    await session.flush()


async def increment_user_messages(session: AsyncSession, user_id: int, count: int = 1) -> None:
    """Увеличивает счетчик сообщений пользователя."""
    stmt = select(UserRetention).where(UserRetention.user_id == user_id)
    result = await session.execute(stmt)
    retention = result.scalar_one_or_none()
    
    if retention:
        retention.total_messages += count
        await session.flush()


async def increment_user_photos(session: AsyncSession, user_id: int, count: int = 1) -> None:
    """Увеличивает счетчик фото пользователя."""
    stmt = select(UserRetention).where(UserRetention.user_id == user_id)
    result = await session.execute(stmt)
    retention = result.scalar_one_or_none()
    
    if retention:
        retention.total_photos += count
        await session.flush()


async def get_retention_stats(
    session: AsyncSession,
    days: int = 30,
) -> dict[str, Any]:
    """Получает статистику retention за последние N дней."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Общая статистика пользователей
    total_users_stmt = select(func.count(UserRetention.user_id))
    total_users_result = await session.execute(total_users_stmt)
    total_users = total_users_result.scalar_one() or 0
    
    # Новые пользователи за период
    new_users_stmt = select(func.count(UserRetention.user_id)).where(
        UserRetention.first_seen >= cutoff_date
    )
    new_users_result = await session.execute(new_users_stmt)
    new_users = new_users_result.scalar_one() or 0
    
    # Активные пользователи за период
    active_users_stmt = select(func.count(func.distinct(UserRetention.user_id))).where(
        UserRetention.last_seen >= cutoff_date
    )
    active_users_result = await session.execute(active_users_stmt)
    active_users = active_users_result.scalar_one() or 0
    
    # Retention по дням (D1, D7, D30)
    today = datetime.now(timezone.utc).date()
    
    # D1 Retention (вернулись на следующий день)
    d1_date = today - timedelta(days=1)
    d1_users_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d1_date
    )
    d1_users_result = await session.execute(d1_users_stmt)
    d1_new = d1_users_result.scalar_one() or 0
    
    d1_returned_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d1_date,
        cast(UserRetention.last_seen, Date) >= today
    )
    d1_returned_result = await session.execute(d1_returned_stmt)
    d1_returned = d1_returned_result.scalar_one() or 0
    
    d1_retention = (d1_returned / d1_new * 100) if d1_new > 0 else 0
    
    # D4 Retention
    d4_date = today - timedelta(days=4)
    d4_users_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d4_date
    )
    d4_users_result = await session.execute(d4_users_stmt)
    d4_new = d4_users_result.scalar_one() or 0
    
    d4_returned_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d4_date,
        UserRetention.last_seen >= d4_date + timedelta(days=1)
    )
    d4_returned_result = await session.execute(d4_returned_stmt)
    d4_returned = d4_returned_result.scalar_one() or 0
    
    d4_retention = (d4_returned / d4_new * 100) if d4_new > 0 else 0
    
    # D7 Retention
    d7_date = today - timedelta(days=7)
    d7_users_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d7_date
    )
    d7_users_result = await session.execute(d7_users_stmt)
    d7_new = d7_users_result.scalar_one() or 0
    
    d7_returned_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d7_date,
        UserRetention.last_seen >= d7_date + timedelta(days=1)
    )
    d7_returned_result = await session.execute(d7_returned_stmt)
    d7_returned = d7_returned_result.scalar_one() or 0
    
    d7_retention = (d7_returned / d7_new * 100) if d7_new > 0 else 0
    
    # D30 Retention
    d30_date = today - timedelta(days=30)
    d30_users_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d30_date
    )
    d30_users_result = await session.execute(d30_users_stmt)
    d30_new = d30_users_result.scalar_one() or 0
    
    d30_returned_stmt = select(func.count(UserRetention.user_id)).where(
        cast(UserRetention.first_seen, Date) == d30_date,
        UserRetention.last_seen >= d30_date + timedelta(days=1)
    )
    d30_returned_result = await session.execute(d30_returned_stmt)
    d30_returned = d30_returned_result.scalar_one() or 0
    
    d30_retention = (d30_returned / d30_new * 100) if d30_new > 0 else 0
    
    # Средние метрики
    avg_messages_stmt = select(func.avg(UserRetention.total_messages))
    avg_messages_result = await session.execute(avg_messages_stmt)
    avg_messages = avg_messages_result.scalar_one() or 0
    
    avg_photos_stmt = select(func.avg(UserRetention.total_photos))
    avg_photos_result = await session.execute(avg_photos_stmt)
    avg_photos = avg_photos_result.scalar_one() or 0
    
    avg_days_active_stmt = select(func.avg(UserRetention.days_active))
    avg_days_active_result = await session.execute(avg_days_active_stmt)
    avg_days_active = avg_days_active_result.scalar_one() or 0
    
    return {
        "total_users": total_users,
        "new_users": new_users,
        "active_users": active_users,
        "d1_retention": round(d1_retention, 2),
        "d4_retention": round(d4_retention, 2),
        "d7_retention": round(d7_retention, 2),
        "d30_retention": round(d30_retention, 2),
        "avg_messages": round(float(avg_messages), 2),
        "avg_photos": round(float(avg_photos), 2),
        "avg_days_active": round(float(avg_days_active), 2),
    }


async def get_daily_activity(
    session: AsyncSession,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Получает ежедневную активность за последние N дней."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    stmt = (
        select(
            cast(UserActivity.activity_date, Date).label("date"),
            func.count(func.distinct(UserActivity.user_id)).label("unique_users"),
            func.sum(UserActivity.messages_count).label("total_messages"),
            func.sum(UserActivity.photos_generated).label("total_photos"),
            func.sum(UserActivity.dialogs_created).label("total_dialogs"),
        )
        .where(UserActivity.activity_date >= cutoff_date)
        .group_by(cast(UserActivity.activity_date, Date))
        .order_by(cast(UserActivity.activity_date, Date).desc())
    )
    
    result = await session.execute(stmt)
    rows = result.all()
    
    return [
        {
            "date": row.date,
            "unique_users": row.unique_users or 0,
            "total_messages": row.total_messages or 0,
            "total_photos": row.total_photos or 0,
            "total_dialogs": row.total_dialogs or 0,
        }
        for row in rows
    ]

