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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from PIL import Image, ImageDraw, ImageFont
import math
import os

# --- НАЛАШТУВАННЯ ЧАСУ ---
# os.environ['TZ'] = 'Europe/Kyiv'
# if hasattr(time, 'tzset'):
#     time.tzset()

# --- НАЛАШТУВАННЯ ---
TOKEN = "8555435292:AAFoqkxaaPI3Vfepf8xMRv723Fly279V6no"  # Той самий, але для тесту
URL_PAGE = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"
ADMIN_USER_ID = 1667269941  # Ваш user_id

# --- НАЛАШТУВАННЯ ПЛАТЕЖІВ ---
# Для Telegram Stars (рекомендовано):
PAYMENT_PROVIDER_TOKEN = ""  # Залишаємо пустим для Stars

# Для інших платіжних систем (як Portmone, Stripe тощо):
# PAYMENT_PROVIDER_TOKEN = "Ваш_токен_від_платіжної_системи"

# Альтернативні варіанти для тестування:
# PAYMENT_PROVIDER_TOKEN = "284685063:TEST:Z2x0X00Xn4t7R6hY5n3"  # Stripe тестовий токен
# PAYMENT_PROVIDER_TOKEN = "381764678:TEST:1234567890"  # Portmone тестовий токен

CURRENCY = "XTR"  # Telegram Stars
# Для інших валют: "UAH", "USD", "EUR" тощо

RGB_SUBSCRIPTION_PRICE = 50  # Ціна в зірках (для XTR) або копійках/центах

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
    conn = sqlite3.connect('test_users.db')
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
    # Підписки користувачів
    cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, subscription_type TEXT, expiry_date TEXT)')
    
    # Міграція наявних користувачів
    cursor.execute('SELECT user_id, subqueue FROM users WHERE subqueue IS NOT NULL')
    existing_users = cursor.fetchall()
    for user_id, subqueue in existing_users:
        # Перевіряємо, чи вже є адреси для цього користувача
        cursor.execute('SELECT COUNT(*) FROM addresses WHERE user_id = ?', (user_id,))
        if cursor.fetchone()[0] == 0:
            # Додаємо основну адресу "Дім"
            cursor.execute('INSERT INTO addresses (user_id, name, subqueue, is_main) VALUES (?, ?, ?, 1)', (user_id, 'Дім', subqueue))
    
    conn.commit()
    conn.close()

def update_user_queue(user_id, subqueue):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, subqueue) VALUES (?, ?)', (user_id, subqueue))
    conn.commit()
    conn.close()

def get_user_subqueue(user_id):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT subqueue FROM addresses WHERE user_id = ? AND is_main = 1', (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

# --- ФУНКЦІЇ ДЛЯ АДРЕС ---
def get_user_addresses(user_id):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, subqueue, is_main FROM addresses WHERE user_id = ? ORDER BY is_main DESC, name', (user_id,))
    addresses = cursor.fetchall()
    conn.close()
    return addresses

def add_user_address(user_id, name, subqueue):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO addresses (user_id, name, subqueue, is_main) VALUES (?, ?, ?, 0)', (user_id, name, subqueue))
    conn.commit()
    conn.close()

def update_address_name(user_id, old_name, new_name):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE addresses SET name = ? WHERE user_id = ? AND name = ?', (new_name, user_id, old_name))
    conn.commit()
    conn.close()

def update_address_queue(user_id, name, new_subqueue):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE addresses SET subqueue = ? WHERE user_id = ? AND name = ?', (new_subqueue, user_id, name))
    conn.commit()
    conn.close()

def set_main_address(user_id, name):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE addresses SET is_main = 0 WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE addresses SET is_main = 1 WHERE user_id = ? AND name = ?', (user_id, name))
    conn.commit()
    conn.close()

def delete_user_address(user_id, name):
    conn = sqlite3.connect('test_users.db')
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
    conn.commit()
    conn.close()

# --- ФУНКЦІЇ ДЛЯ ПІДПИСОК ---
def add_subscription(user_id, subscription_type, days=30):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    expiry_date = (datetime.now() + timedelta(days=days)).isoformat()
    cursor.execute('INSERT OR REPLACE INTO subscriptions (user_id, subscription_type, expiry_date) VALUES (?, ?, ?)', 
                   (user_id, subscription_type, expiry_date))
    conn.commit()
    conn.close()

def get_subscription(user_id):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT subscription_type, expiry_date FROM subscriptions WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    conn.close()
    if res:
        sub_type, expiry_str = res
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now() < expiry:
            return sub_type
    return None

def remove_subscription(user_id):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

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

