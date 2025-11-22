# Настройка для работы на Ubuntu сервере без GUI

## Проблема

На сервере Ubuntu без GUI режима Selenium не может запустить браузер для генерации изображений через Live3D API.

## Решение

Настроен headless режим для Selenium, который работает без GUI.

## Установка зависимостей

### 1. Установка Chrome/Chromium для headless режима

#### Вариант A: Установка Google Chrome (рекомендуется)

```bash
# Обновляем пакеты
sudo apt update

# Устанавливаем зависимости
sudo apt install -y wget gnupg

# Добавляем ключ Google
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg

# Добавляем репозиторий Google Chrome
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Обновляем список пакетов
sudo apt update

# Устанавливаем Chrome
sudo apt install -y google-chrome-stable
```

#### Вариант B: Установка Chromium (проще, но может быть менее стабильным)

```bash
# Обновляем пакеты
sudo apt update

# Устанавливаем Chromium и ChromeDriver
sudo apt install -y chromium-browser chromium-chromedriver

# Создаем симлинк для chromedriver (если нужно)
sudo ln -s /usr/lib/chromium-browser/chromedriver /usr/local/bin/chromedriver
```

#### Вариант C: Использование только cloudscraper (НЕ требует браузер!)

Если не хотите устанавливать браузер, можно использовать только `cloudscraper`, который не требует GUI:

```bash
# Устанавливаем cloudscraper
pip install cloudscraper

# В .env файле убедитесь, что USE_LIVE3D=true
# Код автоматически будет использовать cloudscraper вместо Selenium
```

**Рекомендация:** Начните с варианта C (cloudscraper), так как он не требует установки браузера и работает быстрее.

### 2. Установка ChromeDriver

```bash
# Устанавливаем ChromeDriver через webdriver-manager (автоматически)
# Или вручную:

# Определяем версию Chrome
CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)

# Скачиваем соответствующий ChromeDriver
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION%.*}")
wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip"
unzip /tmp/chromedriver.zip -d /tmp
sudo mv /tmp/chromedriver /usr/local/bin/chromedriver
sudo chmod +x /usr/local/bin/chromedriver
```

### 3. Установка Python зависимостей

```bash
# Убедитесь, что установлены все зависимости из requirements.txt
pip install -r requirements.txt

# Если webdriver-manager не установлен, установите его
pip install webdriver-manager
```

### 4. Установка виртуального дисплея (опционально, если headless не работает)

Если headless режим все еще не работает, можно использовать виртуальный дисплей Xvfb:

```bash
# Устанавливаем Xvfb
sudo apt install -y xvfb

# Запускаем виртуальный дисплей (в фоне)
Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
export DISPLAY=:99

# Или добавьте в ~/.bashrc для постоянной работы:
echo 'export DISPLAY=:99' >> ~/.bashrc
```

## Проверка установки

### Проверка Chrome

```bash
google-chrome --version
# Должно вывести версию Chrome
```

### Проверка ChromeDriver

```bash
chromedriver --version
# Должно вывести версию ChromeDriver
```

### Тест headless режима

```bash
python -c "
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)
driver.get('https://www.google.com')
print('✅ Headless Chrome работает!')
print(f'Заголовок страницы: {driver.title}')
driver.quit()
"
```

## Настройки в коде

Код уже настроен для работы в headless режиме:

- `--headless=new` - новый headless режим Chrome
- `--no-sandbox` - необходимо для работы на сервере
- `--disable-dev-shm-usage` - избегает проблем с /dev/shm
- `--disable-gpu` - отключает GPU в headless режиме
- `--window-size=1920,1080` - устанавливает размер окна

## Альтернативные решения

### 1. Использование cloudscraper (приоритет)

Если Selenium не работает, код автоматически переключится на `cloudscraper`, который не требует GUI:

```bash
pip install cloudscraper
```

### 2. Использование Replicate API

Можно использовать Replicate API вместо Live3D:

```env
USE_REPLICATE=true
USE_LIVE3D=false
REPLICATE_API_TOKEN=your_token_here
```

### 3. Использование локального API

Если у вас есть локальный API для генерации изображений:

```env
USE_REPLICATE=false
USE_LIVE3D=false
IMAGE_API_URL=http://localhost:8000
```

## Troubleshooting

### Ошибка: "ChromeDriver executable needs to be in PATH"

**Решение:**
```bash
# Убедитесь, что ChromeDriver установлен и доступен
which chromedriver
# Если не найден, добавьте в PATH или установите через webdriver-manager
```

### Ошибка: "DevToolsActivePort file doesn't exist"

**Решение:**
Добавьте в код (уже добавлено):
```python
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
```

### Ошибка: "SessionNotCreatedException"

**Решение:**
Убедитесь, что версия ChromeDriver соответствует версии Chrome:
```bash
# Проверьте версии
google-chrome --version
chromedriver --version
```

### Ошибка: Cloudflare блокирует запросы

**Решение:**
1. Убедитесь, что используется headless режим с правильными опциями
2. Попробуйте использовать cloudscraper вместо Selenium
3. Проверьте, что токен Live3D API действителен

## Проверка работы

После установки всех зависимостей запустите бота:

```bash
python main.py
```

И воркер:

```bash
python worker.py
```

Проверьте логи - должны быть сообщения:
- "Selenium доступен, будет использован для получения cookies"
- "Использование Selenium для выполнения запроса..."
- "Генерация изображения через Live3D..."

## Рекомендации

1. **Используйте cloudscraper как основной метод** - он не требует GUI и работает быстрее
2. **Selenium как резервный вариант** - если cloudscraper не справляется с Cloudflare
3. **Мониторинг ресурсов** - headless Chrome все еще потребляет память, следите за использованием

## Дополнительные настройки для production

### Ограничение ресурсов для Chrome

Можно ограничить использование памяти Chrome:

```python
chrome_options.add_argument("--memory-pressure-off")
chrome_options.add_argument("--max_old_space_size=512")  # Ограничение памяти в MB
```

### Использование systemd для виртуального дисплея

Создайте сервис для Xvfb:

```bash
sudo nano /etc/systemd/system/xvfb.service
```

```ini
[Unit]
Description=Virtual Framebuffer X Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/Xvfb :99 -screen 0 1024x768x24
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable xvfb
sudo systemctl start xvfb
```

