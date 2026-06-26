# Аудит VPN Sales Bot — проверка списка улучшений

Дата: 2026-06-26. Проверено, насколько заявленное в `Улучшения.md` («✅ Уже сделано») реально и корректно реализовано в коде. Метод: чтение кода + сверка с тестами, по каждому пункту вердикт с `file:line`.

Легенда: ✅ подтверждено · ⚠️ частично / с оговоркой · ❌ заявлено, но не соответствует / отсутствует.

---

## 🔴 Критические находки (требуют правки в первую очередь)

1. **Идемпотентность платежей по факту сломана.** Метод `get_by_idempotency_key()` вызывается в `bot/services/subscription.py:69`, `:202` и `bot/scheduler/tasks.py:314`, но в `TransactionRepository` (`bot/database/repositories/transaction.py`) он **не определён** — там есть только `charge_id_exists()`. → `AttributeError` в рантайме при покупке / продлении / автопродлении. Unique-констрейнты (`models.py:98-102`) и обработка `IntegrityError` (`payment.py:34-61`) на месте, но защита через предварительную проверку не работает.

2. **HTML-инъекция в сообщениях от админа.** `bot/handlers/admin/users.py:286` и broadcast (`bot/handlers/admin/broadcast.py:114` → `bot/services/notification.py:170`) отправляют пользовательский текст с `parse_mode="HTML"` без экранирования (`esc()`). Битые/вредоносные теги ломают доставку и позволяют спуфинг.

3. **VLESS-ключи хранятся в БД открытым текстом.** `bot/database/models.py:75` и `:125` (`vless_link`), `:124` (`email`) — без шифрования. При компрометации БД утекает весь аутентификационный материал VPN.

4. **enum/строка рассинхрон в статусах подписки.** `bot/database/repositories/subscription.py:155,163` сравнивают `Subscription.status == "active"` (строка), а остальной код — `SubscriptionStatus.ACTIVE`. Тихие баги при рефакторинге enum.

5. **Нет каскадов удаления.** Все `ForeignKey` в `models.py` без `ondelete` → orphan-записи (Subscription/Transaction/VpnKey/AuditLog) при удалении пользователя.

---

## 1. Надёжность и продакшен

| Пункт | Вердикт | Где / комментарий |
|---|---|---|
| PostgreSQL по умолчанию | ✅ | `config.py:21` — дефолт `postgresql+asyncpg://...` |
| Healthchecks БД и контейнера | ✅ | `docker-compose.yml:16-20` (`pg_isready`), `:36-41` (`scripts/healthcheck.py` → `init_db()`) |
| Idempotency платежей | ❌ | Констрейнты + `IntegrityError` есть (`models.py:98-102`, `payment.py:34-61`), но `get_by_idempotency_key()` не определён в репозитории → рантайм-ошибка. См. критическую находку №1 |
| Retry/backoff 3x-ui | ✅ | `xui_client.py:22-23` (3 попытки, backoff 5с), цикл `:141-216` |
| Graceful recovery при недоступности 3x-ui | ⚠️ | Есть периодическая ресинхронизация `scheduler/tasks.py:186-233` (`sync_with_xui`, ping + алерт). Очереди отложенных операций нет — при ошибке просто `raise` (`subscription.py:102-104`) |
| Typed settings validation обязательных env | ⚠️ | pydantic-settings используется, но все критичные поля с дефолтами (`bot_token=""`, `xui_password=""`); проверка ручная в `main.py:139-141`, а не через `Field(...)`/валидатор |

---

## 2. Безопасность

| Пункт | Вердикт | Где / комментарий |
|---|---|---|
| Секреты только через env | ✅ | `config.py:15-26,62` (pydantic-settings, `env_file`), `.env.example` — только плейсхолдеры. Хардкод-секретов не найдено |
| Ограничение админ-действий + audit log | ⚠️ | `@admin_only` (`middlewares/admin_check.py:11-31`) + `AuditLogService` работают, но **не логируются 4 действия**: extend (`admin/settings.py:428`), cancel (`:487`), сообщение юзеру (`admin/users.py:270`), broadcast (`admin/broadcast.py:71`) |
| Валидация ввода | ✅ | `utils/validators.py:6-43` (topup/telegram_id/balance/days), применяется в `balance.py:54,64`, `admin/users.py:191` |
| Rate limit / антиспам | ✅ | `middlewares/throttling.py:15-71` (30/мин + cooldown 60с), подключён в `main.py:65-68` |
| Шифрование чувствительных данных | ❌ | `models.py:75,125` (`vless_link`), `:124` (`email`) — открытым текстом. См. критическую находку №3 |
| Auth / бан-чек | ✅ | `middlewares/auth.py:14-46` (`BanCheckMiddleware`, `is_banned`), срабатывает до хендлеров, обхода нет |

**Доп. дыра:** HTML-инъекция в `admin/users.py:286` и broadcast (`notification.py:170`) — см. критическую находку №2.

---

## 3. Платежи и биллинг