def generate_clock_image(subqueue, time_text, date_info, rgb_enabled=False):
    # Створюємо зображення годинника
    os.makedirs('test_clocks', exist_ok=True)
    filename = f"test_clocks/{subqueue}_{date_info.replace('.', '_')}.png"
    if rgb_enabled:
        filename = f"test_clocks/{subqueue}_{date_info.replace('.', '_')}.gif"
    
    # Очищення старих файлів (старіше 24 годин) на кожному виклику
    now = datetime.now()
    for file in os.listdir('test_clocks'):
        filepath = os.path.join('test_clocks', file)
        if os.path.isfile(filepath):
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if (now - file_mtime).total_seconds() > 86400:  # 24 години
                os.remove(filepath)
    size = 600
    img = Image.new('RGB', (size, size), (220, 220, 220))  # Змінив на RGB для GIF
    draw = ImageDraw.Draw(img)
    
    center = size // 2
    radius = 250
    
    # Фон годинника з градієнтом
    for r in range(radius, 0, -1):
        alpha = int(255 * (1 - r / radius))
        # Для RGB симулюємо alpha змішуванням з фоном
        bg_r, bg_g, bg_b = 220, 220, 220
        color_r = int((200 * alpha + bg_r * (255 - alpha)) / 255)
        color_g = int((220 * alpha + bg_g * (255 - alpha)) / 255)
        color_b = int((255 * alpha + bg_b * (255 - alpha)) / 255)
        color = (color_r, color_g, color_b)
        draw.ellipse((center - r, center - r, center + r, center + r), fill=color)
    
    # Зовнішнє коло
    draw.ellipse((center - radius, center - radius, center + radius, center + radius), 
                 outline=(100, 100, 100), width=3)
    
    # Спроба завантажити більший шрифт
    try:
        font = ImageFont.truetype(os.path.join('C:\\Windows\\Fonts', 'arial.ttf'), 32)
    except:
        try:
            font = ImageFont.truetype('arial.ttf', 32)
        except:
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
    
    for i, (start_str, end_str) in enumerate(intervals):
        try:
            start_h, start_m = map(int, start_str.split(':'))
            end_h, end_m = map(int, end_str.split(':'))
            
            start_angle = (start_h * 15 + start_m * 0.25) - 90
            end_angle = (end_h * 15 + end_m * 0.25) - 90
            
            if end_angle < start_angle:
                end_angle += 360
            
            # RGB сегменти для підписаних користувачів
            if rgb_enabled:
                # Різні кольори для кожного сегменту
                colors = [(255, 0, 0), (255, 165, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (128, 0, 128)]
                color = colors[i % len(colors)]
            else:
                # Також різнокольорові сегменти для звичайних користувачів
                colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100), (255, 100, 255), (100, 255, 255)]
                color = colors[i % len(colors)]
            
            # Малюємо дугу відключення (невелику)
            draw.arc((center - radius + 20, center - radius + 20, center + radius - 20, center + radius - 20),
                     start=start_angle, end=end_angle, fill=color, width=40)
        except:
            continue
    
    # Стрілка поточного часу прибрана
    
    # Текст інформації в верхньому лівому куті
    text = f"{date_info}\nЧерга {subqueue}"
    draw.text((10, 10), text, fill=(0, 0, 0), font=font)
    
    if rgb_enabled:
        try:
            # Створюємо анімований GIF з RGB підсвіткою
            frames = []
            for frame_idx in range(10):  # 10 кадрів
                frame = img.copy()
                frame_draw = ImageDraw.Draw(frame)
                
                # Анімовані сегменти відключення
                for i, (start_str, end_str) in enumerate(intervals):
                    try:
                        start_h, start_m = map(int, start_str.split(':'))
                        end_h, end_m = map(int, end_str.split(':'))
                        
                        start_angle = (start_h * 15 + start_m * 0.25) - 90
                        end_angle = (end_h * 15 + end_m * 0.25) - 90
                        
                        if end_angle < start_angle:
                            end_angle += 360
                        
                        # Анімований колір для сегменту - переливання кольорів по черзі
                        colors = [(255, 0, 0), (255, 165, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (128, 0, 128)]
                        # Зсув кольору залежно від кадру + індексу сегменту для ефекту "обертання"
                        color_index = (frame_idx + i) % len(colors)
                        animated_color = colors[color_index]
                        
                        frame_draw.arc((center - radius + 20, center - radius + 20, center + radius - 20, center + radius - 20),
                                       start=start_angle, end=end_angle, fill=animated_color, width=40)
                    except:
                        continue
                
                # Додаємо RGB рамку, яка змінюється
                border_width = 15
                r = (frame_idx * 25) % 255
                g = (frame_idx * 50) % 255
                b = (frame_idx * 75) % 255
                for j in range(border_width):
                    alpha_sim = 255 - j * 15  # Симулюємо alpha
                    bg_r, bg_g, bg_b = 220, 220, 220
                    color_r = int((r * alpha_sim + bg_r * (255 - alpha_sim)) / 255)
                    color_g = int((g * alpha_sim + bg_g * (255 - alpha_sim)) / 255)
                    color_b = int((b * alpha_sim + bg_b * (255 - alpha_sim)) / 255)
                    frame_draw.rectangle([j, j, size-j-1, size-j-1], outline=(color_r, color_g, color_b), width=1)
                frames.append(frame)
            frames[0].save(filename, save_all=True, append_images=frames[1:], duration=200, loop=0)
        except Exception as e:
            logging.error(f"Failed to create GIF: {e}")
            # Fallback: створити PNG з рамкою
            filename = filename.replace('.gif', '.png')
            import random
            border_width = 15
            for i in range(border_width):
                r = random.randint(0, 255)
                g = random.randint(0, 255)
                b = random.randint(0, 255)
                draw.rectangle([i, i, size-i-1, size-i-1], outline=(r, g, b), width=1)
            img.save(filename)
    else:
        # RGB підсвітка для підписаних користувачів (статична)
        import random
        border_width = 15
        for i in range(border_width):
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)
            draw.rectangle([i, i, size-i-1, size-i-1], outline=(r, g, b), width=1)
        
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
        [KeyboardButton(text="🏠 Керування адресами"), KeyboardButton(text="☕ Підтримати бота")],
        [KeyboardButton(text="👨‍💻 Зв'язок з розробником"), KeyboardButton(text="🧪 Тестове меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_test_menu():
    kb = [
        [KeyboardButton(text="📊 Показати всі графіки на сьогодні")],
        [KeyboardButton(text="📅 Показати всі графіки на завтра")],
        [KeyboardButton(text="🔔 Меню сповіщень")],
        [KeyboardButton(text="💾 Показати базу даних")],
        [KeyboardButton(text="🗑️ Очистити історію сповіщень")],
        [KeyboardButton(text="🌈 Купити RGB-підписку")],
        [KeyboardButton(text="❌ Видалити RGB-підписку")],
        [KeyboardButton(text="🔙 Назад до головного меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_notifications_menu():
    kb = [
        [KeyboardButton(text="🕐 Найближчі сповіщення (1 год)")],
        [KeyboardButton(text="📋 Сповіщення за моєю чергою (сьогодні)")],
        [KeyboardButton(text="📊 Всі сповіщення сьогодні")],
        [KeyboardButton(text="🔄 Перевірка переходу С-З")],
        [KeyboardButton(text="📅 Сповіщення завтра")],
        [KeyboardButton(text="🔙 Назад до тестового меню")]
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
        
        # Генеруємо годинник
        rgb_enabled = has_rgb_subscription(chat_id)
        clock_file = generate_clock_image(subqueue, time_text, data['raw_date'], rgb_enabled)
        try:
            if os.path.exists(clock_file) and clock_file.endswith('.gif'):
                await bot.send_animation(chat_id, animation=types.FSInputFile(clock_file), caption=msg, parse_mode="Markdown")
            else:
                await bot.send_photo(chat_id, photo=types.FSInputFile(clock_file), caption=msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send clock to {chat_id}: {e}")
            # Fallback to original
            try:
                await bot.send_photo(chat_id, photo=img_url, caption=msg, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Failed to send schedule to {chat_id}: {e}")

# --- ОБРОБНИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 **Вітаю!** Оберіть свою підчергу:", reply_markup=get_queue_keyboard(), parse_mode="Markdown")
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
    
    text = "🏠 **Ваші адреси:**\n\n"
    for name, subq, is_main in addresses:
        main_mark = " (основна)" if is_main else ""
        text += f"• **{name}**: черга {subq}{main_mark}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати адресу", callback_data="addr_add")],
        [InlineKeyboardButton(text="✏️ Редагувати назву", callback_data="addr_edit_name")],
        [InlineKeyboardButton(text="🔄 Змінити чергу", callback_data="addr_edit_queue")],
        [InlineKeyboardButton(text="⭐ Зробити основною", callback_data="addr_set_main")],
        [InlineKeyboardButton(text="🗑️ Видалити адресу", callback_data="addr_delete")],
        [InlineKeyboardButton(text="👀 Переглянути графіки", callback_data="addr_view_schedules")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("set_q_"))
async def callback_set_queue(callback: types.CallbackQuery, state: FSMContext):
    subq = callback.data.replace("set_q_", "")
    current_state = await state.get_state()
    if current_state == AddressStates.waiting_for_new_queue:
        # Додаємо нову адресу
        data = await state.get_data()
        name = data['addr_name']
        add_user_address(callback.from_user.id, name, subq)
        await callback.message.edit_text(f"✅ **Успішно!**\nСтворено адресу **{name}** з чергою **{subq}**.", parse_mode="Markdown")
        await state.clear()
    else:
        # Оновлюємо чергу основної адреси
        addresses = get_user_addresses(callback.from_user.id)
        if addresses:
            main_addr = next((name for name, _, is_main in addresses if is_main), None)
            if main_addr:
                update_address_queue(callback.from_user.id, main_addr, subq)
                await callback.message.edit_text(f"✅ **Успішно!**\nОбрано підчергу **{subq}** для адреси **{main_addr}**.", parse_mode="Markdown")
                await send_schedule_logic(callback.from_user.id, subq, "today")
            else:
                await callback.message.edit_text("❌ Помилка: немає основної адреси.")
        else:
            # Якщо немає адрес, створюємо "Дім"
            add_user_address(callback.from_user.id, "Дім", subq)
            set_main_address(callback.from_user.id, "Дім")
            await callback.message.edit_text(f"✅ **Успішно!**\nСтворено адресу **Дім** з чергою **{subq}**.", parse_mode="Markdown")
            await send_schedule_logic(callback.from_user.id, subq, "today")
    await callback.answer()

# --- ОБРОБНИКИ АДРЕС ---
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

@dp.message(F.text == "🧪 Тестове меню")
async def test_menu(message: types.Message):
    await message.answer("🧪 **Тестове меню**", reply_markup=get_test_menu())

@dp.message(F.text == "📊 Показати всі графіки на сьогодні")
async def show_all_today(message: types.Message):
    all_data = await parse_hoe_smart()
    target_dt = datetime.now()
    date_str = target_dt.strftime("%d.%m.%Y")
    short_date = target_dt.strftime("%d.%m.%y")
    data = all_data.get(date_str) or all_data.get(short_date)

    if not data:
        await message.answer("❌ Дані не знайдені.")
        return

    schedules = data['list']
    if not schedules:
        await message.answer("🖼 Графіки ще не розписані.")
        return

    msg = f"📊 **Всі графіки на {date_str}**\n\n"
    for subq, time_text in schedules.items():
        msg += f"**{subq}:** {time_text}\n"
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "📅 Показати всі графіки на завтра")
async def show_all_tomorrow(message: types.Message):
    all_data = await parse_hoe_smart()
    target_dt = datetime.now() + timedelta(days=1)
    date_str = target_dt.strftime("%d.%m.%Y")
    short_date = target_dt.strftime("%d.%m.%y")
    data = all_data.get(date_str) or all_data.get(short_date)

    if not data:
        await message.answer("🕠 Графік на завтра ще не опубліковано.")
        return

    schedules = data['list']
    if not schedules:
        await message.answer("🖼 Графіки ще не розписані.")
        return

    msg = f"📅 **Всі графіки на {date_str}**\n\n"
    for subq, time_text in schedules.items():
        msg += f"**{subq}:** {time_text}\n"
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "🔔 Меню сповіщень")
async def notifications_menu(message: types.Message):
    await message.answer("🔔 **Меню сповіщень**", reply_markup=get_notifications_menu())

@dp.message(F.text == "🕐 Найближчі сповіщення (1 год)")
async def nearest_alerts(message: types.Message):
    all_data = await parse_hoe_smart()
    if not all_data:
        await message.answer("❌ Не вдалося отримати дані.")
        return

    now = datetime.now()
    current_date_str = now.strftime("%d.%m.%Y")
    short_date = now.strftime("%d.%m.%y")
    data_today = all_data.get(current_date_str) or all_data.get(short_date)
    if not data_today:
        await message.answer("❌ Дані на сьогодні не знайдені.")
        return

    schedules_today = data_today['list']
    tomorrow_dt = now + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")
    tomorrow_short = tomorrow_dt.strftime("%d.%m.%y")
    data_tomorrow = all_data.get(tomorrow_str) or all_data.get(tomorrow_short)
    schedules_tomorrow = data_tomorrow['list'] if data_tomorrow else {}

    alerts = []
    t60_dt = now + timedelta(minutes=60)

    for sub_q in schedules_today.keys():
        time_text_today = schedules_today.get(sub_q, "")
        time_text_tomorrow = schedules_tomorrow.get(sub_q, "")

        combined_intervals = []
        intervals_today = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_today.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_today:
            start_dt = datetime.combine(now.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((now + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(now.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))

        intervals_tomorrow = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_tomorrow.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_tomorrow:
            start_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((tomorrow_dt + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))

        for start_dt, end_dt in combined_intervals:
            for change_dt in [start_dt, end_dt]:
                if now < change_dt <= t60_dt:
                    minutes_left = int((change_dt - now).total_seconds() / 60)
                    change_time_str = change_dt.strftime("%H:%M")
                    event_type = "Відключення" if change_dt == start_dt else "Відновлення"
                    alerts.append(f"**{sub_q}** - {event_type} о {change_time_str} (через {minutes_left} хв)")

    if alerts:
        msg = "🕐 **Найближчі сповіщення (1 година):**\n\n" + "\n".join(alerts)
    else:
        msg = "🕐 Немає сповіщень у найближчу годину."
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "📋 Сповіщення за моєю чергою (сьогодні)")
async def alerts_for_my_queue_today(message: types.Message):
    subq = get_user_subqueue(message.from_user.id)
    if not subq:
        await message.answer("❌ Спочатку оберіть чергу.")
        return

    all_data = await parse_hoe_smart()
    if not all_data:
        await message.answer("❌ Не вдалося отримати дані.")
        return

    now = datetime.now()
    current_date_str = now.strftime("%d.%m.%Y")
    short_date = now.strftime("%d.%m.%y")
    data_today = all_data.get(current_date_str) or all_data.get(short_date)
    if not data_today:
        await message.answer("❌ Дані на сьогодні не знайдені.")
        return

    schedules_today = data_today['list']
    tomorrow_dt = now + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")
    tomorrow_short = tomorrow_dt.strftime("%d.%m.%y")
    data_tomorrow = all_data.get(tomorrow_str) or all_data.get(tomorrow_short)
    schedules_tomorrow = data_tomorrow['list'] if data_tomorrow else {}

    time_text_today = schedules_today.get(subq, "")
    time_text_tomorrow = schedules_tomorrow.get(subq, "")

    combined_intervals = []
    intervals_today = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_today.replace("з ", "").replace(" до ", "-"))
    for start, end in intervals_today:
        start_dt = datetime.combine(now.date(), datetime.strptime(start, "%H:%M").time())
        if end == '24:00':
            end_dt = datetime.combine((now + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
        else:
            end_dt = datetime.combine(now.date(), datetime.strptime(end, "%H:%M").time())
        combined_intervals.append((start_dt, end_dt))

    intervals_tomorrow = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_tomorrow.replace("з ", "").replace(" до ", "-"))
    for start, end in intervals_tomorrow:
        start_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(start, "%H:%M").time())
        if end == '24:00':
            end_dt = datetime.combine((tomorrow_dt + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
        else:
            end_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(end, "%H:%M").time())
        combined_intervals.append((start_dt, end_dt))

    alerts = []
    for start_dt, end_dt in combined_intervals:
        start_time = start_dt.strftime("%H:%M")
        end_time = end_dt.strftime("%H:%M")
        alerts.append(f"Відключення: {start_time} - Відновлення: {end_time}")

    if alerts:
        msg = f"📋 **Сповіщення за чергою {subq} (сьогодні):**\n\n" + "\n".join(alerts)
    else:
        msg = f"📋 Немає сповіщень за чергою {subq} сьогодні."
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "📊 Всі сповіщення сьогодні")
async def all_alerts_today(message: types.Message):
    all_data = await parse_hoe_smart()
    if not all_data:
        await message.answer("❌ Не вдалося отримати дані.")
        return

    now = datetime.now()
    current_date_str = now.strftime("%d.%m.%Y")
    short_date = now.strftime("%d.%m.%y")
    data_today = all_data.get(current_date_str) or all_data.get(short_date)
    if not data_today:
        await message.answer("❌ Дані на сьогодні не знайдені.")
        return

    schedules_today = data_today['list']
    tomorrow_dt = now + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")
    tomorrow_short = tomorrow_dt.strftime("%d.%m.%y")
    data_tomorrow = all_data.get(tomorrow_str) or all_data.get(tomorrow_short)
    schedules_tomorrow = data_tomorrow['list'] if data_tomorrow else {}

    msg = "📊 **Всі сповіщення сьогодні (таблиця):**\n\n"
    msg += "| Черга | Відключення | Відновлення |\n"
    msg += "|-------|-------------|-------------|\n"

    for sub_q in sorted(schedules_today.keys()):
        time_text_today = schedules_today.get(sub_q, "")
        time_text_tomorrow = schedules_tomorrow.get(sub_q, "")

        combined_intervals = []
        intervals_today = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_today.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_today:
            start_dt = datetime.combine(now.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((now + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(now.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))

        intervals_tomorrow = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_tomorrow.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_tomorrow:
            start_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((tomorrow_dt + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))

        if combined_intervals:
            for start_dt, end_dt in combined_intervals:
                start_time = start_dt.strftime("%H:%M")
                end_time = end_dt.strftime("%H:%M")
                msg += f"| {sub_q} | {start_time} | {end_time} |\n"
        else:
            msg += f"| {sub_q} | - | - |\n"

    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "🔄 Перевірка переходу С-З")
async def check_transition(message: types.Message):
    all_data = await parse_hoe_smart()
    if not all_data:
        await message.answer("❌ Не вдалося отримати дані.")
        return

    now = datetime.now()
    current_date_str = now.strftime("%d.%m.%Y")
    short_date = now.strftime("%d.%m.%y")
    data_today = all_data.get(current_date_str) or all_data.get(short_date)
    if not data_today:
        await message.answer("❌ Дані на сьогодні не знайдені.")
        return

    schedules_today = data_today['list']
    tomorrow_dt = now + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")
    tomorrow_short = tomorrow_dt.strftime("%d.%m.%y")
    data_tomorrow = all_data.get(tomorrow_str) or all_data.get(tomorrow_short)
    schedules_tomorrow = data_tomorrow['list'] if data_tomorrow else {}

    msg = "🔄 **Перевірка переходу Сьогодні-Завтра:**\n\n"
    msg += "Перевірка на дублюючі сповіщення та правильність злиття інтервалів.\n\n"

    issues = []
    for sub_q in schedules_today.keys():
        time_text_today = schedules_today.get(sub_q, "")
        time_text_tomorrow = schedules_tomorrow.get(sub_q, "")

        combined_intervals = []
        intervals_today = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_today.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_today:
            start_dt = datetime.combine(now.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((now + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(now.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))

        intervals_tomorrow = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text_tomorrow.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals_tomorrow:
            start_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((tomorrow_dt + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(end, "%H:%M").time())
            combined_intervals.append((start_dt, end_dt))

        # Check for overlaps or gaps
        sorted_intervals = sorted(combined_intervals, key=lambda x: x[0])
        for i in range(len(sorted_intervals) - 1):
            if sorted_intervals[i][1] > sorted_intervals[i+1][0]:
                issues.append(f"⚠️ Перекриття в {sub_q}: {sorted_intervals[i][1].strftime('%H:%M')} > {sorted_intervals[i+1][0].strftime('%H:%M')}")
            elif sorted_intervals[i][1] < sorted_intervals[i+1][0]:
                issues.append(f"ℹ️ Проміжок в {sub_q}: {sorted_intervals[i][1].strftime('%H:%M')} - {sorted_intervals[i+1][0].strftime('%H:%M')}")

    if issues:
        msg += "\n".join(issues)
    else:
        msg += "✅ Ніяких проблем з переходом не виявлено."

    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "📅 Сповіщення завтра")
async def alerts_tomorrow(message: types.Message):
    all_data = await parse_hoe_smart()
    if not all_data:
        await message.answer("❌ Не вдалося отримати дані.")
        return

    tomorrow_dt = datetime.now() + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")
    tomorrow_short = tomorrow_dt.strftime("%d.%m.%y")
    data_tomorrow = all_data.get(tomorrow_str) or all_data.get(tomorrow_short)
    if not data_tomorrow:
        await message.answer("🕠 Графік на завтра ще не опубліковано.")
        return

    schedules_tomorrow = data_tomorrow['list']
    if not schedules_tomorrow:
        await message.answer("🖼 Деталі графіка ще не розписані.")
        return

    msg = "📅 **Сповіщення завтра:**\n\n"
    for sub_q in sorted(schedules_tomorrow.keys()):
        time_text = schedules_tomorrow[sub_q]
        intervals = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", time_text.replace("з ", "").replace(" до ", "-"))
        for start, end in intervals:
            start_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(start, "%H:%M").time())
            if end == '24:00':
                end_dt = datetime.combine((tomorrow_dt + timedelta(days=1)).date(), datetime.strptime('00:00', "%H:%M").time())
            else:
                end_dt = datetime.combine(tomorrow_dt.date(), datetime.strptime(end, "%H:%M").time())
            msg += f"**{sub_q}**: Відключення {start} - Відновлення {end}\n"

    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "🔙 Назад до тестового меню")
async def back_to_test_menu(message: types.Message):
    await message.answer("🧪 **Тестове меню**", reply_markup=get_test_menu())

@dp.message(F.text == "💾 Показати базу даних")
async def show_db(message: types.Message):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, subqueue FROM users')
    users = cursor.fetchall()
    cursor.execute('SELECT key, value FROM settings')
    settings = cursor.fetchall()
    cursor.execute('SELECT user_id, event_time, event_date FROM sent_alerts')
    alerts = cursor.fetchall()
    conn.close()

    msg = "💾 **База даних**\n\n"
    msg += "**Користувачі:**\n"
    for uid, subq in users:
        msg += f"ID {uid}: {subq}\n"
    msg += "\n**Налаштування:**\n"
    for key, val in settings:
        msg += f"{key}: {val}\n"
    msg += "\n**Історія сповіщень:**\n"
    for uid, time, date in alerts:
        msg += f"ID {uid}: {time} ({date})\n"
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text == "🗑️ Очистити історію сповіщень")
async def clear_alerts_cmd(message: types.Message):
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sent_alerts')
    conn.commit()
    conn.close()
    await message.answer("🗑️ Історія сповіщень очищена.")

@dp.message(F.text == "🌈 Купити RGB-підписку")
async def buy_rgb_subscription(message: types.Message):
    user_id = message.from_user.id
    current_sub = get_subscription(user_id)
    if current_sub == 'rgb':
        # Actually, need to get expiry date
        conn = sqlite3.connect('test_users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT expiry_date FROM subscriptions WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        conn.close()
        if res:
            expiry_str = res[0]
            expiry = datetime.fromisoformat(expiry_str)
            await message.answer(f"🌈 У вас вже є активна RGB-підписка до {expiry.strftime('%d.%m.%Y %H:%M')}!")
        else:
            await message.answer("🌈 У вас вже є активна RGB-підписка!")
    else:
        # Створюємо invoice для оплати зірками
        prices = [LabeledPrice(label="RGB-підписка на 30 днів", amount=RGB_SUBSCRIPTION_PRICE)]

        try:
            await bot.send_invoice(
                chat_id=user_id,
                title="🌈 RGB-підписка для годинника",
                description="Отримайте анімований годинник з кольоровими сегментами відключення та RGB-рамкою на 30 днів!",
                payload=f"rgb_subscription_{user_id}",
                provider_token=PAYMENT_PROVIDER_TOKEN,
                currency=CURRENCY,
                prices=prices,
                start_parameter="rgb_subscription",
                photo_url="https://via.placeholder.com/512x512.png?text=RGB+Clock",  # Можна замінити на реальне фото
                photo_width=512,
                photo_height=512
            )
        except Exception as e:
            logging.error(f"Failed to send invoice: {e}")
            await message.answer("❌ Помилка створення платежу. Спробуйте пізніше.")

@dp.message(F.text == "❌ Видалити RGB-підписку")
async def remove_rgb_subscription(message: types.Message):
    user_id = message.from_user.id
    current_sub = get_subscription(user_id)
    if current_sub == 'rgb':
        remove_subscription(user_id)
        await message.answer("❌ RGB-підписка видалена!\nТепер ви можете купити її знову для тестування.")
    else:
        await message.answer("❌ У вас немає активної RGB-підписки.")

# --- ОБРОБНИКИ ПЛАТЕЖІВ ---
@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    """Обробка pre-checkout query перед оплатою"""
    try:
        # Перевіряємо payload
        if pre_checkout_query.invoice_payload.startswith("rgb_subscription_"):
            user_id = int(pre_checkout_query.invoice_payload.split("_")[2])
            if user_id == pre_checkout_query.from_user.id:
                await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
            else:
                await bot.answer_pre_checkout_query(
                    pre_checkout_query.id,
                    ok=False,
                    error_message="❌ Помилка користувача"
                )
        else:
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="❌ Невірний товар"
            )
    except Exception as e:
        logging.error(f"Pre-checkout error: {e}")
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="❌ Помилка обробки платежу"
        )

@dp.message(F.content_type == "successful_payment")
async def process_successful_payment(message: types.Message):
    """Обробка успішної оплати"""
    try:
        payment_info = message.successful_payment
        payload = payment_info.invoice_payload

        if payload.startswith("rgb_subscription_"):
            user_id = int(payload.split("_")[2])

            # Перевіряємо що оплата від правильного користувача
            if user_id == message.from_user.id:
                # Активуємо підписку
                add_subscription(user_id, 'rgb', 30)

                # Надсилаємо підтвердження
                await message.answer(
                    "🎉 **Платіж успішний!**\n\n"
                    "🌈 RGB-підписка активована на 30 днів!\n"
                    "Тепер ваші графіки годинника матимуть:\n"
                    "• Анімовану RGB-рамку\n"
                    "• Переливні кольорові сегменти відключення\n"
                    "• Ефект 'танцюючих' кольорів\n\n"
                    "Спробуйте запросити графік! ✨"
                )

                # Логуємо успішну покупку
                logging.info(f"RGB subscription purchased by user {user_id}")
            else:
                await message.answer("❌ Помилка активації підписки")
                logging.error(f"Payment user mismatch: expected {user_id}, got {message.from_user.id}")
        else:
            await message.answer("❌ Невідомий тип платежу")

    except Exception as e:
        logging.error(f"Payment processing error: {e}")
        await message.answer("❌ Помилка обробки платежу. Зв'яжіться з підтримкою.")

@dp.message(F.text == "🔙 Назад до головного меню")
async def back_to_main(message: types.Message):
    await message.answer("Керування ботом 👇", reply_markup=get_main_menu())

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
    # Беремо перший доступний
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

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ заборонено.")
        return
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Загальна статистика
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM addresses')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM addresses')
    total_addresses = cursor.fetchone()[0]
    
    # Статистика по чергах
    cursor.execute('SELECT subqueue, COUNT(*) FROM addresses GROUP BY subqueue ORDER BY subqueue')
    subqueue_stats = cursor.fetchall()
    
    # Користувачі з налаштованими сповіщеннями
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_notifications')
    users_with_config = cursor.fetchone()[0]
    
    # Користувачі з увімкненими сповіщеннями
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_notifications WHERE notifications_enabled = 1')
    users_with_notifications = cursor.fetchone()[0]
    
    # Загальна кількість відправлених сповіщень
    cursor.execute('SELECT COUNT(*) FROM sent_alerts')
    total_alerts = cursor.fetchone()[0]
    
    # Сповіщення за останні 7 днів
    cursor.execute('SELECT COUNT(*) FROM sent_alerts WHERE event_date >= ?', 
                   ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),))
    recent_alerts = cursor.fetchone()[0]
    
    conn.close()
    
    # Формуємо повідомлення
    stats_text = f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
    stats_text += f"👥 <b>Користувачі:</b> {total_users}\n"
    stats_text += f"🏠 <b>Адрес:</b> {total_addresses}\n"
    stats_text += f"⚙️ <b>З налаштованими сповіщеннями:</b> {users_with_config}\n"
    stats_text += f"🔔 <b>З увімкненими сповіщеннями:</b> {users_with_notifications}\n\n"
    
    stats_text += f"📋 <b>Розподіл по чергах:</b>\n"
    for subq, count in subqueue_stats:
        stats_text += f"  {subq}: {count} адрес\n"
    
    stats_text += f"\n📨 <b>Сповіщення:</b>\n"
    stats_text += f"  Загалом: {total_alerts}\n"
    stats_text += f"  За 7 днів: {recent_alerts}\n"
    
    await message.answer(stats_text, parse_mode="HTML")

