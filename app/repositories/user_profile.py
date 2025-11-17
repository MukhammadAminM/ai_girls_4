"""Репозиторий для работы с профилями пользователей."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserProfile


async def get_user_profile(session: AsyncSession, user_id: int) -> UserProfile:
    """
    Получает или создает профиль пользователя.
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
    
    Returns:
        Профиль пользователя
    """
    stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()
    
    if not profile:
        # Создаем новый профиль с начальными значениями
        profile = UserProfile(
            user_id=user_id,
            diamonds=5,  # Начальное количество алмазов
            energy=25,  # Начальная энергия
            max_energy=25,  # Максимальная энергия
        )
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
    
    return profile


async def get_user_diamonds(session: AsyncSession, user_id: int) -> int:
    """Возвращает количество алмазов у пользователя."""
    profile = await get_user_profile(session, user_id)
    return profile.diamonds


async def get_user_energy(session: AsyncSession, user_id: int) -> int:
    """Возвращает текущую энергию пользователя."""
    profile = await get_user_profile(session, user_id)
    return profile.energy


async def spend_diamonds(
    session: AsyncSession,
    user_id: int,
    amount: int,
) -> bool:
    """
    Тратит алмазы у пользователя.
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        amount: Количество алмазов для траты
    
    Returns:
        True если алмазов достаточно и они потрачены, False если недостаточно
    """
    profile = await get_user_profile(session, user_id)
    
    if profile.diamonds < amount:
        return False
    
    profile.diamonds -= amount
    await session.flush()
    return True


async def spend_energy(
    session: AsyncSession,
    user_id: int,
    amount: int,
) -> bool:
    """
    Тратит энергию у пользователя.
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        amount: Количество энергии для траты
    
    Returns:
        True если энергии достаточно и она потрачена, False если недостаточно
    """
    profile = await get_user_profile(session, user_id)
    
    if profile.energy < amount:
        return False
    
    profile.energy -= amount
    await session.flush()
    return True


async def add_diamonds(
    session: AsyncSession,
    user_id: int,
    amount: int,
) -> None:
    """
    Добавляет алмазы пользователю.
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        amount: Количество алмазов для добавления
    """
    profile = await get_user_profile(session, user_id)
    profile.diamonds += amount
    await session.flush()


async def add_energy(
    session: AsyncSession,
    user_id: int,
    amount: int,
) -> None:
    """
    Добавляет энергию пользователю (без ограничения максимумом).
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        amount: Количество энергии для добавления
    """
    profile = await get_user_profile(session, user_id)
    profile.energy += amount
    # Обновляем максимум, если текущая энергия больше
    if profile.energy > profile.max_energy:
        profile.max_energy = profile.energy
    await session.flush()


async def set_max_energy(
    session: AsyncSession,
    user_id: int,
    max_energy: int,
) -> None:
    """
    Устанавливает максимальную энергию пользователя.
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        max_energy: Новое значение максимальной энергии
    """
    profile = await get_user_profile(session, user_id)
    profile.max_energy = max_energy
    # Если текущая энергия больше нового максимума, уменьшаем её
    if profile.energy > max_energy:
        profile.energy = max_energy
    await session.flush()

