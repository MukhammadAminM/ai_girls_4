from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dialog, Girl


async def create_dialog(
    session: AsyncSession,
    *,
    user_id: int,
    girl_id: int,
    title: str | None = None,
) -> Dialog:
    """Создаёт новый диалог с персонажем."""
    dialog = Dialog(
        user_id=user_id,
        girl_id=girl_id,
        title=title,
    )
    session.add(dialog)
    await session.flush()
    await session.refresh(dialog)
    return dialog


async def get_dialog_by_id(
    session: AsyncSession,
    dialog_id: int,
) -> Dialog | None:
    """Возвращает диалог по ID."""
    stmt = select(Dialog).where(Dialog.id == dialog_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_dialogs_with_girl(
    session: AsyncSession,
    *,
    user_id: int,
    girl_id: int,
) -> Sequence[Dialog]:
    """Возвращает все диалоги пользователя с конкретным персонажем."""
    stmt = (
        select(Dialog)
        .where(Dialog.user_id == user_id, Dialog.girl_id == girl_id)
        .order_by(Dialog.updated_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_all_user_dialogs(
    session: AsyncSession,
    *,
    user_id: int,
) -> Sequence[Dialog]:
    """Возвращает все диалоги пользователя со всеми персонажами."""
    stmt = (
        select(Dialog)
        .where(Dialog.user_id == user_id)
        .order_by(Dialog.updated_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_dialogs_by_girls(
    session: AsyncSession,
    *,
    user_id: int,
) -> Sequence[tuple[Girl, Sequence[Dialog]]]:
    """Возвращает диалоги, сгруппированные по персонажам."""
    stmt = (
        select(Dialog, Girl)
        .join(Girl, Dialog.girl_id == Girl.id)
        .where(Dialog.user_id == user_id)
        .order_by(Dialog.updated_at.desc())
    )
    result = await session.execute(stmt)
    
    # Группируем по персонажам
    dialogs_by_girl: dict[int, list[Dialog]] = {}
    girls_dict: dict[int, Girl] = {}
    
    for dialog, girl in result.all():
        if girl.id not in dialogs_by_girl:
            dialogs_by_girl[girl.id] = []
            girls_dict[girl.id] = girl
        dialogs_by_girl[girl.id].append(dialog)
    
    return [(girls_dict[girl_id], dialogs) for girl_id, dialogs in dialogs_by_girl.items()]


async def get_active_dialog(
    session: AsyncSession,
    *,
    user_id: int,
    girl_id: int,
) -> Dialog | None:
    """Возвращает активный (последний обновлённый) диалог с персонажем."""
    stmt = (
        select(Dialog)
        .where(Dialog.user_id == user_id, Dialog.girl_id == girl_id)
        .order_by(Dialog.updated_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_dialog_title(
    session: AsyncSession,
    *,
    dialog_id: int,
    title: str,
) -> None:
    """Обновляет заголовок диалога."""
    dialog = await get_dialog_by_id(session, dialog_id)
    if dialog:
        dialog.title = title
        await session.flush()


async def set_dialog_nsfw_enabled(
    session: AsyncSession,
    *,
    dialog_id: int,
    enabled: bool,
) -> None:
    """Устанавливает флаг 18+ для диалога."""
    dialog = await get_dialog_by_id(session, dialog_id)
    if dialog:
        dialog.nsfw_enabled = enabled
        await session.flush()


async def get_dialog_nsfw_enabled(
    session: AsyncSession,
    *,
    dialog_id: int,
) -> bool:
    """Возвращает состояние флага 18+ для диалога."""
    dialog = await get_dialog_by_id(session, dialog_id)
    return dialog.nsfw_enabled if dialog else False


async def delete_dialog(
    session: AsyncSession,
    *,
    dialog_id: int,
) -> None:
    """Удаляет диалог и все связанные сообщения."""
    from sqlalchemy import delete
    from app.models import ChatMessage
    
    # Удаляем все сообщения диалога
    await session.execute(
        delete(ChatMessage).where(ChatMessage.dialog_id == dialog_id)
    )
    
    # Удаляем сам диалог
    await session.execute(
        delete(Dialog).where(Dialog.id == dialog_id)
    )
    
    await session.flush()

