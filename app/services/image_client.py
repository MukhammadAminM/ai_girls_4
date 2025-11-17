import base64
import json
import logging
from io import BytesIO

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


class ImageClient:
    """Клиент для работы с локальным API генерации изображений."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.image_api_url,
            timeout=120.0,  # Генерация изображений может занимать больше времени
        )

    async def generate_image(
        self,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        negative_prompt: str | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        seed: int | None = None,
        lora_name: str | None = None,
        lora_strength_model: float | None = None,
        lora_strength_clip: float | None = None,
    ) -> bytes:
        """
        Генерирует изображение по промпту.

        Args:
            prompt: Текстовый промпт для генерации
            width: Ширина изображения (по умолчанию из настроек)
            height: Высота изображения (по умолчанию из настроек)
            negative_prompt: Негативный промпт (по умолчанию из настроек)
            steps: Количество шагов генерации (по умолчанию из настроек)
            cfg: CFG scale (по умолчанию из настроек)
            seed: Seed для генерации (по умолчанию из настроек, -1 для случайного)
            lora_name: Имя LoRA модели (по умолчанию из настроек, None если не используется)
            lora_strength_model: Сила LoRA для модели (по умолчанию из настроек)
            lora_strength_clip: Сила LoRA для CLIP (по умолчанию из настроек)

        Returns:
            bytes: Байты изображения в формате PNG

        Raises:
            httpx.HTTPStatusError: При ошибке API
            ValueError: Если не удалось обработать изображение
        """
        payload = {
            "prompt": prompt,
            "width": width or settings.image_default_width,
            "height": height or settings.image_default_height,
            "negative_prompt": negative_prompt or settings.image_default_negative_prompt,
            "steps": steps if steps is not None else settings.image_default_steps,
            "cfg": cfg if cfg is not None else settings.image_default_cfg,
            "seed": seed if seed is not None else settings.image_default_seed,
        }
        
        # Добавляем параметры LoRA, если указаны
        lora_name_to_use = lora_name if lora_name is not None else settings.image_default_lora_name
        if lora_name_to_use:
            payload["lora_name"] = lora_name_to_use
            payload["lora_strength_model"] = (
                lora_strength_model 
                if lora_strength_model is not None 
                else settings.image_default_lora_strength_model
            )
            payload["lora_strength_clip"] = (
                lora_strength_clip 
                if lora_strength_clip is not None 
                else settings.image_default_lora_strength_clip
            )
        response = await self._client.post("/generate", json=payload)
        response.raise_for_status()
        
        content_type = response.headers.get("content-type", "").lower()
        logger.info(f"Content-Type ответа: {content_type}")
        logger.info(f"Размер ответа: {len(response.content)} байт")
        
        image_bytes: bytes | None = None
        
        # Если это JSON, возможно изображение в base64
        # Также проверяем, если content-type не указан, но ответ похож на JSON
        is_json = "application/json" in content_type or (not content_type and response.text.strip().startswith(("{", "[")))
        
        if is_json:
            try:
                data = response.json()
                logger.debug(f"Получен JSON ответ, тип: {type(data)}, ключи: {list(data.keys()) if isinstance(data, dict) else 'не словарь'}")
                # Проверяем разные возможные форматы ответа
                if isinstance(data, dict):
                    # Проверяем наличие ошибки
                    if "error" in data:
                        error_details = data.get("details", "")
                        error_type = data.get("error", "Неизвестная ошибка")
                        
                        # Пытаемся извлечь понятное сообщение об ошибке
                        if isinstance(error_details, str):
                            try:
                                details_json = json.loads(error_details)
                                # Ищем понятное сообщение в структуре ошибки
                                if isinstance(details_json, dict):
                                    if "error" in details_json and isinstance(details_json["error"], dict):
                                        error_msg = details_json["error"].get("message", error_type)
                                        error_details_text = details_json["error"].get("details", "")
                                        if error_details_text:
                                            error_msg = f"{error_msg}: {error_details_text}"
                                        
                                        # Логируем полную информацию об ошибке для отладки
                                        logger.error(f"ComfyUI ошибка: {error_msg}")
                                        if "node_errors" in details_json:
                                            logger.error(f"Ошибки узлов: {json.dumps(details_json['node_errors'], indent=2)}")
                                    else:
                                        error_msg = error_type
                                else:
                                    error_msg = error_type
                            except Exception as parse_error:
                                logger.error(f"Не удалось распарсить детали ошибки: {parse_error}")
                                error_msg = error_type
                        else:
                            error_msg = error_type
                        
                        logger.error(f"API вернул ошибку: {error_msg}")
                        raise ValueError(f"Ошибка генерации изображения: {error_msg}")
                    
                    # Проверяем статус
                    if "status" in data and data["status"] != "ok":
                        error_msg = data.get("error", "Неизвестная ошибка")
                        logger.error(f"API вернул статус не ok: {error_msg}")
                        raise ValueError(f"Ошибка генерации изображения: {error_msg}")
                    
                    # Ищем поле с base64 изображением
                    if "image_base64" in data:
                        image_data = data["image_base64"]
                        logger.debug("Найдено поле 'image_base64'")
                    elif "image" in data:
                        image_data = data["image"]
                        logger.debug("Найдено поле 'image'")
                    elif "data" in data:
                        image_data = data["data"]
                        logger.debug("Найдено поле 'data'")
                    elif "base64" in data:
                        image_data = data["base64"]
                        logger.debug("Найдено поле 'base64'")
                    else:
                        # Пробуем взять первое строковое значение, исключая служебные поля
                        excluded_keys = {"status", "error", "details", "images_sent", "count", "prompt", "seed", "cfg", "steps"}
                        image_data = next(
                            (v for k, v in data.items() 
                             if isinstance(v, str) and k not in excluded_keys and len(v) > 100),  # base64 обычно длинный
                            None
                        )
                        if not image_data:
                            logger.error(f"Не найдено поле с base64. Доступные ключи: {list(data.keys())}")
                            # Если есть статус ok, но нет изображения, значит API не вернул изображение
                            if data.get("status") == "ok":
                                raise ValueError(
                                    "API вернул статус 'ok', но не вернул изображение. "
                                    "Проверь, что API возвращает поле 'image_base64' в ответе."
                                )
                            raise ValueError(f"Не найдено поле с base64 изображением в JSON. Доступные ключи: {list(data.keys())}")
                        logger.debug(f"Использовано первое подходящее строковое значение из JSON")
                elif isinstance(data, str):
                    image_data = data
                    logger.debug("JSON ответ - строка")
                else:
                    logger.error(f"Неожиданный формат JSON: {type(data)}")
                    raise ValueError(f"Неожиданный формат JSON ответа: {type(data)}")
                
                # Если это строка, декодируем base64
                if isinstance(image_data, str):
                    # Убираем префикс data:image/...;base64, если есть
                    if "," in image_data:
                        image_data = image_data.split(",", 1)[1]
                    # Убираем пробелы и переносы строк
                    image_data = image_data.strip().replace("\n", "").replace(" ", "")
                    logger.debug(f"Длина base64 строки: {len(image_data)}")
                    try:
                        logger.debug(f"Длина base64 строки перед декодированием: {len(image_data)}")
                        image_bytes = base64.b64decode(image_data, validate=True)
                        logger.info(f"Base64 успешно декодирован, получено {len(image_bytes)} байт")
                    except Exception as decode_error:
                        logger.error(f"Ошибка декодирования base64: {decode_error}")
                        logger.error(f"Первые 200 символов base64: {image_data[:200]}")
                        raise ValueError(f"Не удалось декодировать base64: {decode_error}")
                else:
                    raise ValueError(f"Изображение должно быть строкой base64, получен тип: {type(image_data)}")
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                raise ValueError(f"Не удалось декодировать base64 изображение: {e}")
        # Если это текстовый ответ (возможно base64 как текст)
        elif "text" in content_type or not content_type:
            try:
                text_content = response.text.strip()
                # Пробуем декодировать как base64
                image_bytes = base64.b64decode(text_content)
            except Exception:
                # Если не получилось, пробуем как обычный текст
                try:
                    # Убираем возможные префиксы
                    text_content = response.text.strip()
                    if "," in text_content:
                        text_content = text_content.split(",", 1)[1]
                    text_content = text_content.replace("\n", "").replace(" ", "")
                    image_bytes = base64.b64decode(text_content)
                except Exception as e:
                    raise ValueError(f"Не удалось декодировать base64 из текстового ответа: {e}")
        else:
            # Если это бинарные данные изображения
            image_bytes = response.content
        
        if not image_bytes:
            raise ValueError("Не удалось получить данные изображения")
        
        # Проверяем магические байты для определения формата
        logger.info(f"Получено {len(image_bytes)} байт данных")
        if len(image_bytes) < 4:
            raise ValueError(f"Получено слишком мало данных: {len(image_bytes)} байт")
        
        # Проверяем магические байты (первые байты файла)
        magic_bytes = image_bytes[:4]
        magic_hex = magic_bytes.hex()
        logger.info(f"Магические байты (hex): {magic_hex}")
        
        # Определяем формат по магическим байтам
        # PNG: 89 50 4E 47
        # JPEG: FF D8 FF E0 или FF D8 FF E1
        # GIF: 47 49 46 38
        if magic_bytes.startswith(b'\x89PNG'):
            logger.info("Обнаружен формат PNG")
        elif magic_bytes.startswith(b'\xff\xd8\xff'):
            logger.info("Обнаружен формат JPEG")
        elif magic_bytes.startswith(b'GIF8'):
            logger.info("Обнаружен формат GIF")
        elif magic_bytes.startswith(b'{') or magic_bytes.startswith(b'['):
            # Возможно, это JSON, а не изображение
            logger.error(f"Получены данные, похожие на JSON, а не изображение. Начало: {image_bytes[:100]}")
            raise ValueError("Получены данные в формате JSON, а не изображение. Проверь формат ответа API.")
        else:
            logger.warning(f"Неизвестный формат изображения. Магические байты: {magic_hex}")
        
        # Валидируем и конвертируем в PNG, если нужно
        try:
            logger.debug(f"Попытка открыть изображение, размер: {len(image_bytes)} байт")
            img = Image.open(BytesIO(image_bytes))
            logger.debug(f"Изображение успешно открыто: {img.format}, размер: {img.size}, режим: {img.mode}")
            
            # Проверяем размер файла (Telegram ограничение ~10MB для фото)
            # Если слишком большое, сжимаем
            max_size = 10 * 1024 * 1024  # 10MB
            
            # Конвертируем в RGB, если нужно (для JPEG и других форматов)
            if img.mode in ("RGBA", "LA", "P"):
                # Сохраняем альфа-канал для PNG
                output = BytesIO()
                img.save(output, format="PNG", optimize=True)
                result = output.getvalue()
            elif img.mode != "RGB":
                img = img.convert("RGB")
                output = BytesIO()
                img.save(output, format="PNG", optimize=True)
                result = output.getvalue()
            else:
                output = BytesIO()
                img.save(output, format="PNG", optimize=True)
                result = output.getvalue()
            
            # Если файл слишком большой, сжимаем
            if len(result) > max_size:
                # Уменьшаем качество и размер
                scale_factor = (max_size / len(result)) ** 0.5
                new_width = int(img.width * scale_factor)
                new_height = int(img.height * scale_factor)
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                output = BytesIO()
                if img_resized.mode in ("RGBA", "LA", "P"):
                    img_resized.save(output, format="PNG", optimize=True)
                else:
                    img_resized = img_resized.convert("RGB")
                    img_resized.save(output, format="PNG", optimize=True)
                result = output.getvalue()
            
            return result
        except Exception as e:
            logger.error(f"Ошибка при обработке изображения: {e}, тип: {type(e).__name__}")
            logger.debug(f"Первые 100 байт данных (hex): {image_bytes[:100].hex()}")
            logger.debug(f"Первые 100 байт данных (repr): {repr(image_bytes[:100])}")
            raise ValueError(f"Не удалось обработать изображение: {e}")

    async def close(self) -> None:
        """Закрывает HTTP клиент."""
        await self._client.aclose()

