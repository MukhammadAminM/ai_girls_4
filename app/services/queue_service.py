import json
import uuid
from enum import Enum
from typing import Any

import redis.asyncio as redis
from pydantic import BaseModel

from app.config import settings


class TaskType(str, Enum):
    """Типы задач в очереди."""
    GENERATE_IMAGE = "generate_image"
    GENERATE_REPLY = "generate_reply"
    GENERATE_IMAGE_PROMPT = "generate_image_prompt"


class TaskStatus(str, Enum):
    """Статусы задач."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueTask(BaseModel):
    """Модель задачи в очереди."""
    task_id: str
    task_type: TaskType
    user_id: int
    data: dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    created_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class QueueService:
    """Сервис для работы с очередями Redis."""
    
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._queue_prefix = settings.redis_queue_prefix
        self._result_prefix = settings.redis_result_prefix
        self._result_ttl = settings.redis_result_ttl
    
    async def connect(self) -> None:
        """Подключается к Redis."""
        if self._redis is None:
            self._redis = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
    
    async def disconnect(self) -> None:
        """Отключается от Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None
    
    async def enqueue_task(
        self,
        task_type: TaskType,
        user_id: int,
        data: dict[str, Any],
    ) -> str:
        """
        Добавляет задачу в очередь.
        
        Args:
            task_type: Тип задачи
            user_id: ID пользователя
            data: Данные задачи
        
        Returns:
            ID задачи
        """
        if self._redis is None:
            await self.connect()
        
        task_id = str(uuid.uuid4())
        import time
        task = QueueTask(
            task_id=task_id,
            task_type=task_type,
            user_id=user_id,
            data=data,
            status=TaskStatus.PENDING,
            created_at=time.time(),
        )
        
        # Добавляем задачу в очередь
        queue_name = f"{self._queue_prefix}{task_type.value}"
        task_json = task.model_dump_json()
        await self._redis.lpush(queue_name, task_json)
        
        # Сохраняем задачу для отслеживания статуса
        result_key = f"{self._result_prefix}{task_id}"
        await self._redis.setex(
            result_key,
            self._result_ttl,
            task_json
        )
        
        return task_id
    
    async def get_task(self, task_id: str) -> QueueTask | None:
        """
        Получает задачу по ID.
        
        Args:
            task_id: ID задачи
        
        Returns:
            Задача или None
        """
        if self._redis is None:
            await self.connect()
        
        result_key = f"{self._result_prefix}{task_id}"
        task_json = await self._redis.get(result_key)
        
        if not task_json:
            return None
        
        try:
            task_dict = json.loads(task_json)
            return QueueTask(**task_dict)
        except Exception:
            return None
    
    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """
        Обновляет статус задачи.
        
        Args:
            task_id: ID задачи
            status: Новый статус
            result: Результат выполнения (если есть)
            error: Ошибка (если есть)
        """
        if self._redis is None:
            await self.connect()
        
        task = await self.get_task(task_id)
        if not task:
            return
        
        task.status = status
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        
        result_key = f"{self._result_prefix}{task_id}"
        task_json = task.model_dump_json()
        await self._redis.setex(
            result_key,
            self._result_ttl,
            task_json
        )
    
    async def dequeue_task(self, task_type: TaskType, timeout: int = 0) -> QueueTask | None:
        """
        Извлекает задачу из очереди (блокирующий вызов).
        
        Args:
            task_type: Тип задачи
            timeout: Таймаут в секундах (0 = бесконечно)
        
        Returns:
            Задача или None
        """
        if self._redis is None:
            await self.connect()
        
        queue_name = f"{self._queue_prefix}{task_type.value}"
        
        # Используем блокирующий pop
        if timeout > 0:
            result = await self._redis.brpop(queue_name, timeout=timeout)
            if result is None:
                return None
            _, task_json = result
        else:
            task_json = await self._redis.rpop(queue_name)
            if task_json is None:
                return None
        
        try:
            task_dict = json.loads(task_json)
            task = QueueTask(**task_dict)
            task.status = TaskStatus.PROCESSING
            await self.update_task_status(task.task_id, TaskStatus.PROCESSING)
            return task
        except Exception:
            return None
    
    async def get_queue_length(self, task_type: TaskType) -> int:
        """
        Возвращает длину очереди.
        
        Args:
            task_type: Тип задачи
        
        Returns:
            Количество задач в очереди
        """
        if self._redis is None:
            await self.connect()
        
        queue_name = f"{self._queue_prefix}{task_type.value}"
        return await self._redis.llen(queue_name)
    
    async def clear_queue(self, task_type: TaskType) -> None:
        """
        Очищает очередь.
        
        Args:
            task_type: Тип задачи
        """
        if self._redis is None:
            await self.connect()
        
        queue_name = f"{self._queue_prefix}{task_type.value}"
        await self._redis.delete(queue_name)


# Глобальный экземпляр сервиса
queue_service = QueueService()

