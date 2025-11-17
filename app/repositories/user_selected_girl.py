from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dialog, Girl, UserSelectedGirl


async def get_selected_girl(session: AsyncSession, user_id: int) -> Girl | None:
    """Возвращает выбранного персонажа для пользователя."""
    stmt = (
        select(Girl)
        .join(UserSelectedGirl, Girl.id == UserSelectedGirl.girl_id)
        .where(UserSelectedGirl.user_id == user_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_dialog_id(session: AsyncSession, user_id: int) -> int | None:
    """Возвращает ID активного диалога пользователя."""
    stmt = select(UserSelectedGirl).where(UserSelectedGirl.user_id == user_id)
    result = await session.execute(stmt)
    selected = result.scalar_one_or_none()
    return selected.active_dialog_id if selected else None


async def set_selected_girl(
    session: AsyncSession,
    user_id: int,
    girl_id: int,
    active_dialog_id: int | None = None,
) -> None:
    """Устанавливает выбранного персонажа для пользователя."""
    stmt = select(UserSelectedGirl).where(UserSelectedGirl.user_id == user_id)
    result = await session.execute(stmt)
    selected = result.scalar_one_or_none()

    if selected:
        selected.girl_id = girl_id
        if active_dialog_id is not None:
            selected.active_dialog_id = active_dialog_id
    else:
        selected = UserSelectedGirl(
            user_id=user_id,
            girl_id=girl_id,
            active_dialog_id=active_dialog_id,
        )
        session.add(selected)

    await session.commit()


async def set_active_dialog(
    session: AsyncSession,
    user_id: int,
    dialog_id: int | None,
) -> None:
    """Устанавливает активный диалог для пользователя."""
    stmt = select(UserSelectedGirl).where(UserSelectedGirl.user_id == user_id)
    result = await session.execute(stmt)
    selected = result.scalar_one_or_none()

    if selected:
        selected.active_dialog_id = dialog_id
        await session.commit()
    else:
        # Если нет записи, создаём с дефолтным персонажем
        from app.repositories.girls import get_default_girl
        girl = await get_default_girl(session)
        if girl:
            selected = UserSelectedGirl(
                user_id=user_id,
                girl_id=girl.id,
                active_dialog_id=dialog_id,
            )
            session.add(selected)
            await session.commit()


async def get_user_photos_used(session: AsyncSession, user_id: int) -> int:
    """Возвращает количество использованных фото пользователем (общий лимит для всех девушек)."""
    stmt = select(UserSelectedGirl).where(UserSelectedGirl.user_id == user_id)
    result = await session.execute(stmt)
    selected = result.scalar_one_or_none()
    return selected.photos_used if selected else 0


async def increment_user_photos_used(session: AsyncSession, user_id: int) -> None:
    """Увеличивает счётчик использованных фото пользователя."""
    stmt = select(UserSelectedGirl).where(UserSelectedGirl.user_id == user_id)
    result = await session.execute(stmt)
    selected = result.scalar_one_or_none()

    if selected:
        selected.photos_used = (selected.photos_used or 0) + 1
        await session.flush()
    else:
        # Если нет записи, создаём с дефолтным персонажем
        from app.repositories.girls import get_default_girl
        girl = await get_default_girl(session)
        if girl:
            selected = UserSelectedGirl(
                user_id=user_id,
                girl_id=girl.id,
                photos_used=1,
            )
            session.add(selected)
            await session.flush()

