"""Клиент для работы с Replicate API для генерации изображений."""
import asyncio
import logging
from io import BytesIO

import httpx
import replicate
from PIL import Image

from app.config import settings

# Импортируем settings для доступа к параметрам по умолчанию

logger = logging.getLogger(__name__)


class ReplicateImageClient:
    """Клиент для генерации изображений через Replicate."""

    def __init__(self) -> None:
        """Инициализирует клиент Replicate."""
        if not settings.replicate_api_token:
            raise ValueError("REPLICATE_API_TOKEN не установлен в настройках")
        
        # Создаем клиент Replicate с токеном
        self._replicate_client = replicate.Client(api_token=settings.replicate_api_token)
        self._model = settings.replicate_model
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Получает или создает HTTP клиент для загрузки изображений."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def generate_image(
        self,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        negative_prompt: str | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        seed: int | None = None,
        **kwargs,  # Игнорируем LoRA параметры, так как Replicate их не поддерживает напрямую
    ) -> bytes:
        """
        Генерирует изображение по промпту через Replicate.

        Args:
            prompt: Текстовый промпт для генерации
            width: Ширина изображения (по умолчанию из настроек)
            height: Высота изображения (по умолчанию из настроек)
            negative_prompt: Негативный промпт (по умолчанию из настроек)
            steps: Количество шагов генерации (игнорируется для flux-dev)
            cfg: CFG scale (игнорируется для flux-dev)
            seed: Seed для генерации (по умолчанию из настроек, -1 для случайного)
            **kwargs: Дополнительные параметры (игнорируются)

        Returns:
            bytes: Байты изображения в формате PNG

        Raises:
            ValueError: При ошибке генерации или загрузки изображения
        """
        # Подготавливаем параметры для Replicate
        input_params: dict[str, any] = {
            "prompt": prompt,
        }
        
        # Добавляем негативный промпт, если указан
        if negative_prompt:
            input_params["negative_prompt"] = negative_prompt
        
        # Добавляем размеры, если указаны
        if width:
            input_params["width"] = width
        if height:
            input_params["height"] = height
        
        # Добавляем seed, если указан (и не -1)
        if seed is not None and seed != -1:
            input_params["seed"] = seed
        
        # Определяем тип модели и добавляем специфичные параметры
        model_name = self._model.lower()
        
        if "wai" in model_name or "illustrious" in model_name:
            # WAI NSFW Illustrious модели
            if steps is not None:
                input_params["num_inference_steps"] = steps
            elif settings.image_default_steps:
                input_params["num_inference_steps"] = settings.image_default_steps
            
            if cfg is not None:
                input_params["guidance_scale"] = cfg
            elif settings.image_default_cfg:
                input_params["guidance_scale"] = settings.image_default_cfg
            
            logger.debug("Используется модель WAI NSFW Illustrious с параметрами steps и guidance_scale")
        elif "animagine" in model_name:
            # Animagine XL модели поддерживают дополнительные параметры
            if steps is not None:
                input_params["num_inference_steps"] = steps
            elif settings.image_default_steps:
                input_params["num_inference_steps"] = settings.image_default_steps
            
            if cfg is not None:
                input_params["guidance_scale"] = cfg
            elif settings.image_default_cfg:
                input_params["guidance_scale"] = settings.image_default_cfg
            
            # Animagine может поддерживать дополнительные параметры
            # Можно добавить: sampler, scale и т.д.
            logger.debug("Используется модель Animagine XL с параметрами steps и guidance_scale")
        elif "flux" in model_name:
            # FLUX модели могут иметь другие параметры
            # Для flux-dev обычно используются: prompt, width, height, num_outputs, guidance_scale
            if cfg is not None:
                input_params["guidance_scale"] = cfg
            elif settings.image_default_cfg:
                input_params["guidance_scale"] = settings.image_default_cfg
            
            if steps is not None:
                input_params["num_inference_steps"] = steps
            
            logger.debug("Используется модель FLUX")
        else:
            # Для других моделей пробуем добавить стандартные параметры
            if steps is not None:
                input_params["num_inference_steps"] = steps
            if cfg is not None:
                input_params["guidance_scale"] = cfg
            logger.debug(f"Используется модель {self._model} с базовыми параметрами")
        
        logger.info(f"Генерация изображения через Replicate (модель: {self._model})")
        logger.debug(f"Параметры: {input_params}")
        
        try:
            # Запускаем генерацию в отдельном потоке (Replicate синхронный)
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                lambda: self._replicate_client.run(self._model, input=input_params)
            )
            
            logger.info(f"Replicate вернул результат: {type(output)}")
            logger.debug(f"Replicate результат repr: {repr(output)}")
            
            # Replicate может возвращать разные форматы:
            # 1. FileOutput объект (можно читать как байты или получить URL)
            # 2. Итератор/список файлов
            # 3. URL строка
            # 4. Байты напрямую
            image_bytes: bytes | None = None
            image_url: str | None = None
            
            # Проверяем, является ли результат уже байтами
            if isinstance(output, bytes):
                image_bytes = output
                logger.info("Replicate вернул байты напрямую")
            # Проверяем FileOutput ПЕРЕД проверкой итератора, так как FileOutput может быть итерируемым
            elif hasattr(output, 'url') or (hasattr(output, 'read') and not isinstance(output, str)):
                # Если это файловый объект (FileOutput)
                try:
                    # Сначала пробуем получить URL (более надежный способ)
                    if hasattr(output, 'url'):
                        url_attr = getattr(output, 'url')
                        if callable(url_attr):
                            image_url = url_attr()
                            logger.info(f"Получен URL из FileOutput: {image_url}")
                        else:
                            image_url = url_attr
                            logger.info(f"Получен URL как свойство: {image_url}")
                    # Если URL не получили, пробуем прочитать напрямую
                    if not image_url and hasattr(output, 'read'):
                        if callable(getattr(output, 'read', None)):
                            # Читаем в синхронном режиме (FileOutput может быть синхронным)
                            loop = asyncio.get_event_loop()
                            image_bytes = await loop.run_in_executor(
                                None,
                                lambda: output.read() if hasattr(output, 'read') else None
                            )
                            if image_bytes:
                                logger.info("Прочитаны байты из FileOutput через read()")
                except Exception as e:
                    logger.warning(f"Ошибка при работе с FileOutput: {e}, пробуем получить URL")
                    # Пробуем получить URL как fallback
                    if not image_url and hasattr(output, 'url'):
                        try:
                            url_attr = getattr(output, 'url')
                            if callable(url_attr):
                                image_url = url_attr()
                            else:
                                image_url = url_attr
                        except Exception as url_error:
                            logger.error(f"Не удалось получить URL из FileOutput: {url_error}")
                            raise ValueError(f"Не удалось обработать FileOutput: {e}")
            elif hasattr(output, '__iter__') and not isinstance(output, str):
                # Если это итератор, список или словарь (как в WAI моделях)
                # Проверяем, является ли это словарем (как в примере с WAI)
                if isinstance(output, dict):
                    # Если это словарь, берем первый элемент (обычно индекс 0)
                    if '0' in output:
                        first_result = output['0']
                    elif 0 in output:
                        first_result = output[0]
                    else:
                        # Берем первый доступный ключ
                        first_key = next(iter(output.keys()))
                        first_result = output[first_key]
                    logger.debug(f"Replicate вернул словарь, первый элемент: {type(first_result)}")
                else:
                    # Если это список или итератор
                    output_list = list(output)
                    logger.debug(f"Replicate вернул список из {len(output_list)} элементов")
                    if not output_list:
                        raise ValueError("Replicate не вернул изображений")
                    first_result = output_list[0]
                
                logger.debug(f"Первый результат: {type(first_result)}")
                
                # Проверяем разные варианты
                if isinstance(first_result, bytes):
                    image_bytes = first_result
                    logger.info("Первый элемент - байты")
                elif isinstance(first_result, str) and first_result.startswith("http"):
                    image_url = first_result
                    logger.debug(f"Найден URL как строка: {image_url}")
                elif hasattr(first_result, 'read'):
                    # Пробуем прочитать как файл
                    try:
                        loop = asyncio.get_event_loop()
                        image_bytes = await loop.run_in_executor(
                            None,
                            lambda: first_result.read() if hasattr(first_result, 'read') else None
                        )
                        if image_bytes:
                            logger.info("Прочитаны байты из первого элемента через read()")
                    except Exception as read_error:
                        logger.warning(f"Не удалось прочитать через read(): {read_error}, пробуем URL")
                        # Если не получилось, пробуем URL
                        if hasattr(first_result, 'url'):
                            url_attr = getattr(first_result, 'url')
                            if callable(url_attr):
                                image_url = url_attr()
                            else:
                                image_url = url_attr
                elif hasattr(first_result, 'url'):
                    # Проверяем, является ли url методом или свойством
                    url_attr = getattr(first_result, 'url')
                    if callable(url_attr):
                        image_url = url_attr()
                        logger.info(f"Найден URL через метод url(): {image_url}")
                    else:
                        image_url = url_attr
                        logger.info(f"Найден URL как свойство: {image_url}")
                else:
                    # Пробуем получить строковое представление
                    result_str = str(first_result)
                    if result_str.startswith("http"):
                        image_url = result_str
                        logger.debug(f"Найден URL через str(): {image_url}")
                    else:
                        logger.error(f"Неожиданный формат результата Replicate: {type(first_result)}")
                        raise ValueError(f"Неожиданный формат результата Replicate: {type(first_result)}. Ожидался URL, байты или объект с методом url()/read()")
            elif isinstance(output, str) and output.startswith("http"):
                # Если результат - это URL напрямую
                image_url = output
                logger.debug(f"Найден URL напрямую: {image_url}")
            else:
                logger.error(f"Неожиданный формат результата Replicate: {type(output)}")
                raise ValueError(f"Неожиданный формат результата Replicate: {type(output)}")
            
            # Если еще не получили байты, скачиваем по URL
            if not image_bytes and image_url:
                logger.info(f"Скачивание изображения с URL: {image_url}")
                client = await self._get_http_client()
                response = await client.get(image_url)
                response.raise_for_status()
                image_bytes = response.content
            elif not image_bytes:
                raise ValueError("Не удалось получить данные изображения от Replicate (ни байты, ни URL)")
            
            if not image_bytes:
                raise ValueError("Не удалось получить данные изображения")
            
            logger.info(f"Получено {len(image_bytes)} байт изображения")
            
            # Валидируем и конвертируем в PNG, если нужно
            try:
                img = Image.open(BytesIO(image_bytes))
                logger.debug(f"Изображение успешно открыто: {img.format}, размер: {img.size}, режим: {img.mode}")
                
                # Проверяем размер файла (Telegram ограничение ~10MB для фото)
                max_size = 10 * 1024 * 1024  # 10MB
                
                # Конвертируем в RGB, если нужно
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
                
                logger.info(f"Изображение успешно обработано, размер: {len(result)} байт")
                return result
                
            except Exception as e:
                logger.error(f"Ошибка при обработке изображения: {e}")
                raise ValueError(f"Не удалось обработать изображение: {e}")
                
        except Exception as e:
            logger.exception(f"Ошибка при генерации изображения через Replicate: {e}")
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Ошибка генерации изображения через Replicate: {e}")

    async def close(self) -> None:
        """Закрывает HTTP клиент."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

