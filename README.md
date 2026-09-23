# Rumis Academy — Telegram-бот Mock Test

Бот записи на Main Test / Mock Test Speaking (online) по ТЗ Приложения №1 договора NST-001/2026.

## Стек

- Python 3.11+
- aiogram 3
- PostgreSQL + SQLAlchemy async
- APScheduler (пост-экзамен через 2ч 50м)
- openpyxl (выгрузка Excel)
- опционально: Google Sheets (Students / Results / Session Log)

## Быстрый старт

### 1. База данных

По умолчанию в `.env.example` — **SQLite** (`rumis_bot.db`), удобно для локальной разработки.

Для боя — PostgreSQL:

```bash
docker compose up -d
```

И в `.env`:

```
DATABASE_URL=postgresql+asyncpg://rumis:rumis@localhost:5432/rumis_bot
```

### 2. Окружение

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Заполните `.env`:

- `BOT_TOKEN` — токен от @BotFather
- `ADMIN_IDS` — ваш Telegram user id (через запятую)
- реквизиты, адрес, канал — можно позже

Узнать свой id: напишите [@userinfobot](https://t.me/userinfobot).

### 3. Таблицы

При старте бот создаёт таблицы сам. Опционально:

```bash
alembic upgrade head
```

### 4. Запуск

```bash
python -m app.bot
```

## Сценарий ученика

1. `/start` → язык → «Поделиться контактом» (**без ФИО**)
2. Записаться → ФИО латиницей + ДР → дата → слот → подтверждение **без цены**
3. Админ назначает 75k / 150k → оплата → «Я оплатил»
4. Админ: Оплачено → слот в лимите даты
5. Через **2ч 50м** после слота — 2 сообщения (Speaking + канал), либо вручную из админки

## Админ-панель

Кнопка «Админ-панель» (только админы из БД / `ADMIN_IDS`):

- даты Main Test + лимит (по умолчанию 10)
- заявки (цена / оплата)
- цены 75k / 150k
- результаты
- ручной пост-экзамен
- уведомления (рассылка зарегистрированным / оплатившим)
- **админы** — добавить / удалить по Telegram ID (системных из `.env` удалить нельзя)
- выгрузка Excel

`ADMIN_IDS` в `.env` — постоянные «владельцы» (не снимаются из панели). Остальных админов клиент крутит сам в боте.

## Чеклист приёмки

1. Первый запуск: язык + телефон, без ФИО  
2. Полный цикл записи на UZ / RU / EN  
3. Админ-панель: даты, лимит, заявки, цены, оплата, результаты, пост-экзамен, уведомления  
4. Excel по полям ТЗ  
5. Пост-экзамен авто 2:50 + ручная кнопка  
6. Меню: Мои тесты, Результаты, Локация, Связаться  
7. После N оплаченных на дату — дата скрыта  

## Не входит

Click/Payme, база учеников, OCR чеков, SMS, Mini App, 1С/CRM.

## Деплой на VPS (только через Git)

Код на сервер **не копируем** (`scp`/`rsync` запрещены). Локаль и VPS = один GitHub-репозиторий.

1. Локально: commit → `git push origin main`
2. На VPS:

```bash
cd /opt/rumis-bot
bash deploy/deploy.sh
# или вручную:
# git pull --ff-only origin main
# .venv/bin/pip install -r requirements.txt
# systemctl restart rumis-bot
```

Первичная установка (если каталога ещё нет):

```bash
git clone https://github.com/Ixollozi/Rumis_Academy_Bot.git /opt/rumis-bot
cd /opt/rumis-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # заполнить секреты; .env в git не попадает
# положить SQLite/Postgres URL в DATABASE_URL
systemctl enable --now rumis-bot
```

Runtime **не в git**: `.env`, `*.db`, `.venv/`, `exports/`.

Пример systemd:

```ini
[Unit]
Description=Rumis Academy Bot
After=network.target

[Service]
WorkingDirectory=/opt/rumis-bot
ExecStart=/opt/rumis-bot/.venv/bin/python -m app.bot
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

## Инструкция администратору

1. Добавьте даты Main Test и слоты  
2. Назначьте цену заявке или отклоните  
3. После «Я оплатил» + чек — Оплачено / Отклонить  
4. Результаты: «Ожидают» → отправка; обработанные — в «Архив»  
5. При необходимости — «Уведомления»  
6. Excel — «Выгрузка Excel»  

## Google Sheets (опционально)

Нужны `GOOGLE_SHEETS_ID` + `GOOGLE_CREDENTIALS_JSON` (путь к JSON service account) и доступ «Редактор» на email из `client_email`. Без ключа синхронизация просто пропускается.