| Пункт | Вердикт | Где / комментарий |
|---|---|---|
| Денежная модель разделена (rub/stars/rate) | ✅ | `models.py:95-97` (`amount_rub`, `amount_stars`, `rate_snapshot`); конвертация `payment.py:30`, баланс в рублях, смешения нет |
| Отдельная таблица PaymentEvent + статусы | ✅ | `models.py:166-181`, enum `domain_enums.py:24-28` (PENDING/PAID/FAILED/REFUNDED) |
| Промокоды как сущность | ✅ | `models.py:152-163`, `price_with_promo()` (`config.py:110-121`), `increment_usage()` (`promo_code.py:29-36`), тесты `test_promo_codes.py`, `test_promo_usage.py` |
| История статусов (pending→paid/failed/refunded) | ⚠️ | PENDING→PAID/FAILED реализованы (`handlers/payments.py:112-131`), но статус `REFUNDED` нигде не выставляется |
| Возвраты / ручные корректировки | ⚠️ | `process_refund()` (`payment.py:72-97`) и admin-корректировка (`admin/users.py:200-213`) меняют баланс, но **не обновляют `PaymentEvent.status` на REFUNDED** — нет связи платежа с возвратом |
| Реферальные уровни | ❌ | Только фикс. бонус: `config.py:41` (`referral_bonus_rub=20`), `referral.py:37-62` (`count * bonus`), уровней/tiers нет |

---

## 4. Подписки и VPN-логика

| Пункт | Вердикт | Где / комментарий |
|---|---|---|
| State-machine подписки | ✅ | `subscription.py:24-32` (`ALLOWED_TRANSITIONS`, 7 статусов) + `_ensure_transition()` `:42-46`; тест `test_subscription_state_machine.py` |
| Trial + защита от повтора | ✅ | `models.py:38` (`trial_used`), `:74` (`is_trial`); проверка `subscriptions.py:123`, выставление `:131` |
| Мультисерверность / регионы | ✅ | `models.py:138-150` (`ServerRegion`), `repositories/server_region.py`, выбор `subscriptions.py:36-51`; тест `test_server_regions.py` |
| Балансировка по стране/загрузке/тарифу | ❌ | Только ручной выбор региона, авто-балансировки нет |
| Ротация / перевыпуск ключей | ✅ | `xui_client.py:352-386` (`regenerate_client`), аудит `admin/keys.py:88` (`KEY_REGENERATED`) |
| Контроль трафика | ✅ | `models.py:76` (`traffic_limit_gb`), `config.py:39,54`, передача `totalGB` `subscription.py:79` |
| Ограничение по устройствам | ❌ | `limitIp: 0` захардкожен (`subscription.py:93`), настройки/поля device_limit нет |

---

## 5. Архитектура, БД, наблюдаемость

| Пункт | Вердикт | Где / комментарий |
|---|---|---|
| Use-cases слой | ⚠️ | `subscription_use_cases.py`, `admin_use_cases.py` есть, но хендлеры всё равно дёргают репозитории напрямую (`subscriptions.py:181-182,215-216`); инкапсуляция неполная |
| Typed enums вместо строк | ❌ | `domain_enums.py` используется, но рассинхрон `repositories/subscription.py:155,163` (`== "active"`). См. критическую находку №4 |
| Audit log | ✅ | `models.py:183-193`, `services/audit_log.py`, просмотр `admin/audit.py` (с пагинацией) |
| Индексы / уникальности | ✅ | index на `telegram_id`, `expires_at`, FK-полях; unique на `telegram_id`, `referral_code`, `xui_client_id`, `idempotency_key`, `charge_id`, `code` |
| Каскады удаления (ondelete) | ❌ | Ни один FK не имеет `ondelete`. См. критическую находку №5 |
| Soft delete | ❌ | Полей `is_deleted`/`deleted_at` нет — удаления физические |
| Структурные логи | ✅ | `utils/observability.py` (`log_event`), loguru |
| Алерты админу | ✅ | `services/ops_alerts.py` (`alert_admin`) — на критических ошибках (payment, 3x-ui, trial) |
| Метрики / Sentry | ❌ | Нет Prometheus/StatsD/Sentry — только логи |

---

## 6. Админка, UX, тесты, DevEx

| Пункт | Вердикт | Где / комментарий |
|---|---|---|
| Сегментированные рассылки | ✅ | `admin/broadcast.py` + `repositories/user.py:162-189` — all/active/expiring/new/trial_unused/inactive, поддержка `lang:*` |
| Аналитика | ⚠️ | `admin/stats.py` — юзеры, активные подписки, доход за период. Нет MRR/churn/LTV/retention/когорт |
| Онбординг | ✅ | `start.py:85-91` (`onboarding_completed`), инструкция при первом `/start` |
| Мастер подключения по платформам | ✅ | `keyboards/user_kb.py` (Android/iOS/Windows/macOS/Linux) + реальные гайды в `support.py` (`GUIDE_TEXTS`) |
| Мультиязычность (i18n) | ❌ | Только поле `language_code` (`models.py:32`); тексты захардкожены на русском, gettext/fluent/.po нет |
| Тесты | ✅ | 8 файлов (pricing, idempotency, promo×2, state-machine, use-cases, regions, payment-events); `pytest` + `pytest-asyncio` в requirements. `conftest.py` отсутствует |
| Makefile / pre-commit / CI | ✅ | Makefile (install/test/lint/typecheck/migrate); pre-commit (ruff + mypy); CI `.github/workflows/ci.yml` (compile/ruff/mypy/pytest/migrations/docker build) |

