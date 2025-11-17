import asyncio
import base64
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import BufferedInputFile, Message

from app.services.queue_service import TaskStatus, TaskType, queue_service

logger = logging.getLogger(__name__)


async def wait_for_task_result(
    bot: Bot,
    message: Message,
    task_id: str,
    check_interval: float = 0.2,  # Уменьшено с 1.0 до 0.2 для более быстрой проверки
    timeout: float = 120.0,
) -> dict[str, Any] | None:
    """
    Ожидает результат выполнения задачи из очереди.
    
    Args:
        bot: Экземпляр бота
        message: Сообщение для отправки обновлений
        task_id: ID задачи
        check_interval: Интервал проверки статуса (секунды)
        timeout: Таймаут ожидания (секунды)
    
    Returns:
        Результат задачи или None при таймауте/ошибке
    """
    start_time = asyncio.get_event_loop().time()
    
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            logger.warning(f"Task {task_id} timeout after {timeout}s")
            return None
        
        task = await queue_service.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return None
        
        if task.status == TaskStatus.COMPLETED:
            return task.result
        
        if task.status == TaskStatus.FAILED:
            logger.error(f"Task {task_id} failed: {task.error}")
            return None
        
        # Задача еще обрабатывается
        await asyncio.sleep(check_interval)


async def send_image_from_task_result(
    bot: Bot,
    message: Message,
    task_result: dict[str, Any],
    girl_name: str,
) -> None:
    """
    Отправляет изображение из результата задачи.
    
    Args:
        bot: Экземпляр бота
        message: Сообщение для отправки фото
        task_result: Результат задачи
        girl_name: Имя персонажа для имени файла
    """
    image_base64 = task_result.get("image_base64")
    if not image_base64:
        await message.answer("❌ Ошибка: изображение не найдено в результате.")
        return
    
    try:
        image_data = base64.b64decode(image_base64)
        photo = BufferedInputFile(image_data, filename=f"{girl_name}.png")
        await message.answer_photo(photo)
    except Exception as exc:
        logger.exception(f"Error sending image from task result: {exc}")
        await message.answer("❌ Ошибка при отправке изображения.")


async def enqueue_image_generation(
    user_id: int,
    prompt: str,
    dialog_id: int | None = None,
    girl_id: int | None = None,
) -> str:
    """
    Добавляет задачу генерации изображения в очередь.
    
    Args:
        user_id: ID пользователя
        prompt: Промпт для генерации
        dialog_id: ID диалога (опционально)
        girl_id: ID персонажа (опционально)
    
    Returns:
        ID задачи
    """
    await queue_service.connect()
    
    task_id = await queue_service.enqueue_task(
        TaskType.GENERATE_IMAGE,
        user_id=user_id,
        data={
            "prompt": prompt,
            "dialog_id": dialog_id,
            "girl_id": girl_id,
        }
    )
    
    return task_id


async def enqueue_reply_generation(
    user_id: int,
    system_prompt: str,
    history: list[dict[str, str]],
    dialog_id: int,
    user_message: str,
) -> str:
    """
    Добавляет задачу генерации ответа в очередь.
    
    Args:
        user_id: ID пользователя
        system_prompt: Системный промпт
        history: История сообщений
        dialog_id: ID диалога
        user_message: Сообщение пользователя
    
    Returns:
        ID задачи
    """
    await queue_service.connect()
    
    task_id = await queue_service.enqueue_task(
        TaskType.GENERATE_REPLY,
        user_id=user_id,
        data={
            "system_prompt": system_prompt,
            "history": history,
            "dialog_id": dialog_id,
            "user_message": user_message,
        }
    )
    
    return task_id


async def enqueue_image_prompt_generation(
    user_id: int,
    girl_name: str,
    girl_description: str,
    recent_dialogue: list[dict[str, str]],
) -> str:
    """
    Добавляет задачу генерации промпта для изображения в очередь.
    
    Args:
        user_id: ID пользователя
        girl_name: Имя персонажа
        girl_description: Описание персонажа
        recent_dialogue: Последние сообщения диалога
    
    Returns:
        ID задачи
    """
    await queue_service.connect()
    
    task_id = await queue_service.enqueue_task(
        TaskType.GENERATE_IMAGE_PROMPT,
        user_id=user_id,
        data={
            "girl_name": girl_name,
            "girl_description": girl_description,
            "recent_dialogue": recent_dialogue,
        }
    )
    
    return task_id

