# Портальный ключ — @portalkey_bot

Telegram-бот для продажи подписок через Telegram Stars с интеграцией 3x-ui панели.

## Возможности

### Пользователь
- Пополнение баланса через Telegram Stars
- Покупка подписки (1 / 3 / 6 / 12 месяцев)
- Получение VLESS-ключа (ссылка + QR-код)
- Автопродление и напоминания
- Реферальная программа
- Инструкции подключения (Android, iOS, Windows, macOS, Linux)

### Администратор
- Управление пользователями, ключами и подписками
- Статистика и рассылки
- Изменение настроек 3x-ui прямо из Telegram
- Статус сервера

### Автоматизация
- Напоминания о продлении (за 3 и 1 день)
- Деактивация истёкших подписок (каждые 15 мин)
- Синхронизация с 3x-ui (каждые 6 часов)
- Ежедневный отчёт администратору

---

## Установка на VPS

### Требования

- VPS с Ubuntu 20.04+ (или Debian 11+)
- Docker и Docker Compose
- Установленная панель 3x-ui с настроенным VLESS inbound
- Telegram-бот (создать через [@BotFather](https://t.me/BotFather))

### 1. Установка Docker (если ещё не установлен)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Перезайдите в SSH-сессию после этого
```

### 2. Клонирование репозитория

```bash
git clone https://github.com/nxksxd/vpn-sales-bot.git
cd vpn-sales-bot
```

### 3. Автоматическая настройка (рекомендуется)

```bash
bash setup.sh
```

Скрипт спросит все параметры, создаст `.env` и запустит бота.

### 4. Ручная настройка (альтернативно)

```bash
cp .env.example .env
nano .env
```

Заполните обязательные поля:

| Параметр | Описание | Пример |
|----------|----------|--------|
| `BOT_TOKEN` | Токен от @BotFather | `123456:ABC...` |
| `ADMIN_TELEGRAM_ID` | Ваш Telegram ID (узнать: [@userinfobot](https://t.me/userinfobot)) | `448795617` |
| `XUI_URL` | Адрес панели 3x-ui | `https://your-server:2053` |
| `XUI_USERNAME` | Логин от панели | `admin` |
| `XUI_PASSWORD` | Пароль от панели | `your_password` |
| `XUI_INBOUND_ID` | ID inbound (см. в панели → Inbounds) | `1` |
| `SERVER_ADDRESS` | IP или домен сервера | `your-server.com` |

Затем запустите:

```bash
docker compose up -d --build
```

---

## Управление ботом

```bash
# Логи (в реальном времени)
docker compose logs -f vpn-bot

# Перезапуск
docker compose restart

# Остановка
docker compose down

# Обновление
git pull
docker compose up -d --build
```

## Автозапуск после перезагрузки сервера

Docker автоматически запускает контейнер при перезагрузке сервера благодаря `restart: always` в `docker-compose.yml`.

Убедитесь, что Docker сам запускается при загрузке:

```bash
sudo systemctl enable docker
```

---

## Настройки тарифов

Цены задаются в `.env` файле (в Telegram Stars):

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `PLAN_1M_STARS` | 100 | 1 месяц |
| `PLAN_3M_STARS` | 250 | 3 месяца |
| `PLAN_6M_STARS` | 450 | 6 месяцев |
| `PLAN_12M_STARS` | 800 | 12 месяцев |
| `TRAFFIC_LIMIT_GB` | 0 | Лимит трафика (0 = безлимит) |
| `REFERRAL_BONUS_STARS` | 10 | Бонус за реферала |

Настройки 3x-ui можно менять прямо из Telegram: `/admin` → Настройки.

---

## Структура проекта

```
├── bot/
│   ├── main.py              # Точка входа
│   ├── config.py            # Настройки (Pydantic Settings)
│   ├── handlers/            # Обработчики команд
│   │   ├── start.py         # /start, главное меню
│   │   ├── balance.py       # Пополнение баланса
│   │   ├── payments.py      # Обработка Stars-платежей
│   │   ├── subscriptions.py # Подписки
│   │   ├── keys.py          # Ключи VLESS + QR
│   │   └── admin/           # Админ-панель
│   ├── services/            # Бизнес-логика
│   │   ├── xui_client.py    # 3x-ui API клиент
│   │   └── subscription.py  # Логика подписок
│   ├── database/            # ORM-модели и CRUD
│   └── scheduler/           # Фоновые задачи
├── setup.sh                 # Интерактивная установка
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Стек

aiogram 3 · SQLAlchemy 2 (async) · APScheduler · aiohttp · Pydantic Settings · SQLite/PostgreSQL · Docker
