# 🤖 Telegram Admin Bot

Умный Telegram-бот для администрирования чатов, работы с пользователями, рейтингами и статистикой. Поддерживает локализацию, логирование и гибкие настройки.

---

## 🚀 Возможности

- 👤 Автоматическое сохранение пользователей
- 💬 Учёт чатов и каналов
- 🏆 Рейтинг активности пользователей
- ⚙️ Админ-функции (по ID)
- 🌐 Локализация: русский и английский языки
- 📦 JSON-хранилище (`data.json`)
- 📁 Лог-файл (`bot.log`)

---

## 📦 Установка

1. Склонируйте проект:

git clone https://github.com/your_username/telegram-admin-bot.git
cd telegram-admin-bot

3. Установите зависимости:

pip install pyTelegramBotAPI

4. Создайте файл .env или пропишите токен прямо в коде:

BOT_TOKEN=ВАШ_ТОКЕН
SUPER_ADMIN_ID=ВАШ_ID

- По умолчанию токен задаётся прямо в main.py в строке:
bot = telebot.TeleBot('ВАШ_ТОКЕН')

## ▶️ Запуск

python main.py

## 📂 Структура

├── main.py            # Основной код бота   


├── data.json          # Хранилище пользователей, чатов и каналов 


├── bot.log            # Логирование событий   


├── README.md          # Документация проекта    


## 🏅 Рейтинг пользователей
- Формула:
рейтинг = сообщения + (реакции * 2)
- Награды по рейтингу:

🥉 до 100

🥈 до 500

🥇 до 1000

🏆 свыше 1000

## 🌍 Локализация
Поддерживаются 2 языка:

- 🇷🇺 Русский

- 🇬🇧 English

Переключение языка — через меню бота.

## 👨‍💻 Автор
Иван

inst: @chll_killer
