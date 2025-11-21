"""Клиент для работы с Live3D API для генерации изображений."""
import asyncio
import json
import logging
import time
from io import BytesIO

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    USE_SELENIUM = True
except ImportError:
    USE_SELENIUM = False

try:
    import cloudscraper
    USE_CLOUDSCRAPER = True
except ImportError:
    USE_CLOUDSCRAPER = False

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


class Live3DImageClient:
    """Клиент для генерации изображений через Live3D API."""

    def __init__(self) -> None:
        """Инициализирует клиент Live3D."""
        # Захардкоженный токен из test_live3d_api.py
        self._api_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjM2NTE2MTcsInN1YiI6Imdvb2dsZSA0NDczNDM3IG11aGFtbWFkYW1pbm1hZGlldkBnbWFpbC5jb20ifQ.Xi6mvxjiJ210vv700GVx8PrNzx483T-qRHsxzkhLtd4"
        
        # Используем токен из настроек, если он установлен, иначе используем захардкоженный
        if settings.live3d_api_token:
            self._api_token = settings.live3d_api_token
            logger.info("Используется токен из настроек")
        else:
            logger.info("Используется захардкоженный токен из test_live3d_api.py")
        self._base_url = "https://api.live3d.io/api/v1"
        self._model_id = settings.live3d_model_id
        self._consume_points = settings.live3d_consume_points
        
        # Логируем информацию о токене (первые и последние символы для безопасности)
        token_preview = f"{self._api_token[:10]}...{self._api_token[-10:]}" if len(self._api_token) > 20 else "***"
        logger.info(f"Live3D клиент инициализирован: model_id={self._model_id}, consume_points={self._consume_points}, token={token_preview}")
        self._driver: webdriver.Chrome | None = None
        self._scraper = None
        
        # Используем Selenium для получения cookie, если доступен
        if USE_SELENIUM:
            logger.info("Selenium доступен, будет использован для получения cookies")
        else:
            logger.warning("Selenium не установлен. Для лучшей работы установите: pip install selenium")
        
        # Используем cloudscraper для запросов
        if USE_CLOUDSCRAPER:
            logger.info("Используется cloudscraper для обхода Cloudflare")
            self._scraper = cloudscraper.create_scraper()
        else:
            logger.warning("cloudscraper не установлен, используем httpx (может не работать с Cloudflare)")
            logger.warning("Для обхода Cloudflare установите: pip install cloudscraper")

    def _get_cf_clearance_with_selenium(self) -> str | None:
        """Получает cf_clearance cookie через Selenium (эмуляция браузера)"""
        if not USE_SELENIUM:
            return None
        
        logger.info("Запуск браузера для получения cf_clearance cookie...")
        chrome_options = Options()
        # Headless режим для работы на сервере без GUI
        chrome_options.add_argument("--headless=new")  # Новый headless режим Chrome
        chrome_options.add_argument("--no-sandbox")  # Необходимо для работы в Docker/сервере
        chrome_options.add_argument("--disable-dev-shm-usage")  # Избегает проблем с /dev/shm
        chrome_options.add_argument("--disable-gpu")  # Отключаем GPU в headless режиме
        chrome_options.add_argument("--disable-software-rasterizer")  # Отключаем софтверный растеризатор
        chrome_options.add_argument("--window-size=1920,1080")  # Устанавливаем размер окна
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            # Сначала открываем главную страницу
            driver.get("https://animegenius.live3d.io/")
            
            # Ждем, пока Cloudflare challenge пройдет
            logger.info("Ожидание прохождения Cloudflare challenge...")
            time.sleep(10)  # Увеличиваем время ожидания
            
            # Получаем cookies
            cookies = driver.get_cookies()
            
            # Ищем cf_clearance для api.live3d.io
            cf_clearance = None
            for cookie in cookies:
                if cookie['name'] == 'cf_clearance':
                    domain = cookie.get('domain', '')
                    if 'api.live3d.io' in domain or 'live3d.io' in domain:
                        cf_clearance = cookie['value']
                        logger.info(f"✅ Получен cf_clearance cookie для {domain}: {cf_clearance[:50]}...")
                        break
            
            if not cf_clearance:
                # Если не нашли для api.live3d.io, берем любой
                for cookie in cookies:
                    if cookie['name'] == 'cf_clearance':
                        cf_clearance = cookie['value']
                        logger.info(f"✅ Получен cf_clearance cookie: {cf_clearance[:50]}...")
                        break
            
            driver.quit()
            return cf_clearance
        except Exception as e:
            logger.error(f"❌ Ошибка при получении cookie через Selenium: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def generate_image(
        self,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        negative_prompt: str | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        seed: int | None = None,
        **kwargs,  # Игнорируем LoRA параметры
    ) -> bytes:
        """
        Генерирует изображение по промпту через Live3D API.

        Args:
            prompt: Текстовый промпт для генерации
            width: Ширина изображения (по умолчанию из настроек)
            height: Высота изображения (по умолчанию из настроек)
            negative_prompt: Негативный промпт (по умолчанию из настроек)
            steps: Количество шагов генерации (по умолчанию из настроек)
            cfg: CFG scale (по умолчанию из настроек)
            seed: Seed для генерации (по умолчанию из настроек, -1 для случайного)

        Returns:
            bytes: Байты изображения в формате PNG

        Raises:
            ValueError: Если не удалось обработать изображение
        """
        # Используем значения по умолчанию из настроек Live3D (как в test_live3d_api.py)
        width = width or settings.live3d_default_width
        height = height or settings.live3d_default_height
        negative_prompt = negative_prompt or settings.image_default_negative_prompt
        steps = steps if steps is not None else settings.live3d_default_steps
        cfg_scale = cfg if cfg is not None else settings.live3d_default_cfg
        seed_value = seed if seed is not None else settings.image_default_seed

        # Формируем payload согласно API Live3D
        payload = {
            "consume_points": self._consume_points,
            "divide_ratio": "",
            "gen_type": "text_to_image",
            "height": height,
            "img_url": "",
            "matrix_mode": "",
            "model_id": self._model_id,
            "prompt": prompt,
            "request_data": {
                "loras": [],
                "resolution": "1",
                "image_number": 1,
                "cfg": {
                    "scale": cfg_scale,
                    "seed": seed_value
                },
                "control_weight": 1,
                "high_priority": True,
                "negative_prompt": negative_prompt,
                "sampling": {
                    "step": steps,
                    "method": "DPM++ 2M Karras"
                },
                "type": 1,
                "width": width
            },
            "width": width
        }

        logger.info(f"Генерация изображения через Live3D (model_id={self._model_id}, width={width}, height={height}, consume_points={self._consume_points})")
        logger.debug(f"Параметры: prompt='{prompt[:50]}...', steps={steps}, cfg={cfg_scale}, seed={seed_value}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)[:500]}...")

        try:
            # Получаем cookie через Selenium, если доступен
            cf_clearance = None
            if USE_SELENIUM:
                loop = asyncio.get_event_loop()
                cf_clearance = await loop.run_in_executor(None, self._get_cf_clearance_with_selenium)
            
            # Используем Selenium для выполнения запроса, если доступен
            if USE_SELENIUM:
                logger.info("Использование Selenium для выполнения запроса...")
                return await self._generate_with_selenium(payload, cf_clearance)
            elif USE_CLOUDSCRAPER:
                logger.info("Использование cloudscraper для выполнения запроса...")
                return await self._generate_with_cloudscraper(payload, cf_clearance)
            else:
                logger.info("Использование httpx для выполнения запроса...")
                return await self._generate_with_httpx(payload)

        except ValueError as e:
            # Пробрасываем ValueError как есть (например, ошибка о недостатке очков)
            raise
        except Exception as e:
            logger.error(f"Ошибка генерации изображения через Live3D: {e}", exc_info=True)
            raise ValueError(f"Ошибка генерации изображения через Live3D: {e}")

    async def _generate_with_selenium(self, payload: dict, cf_clearance: str | None) -> bytes:
        """Генерирует изображение используя Selenium (как в test_live3d_api.py)"""
        chrome_options = Options()
        # Headless режим для работы на сервере без GUI
        chrome_options.add_argument("--headless=new")  # Новый headless режим Chrome
        chrome_options.add_argument("--no-sandbox")  # Необходимо для работы в Docker/сервере
        chrome_options.add_argument("--disable-dev-shm-usage")  # Избегает проблем с /dev/shm
        chrome_options.add_argument("--disable-gpu")  # Отключаем GPU в headless режиме
        chrome_options.add_argument("--disable-software-rasterizer")  # Отключаем софтверный растеризатор
        chrome_options.add_argument("--window-size=1920,1080")  # Устанавливаем размер окна
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.get("https://animegenius.live3d.io/")
            time.sleep(5)  # Ждем загрузки
            
            # Выполняем запрос через JavaScript в браузере
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: driver.execute_async_script("""
                    var callback = arguments[arguments.length - 1];
                    var token = arguments[0];
                    var payload = arguments[1];
                    
                        fetch('https://api.live3d.io/api/v1/generation/generate', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': token,
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify(payload)
                        })
                        .then(response => {
                            if (!response.ok) {
                                return response.text().then(text => {
                                    var errorData = null;
                                    try {
                                        errorData = JSON.parse(text);
                                    } catch(e) {
                                        errorData = {detail: text};
                                    }
                                    return {
                                        success: false,
                                        status: response.status,
                                        error: JSON.stringify(errorData),
                                        errorData: errorData
                                    };
                                });
                            }
                            return response.json().then(data => ({
                                success: true,
                                data: data
                            }));
                        })
                    .then(result => callback(result))
                    .catch(error => callback({
                        success: false,
                        error: error.toString()
                    }));
                """, f"Bearer {self._api_token}", payload)
            )
            
            if not result or not result.get('success'):
                error_msg = result.get('error', 'Unknown error') if result else 'No result'
                status = result.get('status', 'N/A') if result else 'N/A'
                error_data = result.get('errorData', {}) if result else {}
                
                # Проверяем, является ли это ошибкой о недостатке очков
                error_str = str(error_msg).lower() + str(error_data).lower()
                if status == 403 and 'point' in error_str:
                    raise ValueError(f"Недостаточно очков на аккаунте Live3D для генерации (требуется {self._consume_points} очков). Пополните баланс на https://animegenius.live3d.io/")
                
                # Проверяем ошибку авторизации (401)
                if status == 401:
                    token_preview = f"{self._api_token[:10]}...{self._api_token[-10:]}" if len(self._api_token) > 20 else "***"
                    raise ValueError(
                        f"Ошибка авторизации Live3D API (HTTP 401): Токен недействителен или истек.\n"
                        f"Используемый токен: {token_preview}\n"
                        f"Пожалуйста, обновите токен в настройках (.env файл: LIVE3D_API_TOKEN) или получите новый токен на https://animegenius.live3d.io/"
                    )
                
                raise ValueError(f"Selenium запрос не удался (HTTP {status}): {error_msg}")
            
            task_id = result['data'].get('data', {}).get('id')
            if not task_id:
                raise ValueError(f"Не удалось получить ID задачи из ответа: {result['data']}")
            
            logger.info(f"Задача генерации создана, ID: {task_id}")
            
            # Ожидаем завершения генерации
            image_url = await self._wait_for_generation_selenium(driver, task_id)
            
            # Получаем width и height из payload для изменения размера
            target_width = payload.get("width", settings.live3d_default_width)
            target_height = payload.get("height", settings.live3d_default_height)
            
            # Загружаем изображение
            logger.info(f"Загрузка изображения с URL: {image_url}")
            image_response = await loop.run_in_executor(
                None,
                lambda: driver.execute_async_script("""
                    var callback = arguments[arguments.length - 1];
                    var url = arguments[0];
                    
                    fetch(url)
                    .then(response => response.blob())
                    .then(blob => {
                        var reader = new FileReader();
                        reader.onloadend = function() {
                            var base64 = reader.result.split(',')[1];
                            callback({success: true, data: base64});
                        };
                        reader.readAsDataURL(blob);
                    })
                    .catch(error => callback({success: false, error: error.toString()}));
                """, image_url)
            )
            
            if not image_response or not image_response.get('success'):
                raise ValueError(f"Не удалось загрузить изображение: {image_response.get('error', 'Unknown error')}")
            
            import base64
            image_bytes = base64.b64decode(image_response['data'])
            
            # Конвертируем в PNG, если нужно
            image = Image.open(BytesIO(image_bytes))
            if image.format != "PNG":
                png_buffer = BytesIO()
                image.save(png_buffer, format="PNG")
                image_bytes = png_buffer.getvalue()
            
            # Изменяем размер, если нужно
            if target_width != image.width or target_height != image.height:
                image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                png_buffer = BytesIO()
                image.save(png_buffer, format="PNG")
                image_bytes = png_buffer.getvalue()
            
            logger.info(f"Изображение успешно сгенерировано, размер: {len(image_bytes)} байт")
            return image_bytes
            
        finally:
            driver.quit()

    async def _wait_for_generation_selenium(self, driver: webdriver.Chrome, task_id: str, max_attempts: int = 60, delay: int = 3) -> str:
        """Ожидает завершения генерации используя Selenium"""
        logger.info(f"Ожидание завершения генерации (ID: {task_id})...")
        
        loop = asyncio.get_event_loop()
        
        for attempt in range(max_attempts):
            await asyncio.sleep(delay)
            
            try:
                status_result = await loop.run_in_executor(
                    None,
                    lambda: driver.execute_async_script("""
                        var callback = arguments[arguments.length - 1];
                        var token = arguments[0];
                        var taskId = arguments[1];
                        
                        fetch('https://api.live3d.io/api/v1/generation/check_generate_state?ai_art_id=' + taskId, {
                            method: 'GET',
                            headers: {
                                'Authorization': token,
                                'Accept': 'application/json'
                            }
                        })
                        .then(response => response.json())
                        .then(data => callback({success: true, data: data}))
                        .catch(error => callback({success: false, error: error.toString()}));
                    """, f"Bearer {self._api_token}", task_id)
                )
                
                if status_result and status_result.get('success'):
                    status_data = status_result['data']
                    logger.debug(f"Статус генерации (попытка {attempt + 1}): {status_data}")
                    
                    if status_data.get("code") == 200:
                        data = status_data.get("data", {})
                        url_data = data.get("url", [])
                        task_status = data.get("status")
                        
                        has_url = False
                        if isinstance(url_data, list) and len(url_data) > 0:
                            has_url = True
                            image_path = url_data[0]
                        elif isinstance(url_data, str) and url_data:
                            has_url = True
                            image_path = url_data
                        else:
                            image_path = None
                        
                        status_is_complete = False
                        if isinstance(task_status, int):
                            status_is_complete = (task_status == 1)
                        elif isinstance(task_status, str):
                            status_is_complete = task_status in ['completed', 'success', 'done', '1']
                        else:
                            status_is_complete = has_url
                        
                        if has_url or status_is_complete:
                            if not image_path:
                                raise ValueError("URL изображения не найден в ответе")
                            
                            base_url = "https://art-global.yimeta.ai/"
                            if image_path.startswith('http'):
                                full_url = image_path
                            else:
                                image_path = image_path.lstrip('/')
                                full_url = base_url + image_path
                            
                            logger.info(f"Генерация завершена, URL: {full_url}")
                            return full_url
                        else:
                            logger.debug(f"Генерация в процессе (status={task_status}), продолжаем ожидание...")
            except Exception as e:
                logger.warning(f"Ошибка при проверке статуса (попытка {attempt + 1}): {e}")
        
        raise TimeoutError(f"Генерация не завершилась за {max_attempts * delay} секунд")

    async def _generate_with_cloudscraper(self, payload: dict, cf_clearance: str | None) -> bytes:
        """Генерирует изображение используя cloudscraper"""
        cookies = {}
        if cf_clearance:
            cookies["cf_clearance"] = cf_clearance
        
        # Сначала получаем главную страницу для получения cookies
        if self._scraper:
            try:
                logger.info("Получение cookies с главной страницы...")
                main_response = self._scraper.get("https://animegenius.live3d.io/", timeout=30)
                logger.info(f"Главная страница получена, статус: {main_response.status_code}")
            except Exception as e:
                logger.warning(f"Не удалось получить главную страницу: {e}")
        
        headers = {
            "accept": "application/json",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "authorization": f"Bearer {self._api_token}",
            "content-type": "application/json",
            "origin": "https://animegenius.live3d.io",
            "referer": "https://animegenius.live3d.io/",
        }
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._scraper.post(
                f"{self._base_url}/generation/generate",
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=300
            )
        )
        
        # Проверяем ошибки перед raise_for_status
        if response.status_code == 401:
            token_preview = f"{self._api_token[:10]}...{self._api_token[-10:]}" if len(self._api_token) > 20 else "***"
            raise ValueError(
                f"Ошибка авторизации Live3D API (HTTP 401): Токен недействителен или истек.\n"
                f"Используемый токен: {token_preview}\n"
                f"Пожалуйста, обновите токен в настройках (.env файл: LIVE3D_API_TOKEN) или получите новый токен на https://animegenius.live3d.io/"
            )
        elif response.status_code == 403:
            try:
                error_data = response.json()
                if 'point' in str(error_data).lower():
                    raise ValueError(f"Недостаточно очков на аккаунте Live3D для генерации (требуется {self._consume_points} очков). Пополните баланс на https://animegenius.live3d.io/")
            except:
                pass
        
        response.raise_for_status()
        result = response.json()
        
        task_id = result.get("data", {}).get("id")
        if not task_id:
            raise ValueError(f"Не удалось получить ID задачи из ответа: {result}")
        
        logger.info(f"Задача генерации создана, ID: {task_id}")
        
        # Ожидаем завершения генерации
        image_url = await self._wait_for_generation_cloudscraper(task_id, cookies)
        
        # Загружаем изображение
        logger.info(f"Загрузка изображения с URL: {image_url}")
        image_response = await loop.run_in_executor(
            None,
            lambda: self._scraper.get(image_url, timeout=60)
        )
        image_response.raise_for_status()
        image_bytes = image_response.content
        
        # Получаем width и height из payload
        target_width = payload.get("width", settings.live3d_default_width)
        target_height = payload.get("height", settings.live3d_default_height)
        
        # Обрабатываем изображение
        image = Image.open(BytesIO(image_bytes))
        if image.format != "PNG":
            png_buffer = BytesIO()
            image.save(png_buffer, format="PNG")
            image_bytes = png_buffer.getvalue()
        
        if target_width != image.width or target_height != image.height:
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            png_buffer = BytesIO()
            image.save(png_buffer, format="PNG")
            image_bytes = png_buffer.getvalue()
        
        logger.info(f"Изображение успешно сгенерировано, размер: {len(image_bytes)} байт")
        return image_bytes

    async def _wait_for_generation_cloudscraper(self, task_id: str, cookies: dict, max_attempts: int = 60, delay: int = 3) -> str:
        """Ожидает завершения генерации используя cloudscraper"""
        logger.info(f"Ожидание завершения генерации (ID: {task_id})...")
        
        headers = {
            "authorization": f"Bearer {self._api_token}",
            "accept": "application/json",
        }
        
        loop = asyncio.get_event_loop()
        
        for attempt in range(max_attempts):
            await asyncio.sleep(delay)
            
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: self._scraper.get(
                        f"{self._base_url}/generation/check_generate_state",
                        params={"ai_art_id": task_id},
                        headers=headers,
                        cookies=cookies,
                        timeout=30
                    )
                )
                response.raise_for_status()
                status_data = response.json()
                
                if status_data.get("code") == 200:
                    data = status_data.get("data", {})
                    url_data = data.get("url", [])
                    task_status = data.get("status")
                    
                    has_url = False
                    if isinstance(url_data, list) and len(url_data) > 0:
                        has_url = True
                        image_path = url_data[0]
                    elif isinstance(url_data, str) and url_data:
                        has_url = True
                        image_path = url_data
                    else:
                        image_path = None
                    
                    status_is_complete = False
                    if isinstance(task_status, int):
                        status_is_complete = (task_status == 1)
                    elif isinstance(task_status, str):
                        status_is_complete = task_status in ['completed', 'success', 'done', '1']
                    else:
                        status_is_complete = has_url
                    
                    if has_url or status_is_complete:
                        if not image_path:
                            raise ValueError("URL изображения не найден в ответе")
                        
                        base_url = "https://art-global.yimeta.ai/"
                        if image_path.startswith('http'):
                            full_url = image_path
                        else:
                            image_path = image_path.lstrip('/')
                            full_url = base_url + image_path
                        
                        logger.info(f"Генерация завершена, URL: {full_url}")
                        return full_url
            except Exception as e:
                logger.warning(f"Ошибка при проверке статуса (попытка {attempt + 1}): {e}")
        
        raise TimeoutError(f"Генерация не завершилась за {max_attempts * delay} секунд")

    async def _generate_with_httpx(self, payload: dict) -> bytes:
        """Генерирует изображение используя httpx (fallback)"""
        async with httpx.AsyncClient(timeout=300.0) as client:
            headers = {
                "accept": "application/json",
                "authorization": f"Bearer {self._api_token}",
                "content-type": "application/json",
                "origin": "https://animegenius.live3d.io",
                "referer": "https://animegenius.live3d.io/",
            }
            
            response = await client.post(
                f"{self._base_url}/generation/generate",
                headers=headers,
                json=payload
            )
            
            # Проверяем ошибку авторизации (401)
            if response.status_code == 401:
                token_preview = f"{self._api_token[:10]}...{self._api_token[-10:]}" if len(self._api_token) > 20 else "***"
                raise ValueError(
                    f"Ошибка авторизации Live3D API (HTTP 401): Токен недействителен или истек.\n"
                    f"Используемый токен: {token_preview}\n"
                    f"Пожалуйста, обновите токен в настройках (.env файл: LIVE3D_API_TOKEN) или получите новый токен на https://animegenius.live3d.io/"
                )
            
            response.raise_for_status()
            result = response.json()
            
            task_id = result.get("data", {}).get("id")
            if not task_id:
                raise ValueError(f"Не удалось получить ID задачи из ответа: {result}")
            
            logger.info(f"Задача генерации создана, ID: {task_id}")
            
            # Ожидаем завершения генерации
            image_url = await self._wait_for_generation_httpx(client, task_id)
            
            # Загружаем изображение
            logger.info(f"Загрузка изображения с URL: {image_url}")
            image_response = await client.get(image_url)
            image_response.raise_for_status()
            image_bytes = image_response.content
            
        # Получаем width и height из payload
        target_width = payload.get("width", settings.live3d_default_width)
        target_height = payload.get("height", settings.live3d_default_height)
        
        # Обрабатываем изображение
        image = Image.open(BytesIO(image_bytes))
        if image.format != "PNG":
            png_buffer = BytesIO()
            image.save(png_buffer, format="PNG")
            image_bytes = png_buffer.getvalue()
        
        if target_width != image.width or target_height != image.height:
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            png_buffer = BytesIO()
            image.save(png_buffer, format="PNG")
            image_bytes = png_buffer.getvalue()
            
            logger.info(f"Изображение успешно сгенерировано, размер: {len(image_bytes)} байт")
            return image_bytes

    async def _wait_for_generation_httpx(self, client: httpx.AsyncClient, task_id: str, max_attempts: int = 60, delay: int = 3) -> str:
        """Ожидает завершения генерации используя httpx"""
        logger.info(f"Ожидание завершения генерации (ID: {task_id})...")
        
        headers = {
            "authorization": f"Bearer {self._api_token}",
            "accept": "application/json",
        }
        
        for attempt in range(max_attempts):
            await asyncio.sleep(delay)
            
            try:
                response = await client.get(
                    f"{self._base_url}/generation/check_generate_state",
                    params={"ai_art_id": task_id},
                    headers=headers
                )
                response.raise_for_status()
                status_data = response.json()
                
                if status_data.get("code") == 200:
                    data = status_data.get("data", {})
                    url_data = data.get("url", [])
                    task_status = data.get("status")
                    
                    has_url = False
                    if isinstance(url_data, list) and len(url_data) > 0:
                        has_url = True
                        image_path = url_data[0]
                    elif isinstance(url_data, str) and url_data:
                        has_url = True
                        image_path = url_data
                    else:
                        image_path = None
                    
                    status_is_complete = False
                    if isinstance(task_status, int):
                        status_is_complete = (task_status == 1)
                    elif isinstance(task_status, str):
                        status_is_complete = task_status in ['completed', 'success', 'done', '1']
                    else:
                        status_is_complete = has_url
                    
                    if has_url or status_is_complete:
                        if not image_path:
                            raise ValueError("URL изображения не найден в ответе")
                        
                        base_url = "https://art-global.yimeta.ai/"
                        if image_path.startswith('http'):
                            full_url = image_path
                        else:
                            image_path = image_path.lstrip('/')
                            full_url = base_url + image_path
                        
                        logger.info(f"Генерация завершена, URL: {full_url}")
                        return full_url
            except Exception as e:
                logger.warning(f"Ошибка при проверке статуса (попытка {attempt + 1}): {e}")
        
        raise TimeoutError(f"Генерация не завершилась за {max_attempts * delay} секунд")

    async def close(self) -> None:
        """Закрывает HTTP клиент."""
        if self._driver:
            self._driver.quit()
        # cloudscraper и httpx не требуют явного закрытия в этом контексте
