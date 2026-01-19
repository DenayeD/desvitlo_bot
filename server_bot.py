# Copyright (c) 2026 ДеСвітло? BOT
# Licensed under the MIT License. See LICENSE file for details.

import asyncio
import sqlite3
import re
import aiohttp
import logging
import os
import time
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАЛАШТУВАННЯ ЧАСУ ---
os.environ['TZ'] = 'Europe/Kyiv'
if hasattr(time, 'tzset'):
    time.tzset()

# --- НАЛАШТУВАННЯ ---
TOKEN = "7156722185:AAGPhrFVcyInzlTeWurQkqEswzAEnUwO7Pk"
URL_PAGE = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"
ADMIN_USER_ID = 1667269941  # Ваш user_id

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

# --- БАЗА ДАНИХ (ОНОВЛЕНО) ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # Користувачі
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, subqueue TEXT)')
    # Глобальні налаштування (дата останнього графіка)
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    # Історія сповіщень (щоб не дублювати)
    cursor.execute('CREATE TABLE IF NOT EXISTS sent_alerts (user_id INTEGER, event_time TEXT, event_date TEXT)')
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

# --- ЛОГІКА ТА ПАРСИНГ ---
def check_light_status(schedule_text):
    now = datetime.now().time()
    clean_text = schedule_text.replace("з ", "").replace(" до ", "-")
    intervals = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", clean_text)
    for start_str, end_str in intervals:
        try:
            start_t = datetime.strptime(start_str, "%H:%M").time()
            if end_str == '24:00':
                end_t = datetime.strptime('23:59', "%H:%M").time()  # Приблизно кінець дня
            else:
                end_t = datetime.strptime(end_str, "%H:%M").time()
            if start_t <= now <= end_t: return False 
        except ValueError: continue
    return True

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

