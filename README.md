# Telegram Questionnaire Bot

Минимальный Telegram-бот: одна анкета на Telegram ID, PostgreSQL и выгрузка в Excel.

## Railway

1. Создай Telegram-бота через BotFather и получи BOT_TOKEN.
2. Создай новый Railway Project.
3. Добавь PostgreSQL.
4. Добавь сервис из GitHub или загрузи эти файлы в репозиторий.
5. В Variables добавь:
   - BOT_TOKEN
   - DATABASE_URL (можно взять из Railway PostgreSQL)
   - ADMIN_ID
6. Deploy.

Бот работает через long polling, поэтому отдельный домен/webhook/nginx не нужен.

## Команды

/start — начать анкету
/admin — админ-панель (только ADMIN_ID)

## Важно

Текст и обработка данных рассчитаны на легитимную регистрацию. Перед реальным запуском укажи настоящее название оператора данных, цель обработки и необходимые юридические уведомления.
