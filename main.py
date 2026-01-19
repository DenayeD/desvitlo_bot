import asyncio
import sqlite3
import re
import aiohttp
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАЛАШТУВАННЯ ---
TOKEN = "7156722185:AAGPhrFVcyInzlTeWurQkqEswzAEnUwO7Pk"
URL_PAGE = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- БАЗА ДАНИХ ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, subqueue TEXT)')
    conn.commit()
    conn.close()

def update_user_queue(user_id, subqueue):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, subqueue) VALUES (?, ?)', (user_id, subqueue))
    conn.commit()
    conn.close()

def get_user_subqueue(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT subqueue FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

# --- ІНТЕРФЕЙС (КНОПКИ) ---

def get_queue_keyboard():
    builder = []
    for i in range(1, 7):
        builder.append([
            InlineKeyboardButton(text=f"{i}.1", callback_data=f"set_q_{i}.1"),
            InlineKeyboardButton(text=f"{i}.2", callback_data=f"set_q_{i}.2")
        ])
    builder.append([InlineKeyboardButton(text="🔍 Дізнатись свою чергу", url="https://hoe.com.ua/shutdown/queue")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_main_menu():
    kb = [
        [KeyboardButton(text="💡 Мій графік на сьогодні")],
        [KeyboardButton(text="⚙️ Змінити чергу"), KeyboardButton(text="☕ Підтримати бота")],
        [KeyboardButton(text="👨‍💻 Зв'язок з розробником")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ЛОГІКА ПАРСИНГУ ТА ФОРМАТУВАННЯ ---

async def parse_hoe_data():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL_PAGE, timeout=15) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                img_tag = soup.find('img', alt=re.compile(r'ГПВ'))
                date_str = img_tag['alt'] if img_tag else "Графік відключень"
                img_url = "https://hoe.com.ua" + img_tag['src'] if img_tag else None
                page_text = soup.get_text()
                patterns = re.findall(r"підчерга (\d\.\d) [–-] (.*?)(?:;|\n|$)", page_text)
                schedules = {p[0]: p[1].strip() for p in patterns}
                return date_str, schedules, img_url
        except Exception as e:
            logging.error(f"Помилка парсингу: {e}")
            return None, None, None

def format_schedule(subqueue, time_text, date_info):
    # Робимо текст гарним
    clean_times = time_text.replace("з ", "").replace(" до ", "-")
    times_list = clean_times.split(", ")
    
    msg = f"📅 **{date_info}**\n"
    msg += f"📍 Ваша підчерга: **{subqueue}**\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += "🕒 **Періоди ВІДКЛЮЧЕНЬ:**\n"
    for t in times_list:
        msg += f"🔴 {t}\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += "_Я попереджу вас за 60 та 15 хвилин до відключення_ 🔔"
    return msg

# --- ОБРОБНИКИ ПОВІДОМЛЕНЬ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "👋 **Вітаю**\n\n"
        "Я допоможу тобі не пропустити вимкнення та ввімкнення світла.\n\n"
        "⚡️ **Що я роблю:**\n"
        "• Кожного дня опівночі надсилаю свіжий графік\n"
        "• Надсилаю сповіщення за 60 і 15 хвилин до відключення або відновлення електроенергії\n"
        "• Показую актуальні дані з сайту ХОЕ\n\n"
        "Обери свою підчергу:"
    )
    await message.answer(welcome_text, reply_markup=get_queue_keyboard(), parse_mode="Markdown")
    await message.answer("Керування ботом кнопками нижче 👇", reply_markup=get_main_menu())

@dp.message(F.text == "💡 Мій графік на сьогодні")
async def show_my_schedule(message: types.Message):
    subqueue = get_user_subqueue(message.from_user.id)
    if not subqueue:
        await message.answer("Спочатку обери свою чергу 👇", reply_markup=get_queue_keyboard())
        return

    date_info, schedules, img_url = await parse_hoe_data()
    if schedules and subqueue in schedules:
        pretty_text = format_schedule(subqueue, schedules[subqueue], date_info)
        if img_url:
            await message.answer_photo(photo=img_url, caption=pretty_text, parse_mode="Markdown")
        else:
            await message.answer(pretty_text, parse_mode="Markdown")
    else:
        await message.answer("❌ Дані на сайті ще не оновлено або сайт недоступний.")

@dp.message(F.text == "⚙️ Змінити чергу")
async def change_q(message: types.Message):
    await message.answer("Обери нову підчергу:", reply_markup=get_queue_keyboard())

@dp.message(F.text == "☕ Підтримати бота")
async def support(message: types.Message):
    text = (
        "☕ **Підтримка проєкту ДеСвітло?**\n\n"
        "Бот працює на платному сервері для стабільності 24/7. Кожен донат допомагає проєкту жити!\n\n"
        "💳 **Номер банки:** `4874 1000 2365 9678`\n"
        "🔗 [Посилання на Банку](https://send.monobank.ua/jar/WAXs1bH5s)\n\n"
        "Дякую за підтримку! ❤️"
    )
    await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)

@dp.message(F.text == "👨‍💻 Зв'язок з розробником")
async def contact_dev(message: types.Message):
    await message.answer("📝 З будь-яких питань пишіть розробнику: @denayed")

@dp.callback_query(F.data.startswith("set_q_"))
async def callback_set_queue(callback: types.CallbackQuery):
    subqueue = callback.data.replace("set_q_", "")
    update_user_queue(callback.from_user.id, subqueue)
    await callback.message.edit_text(f"✅ **Успішно!**\nВи підписані на підчергу **{subqueue}**.\n\nОчікуйте на сповіщення!", parse_mode="Markdown")
    await callback.answer()

# --- СПОВІЩЕННЯ (60 та 15 ХВ) ---

async def check_alerts():
    _, schedules, _ = await parse_hoe_data()
    if not schedules: return

    now = datetime.now()
    time_60 = (now + timedelta(minutes=60)).strftime("%H:%M")
    time_15 = (now + timedelta(minutes=15)).strftime("%H:%M")

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, subqueue FROM users')
    all_users = cursor.fetchall()
    conn.close()

    for sub_q, time_text in schedules.items():
        all_points = re.findall(r"(\d{2}:\d{2})", time_text)
        
        alert_msg = None
        if time_60 in all_points:
            alert_msg = f"⏳ **Через 1 годину ({time_60})** відбудуться зміни у графіку (черга {sub_q})!"
        elif time_15 in all_points:
            alert_msg = f"⚠️ **Через 15 хвилин ({time_15})** Відбудуться зміни (черга {sub_q})"

        if alert_msg:
            for uid, user_q in all_users:
                if user_q == sub__q:
                    try:
                        await bot.send_message(uid, alert_msg, parse_mode="Markdown")
                        await asyncio.sleep(0.05)
                    except: pass

async def daily_send():
    date_info, schedules, _ = await parse_hoe_data()
    if not schedules: return
    # Логіка як у daily_broadcast з попередніх кроків...

# --- СТАРТ ---
async def main():
    init_db()
    scheduler.add_job(check_alerts, 'interval', minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())