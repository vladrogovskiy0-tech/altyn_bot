import os
import re
import io
import asyncio
import asyncpg
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from openpyxl import Workbook


BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# PostgreSQL sometimes arrives from Railway as postgres://...
DATABASE_URL = re.sub(r"^postgres://", "postgresql://", DATABASE_URL)

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db_pool = None


class Form(StatesGroup):
    country = State()
    age = State()
    first_name = State()
    last_name = State()
    phone = State()
    confirm = State()


def start_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Старт", callback_data="form_start")
    return kb.as_markup()


def countries_keyboard():
    kb = InlineKeyboardBuilder()
    for country in ["Россия", "Беларусь", "Казахстан", "Азейбаржан", "Узбекистан", "Другая"]:
        kb.button(text=country, callback_data=f"country:{country}")
    kb.adjust(2)
    return kb.as_markup()


def confirm_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Всё верно", callback_data="confirm_yes")
    kb.button(text="✏️ Изменить", callback_data="form_restart")
    kb.adjust(1)
    return kb.as_markup()


def admin_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="📋 Последние анкеты", callback_data="admin_latest")
    kb.button(text="📥 Скачать Excel", callback_data="admin_excel")
    kb.adjust(1)
    return kb.as_markup()


async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                country TEXT NOT NULL,
                age INTEGER NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                status TEXT NOT NULL DEFAULT 'new'
            )
        """)


async def get_application(telegram_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM applications WHERE telegram_id = $1",
            telegram_id
        )


async def save_application(user, data):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO applications
            (telegram_id, username, country, age, first_name, last_name, phone)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (telegram_id) DO NOTHING
        """,
            user.id,
            user.username,
            data["country"],
            data["age"],
            data["first_name"],
            data["last_name"],
            data["phone"],
        )


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    existing = await get_application(message.from_user.id)
    if existing:
        await message.answer(
            "Вы уже проходили анкету.\n"
            "Повторная регистрация недоступна."
        )
        return

    await message.answer(
        "🌐 <b>Алтын — удобный цифровой банк 🌐</b>\n\n"
        "Алтын начинает набор в свой новый проект участников "
        "на позицию <b>\"Помощник брокера по цифровым транзакциям "
        "на международных биржах\"</b>.\n\n"
        "Что бы узнать все подробности - нажмите <b>\"Старт\"</b> "
        "и заполните внимательно анкету. Затем ожидайте звонка "
        "от нашего представителя по телефону или в мессенджерах.\n\n"
        "Важно ❗️: Анкету пройти можно лишь один раз, правильно "
        "заполняйте данные и будьте готовы к 30 минутам общение "
        "с представителем Алтын. Места ограничены.\n\n"
        "САЙТ КОМПАНИИ: "
        "<a href=\"https://altyn-wallet.com\">altyn-wallet.com</a>",
        reply_markup=start_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=False,
    )


@dp.callback_query(F.data == "form_start")
async def form_start(callback: CallbackQuery, state: FSMContext):
    existing = await get_application(callback.from_user.id)
    if existing:
        await callback.message.edit_text("Вы уже проходили анкету.")
        await callback.answer()
        return

    await state.set_state(Form.country)
    await callback.message.edit_text(
        "🌍 Выберите страну проживания:",
        reply_markup=countries_keyboard()
    )
    await callback.answer()


@dp.callback_query(Form.country, F.data.startswith("country:"))
async def country_selected(callback: CallbackQuery, state: FSMContext):
    country = callback.data.split(":", 1)[1]
    await state.update_data(country=country)

    if country == "Другая":
        await callback.message.edit_text("Введите страну проживания:")
        # Re-use country state for free text.
        return

    await state.set_state(Form.age)
    await callback.message.edit_text("Введите ваш возраст:")
    await callback.answer()


@dp.message(Form.country)
async def country_text(message: Message, state: FSMContext):
    country = message.text.strip()
    if len(country) < 2 or len(country) > 60:
        await message.answer("Введите корректное название страны.")
        return

    await state.update_data(country=country)
    await state.set_state(Form.age)
    await message.answer("Введите ваш возраст:")


