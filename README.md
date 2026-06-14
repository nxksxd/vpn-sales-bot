# VPN Sales Bot

Полностью автоматизированный Telegram-бот для продажи VPN-подписок через Telegram Stars с интеграцией 3x-ui панели.

## Возможности

### Для пользователей
- **Регистрация** — автоматическая при первом /start
- **Пополнение баланса** — через Telegram Stars (100, 250, 500, 1000 ⭐ или произвольная сумма)
- **Покупка подписки** — 1/3/6/12 месяцев со скидками
- **Просмотр ключа VLESS** — текстовая ссылка + QR-код
- **Продление подписки** — автоматическое продление в 3x-ui
- **Реферальная программа** — бонусы за приглашённых пользователей
- **Инструкции по подключению** — для Android, iOS, Windows, macOS, Linux

### Для администратора
- **Полный CRUD** по пользователям (поиск, просмотр карточки, баланс)
- **Управление ключами** — пересоздание, деактивация, активация, сброс трафика
- **Управление подписками** — продление, отмена, изменение даты
- **Статистика** — пользователи, подписки, доход по периодам
- **Рассылки** — всем, активным подписчикам, с истекающей подпиской
- **Изменение баланса** — пополнение/списание Stars
- **Бан/разбан** пользователей
- **Отправка сообщений** пользователям
- **Статус сервера** — ping до 3x-ui, количество онлайн клиентов

### Автоматизация
- **Напоминания** о продлении (за 3 дня и 1 день)
- **Деактивация** истёкших подписок (каждые 15 минут)
- **Синхронизация** с 3x-ui (каждые 6 часов)
- **Ежедневный отчёт** администратору (09:00 UTC)

## Стек технологий

| Компонент | Технология |
|-----------|------------|
| Bot Framework | aiogram 3.x |
| HTTP Client | aiohttp |
| ORM | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| Scheduler | APScheduler |
| Config | Pydantic Settings |
| QR | qrcode + Pillow |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Logging | Loguru |

## Быстрый старт

### 1. Клонирование

```bash
git clone https://github.com/anten-ka/goVLESS.git
cd goVLESS/vpn_bot
```

### 2. Установка зависимостей

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Конфигурация

```bash
cp .env.example .env
nano .env  # заполните BOT_TOKEN, ADMIN_TELEGRAM_ID, XUI_* параметры
```

### 4. Запуск

```bash
python -m bot.main
```

### Docker

```bash
cp .env.example .env
# Заполните .env
docker-compose up -d
```

## Структура проекта

```
vpn_bot/
├── bot/
│   ├── main.py                 # Точка входа
│   ├── config.py               # Настройки (Pydantic Settings)
│   ├── handlers/
│   │   ├── start.py            # /start, главное меню
│   │   ├── profile.py          # Профиль пользователя
│   │   ├── balance.py          # Пополнение баланса
│   │   ├── payments.py         # Обработка Stars платежей
│   │   ├── subscriptions.py    # Покупка/просмотр подписок
│   │   ├── keys.py             # Управление ключами + QR
│   │   ├── referral.py         # Реферальная система
│   │   ├── support.py          # Поддержка + инструкции
│   │   └── admin/
│   │       ├── main.py         # Админ-меню
│   │       ├── users.py        # CRUD пользователей
│   │       ├── keys.py         # Управление ключами
│   │       ├── stats.py        # Статистика
│   │       ├── broadcast.py    # Рассылки
│   │       └── settings.py     # Настройки + статус сервера
│   ├── keyboards/
│   │   ├── user_kb.py          # Клавиатуры пользователя
│   │   └── admin_kb.py         # Клавиатуры админа
│   ├── middlewares/
│   │   ├── auth.py             # Проверка бана
│   │   ├── throttling.py       # Rate limiting
│   │   └── admin_check.py      # Проверка админа
│   ├── services/
│   │   ├── xui_client.py       # 3x-ui API клиент
│   │   ├── subscription.py     # Логика подписок
│   │   ├── payment.py          # Логика платежей
│   │   ├── notification.py     # Уведомления
│   │   ├── qr_generator.py     # QR-коды
│   │   └── referral.py         # Реферальная логика
│   ├── database/
│   │   ├── models.py           # SQLAlchemy модели
│   │   ├── session.py          # Сессии БД
│   │   └── repositories/       # CRUD операции
│   ├── scheduler/
│   │   └── tasks.py            # Фоновые задачи
│   └── utils/
│       ├── formatters.py       # Форматирование
│       └── validators.py       # Валидация
├── migrations/                  # Alembic
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## База данных

### Таблицы

- **users** — пользователи (telegram_id, balance, referral_code, is_banned)
- **subscriptions** — подписки (plan_type, status, expires_at, xui_client_id)
- **transactions** — все финансовые операции (topup, purchase, refund, admin_adjustment)
- **vpn_keys** — ключи VPN (xui_client_id, vless_link, is_active)
- **notifications** — отправленные уведомления

## Безопасность

- ✅ Проверка `ADMIN_TELEGRAM_ID` во всех admin-хендлерах через middleware
- ✅ Rate limiting — 30 запросов/минуту на пользователя
- ✅ Валидация входных данных через Pydantic + validators
- ✅ Логирование всех admin-действий
- ✅ Защита от двойного зачисления (уникальный `charge_id`)
- ✅ Верификация платежа через `telegram_payment_charge_id`
- ✅ Atomic транзакции (списание + создание ключа)

## Конфигурация (.env)

Все параметры описаны в `.env.example`.

Ключевые:
- `BOT_TOKEN` — токен бота от @BotFather
- `ADMIN_TELEGRAM_ID` — ваш Telegram ID
- `XUI_URL` / `XUI_USERNAME` / `XUI_PASSWORD` — доступ к 3x-ui панели
- `PLAN_*_STARS` — цены тарифов в Stars
- `SERVER_ADDRESS` — IP/домен сервера для VLESS ссылок
