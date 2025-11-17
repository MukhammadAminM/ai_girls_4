from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, Dialog, Girl


async def add_message(
    session: AsyncSession,
    *,
    dialog_id: int,
    role: str,
    content: str,
) -> ChatMessage:
    """Добавляет сообщение в диалог."""
    message = ChatMessage(
        dialog_id=dialog_id,
        role=role,
        content=content,
    )
    session.add(message)
    await session.flush()
    
    # Обновляем время последнего обновления диалога
    dialog = await session.get(Dialog, dialog_id)
    if dialog:
        from datetime import datetime, timezone
        dialog.updated_at = datetime.now(timezone.utc)
        await session.flush()
    
    return message


async def get_recent_messages(
    session: AsyncSession,
    *,
    dialog_id: int,
    limit: int = 20,
) -> Sequence[ChatMessage]:
    """Возвращает последние сообщения из диалога."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.dialog_id == dialog_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    # Возвращаем в обратном порядке для правильной последовательности
    messages = list(result.scalars().all())
    return list(reversed(messages))


async def get_all_messages(
    session: AsyncSession,
    *,
    dialog_id: int,
) -> Sequence[ChatMessage]:
    """Возвращает все сообщения из диалога."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.dialog_id == dialog_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def clear_dialog(session: AsyncSession, *, dialog_id: int) -> None:
    """Очищает все сообщения из диалога."""
    stmt = delete(ChatMessage).where(ChatMessage.dialog_id == dialog_id)
    await session.execute(stmt)
    await session.flush()


async def get_message_count(
    session: AsyncSession,
    *,
    dialog_id: int,
) -> int:
    """Возвращает количество сообщений в диалоге."""
    stmt = (
        select(func.count(ChatMessage.id))
        .where(ChatMessage.dialog_id == dialog_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def get_girls_with_history(
    session: AsyncSession,
    *,
    user_id: int,
) -> Sequence[Girl]:
    """Возвращает список персонажей, с которыми у пользователя есть диалоги."""
    stmt = (
        select(Girl)
        .join(Dialog, Girl.id == Dialog.girl_id)
        .where(Dialog.user_id == user_id)
        .distinct()
        .order_by(Girl.name.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()