@dp.message(Form.age)
async def age_entered(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Возраст должен быть числом. Например: 25")
        return

    age = int(text)
    if age < 18 or age > 100:
        await message.answer("Введите возраст от 18 до 100 лет.")
        return

    await state.update_data(age=age)
    await state.set_state(Form.first_name)
    await message.answer("Введите ваше имя:")


@dp.message(Form.first_name)
async def first_name_entered(message: Message, state: FSMContext):
    name = message.text.strip()
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ' -]{2,60}", name):
        await message.answer("Введите корректное имя.")
        return

    await state.update_data(first_name=name)
    await state.set_state(Form.last_name)
    await message.answer("Введите фамилию:")


@dp.message(Form.last_name)
async def last_name_entered(message: Message, state: FSMContext):
    name = message.text.strip()
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ' -]{2,60}", name):
        await message.answer("Введите корректную фамилию.")
        return

    await state.update_data(last_name=name)
    await state.set_state(Form.phone)
    await message.answer(
        "Введите ваш мобильный номер.\n"
        "Например: <code>+79001234567:</code>",
        parse_mode="HTML"
    )


@dp.message(Form.phone)
async def phone_entered(message: Message, state: FSMContext):
    phone = re.sub(r"[ ()-]", "", message.text.strip())

    if not re.fullmatch(r"\+\d{10,15}", phone):
        await message.answer(
            "Введите номер в международном формате.\n"
            "Например: +79001234567:"
        )
        return

    await state.update_data(phone=phone)
    data = await state.get_data()

    text = (
        "🔎 <b>Проверьте данные</b>\n\n"
        f"Страна: {data['country']}\n"
        f"Возраст: {data['age']}\n"
        f"Имя: {data['first_name']}\n"
        f"Фамилия: {data['last_name']}\n"
        f"Телефон: {data['phone']}\n\n"
        "Всё указано верно?"
    )

    await state.set_state(Form.confirm)
    await message.answer(text, reply_markup=confirm_keyboard(), parse_mode="HTML")


@dp.callback_query(Form.confirm, F.data == "confirm_yes")
async def confirm_yes(callback: CallbackQuery, state: FSMContext):
    existing = await get_application(callback.from_user.id)
    if existing:
        await callback.message.edit_text("Вы уже проходили анкету.")
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()
    await save_application(callback.from_user, data)
    await state.clear()

    await callback.message.edit_text(
        "✅ <b>Спасибо за регистрацию!</b>\n\n"
        "Ваши данные успешно сохранены. "
        "Представитель свяжется с вами в рабочее время с 9:00 - 19:00 МСК. Ожидайте звонка.",
        parse_mode="HTML"
    )
    await callback.answer()

    if ADMIN_ID:
        await bot.send_message(
            ADMIN_ID,
            "🆕 Новая анкета\n\n"
            f"Имя: {data['first_name']} {data['last_name']}\n"
            f"Страна: {data['country']}\n"
            f"Возраст: {data['age']}\n"
            f"Телефон: {data['phone']}\n"
            f"Telegram ID: {callback.from_user.id}"
        )


@dp.callback_query(Form.confirm, F.data == "form_restart")
async def form_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Form.country)
    await callback.message.edit_text(
        "Начнём заново.\n\n🌍 Выберите страну проживания:",
        reply_markup=countries_keyboard()
    )
    await callback.answer()


@dp.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Панель администратора:", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM applications")
        today = await conn.fetchval("""
            SELECT COUNT(*) FROM applications
            WHERE created_at >= CURRENT_DATE
        """)

    await callback.message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"Всего анкет: <b>{total}</b>\n"
        f"За сегодня: <b>{today}</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_latest")
async def admin_latest(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, first_name, last_name, country, phone, created_at
            FROM applications
            ORDER BY id DESC
            LIMIT 10
        """)

    if not rows:
        await callback.message.answer("Анкет пока нет.")
        await callback.answer()
        return

    lines = ["📋 <b>Последние 10 анкет</b>\n"]
    for r in rows:
        dt = r["created_at"].astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"#{r['id']} — {r['first_name']} {r['last_name']} — "
            f"{r['country']} — {r['phone']} — {dt} UTC"
        )

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_excel")
async def admin_excel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, telegram_id, username, country, age,
                   first_name, last_name, phone, created_at, status
            FROM applications
            ORDER BY id ASC
        """)

    wb = Workbook()
    ws = wb.active
    ws.title = "Анкеты"

    headers = [
        "ID", "Telegram ID", "Username", "Страна", "Возраст",
        "Имя", "Фамилия", "Телефон", "Дата регистрации", "Статус"
    ]
    ws.append(headers)

    for r in rows:
        dt = r["created_at"].astimezone(timezone.utc).replace(tzinfo=None)
        ws.append([
            r["id"],
            r["telegram_id"],
            r["username"] or "",
            r["country"],
            r["age"],
            r["first_name"],
            r["last_name"],
            r["phone"],
            dt,
            r["status"],
        ])

    for column in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[column[0].column_letter].width = min(max_len + 2, 35)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"ankety_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"

    await callback.message.answer_document(
        BufferedInputFile(output.read(), filename=filename),
        caption=f"📥 Выгрузка анкет: {len(rows)} записей"
    )
    await callback.answer()


async def main():
    await init_db()
    print("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
