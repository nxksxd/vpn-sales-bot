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

При старте контейнер автоматически применяет `alembic upgrade head`, затем запускает бота.

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

Цены задаются в `.env` файле в рублях, а стоимость в Telegram Stars рассчитывается по курсу `STARS_TO_RUB_RATE`:

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `PLAN_1M_RUB` | 200 | 1 месяц |
| `PLAN_3M_RUB` | 500 | 3 месяца |
| `PLAN_6M_RUB` | 900 | 6 месяцев |
| `PLAN_12M_RUB` | 1600 | 12 месяцев |
| `STARS_TO_RUB_RATE` | 2.0 | Курс Stars → рубли |
| `TRAFFIC_LIMIT_GB` | 0 | Лимит трафика (0 = безлимит) |
| `REFERRAL_BONUS_RUB` | 20 | Бонус за реферала |

Настройки 3x-ui можно менять прямо из Telegram: `/admin` → Настройки.

---

## Тесты

Быстрая проверка Python-кода:

```bash
python3 -m compileall bot scripts
pytest
```

---

## Перенос данных со старой SQLite базы

Если у вас уже есть старая база `vpn_bot.db`, сначала поднимите PostgreSQL и примените миграции:

```bash
docker compose up -d --build
```

Затем выполните перенос данных в пустую PostgreSQL базу:

```bash
python3 scripts/migrate_sqlite_to_postgres.py /path/to/vpn_bot.db
```

Скрипт перенесёт таблицы `users`, `subscriptions`, `transactions`, `vpn_keys`, `notifications` и обновит sequence для автоинкрементных ID.

Важно:
- целевая PostgreSQL база должна быть пустой;
- `DATABASE_URL` должен указывать на PostgreSQL;
- перед переносом желательно сделать backup старой базы.

---

## Резервные копии PostgreSQL

Создать backup вручную:

```bash
bash scripts/backup_postgres.sh
```

По умолчанию backup будет сохранён в `./backups`. При необходимости можно переопределить переменные окружения:

```bash
BACKUP_DIR=./backups POSTGRES_CONTAINER=vpn-bot-db POSTGRES_DB=vpn_bot POSTGRES_USER=vpn_bot bash scripts/backup_postgres.sh
```

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

aiogram 3 · SQLAlchemy 2 (async) · APScheduler · aiohttp · Pydantic Settings · PostgreSQL (production default) / SQLite (local dev) · Docker
