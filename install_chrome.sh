#!/bin/bash
# Скрипт для установки Google Chrome на Ubuntu сервере

set -e

echo "=========================================="
echo "Установка Google Chrome для headless режима"
echo "=========================================="

# Проверяем, что мы на Ubuntu/Debian
if ! command -v apt &> /dev/null; then
    echo "❌ Ошибка: Этот скрипт предназначен для Ubuntu/Debian"
    exit 1
fi

# Обновляем пакеты
echo "📦 Обновление списка пакетов..."
sudo apt update

# Устанавливаем зависимости
echo "📦 Установка зависимостей..."
sudo apt install -y wget gnupg ca-certificates

# Добавляем ключ Google
echo "🔑 Добавление ключа Google..."
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg

# Добавляем репозиторий Google Chrome
echo "📝 Добавление репозитория Google Chrome..."
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list > /dev/null

# Обновляем список пакетов
echo "🔄 Обновление списка пакетов после добавления репозитория..."
sudo apt update

# Устанавливаем Chrome
echo "⬇️ Установка Google Chrome..."
sudo apt install -y google-chrome-stable

# Проверяем установку
if command -v google-chrome &> /dev/null; then
    CHROME_VERSION=$(google-chrome --version)
    echo "✅ Google Chrome успешно установлен!"
    echo "   Версия: $CHROME_VERSION"
else
    echo "❌ Ошибка: Google Chrome не установлен"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Установка завершена!"
echo "=========================================="
echo ""
echo "Следующие шаги:"
echo "1. Установите ChromeDriver (опционально, если используете webdriver-manager):"
echo "   pip install webdriver-manager"
echo ""
echo "2. Или установите ChromeDriver вручную:"
echo "   См. инструкции в UBUNTU_SERVER_SETUP.md"
echo ""
echo "3. Проверьте работу:"
echo "   python -c \"from selenium import webdriver; from selenium.webdriver.chrome.options import Options; opts = Options(); opts.add_argument('--headless=new'); driver = webdriver.Chrome(options=opts); print('✅ Работает!')\""

