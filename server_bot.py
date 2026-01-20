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
from PIL import Image, ImageDraw, ImageFont
import math
from dotenv import load_dotenv

# Завантажуємо змінні середовища
load_dotenv()

# --- НАЛАШТУВАННЯ ЧАСУ ---
os.environ['TZ'] = 'Europe/Kyiv'
if hasattr(time, 'tzset'):
    time.tzset()

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
URL_PAGE = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

class AddressStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_queue = State()
    waiting_for_edit_name = State()
    waiting_for_edit_queue = State()

# --- БАЗА ДАНИХ (ОНОВЛЕНО) ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # Користувачі
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, subqueue TEXT)')
    # Адреси користувачів
    cursor.execute('''CREATE TABLE IF NOT EXISTS addresses (
        user_id INTEGER,
        name TEXT,
        subqueue TEXT,
        is_main BOOLEAN DEFAULT 0,
        PRIMARY KEY (user_id, name)
    )''')
    # Глобальні налаштування (дата останнього графіка)
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    # Історія сповіщень (щоб не дублювати)
    cursor.execute('CREATE TABLE IF NOT EXISTS sent_alerts (user_id INTEGER, event_time TEXT, event_date TEXT)')
    # Налаштування сповіщень
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_notifications (
        user_id INTEGER,
        address_name TEXT,
        notifications_enabled BOOLEAN DEFAULT 1,
        new_schedule_enabled BOOLEAN DEFAULT 1,
        schedule_changes_enabled BOOLEAN DEFAULT 1,
        PRIMARY KEY (user_id, address_name)
    )''')
    
    # Міграція наявних користувачів
    cursor.execute('SELECT user_id, subqueue FROM users WHERE subqueue IS NOT NULL')
    existing_users = cursor.fetchall()
    for user_id, subqueue in existing_users:
        # Перевіряємо, чи вже є адреси для цього користувача
        cursor.execute('SELECT COUNT(*) FROM addresses WHERE user_id = ?', (user_id,))
        if cursor.fetchone()[0] == 0:
            # Додаємо основну адресу "Дім"
            cursor.execute('INSERT INTO addresses (user_id, name, subqueue, is_main) VALUES (?, ?, ?, 1)', (user_id, 'Дім', subqueue))
    
    # Ініціалізуємо налаштування для всіх користувачів
    cursor.execute('SELECT DISTINCT user_id FROM users')  # Всі користувачі, не тільки з addresses
    all_users = cursor.fetchall()
    for (user_id,) in all_users:
        # Загальні налаштування
        cursor.execute('SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND address_name IS NULL', (user_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, NULL, 1, 1, 1)', (user_id,))
        # Налаштування для адрес
        cursor.execute('SELECT name FROM addresses WHERE user_id = ?', (user_id,))
        addresses = cursor.fetchall()
        for (name,) in addresses:
            cursor.execute('SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, name))
            if cursor.fetchone()[0] == 0:
                cursor.execute('INSERT INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, ?, 1, 1, 1)', (user_id, name))
    
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
    cursor.execute('SELECT subqueue FROM addresses WHERE user_id = ? AND is_main = 1', (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

# --- ФУНКЦІЇ ДЛЯ АДРЕС ---
def get_user_addresses(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, subqueue, is_main FROM addresses WHERE user_id = ? ORDER BY is_main DESC, name', (user_id,))
    addresses = cursor.fetchall()
    conn.close()
    return addresses

def add_user_address(user_id, name, subqueue):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO addresses (user_id, name, subqueue, is_main) VALUES (?, ?, ?, 0)', (user_id, name, subqueue))
    # Ініціалізуємо налаштування для нової адреси
    set_user_notification_settings(user_id, name, True, True, True)
    conn.commit()
    conn.close()

def update_address_name(user_id, old_name, new_name):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE addresses SET name = ? WHERE user_id = ? AND name = ?', (new_name, user_id, old_name))
    conn.commit()
    conn.close()

def update_address_queue(user_id, name, new_subqueue):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE addresses SET subqueue = ? WHERE user_id = ? AND name = ?', (new_subqueue, user_id, name))
    conn.commit()
    conn.close()

def set_main_address(user_id, name):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE addresses SET is_main = 0 WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE addresses SET is_main = 1 WHERE user_id = ? AND name = ?', (user_id, name))
    conn.commit()
    conn.close()

def delete_user_address(user_id, name):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # Не видаляємо, якщо це основна адреса і є інші
    cursor.execute('SELECT COUNT(*) FROM addresses WHERE user_id = ?', (user_id,))
    count = cursor.fetchone()[0]
    if count > 1:
        cursor.execute('DELETE FROM addresses WHERE user_id = ? AND name = ?', (user_id, name))
        # Якщо видалена була основною, призначаємо іншу
        cursor.execute('SELECT is_main FROM addresses WHERE user_id = ? AND name = ?', (user_id, name))
        was_main = cursor.fetchone()
        if was_main and was_main[0]:
            cursor.execute('UPDATE addresses SET is_main = 1 WHERE user_id = ? LIMIT 1', (user_id,))
        # Видаляємо налаштування для цієї адреси
        cursor.execute('DELETE FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, name))
    conn.commit()
    conn.close()

# --- ФУНКЦІЇ ДЛЯ НАЛАШТУВАНЬ СПОВІЩЕНЬ ---
def get_user_notification_settings(user_id, address_name=None):
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        if address_name is None:
            # Загальні налаштування
            cursor.execute('SELECT notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE user_id = ? AND address_name IS NULL', (user_id,))
        else:
            # Налаштування для конкретної адреси
            cursor.execute('SELECT notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, address_name))
        res = cursor.fetchone()
        conn.close()
        logging.info(f"Get settings for user {user_id}, addr {address_name}: {res}")
        if res:
            return {
                'notifications_enabled': res[0],
                'new_schedule_enabled': res[1],
                'schedule_changes_enabled': res[2]
            }
        else:
            # Дефолтні налаштування
            logging.info(f"No row found for user {user_id}, addr {address_name}, returning defaults")
            return {
                'notifications_enabled': True,
                'new_schedule_enabled': True,
                'schedule_changes_enabled': True
            }
    except Exception as e:
        logging.error(f"Error getting notification settings for user {user_id}, addr {address_name}: {e}")
        return {
            'notifications_enabled': True,
            'new_schedule_enabled': True,
            'schedule_changes_enabled': True
        }

def set_user_notification_settings(user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled):
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        # Перетворюємо булеві значення в цілі числа явно
        notifications_enabled = int(notifications_enabled)
        new_schedule_enabled = int(new_schedule_enabled)
        schedule_changes_enabled = int(schedule_changes_enabled)

        logging.info(f"Setting notifications for user {user_id}, addr {address_name}: {notifications_enabled}, {new_schedule_enabled}, {schedule_changes_enabled}")

        if address_name is None:
            cursor.execute('UPDATE user_notifications SET notifications_enabled = ?, new_schedule_enabled = ?, schedule_changes_enabled = ? WHERE user_id = ? AND address_name IS NULL',
                           (notifications_enabled, new_schedule_enabled, schedule_changes_enabled, user_id))
            if cursor.rowcount == 0:
                cursor.execute('INSERT INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, NULL, ?, ?, ?)',
                               (user_id, notifications_enabled, new_schedule_enabled, schedule_changes_enabled))
        else:
            cursor.execute('UPDATE user_notifications SET notifications_enabled = ?, new_schedule_enabled = ?, schedule_changes_enabled = ? WHERE user_id = ? AND address_name = ?',
                           (notifications_enabled, new_schedule_enabled, schedule_changes_enabled, user_id, address_name))
            if cursor.rowcount == 0:
                cursor.execute('INSERT INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, ?, ?, ?, ?)',
                               (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled))

        conn.commit()
        conn.close()
        logging.info(f"Successfully set notifications for user {user_id}, addr {address_name}")
    except Exception as e:
        logging.error(f"Error setting notification settings for user {user_id}, addr {address_name}: {e}")

def init_user_notification_settings(user_id):
    # Ініціалізуємо дефолтні налаштування для користувача
    addresses = get_user_addresses(user_id)
    for name, _, _ in addresses:
        settings = get_user_notification_settings(user_id, name)
        if not settings:  # Якщо немає, встановлюємо дефолтні
            set_user_notification_settings(user_id, name, True, True, True)
    # Загальні налаштування
    settings = get_user_notification_settings(user_id)
    if not settings:
        set_user_notification_settings(user_id, None, True, True, True)

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
                # Use lxml if available for better performance
                try:
                    soup = BeautifulSoup(html, 'lxml')
                except:
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

def generate_clock_image(subqueue, time_text, date_info):
    # Створюємо зображення годинника
    os.makedirs('clocks', exist_ok=True)
    filename = f"clocks/{subqueue}_{date_info.replace('.', '_')}.png"
    
    # Очищення старих файлів (старіше 24 годин) на кожному виклику
    now = datetime.now()
    for file in os.listdir('clocks'):
        filepath = os.path.join('clocks', file)
        if os.path.isfile(filepath):
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if (now - file_mtime).total_seconds() > 86400:  # 24 години
                os.remove(filepath)
    size = 600
    img = Image.new('RGBA', (size, size), (220, 220, 220, 255))  # Світло-сірий фон
    draw = ImageDraw.Draw(img)
    
    center = size // 2
    radius = 250
    
    # Фон годинника з градієнтом
    for r in range(radius, 0, -1):
        alpha = int(255 * (1 - r / radius))
        color = (200, 220, 255, alpha)  # М'який блакитний
        draw.ellipse((center - r, center - r, center + r, center + r), fill=color)
    
    # Зовнішнє коло
    draw.ellipse((center - radius, center - radius, center + radius, center + radius), 
                 outline=(100, 100, 100), width=3)
    
    # Спроба завантажити шрифт (для Linux сервера)
    try:
        # Спробуємо arial.ttf в поточній папці (якщо завантажено)
        font = ImageFont.truetype('arial.ttf', 36)  # Збільшено до 36
    except:
        try:
            # Системний шрифт для Linux
            font = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 36)
        except:
            try:
                # Альтернативний системний шрифт
                font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 36)
            except:
                # Якщо нічого не працює, використовуємо default
                font = ImageFont.load_default()
    
    # Засічки годин
    for hour in range(24):
        angle = math.radians(hour * 15 - 90)  # 15 градусів на годину, 0 годин вгорі
        inner_r = radius - 20
        outer_r = radius - 10 if hour % 6 == 0 else radius - 5
        x1 = center + inner_r * math.cos(angle)
        y1 = center + inner_r * math.sin(angle)
        x2 = center + outer_r * math.cos(angle)
        y2 = center + outer_r * math.sin(angle)
        draw.line((x1, y1, x2, y2), fill=(50, 50, 50), width=2)
        
        # Цифри годин
        if True:  # Показувати всі години
            text_r = radius + 15  # За межами кола годинника
            x = center + text_r * math.cos(angle)
            y = center + text_r * math.sin(angle)
            # Розмір тексту для центрування
            bbox = draw.textbbox((0, 0), str(hour), font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            cx = x - text_width / 2
            cy = y - text_height / 2
            # Обведення чорним
            draw.text((cx-1, cy-1), str(hour), fill=(0, 0, 0), font=font)
            draw.text((cx+1, cy-1), str(hour), fill=(0, 0, 0), font=font)
            draw.text((cx-1, cy+1), str(hour), fill=(0, 0, 0), font=font)
            draw.text((cx+1, cy+1), str(hour), fill=(0, 0, 0), font=font)
            # Основний текст білим
            draw.text((cx, cy), str(hour), fill=(255, 255, 255), font=font)
    
    # Парсимо інтервали відключень
    intervals = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text.replace("з ", "").replace(" до ", "-"))
    
    for start_str, end_str in intervals:
        try:
            start_h, start_m = map(int, start_str.split(':'))
            end_h, end_m = map(int, end_str.split(':'))
            
            start_angle = (start_h * 15 + start_m * 0.25) - 90
            end_angle = (end_h * 15 + end_m * 0.25) - 90
            
            if end_angle < start_angle:
                end_angle += 360
            
            # Малюємо дугу відключення (невелику)
            draw.arc((center - radius + 20, center - radius + 20, center + radius - 20, center + radius - 20),
                     start=start_angle, end=end_angle, fill=(255, 100, 100), width=40)
        except:
            continue
    
    # Стрілка поточного часу прибрана
    
    # Текст інформації в верхньому лівому куті
    text = f"{date_info}\nЧерга {subqueue}"
    draw.text((10, 10), text, fill=(0, 0, 0), font=font)
    
    # Зберігаємо зображення
    img.save(filename)
    return filename

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

def get_address_selection_keyboard(user_id, action_prefix):
    addresses = get_user_addresses(user_id)
    builder = []
    for name, subq, is_main in addresses:
        main_mark = " ⭐" if is_main else ""
        builder.append([InlineKeyboardButton(text=f"{name} (черга {subq}){main_mark}", callback_data=f"{action_prefix}_{name}")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_main_menu():
    kb = [
        
        [KeyboardButton(text="📅 Графік на сьогодні"), KeyboardButton(text="🗓️ Графік на завтра")],
        [KeyboardButton(text="📊 Загальний графік")],
        [KeyboardButton(text="🏠 Керування адресами"), KeyboardButton(text="⚙️ Налаштування бота")],
        [KeyboardButton(text="☕ Підтримати бота"), KeyboardButton(text="👨‍💻 Зв'язок з розробником")]
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
                await bot.send_message(chat_id, "🕠 <b>Графік на завтра ще не опубліковано.</b>\nЗазвичай він з'являється після <b>20:00</b>.", parse_mode="HTML")
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
            await bot.send_photo(chat_id, photo=img_url, caption=f"🆕 <b>ОНОВЛЕННЯ НА САЙТІ!</b>\nГрафік на {date_str} вже доступний.", parse_mode="HTML")
            if not schedules:
                await bot.send_message(chat_id, "📝 <b>Зверніть увагу:</b> Детальні списки годин відключень будуть розписані трохи пізніше (зазвичай протягом години).", parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send update to {chat_id}: {e}")
        return

    if not schedules:
        if day_type == "tomorrow":
            text = f"📅 <b>Графік на {date_str}</b>\n\n🖼 Детального опису черг ще немає.\n\nПротягом години буде додано детальну інформацію по вашій черзі <b>{subqueue}</b>."
        else:
            text = f"📅 <b>Графік на {date_str}</b>\n\n🖼 Детального опису черг ще немає."
        try:
            await bot.send_photo(chat_id, photo=img_url, caption=text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send photo to {chat_id}: {e}")
    else:
        time_text = schedules.get(subqueue, "")
        if day_type == "today":
            light_now = check_light_status(time_text)
            status = "🟢 ЗАРАЗ СВІТЛО Є" if light_now else "🔴 ЗАРАЗ СВІТЛА НЕМАЄ"
            msg = f"<b>{status}</b>\n━━━━━━━━━━━━━━━\n"
        else:
            msg = "━━━━━━━━━━━━━━━\n"
        msg += f"📅 <b>{data['raw_date']}</b>\n📍 Підчерга: <b>{subqueue}</b>\n\n"
        msg += f"🕒 <b>ВІДКЛЮЧЕННЯ:</b>\n"
        for t in time_text.replace("з ", "").replace(" до ", "-").split(", "):
            msg += f"• {t.strip()}\n"
        msg += "━━━━━━━━━━━━━━━"
        
        # Генеруємо годинник
        clock_file = generate_clock_image(subqueue, time_text, data['raw_date'])
        try:
            await bot.send_photo(chat_id, photo=types.FSInputFile(clock_file), caption=msg, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send clock to {chat_id}: {e}")
            # Fallback to original
            try:
                await bot.send_photo(chat_id, photo=img_url, caption=msg, parse_mode="HTML")
            except Exception as e:
                logging.error(f"Failed to send schedule to {chat_id}: {e}")

# --- ОБРОБНИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 <b>Вітаю!</b> Оберіть свою підчергу:", reply_markup=get_queue_keyboard(), parse_mode="HTML")
    await message.answer("Керування ботом 👇", reply_markup=get_main_menu())

@dp.message(F.text == "📅 Графік на сьогодні")
async def show_my_schedule(message: types.Message, state: FSMContext):
    await state.clear()
    subq = get_user_subqueue(message.from_user.id)
    if not subq: await message.answer("Оберіть чергу 👇", reply_markup=get_queue_keyboard())
    else: await send_schedule_logic(message.from_user.id, subq, "today")

@dp.message(F.text == "🏠 Керування адресами")
async def manage_addresses(message: types.Message, state: FSMContext):
    await state.clear()  # Зупиняємо будь-який процес
    addresses = get_user_addresses(message.from_user.id)
    if not addresses:
        await message.answer("У вас немає адрес. Додайте першу адресу.")
        # Можливо, автоматично додати "Дім" але оскільки міграція вже зроблена, має бути
        return
    
    text = "🏠 <b>Ваші адреси:</b>\n\n"
    for name, subq, is_main in addresses:
        main_mark = " (основна)" if is_main else ""
        text += f"• <b>{name}</b>: черга {subq}{main_mark}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати адресу", callback_data="addr_add")],
        [InlineKeyboardButton(text="✏️ Редагувати назву", callback_data="addr_edit_name")],
        [InlineKeyboardButton(text="🔄 Змінити чергу", callback_data="addr_edit_queue")],
        [InlineKeyboardButton(text="⭐ Зробити основною", callback_data="addr_set_main")],
        [InlineKeyboardButton(text="🗑️ Видалити адресу", callback_data="addr_delete")],
        [InlineKeyboardButton(text="👀 Переглянути графіки", callback_data="addr_view_schedules")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")



@dp.callback_query(F.data.startswith("set_q_"))
async def callback_set_queue(callback: types.CallbackQuery, state: FSMContext):
    subq = callback.data.replace("set_q_", "")
    current_state = await state.get_state()
    if current_state == AddressStates.waiting_for_new_queue:
        # Додаємо нову адресу
        data = await state.get_data()
        name = data['addr_name']
        add_user_address(callback.from_user.id, name, subq)
        await callback.message.edit_text(f"✅ <b>Успішно!</b>\nСтворено адресу <b>{name}</b> з чергою <b>{subq}</b>.", parse_mode="HTML")
        await state.clear()
    else:
        # Оновлюємо чергу основної адреси
        addresses = get_user_addresses(callback.from_user.id)
        if addresses:
            main_addr = next((name for name, _, is_main in addresses if is_main), None)
            if main_addr:
                update_address_queue(callback.from_user.id, main_addr, subq)
                await callback.message.edit_text(f"✅ <b>Успішно!</b>\nОбрано підчергу <b>{subq}</b> для адреси <b>{main_addr}</b>.", parse_mode="HTML")
                await send_schedule_logic(callback.from_user.id, subq, "today")
            else:
                await callback.message.edit_text("❌ Помилка: немає основної адреси.")
        else:
            # Якщо немає адрес, створюємо "Дім"
            add_user_address(callback.from_user.id, "Дім", subq)
            set_main_address(callback.from_user.id, "Дім")
            await callback.message.edit_text(f"✅ <b>Успішно!</b>\nСтворено адресу <b>Дім</b> з чергою <b>{subq}</b>.", parse_mode="HTML")
            await send_schedule_logic(callback.from_user.id, subq, "today")
    await callback.answer()

@dp.message(F.text == "⚙️ Змінити чергу")
async def change_q(message: types.Message):
    await message.answer("Оберіть нову підчергу:", reply_markup=get_queue_keyboard())

@dp.message(F.text == "☕ Підтримати бота")
async def support(message: types.Message):
    text = (
        "☕ <b>Підтримка проєкту ДеСвітло?</b>\n\n"
        "Бот працює на хмарному сервері. Кожен донат допомагає проєкту жити!\n\n"
        "💳 <b>Номер банки:</b> <code>4874 1000 2365 9678</code>\n"
        "🔗 [Посилання на Банку](https://send.monobank.ua/jar/WAXs1bH5s)\n\n"
        "Дякую за підтримку! ❤️"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

@dp.message(F.text == "👨‍💻 Зв'язок з розробником")
async def contact_dev(message: types.Message):
    await message.answer("📝 З будь-яких питань пишіть розробнику: @denayed")

@dp.message(F.text == "⚙️ Налаштування бота")
async def bot_settings(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    init_user_notification_settings(user_id)  # Ініціалізуємо налаштування, якщо не існують
    
    addresses = get_user_addresses(user_id)
    if not addresses:
        await message.answer("У вас немає адрес. Спочатку додайте адресу в керуванні адресами.")
        return
    
    text = "⚙️ <b>Налаштування сповіщень бота</b>\n\n"
    text += "Оберіть, що налаштувати:\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Загальні сповіщення", callback_data="settings_general")],
    ])
    
    for name, _, _ in addresses:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name}", callback_data=f"settings_addr_{name}")])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🗓️ Графік на завтра")
async def act_tomorrow(message: types.Message, state: FSMContext):
    await state.clear()
    subq = get_user_subqueue(message.from_user.id)
    if not subq: await message.answer("Оберіть чергу 👇", reply_markup=get_queue_keyboard())
    else: await send_schedule_logic(message.from_user.id, subq, "tomorrow")

@dp.message(F.text == "📊 Загальний графік")
async def act_general(message: types.Message, state: FSMContext):
    await state.clear()
    # Надсилаємо загальний графік з сайту
    all_data = await parse_hoe_smart()
    if not all_data:
        await message.answer("❌ Не вдалося отримати дані.")
        return
    
    # Спробуємо знайти графік на сьогодні
    now = datetime.now()
    current_date_str = now.strftime("%d.%m.%Y")
    short_date = now.strftime("%d.%m.%y")
    
    data = all_data.get(current_date_str) or all_data.get(short_date)
    if data:
        img_url = data['img']
        try:
            await bot.send_photo(message.from_user.id, photo=img_url, caption=f"📊 Загальний графік на {current_date_str}")
        except Exception as e:
            logging.error(f"Failed to send general schedule: {e}")
            await message.answer("❌ Помилка при відправці графіка.")
    else:
        # Якщо сьогодні немає, беремо перший доступний
        for date_key, data in all_data.items():
            img_url = data['img']
            try:
                await bot.send_photo(message.from_user.id, photo=img_url, caption=f"📊 Загальний графік на {date_key}")
                break
            except Exception as e:
                logging.error(f"Failed to send general schedule: {e}")



@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:  
        await message.answer("❌ Доступ заборонено.")
        return
    
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer("📝 Надішліть повідомлення для розсилки всім користувачам.")



#ОБРОБНИКИ АДРЕС
@dp.callback_query(F.data == "addr_add")
async def addr_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введіть назву нової адреси (наприклад, 'Дім', 'Робота'):")
    await state.set_state(AddressStates.waiting_for_new_name)
    await callback.answer()

@dp.callback_query(F.data == "addr_edit_name")
async def addr_edit_name(callback: types.CallbackQuery):
    kb = get_address_selection_keyboard(callback.from_user.id, "edit_name")
    await callback.message.edit_text("Оберіть адресу для зміни назви:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "addr_edit_queue")
async def addr_edit_queue(callback: types.CallbackQuery):
    kb = get_address_selection_keyboard(callback.from_user.id, "edit_queue")
    await callback.message.edit_text("Оберіть адресу для зміни черги:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "addr_set_main")
async def addr_set_main(callback: types.CallbackQuery):
    kb = get_address_selection_keyboard(callback.from_user.id, "set_main")
    await callback.message.edit_text("Оберіть адресу, яку зробити основною:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "addr_delete")
async def addr_delete(callback: types.CallbackQuery):
    kb = get_address_selection_keyboard(callback.from_user.id, "delete")
    await callback.message.edit_text("Оберіть адресу для видалення:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "addr_view_schedules")
async def addr_view_schedules(callback: types.CallbackQuery):
    kb = get_address_selection_keyboard(callback.from_user.id, "view_sched")
    await callback.message.edit_text("Оберіть адресу для перегляду графіка:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_name_"))
async def select_addr_edit_name(callback: types.CallbackQuery, state: FSMContext):
    addr_name = callback.data.replace("edit_name_", "")
    await state.update_data(addr_name=addr_name)
    await callback.message.edit_text(f"Введіть нову назву для адреси '{addr_name}':")
    await state.set_state(AddressStates.waiting_for_edit_name)
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_queue_"))
async def select_addr_edit_queue(callback: types.CallbackQuery):
    addr_name = callback.data.replace("edit_queue_", "")
    kb = get_queue_keyboard()
    # Змінюємо callback_data щоб знати адресу
    # Але оскільки get_queue_keyboard має set_q_, потрібно створити нову
    builder = []
    for i in range(1, 7):
        builder.append([InlineKeyboardButton(text=f"{i}.1", callback_data=f"set_addr_q_{addr_name}_{i}.1"),
                        InlineKeyboardButton(text=f"{i}.2", callback_data=f"set_addr_q_{addr_name}_{i}.2")])
    builder.append([InlineKeyboardButton(text="🔍 Дізнатись свою чергу", url="https://hoe.com.ua/shutdown/queue")])
    kb = InlineKeyboardMarkup(inline_keyboard=builder)
    await callback.message.edit_text(f"Оберіть нову чергу для адреси '{addr_name}':", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("set_main_"))
async def select_addr_set_main(callback: types.CallbackQuery):
    addr_name = callback.data.replace("set_main_", "")
    set_main_address(callback.from_user.id, addr_name)
    await callback.message.edit_text(f"✅ Адреса '{addr_name}' встановлена як основна.")
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_"))
async def select_addr_delete(callback: types.CallbackQuery):
    addr_name = callback.data.replace("delete_", "")
    addresses = get_user_addresses(callback.from_user.id)
    if len(addresses) <= 1:
        await callback.message.edit_text("❌ Неможливо видалити єдину адресу.")
    else:
        delete_user_address(callback.from_user.id, addr_name)
        await callback.message.edit_text(f"✅ Адреса '{addr_name}' видалена.")
    await callback.answer()

@dp.callback_query(F.data.startswith("view_sched_"))
async def select_addr_view_sched(callback: types.CallbackQuery):
    addr_name = callback.data.replace("view_sched_", "")
    addresses = get_user_addresses(callback.from_user.id)
    subq = next((subq for name, subq, _ in addresses if name == addr_name), None)
    if subq:
        await send_schedule_logic(callback.from_user.id, subq, "today")
    await callback.answer()

@dp.callback_query(F.data.startswith("set_addr_q_"))
async def set_addr_queue(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    addr_name = parts[3]
    subq = f"{parts[4]}.{parts[5]}"
    update_address_queue(callback.from_user.id, addr_name, subq)
    await callback.message.edit_text(f"✅ Чергу для адреси '{addr_name}' змінено на {subq}.")
    await callback.answer()

# --- ОБРОБНИКИ НАЛАШТУВАНЬ ---
@dp.callback_query(F.data == "settings_general")
async def settings_general(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id)
    
    text = "📢 <b>Загальні налаштування сповіщень</b>\n\n"
    text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n"
    text += f"Нові графіки: {'✅ Увімкнено' if settings['new_schedule_enabled'] else '❌ Вимкнено'}\n"
    text += f"Зміни в графіках: {'✅ Увімкнено' if settings['schedule_changes_enabled'] else '❌ Вимкнено'}\n\n"
    text += "Оберіть, що змінити:"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data="toggle_general_notifications")],
        [InlineKeyboardButton(text="🆕 Нові графіки", callback_data="toggle_general_new")],
        [InlineKeyboardButton(text="🔄 Зміни в графіках", callback_data="toggle_general_changes")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("settings_addr_"))
async def settings_address(callback: types.CallbackQuery):
    addr_name = callback.data.replace("settings_addr_", "")
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id, addr_name)
    
    text = f"🏠 <b>Налаштування для адреси '{addr_name}'</b>\n\n"
    text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n\n"
    text += "Оберіть, що змінити:"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data=f"toggle_addr_{addr_name}_notifications")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_setting(callback: types.CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    
    if data == "toggle_general_notifications":
        settings = get_user_notification_settings(user_id)
        logging.info(f"Before toggle: {settings}")
        new_val = not settings['notifications_enabled']
        set_user_notification_settings(user_id, None, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])
        await callback.answer(f"Сповіщення про відключення {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
        settings = get_user_notification_settings(user_id)
        logging.info(f"After toggle: {settings}")
        text = "📢 <b>Загальні налаштування сповіщень</b>\n\n"
        text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n"
        text += f"Нові графіки: {'✅ Увімкнено' if settings['new_schedule_enabled'] else '❌ Вимкнено'}\n"
        text += f"Зміни в графіках: {'✅ Увімкнено' if settings['schedule_changes_enabled'] else '❌ Вимкнено'}\n\n"
        text += "Оберіть, що змінити:"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data="toggle_general_notifications")],
            [InlineKeyboardButton(text="🆕 Нові графіки", callback_data="toggle_general_new")],
            [InlineKeyboardButton(text="🔄 Зміни в графіках", callback_data="toggle_general_changes")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        
    elif data == "toggle_general_new":
        settings = get_user_notification_settings(user_id)
        new_val = not settings['new_schedule_enabled']
        set_user_notification_settings(user_id, None, settings['notifications_enabled'], new_val, settings['schedule_changes_enabled'])
        await callback.answer(f"Сповіщення про нові графіки {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
        settings = get_user_notification_settings(user_id)
        text = "📢 <b>Загальні налаштування сповіщень</b>\n\n"
        text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n"
        text += f"Нові графіки: {'✅ Увімкнено' if settings['new_schedule_enabled'] else '❌ Вимкнено'}\n"
        text += f"Зміни в графіках: {'✅ Увімкнено' if settings['schedule_changes_enabled'] else '❌ Вимкнено'}\n\n"
        text += "Оберіть, що змінити:"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data="toggle_general_notifications")],
            [InlineKeyboardButton(text="🆕 Нові графіки", callback_data="toggle_general_new")],
            [InlineKeyboardButton(text="🔄 Зміни в графіках", callback_data="toggle_general_changes")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        
    elif data == "toggle_general_changes":
        settings = get_user_notification_settings(user_id)
        new_val = not settings['schedule_changes_enabled']
        set_user_notification_settings(user_id, None, settings['notifications_enabled'], settings['new_schedule_enabled'], new_val)
        await callback.answer(f"Сповіщення про зміни в графіках {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
        settings = get_user_notification_settings(user_id)
        text = "📢 <b>Загальні налаштування сповіщень</b>\n\n"
        text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n"
        text += f"Нові графіки: {'✅ Увімкнено' if settings['new_schedule_enabled'] else '❌ Вимкнено'}\n"
        text += f"Зміни в графіках: {'✅ Увімкнено' if settings['schedule_changes_enabled'] else '❌ Вимкнено'}\n\n"
        text += "Оберіть, що змінити:"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data="toggle_general_notifications")],
            [InlineKeyboardButton(text="🆕 Нові графіки", callback_data="toggle_general_new")],
            [InlineKeyboardButton(text="🔄 Зміни в графіках", callback_data="toggle_general_changes")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        
    elif data.startswith("toggle_addr_"):
        parts = data.split("_")
        addr_name = parts[2]
        setting_type = parts[3]
        settings = get_user_notification_settings(user_id, addr_name)
        if setting_type == "notifications":
            new_val = not settings['notifications_enabled']
            set_user_notification_settings(user_id, addr_name, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])
            await callback.answer(f"Сповіщення про відключення для {addr_name} {'увімкнено' if new_val else 'вимкнено'}")
            
            # Оновлюємо повідомлення відразу
            settings = get_user_notification_settings(user_id, addr_name)
            text = f"🏠 <b>Налаштування для адреси '{addr_name}'</b>\n\n"
            text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n\n"
            text += "Оберіть, що змінити:"
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data=f"toggle_addr_{addr_name}_notifications")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
            ])
            
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "settings_back")
async def settings_back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    addresses = get_user_addresses(user_id)
    
    text = "⚙️ <b>Налаштування сповіщень бота</b>\n\n"
    text += "Оберіть, що налаштувати:\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Загальні сповіщення", callback_data="settings_general")],
    ])
    
    for name, _, _ in addresses:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name}", callback_data=f"settings_addr_{name}")])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# --- СТАНИ АДРЕС ---
@dp.message(AddressStates.waiting_for_new_name)
async def process_new_addr_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Назва не може бути порожньою.")
        return
    addresses = get_user_addresses(message.from_user.id)
    if any(n == name for n, _, _ in addresses):
        await message.answer("Адреса з такою назвою вже існує.")
        return
    await state.update_data(addr_name=name)
    kb = get_queue_keyboard()
    await message.answer(f"Назва '{name}' прийнята. Тепер оберіть чергу:", reply_markup=kb)
    await state.set_state(AddressStates.waiting_for_new_queue)

@dp.message(AddressStates.waiting_for_new_queue)
async def process_new_addr_queue(message: types.Message, state: FSMContext):
    # Це буде оброблено через callback, але якщо текст, ігноруємо
    pass

@dp.message(AddressStates.waiting_for_edit_name)
async def process_edit_addr_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    old_name = data['addr_name']
    new_name = message.text.strip()
    if not new_name:
        await message.answer("Назва не може бути порожньою.")
        return
    addresses = get_user_addresses(message.from_user.id)
    if any(n == new_name for n, _, _ in addresses):
        await message.answer("Адреса з такою назвою вже існує.")
        return
    update_address_name(message.from_user.id, old_name, new_name)
    await message.answer(f"✅ Назву адреси змінено з '{old_name}' на '{new_name}'.")
    await state.clear()



# --- МОНІТОРИНГ ТА СПОВІЩЕННЯ ---
async def monitor_job():
    try:
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
        
        # Get all users and their addresses
        cursor.execute('SELECT user_id, name, subqueue FROM addresses')
        all_user_addresses = cursor.fetchall()
        
        now = datetime.now()
        current_date_str = now.strftime("%d.%m.%Y")
        short_date = now.strftime("%d.%m.%y")
        
        updated_dates = []
        
        for date_key, data in all_data.items():
            try:
                is_new = date_key not in known_schedules
                has_list_now = bool(data['list'])
                had_list = known_schedules.get(date_key, {}).get('has_list', False)
                list_changed = known_schedules.get(date_key, {}).get('list', {}) != data['list']
                img_changed = known_schedules.get(date_key, {}).get('img', '') != data['img']
                
                if is_new or img_changed or (not had_list and has_list_now):
                    logging.info(f"Detected change for {date_key}: is_new={is_new}, list_changed={list_changed}, img_changed={img_changed}, has_list_now={has_list_now}, had_list={had_list}")
                    
                    old_list = known_schedules.get(date_key, {}).get('list', {})
                    new_list = data['list']
                    
                    # Determine affected subqueues
                    if is_new:
                        # New schedule - affects all subqueues
                        affected_subqueues = set(new_list.keys())
                        change_type = "new_schedule"
                    elif not had_list and has_list_now:
                        # Lists just appeared - affects all subqueues
                        affected_subqueues = set(new_list.keys())
                        change_type = "lists_added"
                    elif list_changed:
                        # Existing schedule changed - find which subqueues changed
                        affected_subqueues = set()
                        for sq in set(old_list.keys()) | set(new_list.keys()):
                            old_schedule = old_list.get(sq, "")
                            new_schedule = new_list.get(sq, "")
                            if old_schedule != new_schedule:
                                affected_subqueues.add(sq)
                        change_type = "schedule_updated"
                    else:
                        # img_changed
                        affected_subqueues = set(new_list.keys())
                        change_type = "img_updated"
                    
                    logging.info(f"Affected subqueues for {date_key}: {affected_subqueues}, change_type: {change_type}")
                    
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
                    user_notifications = {}  # uid -> list of (addr_name, subq, msg_type)
                    for uid, addr_name, subq in all_user_addresses:
                        if subq not in affected_subqueues:
                            continue  # Надсилаємо тільки якщо черга користувача була змінена
                        
                        # Перевіряємо налаштування
                        general_settings = get_user_notification_settings(uid)
                        addr_settings = get_user_notification_settings(uid, addr_name)
                        
                        send_new = addr_settings['new_schedule_enabled'] and general_settings['new_schedule_enabled']
                        send_changes = addr_settings['schedule_changes_enabled'] and general_settings['schedule_changes_enabled']
                        
                        should_send = False
                        if msg_type in ["new_tomorrow", "new_future"] and send_new:
                            should_send = True
                        elif msg_type in ["update_today", "update_tomorrow"] and send_changes:
                            should_send = True
                        
                        if should_send:
                            if uid not in user_notifications:
                                user_notifications[uid] = []
                            user_notifications[uid].append((addr_name, subq, msg_type))
                    
                    # Надсилаємо груповані сповіщення
                    for uid, notifications in user_notifications.items():
                        try:
                            if len(notifications) == 1:
                                addr_name, subq, msg_type = notifications[0]
                                if msg_type in ["new_tomorrow", "new_future"]:
                                    caption = f"🆕 <b>НОВИЙ ГРАФІК!</b>\n\nГрафік на {date_key} вже доступний на сайті для адреси <b>{addr_name}</b> (черга {subq})."
                                    await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                                    if not has_list_now:
                                        await bot.send_message(uid, "📝 <b>Зверніть увагу:</b> Детальні списки годин відключень будуть розписані трохи пізніше (зазвичай протягом години).", parse_mode="HTML")
                                elif msg_type == "update_today":
                                    await send_schedule_logic(uid, subq, "today", is_update=True)
                                elif msg_type == "update_tomorrow":
                                    if has_list_now and not had_list:
                                        caption = f"📝 <b>ОНОВЛЕННЯ ГРАФІКА!</b>\n\nДетальні списки годин відключень на {date_key} тепер доступні для адреси <b>{addr_name}</b> (черга {subq})."
                                        await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                            else:
                                # Групуємо повідомлення
                                addr_list = [f"<b>{name}</b> (черга {subq})" for name, subq, _ in notifications]
                                addr_text = ", ".join(addr_list)
                                if msg_type in ["new_tomorrow", "new_future"]:
                                    caption = f"🆕 <b>НОВИЙ ГРАФІК!</b>\n\nГрафік на {date_key} вже доступний на сайті для ваших адрес: {addr_text}."
                                    await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                                    if not has_list_now:
                                        await bot.send_message(uid, "📝 <b>Зверніть увагу:</b> Детальні списки годин відключень будуть розписані трохи пізніше (зазвичай протягом години).", parse_mode="HTML")
                                elif msg_type == "update_today":
                                    # Для оновлень сьогодні надсилаємо для основної адреси або першої
                                    main_addr = next((name for name, _, is_main in get_user_addresses(uid) if is_main), notifications[0][0])
                                    main_subq = next(subq for name, subq, _ in notifications if name == main_addr)
                                    await send_schedule_logic(uid, main_subq, "today", is_update=True)
                                elif msg_type == "update_tomorrow":
                                    if has_list_now and not had_list:
                                        caption = f"📝 <b>ОНОВЛЕННЯ ГРАФІКА!</b>\n\nДетальні списки годин відключень на {date_key} тепер доступні для ваших адрес: {addr_text}."
                                        await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                        except Exception as e:
                            logging.error(f"Failed to send notification to {uid}: {e}")
                        await asyncio.sleep(0.05)
                    
                    # Update known
                    known_schedules[date_key] = {
                        'img': data['img'],
                        'list': data['list'],
                        'has_list': has_list_now
                    }
            except Exception as e:
                logging.error(f"Error processing date {date_key}: {e}")
                continue
        
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
            try:
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
                
                # Знаходимо точки зміни в найближчі 30 хв
                t30_dt = now + timedelta(minutes=30)
                user_alerts = {}  # uid -> list of (change_dt, is_shutdown, addr_names)
                
                for start_dt, end_dt in combined_intervals:
                    change_points = [(start_dt, True), (end_dt, False)]  # True = shutdown, False = restore
                    for change_dt, is_shutdown in change_points:
                        if now < change_dt <= t30_dt:
                            minutes_left = int((change_dt - now).total_seconds() / 60)
                            change_time_str = change_dt.strftime("%H:%M")
                            event_date = change_dt.strftime("%Y-%m-%d")
                            
                            # Знаходимо користувачів з цією чергою
                            cursor.execute('SELECT user_id, GROUP_CONCAT(name) FROM addresses WHERE subqueue = ? GROUP BY user_id', (sub_q,))
                            users_in_q = cursor.fetchall()
                            for uid, addr_names_str in users_in_q:
                                # Перевіряємо налаштування
                                general_settings = get_user_notification_settings(uid)
                                if not general_settings['notifications_enabled']:
                                    continue
                                
                                addr_list = addr_names_str.split(',')
                                # Перевіряємо налаштування для кожної адреси
                                enabled_addrs = []
                                for addr_name in addr_list:
                                    addr_settings = get_user_notification_settings(uid, addr_name.strip())
                                    if addr_settings['notifications_enabled']:
                                        enabled_addrs.append(addr_name.strip())
                                
                                if not enabled_addrs:
                                    continue
                                
                                # Перевіряємо, чи вже надсилали
                                cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?', 
                                               (uid, change_time_str, event_date))
                                if cursor.fetchone():
                                    continue
                                
                                if uid not in user_alerts:
                                    user_alerts[uid] = []
                                user_alerts[uid].append((change_dt, is_shutdown, enabled_addrs, sub_q))
                
                # Надсилаємо сповіщення користувачам
                for uid, alerts in user_alerts.items():
                    # Групуємо за часом
                    time_groups = {}
                    for change_dt, is_shutdown, addrs, subq in alerts:
                        key = (change_dt, is_shutdown)
                        if key not in time_groups:
                            time_groups[key] = []
                        time_groups[key].extend(addrs)
                    
                    for (change_dt, is_shutdown), addr_list in time_groups.items():
                        minutes_left = int((change_dt - now).total_seconds() / 60)
                        change_time_str = change_dt.strftime("%H:%M")
                        event_date = change_dt.strftime("%Y-%m-%d")
                        
                        if is_shutdown:
                            alert_base = f"⚠️ <b>Увага! Відключення світла</b>\n\nЧерез {minutes_left} хв ({change_time_str}) подача електроенергії буде <b>припинена</b>"
                        else:
                            alert_base = f"✅ <b>Відновлення електроенергії</b>\n\nЧерез {minutes_left} хв ({change_time_str}) подача електроенергії буде <b>відновлена</b>"
                        
                        if len(addr_list) == 1:
                            alert_msg = f"{alert_base} для вашої адреси <b>{addr_list[0]}</b>."
                        else:
                            addr_text = ", ".join(addr_list)
                            alert_msg = f"{alert_base} для ваших адрес: <b>{addr_text}</b>."
                        
                        try:
                            await bot.send_message(uid, alert_msg, parse_mode="HTML")
                            cursor.execute('INSERT INTO sent_alerts VALUES (?, ?, ?)', (uid, change_time_str, event_date))
                            conn.commit()
                        except Exception as e:
                            logging.error(f"Failed to send alert to {uid}: {e}")
            except Exception as e:
                logging.error(f"Error processing subqueue {sub_q}: {e}")
                continue
        
        # Clean up old sent alerts (older than today)
        logging.info("Cleaning up old sent_alerts")
        cursor.execute('DELETE FROM sent_alerts WHERE event_date < ?', (now.strftime("%Y-%m-%d"),))
        conn.commit()
        
        # Delete old clock files for updated dates
        for date_key in updated_dates:
            date_clean = date_key.replace('.', '_')
            for file in os.listdir('clocks'):
                if date_clean in file and file.endswith('.png'):
                    try:
                        os.remove(os.path.join('clocks', file))
                    except:
                        pass
        
        conn.close()
    except Exception as e:
        logging.error(f"Error in monitor_job: {e}")
async def process_broadcast_message(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:  # Додаткова перевірка
        await message.answer("❌ Доступ заборонено.")
        await state.clear()
        return
    
    broadcast_text = message.text
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT user_id FROM addresses')
    users = cursor.fetchall()
    conn.close()
    
    sent_count = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, broadcast_text, parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.1)  # Щоб не перевантажувати
        except Exception as e:
            logging.error(f"Failed to send to {uid}: {e}")
    
    await message.answer(f"✅ Повідомлення відправлено {sent_count} користувачам.")
    await state.clear()

async def main():
    init_db()
    scheduler.add_job(monitor_job, 'interval', minutes=5)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())