async def parse_hoe_smart():
    logging.info("Parsing site...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL_PAGE, timeout=15) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Шукаємо всі блоки з картинками ГПВ
                img_containers = soup.find_all('img', alt=re.compile(r'ГПВ'))
                data_by_date = {}

                for img in img_containers:
                    # Витягуємо дату з alt (напр. "ГПВ-17.01.26")
                    alt_text = img.get('alt', '')
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', alt_text)
                    if not date_match: continue
                    
                    date_key = date_match.group(1)
                    # Форматуємо дату до стандарту DD.MM.YYYY якщо треба
                    if len(date_key.split('.')[-1]) == 2:
                        date_key = date_key[:-2] + "20" + date_key[-2:]

                    img_url = "https://hoe.com.ua" + img['src']
                    
                    # Шукаємо список <ul>, який йде ПІСЛЯ цієї картинки
                    ul = img.find_next('ul')
                    schedules = {}
                    if ul:
                        text = ul.get_text()
                        patterns = re.findall(r"підчерга (\d\.\d) [–\-\—\−] (.*?)(?:;|\n|$)", text)
                        schedules = {p[0]: p[1].strip() for p in patterns}

                    data_by_date[date_key] = {
                        "img": img_url,
                        "list": schedules,
                        "raw_date": alt_text
                    }
                return data_by_date
        except Exception as e:
            logging.error(f"Парсинг error: {e}")
            return {}

def format_schedule_pretty(subqueue, time_text, date_info):
    light_now = check_light_status(time_text)
    status_emoji = "🟢" if light_now else "🔴"
    status_text = "СВІТЛО Є" if light_now else "СВІТЛА НЕМАЄ"
    clean_display = re.sub(r"[–\—\−]", "-", time_text.replace("з ", "").replace(" до ", "-"))
    
    msg = f"{status_emoji} **ЗАРАЗ {status_text}**\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += f"📅 **{date_info}**\n"
    msg += f"📍 Підчерга: **{subqueue}**\n\n"
    msg += "🕒 **Періоди ВІДКЛЮЧЕНЬ:**\n"
    for t in clean_display.split(", "):
        msg += f"• {t.strip()}\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += "_Оновлено автоматично_ 🔄"
    return msg

# --- КЛАВІАТУРИ ---
def get_queue_keyboard():
    builder = []
    for i in range(1, 7):
        builder.append([InlineKeyboardButton(text=f"{i}.1", callback_data=f"set_q_{i}.1"),
                        InlineKeyboardButton(text=f"{i}.2", callback_data=f"set_q_{i}.2")])
    builder.append([InlineKeyboardButton(text="🔍 Дізнатись свою чергу", url="https://hoe.com.ua/shutdown/queue")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_main_menu():
    kb = [
        [KeyboardButton(text="💡 Графік на сьогодні"), KeyboardButton(text="🗓️ Графік на завтра")],
        [KeyboardButton(text="⚙️ Змінити чергу"), KeyboardButton(text="☕ Підтримати бота")],
        [KeyboardButton(text="👨‍💻 Зв'язок з розробником")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- УНІВЕРСАЛЬНА ФУНКЦІЯ ВИДАЧІ ---
async def send_schedule_logic(chat_id, subqueue, day_type="today", is_update=False):
    all_data = await parse_hoe_smart()
    
    target_dt = datetime.now() if day_type == "today" else datetime.now() + timedelta(days=1)
    date_str = target_dt.strftime("%d.%m.%Y")
    
    # Спроба знайти дату в ключах (може бути 17.01.26 або 17.01.2026)
    short_date = target_dt.strftime("%d.%m.%y")
    data = all_data.get(date_str) or all_data.get(short_date)

    if not data:
        if day_type == "tomorrow":
            try:
                await bot.send_message(chat_id, "🕠 **Графік на завтра ще не опубліковано.**\nЗазвичай він з'являється після **20:00**.")
            except Exception as e:
                logging.error(f"Failed to send message to {chat_id}: {e}")
        else:
            try:
                await bot.send_message(chat_id, "❌ Дані на сьогодні не знайдені на сайті.")
            except Exception as e:
                logging.error(f"Failed to send message to {chat_id}: {e}")
        return

    img_url = data['img']
    schedules = data['list']
    
    if is_update:
        try:
            await bot.send_photo(chat_id, photo=img_url, caption=f"🆕 **ОНОВЛЕННЯ НА САЙТІ!**\nГрафік на {date_str} вже доступний.")
            if not schedules:
                await bot.send_message(chat_id, "📝 **Зверніть увагу:** Детальні списки годин відключень будуть розписані трохи пізніше (зазвичай протягом години).")
        except Exception as e:
            logging.error(f"Failed to send update to {chat_id}: {e}")
        return

    if not schedules:
        if day_type == "tomorrow":
            text = f"📅 **Графік на {date_str}**\n\n🖼 Детального опису черг ще немає.\n\nПротягом години буде додано детальну інформацію по вашій черзі **{subqueue}**."
        else:
            text = f"📅 **Графік на {date_str}**\n\n🖼 Детального опису черг ще немає."
        try:
            await bot.send_photo(chat_id, photo=img_url, caption=text)
        except Exception as e:
            logging.error(f"Failed to send photo to {chat_id}: {e}")
    else:
        time_text = schedules.get(subqueue, "")
        if day_type == "today":
            light_now = check_light_status(time_text)
            status = "🟢 ЗАРАЗ СВІТЛО Є" if light_now else "🔴 ЗАРАЗ СВІТЛА НЕМАЄ"
            msg = f"**{status}**\n━━━━━━━━━━━━━━━\n"
        else:
            msg = "━━━━━━━━━━━━━━━\n"
        msg += f"📅 **{data['raw_date']}**\n📍 Підчерга: **{subqueue}**\n\n"
        msg += f"🕒 **ВІДКЛЮЧЕННЯ:**\n"
        for t in time_text.replace("з ", "").replace(" до ", "-").split(", "):
            msg += f"• {t.strip()}\n"
        msg += "━━━━━━━━━━━━━━━"
        try:
            await bot.send_photo(chat_id, photo=img_url, caption=msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send schedule to {chat_id}: {e}")

# --- ОБРОБНИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 **Вітаю!** Оберіть свою підчергу:", reply_markup=get_queue_keyboard(), parse_mode="Markdown")
    await message.answer("Керування ботом 👇", reply_markup=get_main_menu())

@dp.message(F.text == "💡 Графік на сьогодні")
async def show_my_schedule(message: types.Message):
    subq = get_user_subqueue(message.from_user.id)
    if not subq: await message.answer("Оберіть чергу 👇", reply_markup=get_queue_keyboard())
    else: await send_schedule_logic(message.from_user.id, subq, "today")

@dp.callback_query(F.data.startswith("set_q_"))
async def callback_set_queue(callback: types.CallbackQuery):
    subq = callback.data.replace("set_q_", "")
    update_user_queue(callback.from_user.id, subq)
    await callback.message.edit_text(f"✅ **Успішно!**\nОбрано підчергу **{subq}**.", parse_mode="Markdown")
    await send_schedule_logic(callback.from_user.id, subq, "today")
    await callback.answer()

@dp.message(F.text == "⚙️ Змінити чергу")
async def change_q(message: types.Message):
    await message.answer("Оберіть нову підчергу:", reply_markup=get_queue_keyboard())

@dp.message(F.text == "☕ Підтримати бота")
async def support(message: types.Message):
    text = (
        "☕ **Підтримка проєкту ДеСвітло?**\n\n"
        "Бот працює на хмарному сервері. Кожен донат допомагає проєкту жити!\n\n"
        "💳 **Номер банки:** `4874 1000 2365 9678`\n"
        "🔗 [Посилання на Банку](https://send.monobank.ua/jar/WAXs1bH5s)\n\n"
        "Дякую за підтримку! ❤️"
    )
    await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)

@dp.message(F.text == "👨‍💻 Зв'язок з розробником")
async def contact_dev(message: types.Message):
    await message.answer("📝 З будь-яких питань пишіть розробнику: @denayed")

@dp.message(F.text == "🗓️ Графік на завтра")
async def act_tomorrow(message: types.Message):
    subq = get_user_subqueue(message.from_user.id)
    if not subq: await message.answer("Оберіть чергу 👇", reply_markup=get_queue_keyboard())
    else: await send_schedule_logic(message.from_user.id, subq, "tomorrow")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:  
        await message.answer("❌ Доступ заборонено.")
        return
    
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer("📝 Надішліть повідомлення для розсилки всім користувачам.")

# --- МОНІТОРИНГ ТА СПОВІЩЕННЯ ---
async def monitor_job():
    all_data = await parse_hoe_smart()
    if not all_data: 
        logging.info("No data parsed from site")
        return

    logging.info(f"Parsed data for dates: {list(all_data.keys())}")

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Load known schedules
    cursor.execute('SELECT value FROM settings WHERE key = "known_schedules"')
    res = cursor.fetchone()
    known_schedules = json.loads(res[0]) if res and res[0] else {}
    logging.info(f"Loaded known_schedules: {list(known_schedules.keys())}")
    
    # Get all users
    cursor.execute('SELECT user_id, subqueue FROM users')
    all_users = cursor.fetchall()
    
    now = datetime.now()
    current_date_str = now.strftime("%d.%m.%Y")
    short_date = now.strftime("%d.%m.%y")
    
    updated_dates = []
    
    for date_key, data in all_data.items():
        is_new = date_key not in known_schedules
        has_list_now = bool(data['list'])
        had_list = known_schedules.get(date_key, {}).get('has_list', False)
        list_changed = known_schedules.get(date_key, {}).get('list', {}) != data['list']
        
        if is_new or list_changed or (not had_list and has_list_now):
            logging.info(f"Detected change for {date_key}: is_new={is_new}, list_changed={list_changed}, has_list_now={has_list_now}, had_list={had_list}")
            # This is new or updated
            updated_dates.append(date_key)
            
            # Determine if it's today, tomorrow, or future
            try:
                date_dt = datetime.strptime(date_key, "%d.%m.%Y")
            except ValueError:
                try:
                    date_dt = datetime.strptime(date_key, "%d.%m.%y")
                    date_dt = date_dt.replace(year=2000 + date_dt.year % 100)
                except ValueError:
                    continue
            
            days_diff = (date_dt.date() - now.date()).days
            
            if days_diff == 0:
                msg_type = "update_today"
            elif days_diff == 1:
                msg_type = "new_tomorrow" if is_new else "update_tomorrow"
            else:
                msg_type = "new_future" if is_new else "update_future"
            
            # Send notifications
            for uid, subq in all_users:
                try:
                    if msg_type in ["new_tomorrow", "new_future"]:
                        caption = f"🆕 **НОВИЙ ГРАФІК!**\n\nГрафік на {date_key} вже доступний на сайті."
                        await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="Markdown")
                        if not has_list_now:
                            await bot.send_message(uid, "📝 **Зверніть увагу:** Детальні списки годин відключень будуть розписані трохи пізніше (зазвичай протягом години).")
                    elif msg_type == "update_today":
                        await send_schedule_logic(uid, subq, "today", is_update=True)
                    elif msg_type == "update_tomorrow":
                        if has_list_now and not had_list:
                            caption = f"📝 **ОНОВЛЕННЯ ГРАФІКА!**\n\nДетальні списки годин відключень на {date_key} тепер доступні."
                            await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Failed to send notification to {uid}: {e}")
                await asyncio.sleep(0.05)
            
            # Update known
            known_schedules[date_key] = {
                'img': data['img'],
                'list': data['list'],
                'has_list': has_list_now
            }
    
    # Clean up old schedules (keep only current and future dates from the site)
    current_keys = set(all_data.keys())
    future_dates = set()
    for k in known_schedules.keys():
        try:
            dt = datetime.strptime(k, "%d.%m.%Y")
            if dt.date() >= now.date():
                future_dates.add(k)
        except ValueError:
            pass
    known_schedules = {k: v for k, v in known_schedules.items() if k in current_keys or k in future_dates}
    logging.info(f"After cleanup, known_schedules: {list(known_schedules.keys())}")
    
    # Save updated known_schedules
    logging.info("Saving known_schedules")
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("known_schedules", ?)', (json.dumps(known_schedules),))
    conn.commit()
    
    # Now do the 30-min alerts
    data_today = all_data.get(current_date_str) or all_data.get(short_date)
    if not data_today or not data_today['list']: 
        conn.close()
        return

    schedules_today = data_today['list']
    
    tomorrow_dt = now + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")
    tomorrow_short = tomorrow_dt.strftime("%d.%m.%y")
    data_tomorrow = all_data.get(tomorrow_str) or all_data.get(tomorrow_short)
    schedules_tomorrow = data_tomorrow['list'] if data_tomorrow else {}

    for sub_q in schedules_today.keys():
        time_text_today = schedules_today.get(sub_q, "")
        time_text_tomorrow = schedules_tomorrow.get(sub_q, "")

        # Збираємо всі інтервали для сьогодні і завтра
        combined_intervals = []
        
        # Інтервали сьогодні
        intervals_today = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_today.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_today:
            start_dt = datetime.combine(now.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((now + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(now.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))
        
        # Інтервали завтра
        intervals_tomorrow = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_tomorrow.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_tomorrow:
            start_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((tomorrow_dt + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))
        
        # Об'єднуємо суміжні інтервали (наприклад, через північ)
        if combined_intervals:
            combined_intervals.sort(key=lambda x: x[0])  # Сортуємо за початком
            merged_intervals = []
            current_start, current_end = combined_intervals[0]
            for start, end in combined_intervals[1:]:
                if start == current_end:  # Суміжні, об'єднуємо
                    current_end = end
                else:
                    merged_intervals.append((current_start, current_end))
                    current_start, current_end = start, end
            merged_intervals.append((current_start, current_end))
            combined_intervals = merged_intervals
        
        # Знаходимо точки зміни в найближчі 30 хв
        t30_dt = now + timedelta(minutes=30)
        for start_dt, end_dt in combined_intervals:
            change_points = [start_dt, end_dt]
            for change_dt in change_points:
                if now < change_dt <= t30_dt:
                    minutes_left = int((change_dt - now).total_seconds() / 60)
                    change_time_str = change_dt.strftime("%H:%M")
                    event_date = change_dt.strftime("%Y-%m-%d")
                    
                    # Визначаємо тип події: початок відключення чи відновлення
                    if change_dt == start_dt:
                        alert_msg = f"⚠️ **Увага! Відключення світла**\n\nЧерез {minutes_left} хв ({change_time_str}) подача електроенергії буде **припинена** за вашою підчергою **{sub_q}**."
                    else:
                        alert_msg = f"✅ **Відновлення електроенергії**\n\nЧерез {minutes_left} хв ({change_time_str}) подача електроенергії буде **відновлена** для вашої підчерги **{sub_q}**."
                    
                    cursor.execute('SELECT user_id FROM users WHERE subqueue = ?', (sub_q,))
                    users_in_q = cursor.fetchall()
                    for (uid,) in users_in_q:
                        cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?', 
                                       (uid, change_time_str, event_date))
                        if not cursor.fetchone():
                            try:
                                await bot.send_message(uid, alert_msg, parse_mode="Markdown")
                                cursor.execute('INSERT INTO sent_alerts VALUES (?, ?, ?)', (uid, change_time_str, event_date))
                                conn.commit()
                            except: pass
    
    # Clean up old sent alerts (older than today)
    logging.info("Cleaning up old sent_alerts")
    cursor.execute('DELETE FROM sent_alerts WHERE event_date < ?', (now.strftime("%Y-%m-%d"),))
    conn.commit()
    
    conn.close()

@dp.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:  # Додаткова перевірка
        await message.answer("❌ Доступ заборонено.")
        await state.clear()
        return
    
    broadcast_text = message.text
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    sent_count = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, broadcast_text)
            sent_count += 1
            await asyncio.sleep(0.1)  # Щоб не перевантажувати
        except Exception as e:
            logging.error(f"Failed to send to {uid}: {e}")
    
    await message.answer(f"✅ Повідомлення відправлено {sent_count} користувачам.")
    await state.clear()

async def main():
    init_db()
    scheduler.add_job(monitor_job, 'interval', minutes=2)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())