# --- МОНІТОРИНГ ТА СПОВІЩЕННЯ ---
async def monitor_job():
    all_data = await parse_hoe_smart()
    if not all_data: return

    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    
    # Load known schedules
    cursor.execute('SELECT value FROM settings WHERE key = "known_schedules"')
    res = cursor.fetchone()
    known_schedules = json.loads(res[0]) if res and res[0] else {}
    
    # Get all users and their addresses
    cursor.execute('SELECT user_id, name, subqueue FROM addresses')
    all_user_addresses = cursor.fetchall()
    
    now = datetime.now()
    current_date_str = now.strftime("%d.%m.%Y")
    short_date = now.strftime("%d.%m.%y")
    
    updated_dates = []
    
    for date_key, data in all_data.items():
        is_new = date_key not in known_schedules
        has_list_now = bool(data['list'])
        had_list = known_schedules.get(date_key, {}).get('has_list', False)
        img_changed = known_schedules.get(date_key, {}).get('img', '') != data['img']
        
        if is_new or img_changed or (not had_list and has_list_now):
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
            for uid, addr_name, subq in all_user_addresses:
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
                'has_list': has_list_now
            }
    
    # Save updated known_schedules
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("known_schedules", ?)', (json.dumps(known_schedules),))
    conn.commit()
    
    # Now do the 60-min alerts
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
        
        # Знаходимо точки зміни в найближчі 60 хв
        t60_dt = now + timedelta(minutes=60)
        for start_dt, end_dt in combined_intervals:
            change_points = [start_dt, end_dt]
            for change_dt in change_points:
                if now < change_dt <= t60_dt:
                    minutes_left = int((change_dt - now).total_seconds() / 60)
                    change_time_str = change_dt.strftime("%H:%M")
                    event_date = change_dt.strftime("%Y-%m-%d")
                    
                    # Визначаємо тип події: початок відключення чи відновлення
                    if change_dt == start_dt:
                        alert_base = f"⚠️ **Увага! Відключення світла**\n\nЧерез {{minutes_left}} хв ({{change_time_str}}) подача електроенергії буде **припинена** за {{details}}."
                    else:
                        alert_base = f"✅ **Відновлення електроенергії**\n\nЧерез {{minutes_left}} хв ({{change_time_str}}) подача електроенергії буде **відновлена** для {{details}}."
                    
                    cursor.execute('SELECT user_id, GROUP_CONCAT(name) FROM addresses WHERE subqueue = ? GROUP BY user_id', (sub_q,))
                    users_in_q = cursor.fetchall()
                    for uid, addr_names_str in users_in_q:
                        cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?', 
                                       (uid, change_time_str, event_date))
                        if not cursor.fetchone():
                            addr_list = addr_names_str.split(',')
                            if len(addr_list) == 1:
                                details = f"вашою адресою **{addr_list[0]}** (черга {sub_q})"
                            else:
                                details = f"вашими адресами **{addr_names_str.replace(',', ', ')}** (черга {sub_q})"
                            alert_msg = alert_base.format(minutes_left=minutes_left, change_time_str=change_time_str, details=details)
                            try:
                                await bot.send_message(uid, alert_msg, parse_mode="Markdown")
                                cursor.execute('INSERT INTO sent_alerts VALUES (?, ?, ?)', (uid, change_time_str, event_date))
                                conn.commit()
                            except: pass
    
    # Delete old clock files for updated dates
    for date_key in updated_dates:
        date_clean = date_key.replace('.', '_')
        for file in os.listdir('test_clocks'):
            if date_clean in file and file.endswith('.png'):
                try:
                    os.remove(os.path.join('test_clocks', file))
                except:
                    pass
    
    conn.close()

@dp.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:  # Додаткова перевірка
        await message.answer("❌ Доступ заборонено.")
        await state.clear()
        return
    
    broadcast_text = message.text
    
    conn = sqlite3.connect('test_users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT user_id FROM addresses')
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