---

## Сводка по статусам

**❌ Заявлено как «сделано», но не соответствует / ломает рантайм (6):**
Idempotency (`get_by_idempotency_key` отсутствует), Typed enums (рассинхрон со строками).

**❌ Из общего списка улучшений не реализовано (8):**
Реферальные уровни, авто-балансировка серверов, ограничение по устройствам, шифрование в БД, каскады удаления, soft delete, метрики/Sentry, i18n.

**⚠️ Частично / с оговорками (7):**
Graceful recovery (нет очереди), validation env (ручная), audit-логирование (пропущены 4 действия), история статусов/возвраты (нет REFUNDED), use-cases (неполная инкапсуляция), аналитика (базовая).

**✅ Подтверждено полностью (~20):**
PostgreSQL, healthchecks, retry/backoff, секреты через env, валидация ввода, rate limit, auth/бан, денежная модель, PaymentEvent, промокоды, state-machine, trial, регионы, ротация ключей, контроль трафика, audit log, индексы/уникальности, структурные логи, алерты, рассылки, онбординг, мастер подключения, тесты, Makefile/pre-commit/CI.

## Рекомендуемый порядок исправлений
1. Добавить `TransactionRepository.get_by_idempotency_key()` (критично — ломает покупку/продление).
2. Экранировать пользовательский текст (`esc()`) в сообщениях админа и broadcast.
3. Зашифровать `vless_link`/`email` в БД (например, Fernet на уровне приложения).
4. Привести `subscription.py:155,163` к `SubscriptionStatus.ACTIVE`.
5. Добавить `ondelete` на FK + рассмотреть soft delete.
6. Дологировать 4 админ-действия в audit log.
7. Дальше — наблюдаемость (Sentry/метрики), i18n, рефералные уровни, авто-балансировка.

---

## Внесённые исправления (2026-06-26)

Закрыты критические находки №1, №2, №4, №5 и пропуски audit-логирования:

- **№1 idempotency** — добавлен `TransactionRepository.get_by_idempotency_key()` (`transaction.py`). Покупка/продление/автопродление больше не падают с `AttributeError`. Тесты 10/10 зелёные.
- **№2 HTML-инъекция** — экранирование `esc()` для сообщения админа (`admin/users.py:286`) и текста рассылки (`admin/broadcast.py`, + импорт `esc`).
- **№4 enum/строка** — `subscription.py:155,163` переведены на `SubscriptionStatus.ACTIVE`.
- **№5 каскады** — `ondelete="CASCADE"` на FK (subscriptions/transactions/vpn_keys/payment_events/notifications.user_id, vpn_keys.subscription_id), `SET NULL` на notifications.subscription_id; модели + миграция `0006_fk_ondelete_cascades.py` (Postgres; на SQLite no-op).
- **Audit-логирование** — добавлены действия `SUBSCRIPTION_EXTENDED`, `SUBSCRIPTION_CANCELLED`, `BROADCAST_SENT` (+ использование `USER_MESSAGE_SENT`) в `domain_enums.py` и логирование в соответствующих хендлерах (`admin/settings.py`, `admin/users.py`, `admin/broadcast.py`).
- **№3 шифрование `vless_link`/`email`** — прозрачное шифрование Fernet через SQLAlchemy `TypeDecorator` (`bot/utils/crypto.py`, `EncryptedString`), применено к `Subscription.vless_link`, `VpnKey.vless_link`, `VpnKey.email` — без правок в репозиториях/хендлерах (шифрование на write, дешифрование на read). Ключ `ENCRYPTION_KEY` в config/.env (Fernet). Обратная совместимость: без ключа — passthrough; legacy-plaintext читается как есть и перешифровывается при следующей записи. Зависимость `cryptography`, миграция `0007` (email → TEXT на Postgres), тесты `test_encryption.py` (round-trip, legacy-fallback, шифртекст в БД).

**Осталось (требует отдельного решения):**
- Из общего списка: метрики/Sentry, i18n, реферальные уровни, авто-балансировка, soft delete, лимит устройств, REFUNDED-переход.

Проверки после правок: `py_compile` всех изменённых файлов — OK; `ruff` на новых файлах (`crypto.py`, миграции `0006`/`0007`, `test_encryption.py`) — clean; `pytest` — 14 passed.

> Важно: задеплоить с заданным `ENCRYPTION_KEY` ДО появления реальных данных. Ключ нельзя терять/менять — иначе ранее зашифрованные `vless_link`/`email` станут нечитаемыми (расшифровка вернёт шифртекст как «legacy plaintext»). Хранить ключ в secret manager, не в репозитории.






