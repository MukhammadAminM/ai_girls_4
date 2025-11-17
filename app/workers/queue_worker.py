import asyncio
import base64
import logging
from typing import Any

from app.config import settings
from app.db import get_session
from app.repositories.dialogs import get_dialog_by_id
from app.repositories.girls import get_girl_by_id
from app.repositories.messages import add_message, get_recent_messages
from app.repositories.user_selected_girl import get_user_photos_used, increment_user_photos_used
from app.config import settings
from app.services.image_client import ImageClient
from app.services.replicate_client import ReplicateImageClient
from app.services.queue_service import QueueService, TaskStatus, TaskType
from app.services.venice_client import VeniceClient

logger = logging.getLogger(__name__)


class QueueWorker:
    """Воркер для обработки задач из очереди Redis."""
    
    def __init__(self) -> None:
        self.queue_service = QueueService()
        self.running = False
    
    async def start(self) -> None:
        """Запускает воркер."""
        await self.queue_service.connect()
        self.running = True
        logger.info("Queue worker started")
        
        # Запускаем обработчики для каждого типа задач
        tasks = [
            self._process_generate_image_tasks(),
            self._process_generate_reply_tasks(),
            self._process_generate_image_prompt_tasks(),
        ]
        
        await asyncio.gather(*tasks)
    
    async def stop(self) -> None:
        """Останавливает воркер."""
        self.running = False
        await self.queue_service.disconnect()
        logger.info("Queue worker stopped")
    
    async def _process_generate_image_tasks(self) -> None:
        """Обрабатывает задачи генерации изображений."""
        while self.running:
            try:
                task = await self.queue_service.dequeue_task(
                    TaskType.GENERATE_IMAGE,
                    timeout=1
                )
                
                if task is None:
                    await asyncio.sleep(0.1)
                    continue
                
                logger.info(f"Processing image generation task: {task.task_id}")
                
                try:
                    # Извлекаем данные задачи
                    prompt = task.data.get("prompt")
                    user_id = task.user_id
                    dialog_id = task.data.get("dialog_id")
                    girl_id = task.data.get("girl_id")
                    
                    if not prompt:
                        raise ValueError("Prompt is required")
                    
                    # Генерируем изображение (используем Replicate или локальный API)
                    if settings.use_replicate:
                        logger.info("Используется Replicate для генерации изображения")
                        image_client = ReplicateImageClient()
                    else:
                        logger.info("Используется локальный API для генерации изображения")
                        image_client = ImageClient()
                    
                    try:
                        image_data = await image_client.generate_image(prompt)
                        image_base64 = base64.b64encode(image_data).decode("utf-8")
                        
                        # Обновляем счётчик фото, если указан dialog_id
                        if dialog_id:
                            async with get_session() as session:
                                await increment_user_photos_used(session, user_id=user_id)
                                await session.commit()
                        
                        # Сохраняем результат
                        await self.queue_service.update_task_status(
                            task.task_id,
                            TaskStatus.COMPLETED,
                            result={
                                "image_base64": image_base64,
                                "image_size": len(image_data),
                                "dialog_id": dialog_id,
                                "girl_id": girl_id,
                            }
                        )
                        
                        logger.info(f"Image generation completed: {task.task_id}")
                    finally:
                        await image_client.close()
                
                except Exception as exc:
                    logger.exception(f"Error processing image generation task {task.task_id}: {exc}")
                    await self.queue_service.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error=str(exc)
                    )
            
            except Exception as exc:
                logger.exception(f"Error in image generation worker: {exc}")
                await asyncio.sleep(1)
    
    async def _process_generate_reply_tasks(self) -> None:
        """Обрабатывает задачи генерации ответов AI."""
        while self.running:
            try:
                task = await self.queue_service.dequeue_task(
                    TaskType.GENERATE_REPLY,
                    timeout=1
                )
                
                if task is None:
                    await asyncio.sleep(0.1)
                    continue
                
                logger.info(f"Processing reply generation task: {task.task_id}")
                
                try:
                    # Извлекаем данные задачи
                    system_prompt = task.data.get("system_prompt")
                    history = task.data.get("history", [])
                    dialog_id = task.data.get("dialog_id")
                    user_message = task.data.get("user_message")
                    
                    if not system_prompt:
                        raise ValueError("System prompt is required")
                    
                    # Генерируем ответ
                    venice_client = VeniceClient()
                    try:
                        reply_text = await venice_client.generate_reply(system_prompt, history)
                        
                        # Сохраняем сообщение в БД
                        if dialog_id and user_message:
                            async with get_session() as session:
                                # Добавляем сообщение пользователя, если его еще нет
                                # (может быть уже добавлено в handlers)
                                # Добавляем ответ ассистента
                                await add_message(
                                    session,
                                    dialog_id=dialog_id,
                                    role="assistant",
                                    content=reply_text,
                                )
                                await session.commit()
                        
                        # Сохраняем результат
                        await self.queue_service.update_task_status(
                            task.task_id,
                            TaskStatus.COMPLETED,
                            result={
                                "reply": reply_text,
                                "dialog_id": dialog_id,
                            }
                        )
                        
                        logger.info(f"Reply generation completed: {task.task_id}")
                    finally:
                        await venice_client.close()
                
                except Exception as exc:
                    logger.exception(f"Error processing reply generation task {task.task_id}: {exc}")
                    await self.queue_service.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error=str(exc)
                    )
            
            except Exception as exc:
                logger.exception(f"Error in reply generation worker: {exc}")
                await asyncio.sleep(1)
    
    async def _process_generate_image_prompt_tasks(self) -> None:
        """Обрабатывает задачи генерации промптов для изображений."""
        while self.running:
            try:
                task = await self.queue_service.dequeue_task(
                    TaskType.GENERATE_IMAGE_PROMPT,
                    timeout=1
                )
                
                if task is None:
                    await asyncio.sleep(0.1)
                    continue
                
                logger.info(f"Processing image prompt generation task: {task.task_id}")
                
                try:
                    # Извлекаем данные задачи
                    girl_name = task.data.get("girl_name")
                    girl_description = task.data.get("girl_description")
                    recent_dialogue = task.data.get("recent_dialogue", [])
                    
                    if not girl_name:
                        raise ValueError("Girl name is required")
                    
                    # Генерируем промпт
                    venice_client = VeniceClient()
                    try:
                        prompt = await venice_client.generate_image_prompt(
                            girl_name=girl_name,
                            girl_description=girl_description or "",
                            recent_dialogue=recent_dialogue,
                        )
                        
                        # Сохраняем результат
                        await self.queue_service.update_task_status(
                            task.task_id,
                            TaskStatus.COMPLETED,
                            result={
                                "prompt": prompt,
                            }
                        )
                        
                        logger.info(f"Image prompt generation completed: {task.task_id}")
                    finally:
                        await venice_client.close()
                
                except Exception as exc:
                    logger.exception(f"Error processing image prompt generation task {task.task_id}: {exc}")
                    await self.queue_service.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error=str(exc)
                    )
            
            except Exception as exc:
                logger.exception(f"Error in image prompt generation worker: {exc}")
                await asyncio.sleep(1)


async def main() -> None:
    """Главная функция для запуска воркера."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    worker = QueueWorker()
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())

