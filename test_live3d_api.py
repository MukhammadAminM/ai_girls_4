"""Тестовый скрипт для проверки API live3d.io

ВАЖНО: Cloudflare требует JavaScript challenge, который сложно обойти программно.

Варианты решения:
1. Получить свежий cookie cf_clearance из браузера:
   - Откройте https://animegenius.live3d.io/ в браузере
   - F12 -> Application -> Cookies -> https://api.live3d.io
   - Скопируйте значение cf_clearance и обновите в переменной cookies

2. Использовать Selenium для автоматического получения cookie (требует установки)
"""
import json
import time

try:
    import cloudscraper
    USE_CLOUDSCRAPER = True
except ImportError:
    import requests
    USE_CLOUDSCRAPER = False
    print("⚠️ cloudscraper не установлен, используем обычный requests")
    print("   Для лучшей работы с Cloudflare установите: pip install cloudscraper")

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    USE_SELENIUM = True
except ImportError:
    USE_SELENIUM = False
    print("⚠️ Selenium не установлен. Для автоматического получения cookie установите:")
    print("   pip install selenium")
    print("   И скачайте ChromeDriver: https://chromedriver.chromium.org/")


def get_cf_clearance_with_selenium():
    """Получает cf_clearance cookie через Selenium (эмуляция браузера)"""
    if not USE_SELENIUM:
        return None
    
    print("Запуск браузера для получения cf_clearance cookie...")
    chrome_options = Options()
    # Убираем headless, чтобы Cloudflare не блокировал
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        # Сначала открываем главную страницу
        driver.get("https://animegenius.live3d.io/")
        
        # Ждем, пока Cloudflare challenge пройдет
        print("Ожидание прохождения Cloudflare challenge...")
        time.sleep(10)  # Увеличиваем время ожидания
        
        # Теперь делаем запрос к API через Selenium, чтобы получить cookie для api.live3d.io
        # Выполняем JavaScript запрос для получения cookie
        driver.execute_script("""
            fetch('https://api.live3d.io/api/v1/generation/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjM0NzI4MTEsInN1YiI6Imdvb2dsZSA0NDczNDM3IG11aGFtbWFkYW1pbm1hZGlldkBnbWFpbC5jb20ifQ.c2ce_v3L1KfeVH9MQqTHqsZYVDY3NbGHFXegR1D21-s'
                },
                body: JSON.stringify({prompt: 'test'})
            }).catch(() => {});
        """)
        time.sleep(2)
        
        # Получаем cookies для обоих доменов
        cookies = driver.get_cookies()
        
        # Ищем cf_clearance для api.live3d.io
        cf_clearance = None
        for cookie in cookies:
            if cookie['name'] == 'cf_clearance':
                # Проверяем домен
                domain = cookie.get('domain', '')
                if 'api.live3d.io' in domain or 'live3d.io' in domain:
                    cf_clearance = cookie['value']
                    print(f"✅ Получен cf_clearance cookie для {domain}: {cf_clearance[:50]}...")
                    break
        
        if not cf_clearance:
            # Если не нашли для api.live3d.io, берем любой
            for cookie in cookies:
                if cookie['name'] == 'cf_clearance':
                    cf_clearance = cookie['value']
                    print(f"✅ Получен cf_clearance cookie: {cf_clearance[:50]}...")
                    break
        
        driver.quit()
        return cf_clearance
    except Exception as e:
        print(f"❌ Ошибка при получении cookie через Selenium: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_live3d_api():
    """Тестирует API live3d.io"""
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjM0NzI4MTEsInN1YiI6Imdvb2dsZSA0NDczNDM3IG11aGFtbWFkYW1pbm1hZGlldkBnbWFpbC5jb20ifQ.c2ce_v3L1KfeVH9MQqTHqsZYVDY3NbGHFXegR1D21-s"
    
    headers = {
        "accept": "application/json",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "origin": "https://animegenius.live3d.io",
        "referer": "https://animegenius.live3d.io/",
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }
    
    # Правильная структура payload на основе примера
    payload = {
        "consume_points": 20,
        "divide_ratio": "",
        "gen_type": "text_to_image",
        "height": 768,
        "img_url": "",
        "matrix_mode": "",
        "model_id": 135,
        "prompt": "(masterpiece), best quality, expressive eyes, perfect face, beautiful girl",
        "request_data": {
            "loras": [],
            "resolution": "1",
            "image_number": 1,
            "cfg": {
                "scale": 7,
                "seed": -1
            },
            "control_weight": 1,
            "high_priority": True,
            "negative_prompt": "(worst quality, low quality:1.4), (greyscale, monochrome:1.1), cropped, lowres , username, blurry, trademark, watermark, title, strabismus, clothing cutout, side slit,worst hand, (ugly face:1.2), extra leg, extra arm, bad foot, text, name, badhandv4, easynegative, EasyNegativeV2, negative_hand, ng_deepnegative_v1_75t",
            "sampling": {
                "step": 25,
                "method": "DPM++ 2M Karras"
            },
            "type": 1,
            "width": 512
        },
        "width": 512
    }
    
    # Упрощенный вариант для теста
    payload_simple = {
        "consume_points": 20,
        "divide_ratio": "",
        "gen_type": "text_to_image",
        "height": 768,
        "img_url": "",
        "matrix_mode": "",
        "model_id": 135,
        "prompt": "beautiful girl",
        "request_data": {
            "loras": [],
            "resolution": "1",
            "image_number": 1,
            "cfg": {
                "scale": 7,
                "seed": -1
            },
            "control_weight": 1,
            "high_priority": True,
            "negative_prompt": "",
            "sampling": {
                "step": 25,
                "method": "DPM++ 2M Karras"
            },
            "type": 1,
            "width": 512
        },
        "width": 512
    }
    
    # Используем полный payload
    payloads = [payload, payload_simple]
    
    # Попробуем получить свежий cookie через Selenium или используем предоставленный
    cookies = {}
    
    # Сначала попробуем получить через Selenium
    cf_clearance = get_cf_clearance_with_selenium() if USE_SELENIUM else None
    
    if cf_clearance:
        cookies["cf_clearance"] = cf_clearance
    else:
        # Используем предоставленный свежий cookie
        cookies["cf_clearance"] = "1XxvG.41gevTX.Au7Fld_I40l75nz5jysCtOdw4sT_Q-1763391265-1.2.1.1-kurTA9NvnS3rXQV9MdjUzMaI2JL9TxP6CsxJ43RFLS6zO9sxzWVTWzBgtDyJV_KqaCktNQaKLb9_WHMs3jzoGYV9nGhSnd28Y9TRfuonBPi9czlfGzu2tErVpJIrag7rZzh9hmhX0V1WmL4kL0lbTFpdPrv_Bcs8ps2nbxSo.HY_durAYC5Q6Pbc4ORYuYG3q.C0cFsJ59sQ0mLSZUDx1jBHGmuAnhg2maoTfCjfg.Y"
        print("✅ Используется предоставленный свежий cookie")
    
    try:
        # Если есть Selenium и cookie, попробуем использовать Selenium для запроса
        if USE_SELENIUM and cookies.get('cf_clearance'):
            print("Попытка выполнить запрос через Selenium...")
            try:
                chrome_options = Options()
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                driver = webdriver.Chrome(options=chrome_options)
                driver.get("https://animegenius.live3d.io/")
                time.sleep(5)  # Ждем загрузки
                
                # Выполняем запрос через JavaScript в браузере
                # Используем async/await для правильной обработки Promise
                # Пробуем все варианты payload
                result = None
                for i, test_payload in enumerate(payloads):
                    payload_type = "полный" if i == 0 else "упрощенный"
                    print(f"Попытка {i+1}/{len(payloads)} ({payload_type}): model_id={test_payload['model_id']}, consume_points={test_payload['consume_points']}, prompt='{test_payload['prompt'][:50]}...'")
                    result = driver.execute_async_script("""
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
                                return response.text().then(text => ({
                                    success: false,
                                    status: response.status,
                                    error: text.substring(0, 500)
                                }));
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
                    """, f"Bearer {token}", test_payload)
                    
                    if result and result.get('success'):
                        print(f"✅ Успешный запрос с payload {i+1}!")
                        break
                    elif result and result.get('status') == 422:
                        # Пробуем следующий вариант
                        print(f"⚠️ Ошибка валидации, пробуем следующий вариант...")
                        continue
                    elif result and result.get('status') == 400:
                        # Ошибка запроса, но не валидация
                        print(f"⚠️ Ошибка запроса (400), пробуем следующий вариант...")
                        continue
                    else:
                        # Другая ошибка, останавливаемся
                        break
                
                if result and result.get('success'):
                    print(f"✅ Успешный ответ через Selenium:")
                    print(json.dumps(result['data'], indent=2, ensure_ascii=False))
                    
                    # Если получили ID задачи, проверяем статус
                    task_id = result['data'].get('data', {}).get('id')
                    if task_id:
                        print(f"\n📋 ID задачи генерации: {task_id}")
                        print("⏳ Проверяем статус задачи...")
                        
                        # Проверяем статус несколько раз
                        for attempt in range(10):  # Увеличиваем количество попыток
                            time.sleep(3)  # Ждем 3 секунды между проверками
                            status_result = driver.execute_async_script("""
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
                            """, f"Bearer {token}", task_id)
                            
                            if status_result and status_result.get('success'):
                                status_data = status_result['data']
                                print(f"\nПопытка {attempt + 1}:")
                                print(json.dumps(status_data, indent=2, ensure_ascii=False))
                                
                                # Проверяем, завершена ли генерация
                                if status_data.get('code') == 200:
                                    data = status_data.get('data', {})
                                    
                                    # Получаем URL из ответа
                                    url_data = data.get('url', [])
                                    
                                    # Проверяем, есть ли URL (главный признак завершения)
                                    has_url = False
                                    if isinstance(url_data, list) and len(url_data) > 0:
                                        has_url = True
                                    elif isinstance(url_data, str) and url_data:
                                        has_url = True
                                    
                                    # Проверяем статус (может быть числом: 1 = завершено, 0 = в процессе)
                                    task_status = data.get('status')
                                    status_is_complete = False
                                    
                                    if isinstance(task_status, int):
                                        # Числовой статус: 1 = завершено, 0 = в процессе
                                        status_is_complete = (task_status == 1)
                                    elif isinstance(task_status, str):
                                        # Строковый статус
                                        status_is_complete = task_status in ['completed', 'success', 'done', '1']
                                    else:
                                        # Если статус не определен, проверяем по URL
                                        status_is_complete = has_url
                                    
                                    # Генерация завершена, если есть URL или статус = 1
                                    if has_url or status_is_complete:
                                        print("\n✅ Генерация завершена!")
                                        
                                        if has_url:
                                            # URL может быть массивом или строкой
                                            if isinstance(url_data, list) and len(url_data) > 0:
                                                image_path = url_data[0]
                                            elif isinstance(url_data, str):
                                                image_path = url_data
                                            else:
                                                image_path = None
                                            
                                            if image_path:
                                                base_url = "https://art-global.yimeta.ai/"
                                                # Формируем полный URL
                                                if image_path.startswith('http'):
                                                    full_url = image_path
                                                else:
                                                    # Убираем ведущий слеш, если есть
                                                    image_path = image_path.lstrip('/')
                                                    full_url = base_url + image_path
                                                
                                                print(f"📸 Полный URL изображения:")
                                                print(f"   {full_url}")
                                                print(f"\n💾 Для скачивания:")
                                                print(f"   curl -o image.webp '{full_url}'")
                                            else:
                                                print(f"⚠️ URL не найден в ответе")
                                        else:
                                            print(f"⚠️ Поле 'url' отсутствует в ответе")
                                        
                                        # Показываем все данные для анализа
                                        print(f"\n📊 Полные данные результата:")
                                        print(json.dumps(data, indent=2, ensure_ascii=False))
                                        break
                                    else:
                                        # Генерация еще не завершена
                                        status_str = f"status={task_status}" if task_status is not None else "status=None"
                                        print(f"⏳ Генерация в процессе ({status_str}), продолжаем ожидание...")
                                else:
                                    print(f"⚠️ Ошибка при проверке статуса: {status_data.get('message', 'Unknown')}")
                            else:
                                print(f"⚠️ Не удалось проверить статус: {status_result.get('error', 'Unknown error')}")
                        
                        print("\n💡 Для проверки статуса используйте:")
                        print(f"   GET https://api.live3d.io/api/v1/generation/check_generate_state?ai_art_id={task_id}")
                    
                    driver.quit()
                    return
                else:
                    driver.quit()
                    error_msg = result.get('error', 'Unknown error') if result else 'No result'
                    status = result.get('status', 'N/A') if result else 'N/A'
                    print(f"⚠️ Selenium запрос не удался (HTTP {status}):")
                    print(f"   {error_msg}")
                    # Показываем полный ответ для отладки
                    if result and result.get('error'):
                        try:
                            error_json = json.loads(result['error'])
                            print(f"   Детали ошибки: {json.dumps(error_json, indent=2, ensure_ascii=False)}")
                        except:
                            pass
            except Exception as e:
                print(f"⚠️ Ошибка при запросе через Selenium: {e}")
        
        if USE_CLOUDSCRAPER:
            print("Используем cloudscraper для обхода Cloudflare...")
            scraper = cloudscraper.create_scraper()
            
            # Попробуем сначала получить главную страницу для получения cf_clearance
            print("Попытка получить cf_clearance cookie через главную страницу...")
            try:
                main_page = scraper.get("https://animegenius.live3d.io/", timeout=30)
                print(f"Главная страница: статус {main_page.status_code}")
                # Проверяем, есть ли cookie в сессии
                if hasattr(scraper, 'cookies'):
                    print(f"Cookies в сессии: {list(scraper.cookies.keys())}")
            except Exception as e:
                print(f"Не удалось получить главную страницу: {e}")
            
            # Добавляем cookie из сессии, если они есть
            if hasattr(scraper, 'cookies') and 'cf_clearance' in scraper.cookies:
                cookies['cf_clearance'] = scraper.cookies['cf_clearance']
                print(f"Используем автоматически полученный cf_clearance cookie")
            
            print(f"Отправка POST запроса с cookie: {list(cookies.keys())}")
            # Пробуем первый payload
            response = scraper.post(
                "https://api.live3d.io/api/v1/generation/generate",
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=30
            )
        else:
            print("Используем обычный requests...")
            response = requests.post(
                "https://api.live3d.io/api/v1/generation/generate",
                headers=headers,
                json=payload,
                timeout=30
            )
        
        print(f"Статус код: {response.status_code}")
        print(f"Заголовки ответа: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("\n✅ Успешный ответ:")
            try:
                result = response.json()
                print(json.dumps(result, indent=2, ensure_ascii=False))
            except:
                print(f"Ответ (текст): {response.text[:500]}")
        else:
            print(f"\n❌ Ошибка {response.status_code}:")
            print(response.text[:1000])
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_live3d_api()

