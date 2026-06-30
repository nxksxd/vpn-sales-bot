# Интеграция ЮKassa

## Обзор

Бот поддерживает два способа пополнения баланса:
1. **Telegram Stars** — встроенные платежи через Telegram (работает без дополнительной настройки)
2. **ЮKassa** — банковские карты, ЮMoney, SBP и другие способы оплаты

Если ЮKassa не настроена (`YOOKASSA_SHOP_ID` пусто), пользователям будет доступна только оплата Stars.

---

## Как получить Shop ID и Secret Key

1. Зарегистрируйтесь на [yookassa.ru](https://yookassa.ru)
2. Создайте магазин (или используйте тестовый)
3. Перейдите в **Настройки магазина** → **Ключи API**
4. Скопируйте **shopId** и **Секретный ключ**

Для тестового режима создайте тестовый магазин в разделе **Интеграция** → **Тестовый магазин**.

---

## Переменные окружения

Добавьте в `.env` на сервере:

```env
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET_KEY=test_XXXXXXXXXXXXXXXXXXXXXXXXX
YOOKASSA_RETURN_URL=https://t.me/portalkey_bot
YOOKASSA_WEBHOOK_PORT=8080
YOOKASSA_WEBHOOK_SECRET=long-random-secret-path
YOOKASSA_TRUST_X_FORWARDED_FOR=false
```

| Переменная | Описание | Обязательно |
|---|---|---|
| `YOOKASSA_SHOP_ID` | Идентификатор магазина (shopId) | Да |
| `YOOKASSA_SECRET_KEY` | Секретный ключ API | Да |
| `YOOKASSA_RETURN_URL` | URL возврата после оплаты | Нет (по умолчанию: `https://t.me/portalkey_bot`) |
| `YOOKASSA_WEBHOOK_PORT` | Порт для приёма webhook-уведомлений | Нет (по умолчанию: `8080`) |
| `YOOKASSA_WEBHOOK_SECRET` | Секретный суффикс webhook URL: `/yookassa/webhook/<secret>` | Рекомендуется |
| `YOOKASSA_TRUST_X_FORWARDED_FOR` | Доверять `X-Forwarded-For` только за собственным reverse proxy | Нет |

Чтобы безопасно записать секретный ключ в локальный `.env` без вывода в терминал:

```bash
python scripts/set_yookassa_secret.py
```

---

## Настройка Webhook в кабинете ЮKassa

ЮKassa отправляет уведомления о статусе платежа на ваш сервер. Настройте URL webhook:

1. Перейдите в [кабинет ЮKassa](https://yookassa.ru/my/shop-settings) → **Интеграция** → **HTTP-уведомления**
2. Укажите URL:
   - без secret path: `http://ВАШ_СЕРВЕР:8080/yookassa/webhook`
   - с `YOOKASSA_WEBHOOK_SECRET`: `http://ВАШ_СЕРВЕР:8080/yookassa/webhook/<secret>`
3. Выберите события: **payment.succeeded**, **payment.canceled**
4. Сохраните

**Важно:** Webhook URL должен быть доступен из интернета. Если используется reverse proxy (nginx), проксируйте порт 8080.

### Пример настройки nginx (если нужен HTTPS для webhook):

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /yookassa/webhook/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }
}
```

В этом случае URL webhook в кабинете ЮKassa: `https://your-domain.com/yookassa/webhook/<secret>`.
`X-Forwarded-For` по умолчанию не используется приложением; включайте `YOOKASSA_TRUST_X_FORWARDED_FOR=true` только если бот недоступен напрямую извне и весь внешний трафик проходит через ваш trusted proxy.

---

## Тестовый режим

1. В кабинете ЮKassa создайте **тестовый магазин**
2. Используйте тестовые ключи (начинаются с `test_`)
3. Для тестовой оплаты используйте карту: `1111 1111 1111 1026`, любой срок, любой CVC
4. Другие тестовые карты: [документация](https://yookassa.ru/developers/payment-acceptance/testing-and-going-live/testing)

---

## Как перейти в боевой режим

1. Завершите интеграцию в тестовом режиме
2. В кабинете ЮKassa перейдите в **Интеграция** → **Готово к проверке**
3. После проверки ЮKassa активирует боевой режим
4. Замените тестовые ключи на боевые в `.env`:
   ```env
   YOOKASSA_SHOP_ID=ваш_боевой_shop_id
   YOOKASSA_SECRET_KEY=live_XXXXXXXXXXXXXXXXXXXXXXXXX
   ```
5. Перезапустите бот: `docker compose up -d --build`

---

## Как протестировать оплату

1. Убедитесь что `.env` содержит `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и, желательно, `YOOKASSA_WEBHOOK_SECRET`
2. Перезапустите бот: `docker compose up -d --build`
3. В Telegram: нажмите **Пополнить баланс** → **Оплата через ЮKassa**
4. Выберите сумму → перейдите по ссылке оплаты
5. Оплатите тестовой картой `1111 1111 1111 1026`
6. Баланс пополнится автоматически (через webhook)

---

## Защита от двойного зачисления

Реализована на двух уровнях:
1. **`idempotency_key`** в таблице `transactions` — уникальный ключ `yookassa:{payment_id}` предотвращает дублирование на уровне БД
2. **Проверка статуса** в `payment_events` — если платёж уже в статусе `paid`, повторный webhook игнорируется

---

## Верификация webhook

Входящие webhook-запросы проверяются по IP-адресу отправителя. `X-Forwarded-For` игнорируется по умолчанию, чтобы нельзя было подделать источник запроса через raw header. Принимаются только запросы с [доверенных IP ЮKassa](https://yookassa.ru/developers/using-api/webhooks#ip):
- `185.71.76.0/27`
- `185.71.77.0/27`
- `77.75.153.0/25`
- `77.75.156.11`
- `77.75.156.35`
- `77.75.154.128/25`
- `2a02:5180::/32`

---

## Архитектура

```
Пользователь → "Пополнить баланс" → "Оплата через ЮKassa"
     │
     ▼
Бот создаёт платёж (YooKassa API) → сохраняет в payment_events (status=pending)
     │
     ▼
Пользователь получает ссылку → оплачивает на странице ЮKassa
     │
     ▼
ЮKassa → webhook POST /yookassa/webhook[/<secret>] → aiohttp сервер (порт 8080)
     │
     ▼
Проверка IP → парсинг notification → зачисление баланса → уведомление пользователю
```

---

## Что нужно сделать вручную после настройки

1. Добавить `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и `YOOKASSA_WEBHOOK_SECRET` в `.env` на сервере
2. Настроить webhook URL в кабинете ЮKassa с secret path
3. Открыть порт 8080 (или настроить nginx proxy)
4. Перезапустить бот: `cd ~/vpn-sales-bot && docker compose up -d --build`
