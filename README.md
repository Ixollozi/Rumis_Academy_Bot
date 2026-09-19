# Rumis Academy — Telegram-бот Mock Test

Бот записи на Main Test / Mock Test Speaking (online) по ТЗ Приложения №1 договора NST-001/2026.

## Стек

- Python 3.11+
- aiogram 3
- PostgreSQL + SQLAlchemy async
- APScheduler (пост-экзамен через 2ч 50м)
- openpyxl (выгрузка Excel)

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

Кнопка «Админ-панель» (только `ADMIN_IDS`):

- даты Main Test + лимит (по умолчанию 10)
- заявки (цена / оплата)
- цены 75k / 150k
- результаты
- ручной пост-экзамен
- выгрузка Excel

## Чеклист приёмки

1. Первый запуск: язык + телефон, без ФИО  
2. Полный цикл записи на UZ / RU / EN  
3. Админ-панель: даты, лимит, заявки, цены, оплата, результаты, пост-экзамен  
4. Excel по полям ТЗ  
5. Пост-экзамен авто 2:50 + ручная кнопка  
6. Меню: Мои тесты, Результаты, Локация, Связаться  
7. После N оплаченных на дату — дата скрыта  

## Не входит

Click/Payme, база учеников, OCR чеков, SMS, Mini App, 1С/CRM.

## Деплой на VPS

1. VPS (например [eskis.uz](https://eskis.uz))
2. Python 3.11+, Docker или Postgres
3. Скопировать проект, `.env`, `pip install -r requirements.txt`
4. `python -m app.bot` (systemd / screen)

Пример systemd:

```ini
[Unit]
Description=Rumis Academy Bot
After=network.target

[Service]
WorkingDirectory=/opt/rumis-bot
ExecStart=/opt/rumis-bot/.venv/bin/python -m app.bot
Restart=always

[Install]
WantedBy=multi-user.target
```

## Инструкция администратору

1. Добавьте даты Main Test  
2. Назначьте цену заявке или отклоните  
3. После «Я оплатил» — Оплачено / Отклонить  
4. Опубликуйте результат  
5. Excel — «Выгрузка Excel»  
