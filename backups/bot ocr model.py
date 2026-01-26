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
import cv2
import numpy as np
import pytesseract

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

class ManualScheduleStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_subqueue = State()
    waiting_for_guaranteed = State()
    waiting_for_possible = State()
    waiting_for_confirm = State()

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
    
    # Ручні графіки для адмінів
    cursor.execute('''CREATE TABLE IF NOT EXISTS manual_schedules (
        date TEXT,
        subqueue TEXT,
        guaranteed_text TEXT,
        possible_text TEXT,
        admin_id INTEGER,
        created_at TEXT,
        updated_at TEXT,
        PRIMARY KEY (date, subqueue)
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

# --- РУЧНІ ГРАФІКИ ---
def init_manual_schedules_table():
    """Створює таблицю для ручних графіків якщо її немає"""
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS manual_schedules (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                subqueue TEXT NOT NULL,
                guaranteed_text TEXT,
                possible_text TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                UNIQUE(date, subqueue)
            )
        ''')
        conn.commit()
        conn.close()
        logging.info("Manual schedules table initialized")
    except Exception as e:
        logging.error(f"Error creating manual_schedules table: {e}")

def get_manual_schedule(date, subqueue):
    """Отримує ручний графік для дати та черги"""
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT guaranteed_text, possible_text, admin_id, created_at
            FROM manual_schedules
            WHERE date = ? AND subqueue = ?
        ''', (date, subqueue))
        res = cursor.fetchone()
        conn.close()
        if res:
            return {
                'guaranteed_text': res[0] or '',
                'possible_text': res[1] or '',
                'created_by': res[2],
                'created_at': res[3]
            }
        return None
    except Exception as e:
        logging.error(f"Error getting manual schedule for {date}, {subqueue}: {e}")
        return None

def set_manual_schedule(date, subqueue, guaranteed_text, possible_text, user_id):
    """Створює або оновлює ручний графік"""
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO manual_schedules
            (date, subqueue, guaranteed_text, possible_text, admin_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (date, subqueue, guaranteed_text, possible_text, user_id))
        conn.commit()
        conn.close()
        logging.info(f"Manual schedule set for {date}, {subqueue} by user {user_id}")
        return True
    except Exception as e:
        logging.error(f"Error setting manual schedule: {e}")
        return False

def delete_manual_schedule(date, subqueue):
    """Видаляє ручний графік"""
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM manual_schedules
            WHERE date = ? AND subqueue = ?
        ''', (date, subqueue))
        conn.commit()
        conn.close()
        logging.info(f"Manual schedule deactivated for {date}, {subqueue}")
        return True
    except Exception as e:
        logging.error(f"Error deleting manual schedule: {e}")
        return False

def get_combined_schedule(date, subqueue, site_data=None):
    """Отримує комбінований графік: гарантовані з сайту + ймовірні з ручних"""
    guaranteed = ''
    possible = ''

    # Отримуємо дані з сайту
    if site_data and date in site_data:
        schedule_text = site_data[date]['list'].get(subqueue, '')
        # Розділяємо на guaranteed і possible
        if "Вимкнено:" in schedule_text:
            guaranteed = schedule_text.split("Вимкнено:")[1].split(";")[0].strip()
        if "Можливо вимкнено:" in schedule_text:
            possible = schedule_text.split("Можливо вимкнено:")[1].strip()

    # Додаємо ручні дані
    manual = get_manual_schedule(date, subqueue)
    if manual:
        if manual['guaranteed_text']:
            guaranteed = manual['guaranteed_text'] if not guaranteed else f"{guaranteed}; {manual['guaranteed_text']}"
        if manual['possible_text']:
            possible = manual['possible_text'] if not possible else f"{possible}; {manual['possible_text']}"

    return {
        'guaranteed': guaranteed,
        'possible': possible,
        'source': 'site' if site_data and date in site_data else 'manual'
    }

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
                    
                    # Витягуємо timestamp з назви файлу для порівняння свіжості
                    filename = img_url.split('/')[-1]  # file20260124035522426.png
                    timestamp = 0
                    if filename.startswith('file') and filename.endswith('.png'):
                        # file20260124035522426.png -> 20260124035522426
                        ts_str = filename[4:-4]  # remove 'file' and '.png'
                        try:
                            # Це timestamp в форматі YYYYMMDDHHMMSSmmm
                            timestamp = int(ts_str)
                        except ValueError:
                            timestamp = 0
                    
                    # Шукаємо список <ul>, який йде ПІСЛЯ цієї картинки
                    schedules = {}
                    ul = img.find_next('ul')
                    if ul:
                        for li in ul.find_all('li'):
                            li_text = li.get_text()
                            match = re.search(r"підчерга (\d\.\d) [–\-\—\−] (.*)", li_text)
                            if match:
                                subq, schedule = match.groups()
                                schedules[subq] = normalize_schedule_text(schedule)
                    
                    # Якщо немає текстового опису, пробуємо OCR парсинг зображення
                    if not schedules:
                        logging.info(f"Немає текстового опису для {date_key}, використовуємо OCR парсинг")
                        schedules = await parse_schedule_image(img_url)
                    
                    # Якщо для цієї дати вже є запис, порівнюємо за timestamp (свіжіший виграє)
                    if date_key not in data_by_date or timestamp > data_by_date[date_key].get('timestamp', 0):
                        data_by_date[date_key] = {
                            "img": img_url,
                            "list": schedules,
                            "raw_date": alt_text,
                            "has_image": True,
                            "timestamp": timestamp
                        }
                return data_by_date
        except Exception as e:
            logging.error(f"Парсинг error: {e}")
            return {}

async def parse_schedule_image(image_path_or_url):
    """
    Парсинг графіку з зображення.
    Повертає словник {subqueue: schedule_text}
    """
    try:
        # Завантажуємо зображення
        if image_path_or_url.startswith('http'):
            async with aiohttp.ClientSession() as session:
                async with session.get(image_path_or_url) as response:
                    image_data = await response.read()
                    nparr = np.frombuffer(image_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(image_path_or_url)
        
        if img is None:
            logging.error(f"Не вдалося завантажити зображення: {image_path_or_url}")
            return {}
        
        # Конвертуємо в RGB для PIL
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        
        # OCR для розпізнавання тексту (якщо потрібно для заголовків)
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # налаштувати шлях
        
        # Основна логіка парсингу кольорів
        schedules = parse_table_colors(img)
        
        return schedules
        
    except Exception as e:
        logging.error(f"OCR парсинг error: {e}")
        return {}

def parse_table_colors(img):
    """
    Аналіз кольорів таблиці графіку.
    Повертає словник з розкладом для кожної черги.
    """
    # Конвертуємо в HSV для кращого аналізу кольорів
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Визначаємо діапазони кольорів на основі аналізу test_schedule.png
    # Синій/бірюзовий (немає світла) - RGB [143,170,220], HSV [109,89,220]
    blue_lower = np.array([100, 50, 100])
    blue_upper = np.array([120, 255, 255])
    
    # Сірий (можливо вимкнуть) - RGB [224,224,224], HSV [0,0,224]
    gray_lower = np.array([0, 0, 200])
    gray_upper = np.array([180, 30, 250])
    
    # Білий (буде світло) - RGB [255,255,255], HSV [0,0,255]
    white_lower = np.array([0, 0, 250])
    white_upper = np.array([180, 20, 255])
    
    height, width = img.shape[:2]
    
    # Завантажуємо налаштування таблиці
    try:
        with open('table_bounds.json', 'r') as f:
            settings = json.load(f)
        table_left = settings.get('table_left', int(width * 0.05))
        table_right = settings.get('table_right', int(width * 0.95))
        table_top = settings.get('table_top', int(height * 0.15))
        table_bottom = settings.get('table_bottom', int(height * 0.95))
        cell_width = settings.get('cell_width', (table_right - table_left) // 24)
        cell_height = settings.get('cell_height', (table_bottom - table_top) // 12)
        rows = settings.get('rows', 12)  # черги по вертикалі
        cols = settings.get('cols', 24)  # години по горизонталі
    except:
        # Налаштування за замовчуванням
        rows = 12  # черги
        cols = 24  # години
        table_top = int(height * 0.15)
        table_bottom = int(height * 0.95)
        table_left = int(width * 0.05)
        table_right = int(width * 0.95)
        cell_height = (table_bottom - table_top) // rows
        cell_width = (table_right - table_left) // cols
    
    schedules = {}
    
    for row in range(rows):
        subqueue = f"{row//2 + 1}.{row%2 + 1}"  # 1.1, 1.2, 2.1, 2.2, ...
        intervals_off = []  # гарантовані відключення
        intervals_possible = []  # можливі відключення
        
        for col in range(cols):
            x1 = table_left + col * cell_width
            y1 = table_top + row * cell_height
            x2 = x1 + cell_width
            y2 = y1 + cell_height
            
            # Беремо центральну частину клітинки
            margin = 3
            cell_roi = img[y1+margin:y2-margin, x1+margin:x2-margin]
            if cell_roi.size == 0:
                continue
                
            # Конвертуємо в HSV
            hsv_cell = cv2.cvtColor(cell_roi, cv2.COLOR_BGR2HSV)
            
            # Рахуємо пікселі кожного кольору
            blue_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, blue_lower, blue_upper))
            gray_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, gray_lower, gray_upper))
            white_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, white_lower, white_upper))
            
            total_pixels = cell_roi.size // 3
            
            # Визначаємо домінуючий колір
            max_pixels = max(blue_pixels, gray_pixels, white_pixels)
            
            if max_pixels / total_pixels > 0.3:  # більше 30% пікселів цього кольору
                if blue_pixels == max_pixels:
                    status = "off"  # немає світла
                elif gray_pixels == max_pixels:
                    status = "possible"  # можливо
                else:
                    status = "on"  # буде світло
            else:
                status = "on"  # за замовчуванням
            
            # Додаємо інтервали
            if status == "off":
                start_hour = col
                end_hour = col + 1
                intervals_off.append(f"{start_hour:02d}:00-{end_hour:02d}:00")
            elif status == "possible":
                start_hour = col
                end_hour = col + 1
                intervals_possible.append(f"{start_hour:02d}:00-{end_hour:02d}:00")
        
        # Формуємо текст розкладу
        schedule_parts = []
        if intervals_off:
            schedule_parts.append("Вимкнено: " + ", ".join(intervals_off))
        if intervals_possible:
            schedule_parts.append("Можливо вимкнено: " + ", ".join(intervals_possible))
        
        if schedule_parts:
            schedules[subqueue] = "; ".join(schedule_parts)
    
    return schedules

# --- СИСТЕМА КЕШУВАННЯ РОЗПАРСЕНИХ ГРАФІКІВ ---

def load_cached_schedules():
    """Завантажує кешовані розклади з файлу"""
    try:
        with open('cached_schedules.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_cached_schedules(cached_schedules):
    """Зберігає кешовані розклади у файл"""
    try:
        with open('cached_schedules.json', 'w', encoding='utf-8') as f:
            json.dump(cached_schedules, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving cached schedules: {e}")

def get_schedule_for_date(date_key, subqueue):
    """Отримує розклад для конкретної дати та черги з кешу"""
    cached = load_cached_schedules()
    date_data = cached.get(date_key, {})
    return date_data.get(subqueue, "")

def update_cached_schedule(date_key, subqueue, schedule_text, schedule_type="full"):
    """
    Оновлює кешований розклад
    schedule_type: "full" - повний розклад, "changes" - тільки зміни
    """
    cached = load_cached_schedules()
    
    if date_key not in cached:
        cached[date_key] = {}
    
    if schedule_type == "full":
        # Повне оновлення розкладу
        cached[date_key][subqueue] = schedule_text
    elif schedule_type == "changes":
        # Доповнення існуючого розкладу змінами
        existing = cached[date_key].get(subqueue, "")
        if existing and schedule_text:
            # Логіка злиття розкладів (спростимо поки що)
            cached[date_key][subqueue] = existing + "; " + schedule_text
        else:
            cached[date_key][subqueue] = schedule_text
    
    save_cached_schedules(cached)
    logging.info(f"Updated cached schedule for {date_key}, {subqueue}")

def parse_schedule_to_intervals(schedule_text):
    """
    Парсить текст розкладу в інтервали для годинника
    Повертає словник з guaranteed та possible інтервалами
    """
    intervals = {
        'guaranteed': [],  # [(start_hour, end_hour), ...]
        'possible': []     # [(start_hour, end_hour), ...]
    }
    
    if not schedule_text:
        return intervals
    
    # Розділяємо на частини по ";"
    parts = schedule_text.split(';')
    
    # Якщо є тільки одна частина - це гарантовані відключення
    if len(parts) == 1:
        text = parts[0].strip()
        if text:
            intervals['guaranteed'].extend(parse_intervals_text(text))
    else:
        # Перша частина - гарантовані, друга - можливі
        guaranteed_text = parts[0].strip()
        possible_text = parts[1].strip()
        
        if guaranteed_text:
            intervals['guaranteed'].extend(parse_intervals_text(guaranteed_text))
        if possible_text:
            intervals['possible'].extend(parse_intervals_text(possible_text))
    
    return intervals

def parse_intervals_text(text):
    """Парсить текст інтервалів типу '01:00-02:00, 03:00-04:00'"""
    intervals = []
    if not text:
        return intervals
    
    # Розділяємо по комах
    time_ranges = text.split(',')
    for time_range in time_ranges:
        time_range = time_range.strip()
        match = re.search(r'(\d{1,2}):00-(\d{1,2}):00', time_range)
        if match:
            start_hour = int(match.group(1))
            end_hour = int(match.group(2))
            intervals.append((start_hour, end_hour))
    
    return intervals

def merge_consecutive_intervals(intervals):
    """Об'єднує інтервали, які йдуть підряд"""
    if not intervals:
        return intervals
    
    # Сортуємо інтервали за початковим часом
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]
    
    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        # Якщо поточний інтервал починається відразу після попереднього
        if start == last_end:
            # Об'єднуємо інтервали
            merged[-1] = (last_start, end)
        else:
            # Додаємо новий інтервал
            merged.append((start, end))
    
    return merged

def generate_clock_image(subqueue, schedule_text, date_info=""):
    """
    Створює зображення годинника з відключеннями
    schedule_text: об'єднаний текст розкладу типу "Вимкнено: 01:00-02:00; Можливо вимкнено: 03:00-04:00"
    """
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
    
    # Спроба завантажити шрифт
    try:
        font = ImageFont.truetype('arial.ttf', 32)
    except:
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 32)
        except:
            try:
                font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 32)
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
    
    # Парсимо інтервали відключень з об'єднаного тексту
    intervals = parse_schedule_to_intervals(schedule_text)
    
    # Гарантовані відключення - червоним
    for start_hour, end_hour in intervals['guaranteed']:
        try:
            start_angle = (start_hour * 15) - 90
            end_angle = (end_hour * 15) - 90
            
            if end_angle < start_angle:
                end_angle += 360
            
            # Малюємо дугу гарантованого відключення (червоним)
            draw.arc((center - radius + 20, center - radius + 20, center + radius - 20, center + radius - 20),
                     start=start_angle, end=end_angle, fill=(255, 100, 100), width=40)
            # Додаємо обведення
            draw.arc((center - radius + 20, center - radius + 20, center + radius - 20, center + radius - 20),
                     start=start_angle, end=end_angle, fill=None, outline=(0, 0, 0), width=4)
        except:
            continue
    
    # Можливі відключення - сірим
    for start_hour, end_hour in intervals['possible']:
        try:
            start_angle = (start_hour * 15) - 90
            end_angle = (end_hour * 15) - 90
            
            if end_angle < start_angle:
                end_angle += 360
            
            # Малюємо дугу можливого відключення (сірим)
            draw.arc((center - radius + 60, center - radius + 60, center + radius - 60, center + radius - 60),
                     start=start_angle, end=end_angle, fill=(150, 150, 150), width=20)
            # Додаємо обведення
            draw.arc((center - radius + 60, center - radius + 60, center + radius - 60, center + radius - 60),
                     start=start_angle, end=end_angle, fill=None, outline=(0, 0, 0), width=2)
        except:
            continue
    
    # Зберігаємо зображення
    img.save(filename)
    return filename

def format_schedule_pretty(subqueue, guaranteed_text, possible_text, date_info):
    # Перевіряємо статус світла (гарантовані відключення)
    light_now = check_light_status(guaranteed_text)
    status_emoji = "🟢" if light_now else "🔴"
    status_text = "СВІТЛО Є" if light_now else "СВІТЛА НЕМАЄ"

    msg = f"{status_emoji} **ЗАРАЗ {status_text}**\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += f"📅 **{date_info}**\n"
    msg += f"📍 Підчерга: **{subqueue}**\n\n"

    if guaranteed_text.strip():
        msg += "🔴 **ГАРАНТОВАНІ ВІДКЛЮЧЕННЯ:**\n"
        clean_display = re.sub(r"[–\—\−]", "-", guaranteed_text.replace("з ", "").replace(" до ", "-"))
        for t in clean_display.split("; "):
            if t.strip():
                msg += f"• {t.strip()}\n"

    if possible_text.strip():
        msg += "\n🟡 **МОЖЛИВІ ВІДКЛЮЧЕННЯ:**\n"
        clean_display = re.sub(r"[–\—\−]", "-", possible_text.replace("з ", "").replace(" до ", "-"))
        for t in clean_display.split("; "):
            if t.strip():
                msg += f"• {t.strip()}\n"

    if not guaranteed_text.strip() and not possible_text.strip():
        msg += "✅ **ЦІЛОДОБОВО СВІТЛО**\n"

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

def format_outages_compact(intervals):
    """
    Форматує відключення в компактному вигляді з об'єднанням інтервалів
    Повертає список рядків для відображення
    """
    # Об'єднуємо гарантовані інтервали
    guaranteed = merge_consecutive_intervals(intervals['guaranteed'])
    possible = merge_consecutive_intervals(intervals['possible'])
    
    # Створюємо список всіх інтервалів з типом
    all_intervals = []
    for start, end in guaranteed:
        all_intervals.append((start, end, 'guaranteed'))
    for start, end in possible:
        all_intervals.append((start, end, 'possible'))
    
    # Сортуємо за часом
    all_intervals.sort(key=lambda x: x[0])
    
    # Форматуємо
    formatted = []
    for start, end, outage_type in all_intervals:
        time_str = f"{start:02d}:00-{end:02d}:00"
        if outage_type == 'guaranteed':
            formatted.append(f"🔴 {time_str}")
        else:  # possible
            formatted.append(f"🟡 {time_str}")
    
    return formatted

def format_all_periods(intervals):
    """
    Форматує всі періоди (відключення + електропостачання) в одному блоці
    Кожен період на окремому рядку, відсортовані за часом
    """
    # Об'єднуємо гарантовані інтервали
    guaranteed = merge_consecutive_intervals(intervals['guaranteed'])
    possible = merge_consecutive_intervals(intervals['possible'])
    
    # Збираємо всі періоди відключень
    all_outages = []
    for start, end in guaranteed:
        all_outages.append((start, end, '🔴', 'guaranteed'))
    for start, end in possible:
        all_outages.append((start, end, '🟡', 'possible'))
    
    # Сортуємо відключення за часом
    all_outages.sort(key=lambda x: x[0])
    
    # Збираємо всі періоди електропостачання
    power_periods = []
    current_time = 0
    
    for start, end, emoji, outage_type in all_outages:
        if current_time < start:
            power_periods.append((current_time, start, '🟢', 'power'))
        current_time = max(current_time, end)
    
    if current_time < 24:
        power_periods.append((current_time, 24, '🟢', 'power'))
    
    # Об'єднуємо всі періоди
    all_periods = all_outages + power_periods
    
    # Сортуємо за часом початку
    all_periods.sort(key=lambda x: x[0])
    
    # Форматуємо кожен період на окремому рядку
    formatted_lines = []
    for start, end, emoji, period_type in all_periods:
        time_str = f"{start:02d}:00-{end:02d}:00"
        formatted_lines.append(f"{emoji} {time_str}")
    
    return formatted_lines

# --- УНІВЕРСАЛЬНА ФУНКЦІЯ ВИДАЧІ ---
async def send_schedule_logic(chat_id, subqueue, day_type="today", is_update=False):
    target_dt = datetime.now() if day_type == "today" else datetime.now() + timedelta(days=1)
    date_str = target_dt.strftime("%d.%m.%Y")

    # Отримуємо розклад з кешу
    schedule_text = get_schedule_for_date(date_str, subqueue)

    # Якщо немає в кеші, пробуємо отримати з сайту
    if not schedule_text:
        all_data = await parse_hoe_smart()
        short_date = target_dt.strftime("%d.%m.%y")
        data = all_data.get(date_str) or all_data.get(short_date)

        if data and data.get('list'):
            schedule_text = normalize_schedule_text(data['list'].get(subqueue, ""))
            # Зберігаємо в кеш
            if schedule_text:
                update_cached_schedule(date_str, subqueue, schedule_text, "full")

    # Отримуємо дані з сайту для зображення
    all_data = await parse_hoe_smart()
    short_date = target_dt.strftime("%d.%m.%y")
    data = all_data.get(date_str) or all_data.get(short_date)

    img_url = data['img'] if data else None

    if not schedule_text and not data:
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

    if is_update:
        try:
            if img_url:
                await bot.send_photo(chat_id, photo=img_url, caption=f"🆕 <b>ОНОВЛЕННЯ НА САЙТІ!</b>\nГрафік на {date_str} вже доступний.", parse_mode="HTML")
            else:
                await bot.send_message(chat_id, f"🆕 <b>ОНОВЛЕННЯ НА САЙТІ!</b>\nГрафік на {date_str} вже доступний.", parse_mode="HTML")
            if not schedule_text:
                await bot.send_message(chat_id, "📝 <b>Зверніть увагу:</b> Детальні списки годин відключень будуть розписані трохи пізніше (зазвичай протягом години).", parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send update to {chat_id}: {e}")
        return

    # Формуємо повідомлення
    intervals = parse_schedule_to_intervals(schedule_text)

    if day_type == "today":
        # Перевіряємо статус світла тільки по гарантованих відключеннях
        guaranteed_text = "; ".join([f"{start:02d}:00-{end:02d}:00" for start, end in intervals['guaranteed']])
        light_now = check_light_status(guaranteed_text)
        status = "🟢 Електропостачання увімкнене" if light_now else "🔴 Електропостачання вимкнене"
        msg = f"<b>{status}</b>\n━━━━━━━━━━━━━━━\n"
    else:
        msg = "━━━━━━━━━━━━━━━\n"

    msg += f"📅 <b>Графік на {date_str}</b>\n📍 Підчерга: <b>{subqueue}</b>\n\n"

    # Форматуємо всі періоди в одному блоці
    formatted_periods = format_all_periods(intervals)
    
    if formatted_periods:
        msg += f"⚡ <b>ВІДКЛЮЧЕННЯ:</b>\n"
        msg += "\n".join(formatted_periods)
        msg += "\n\n"
        msg += "🟡 - електропостачання можливе\n"
        msg += "🔴 - електропостачання вимкнене\n"
        msg += "🟢 - електропостачання увімкнене"
    else:
        msg += "🕒 <b>ВІДКЛЮЧЕНЬ НЕМАЄ</b>"

    msg += "\n━━━━━━━━━━━━━━━"

    # Генеруємо годинник з об'єднаним текстом
    clock_file = generate_clock_image(subqueue, schedule_text, date_str)
    
    try:
        await bot.send_photo(chat_id, photo=types.FSInputFile(clock_file), caption=msg, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Failed to send clock to {chat_id}: {e}")
        # Fallback до зображення з сайту або просто текст
        if img_url:
            try:
                await bot.send_photo(chat_id, photo=img_url, caption=msg, parse_mode="HTML")
            except Exception as e:
                logging.error(f"Failed to send schedule to {chat_id}: {e}")
                try:
                    await bot.send_message(chat_id, msg, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Failed to send message to {chat_id}: {e}")
        else:
            try:
                await bot.send_message(chat_id, msg, parse_mode="HTML")
            except Exception as e:
                logging.error(f"Failed to send message to {chat_id}: {e}")

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

@dp.message(Command("manual_schedule"))
async def cmd_manual_schedule(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ заборонено.")
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати графік", callback_data="manual_add")],
        [InlineKeyboardButton(text="📝 Редагувати графік", callback_data="manual_edit")],
        [InlineKeyboardButton(text="🗑️ Видалити графік", callback_data="manual_delete")],
        [InlineKeyboardButton(text="👁️ Переглянути графіки", callback_data="manual_view")]
    ])
    
    await message.answer("🔧 <b>УПРАВЛІННЯ РУЧНИМИ ГРАФІКАМИ</b>\n\nОберіть дію:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "manual_add")
async def manual_add_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📅 Введіть дату у форматі ДД.ММ.РРРР (наприклад, 15.12.2024):")
    await state.set_state(ManualScheduleStates.waiting_for_date)
    await callback.answer()

@dp.callback_query(F.data == "manual_edit")
async def manual_edit_start(callback: types.CallbackQuery):
    # Показуємо всі існуючі ручні графіки
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, subqueue, guaranteed_text, possible_text FROM manual_schedules ORDER BY date, subqueue')
    schedules = cursor.fetchall()
    conn.close()
    
    if not schedules:
        await callback.message.edit_text("❌ Немає ручних графіків для редагування.")
        return
    
    kb = []
    for date, subq, guar, poss in schedules:
        text = f"{date} - {subq}"
        if guar: text += " (гарантовано)"
        if poss: text += " (можливо)"
        kb.append([InlineKeyboardButton(text=text, callback_data=f"edit_sched_{date}_{subq}")])
    
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="manual_back")])
    
    await callback.message.edit_text("📝 Оберіть графік для редагування:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data == "manual_delete")
async def manual_delete_start(callback: types.CallbackQuery):
    # Показуємо всі існуючі ручні графіки
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, subqueue, guaranteed_text, possible_text FROM manual_schedules ORDER BY date, subqueue')
    schedules = cursor.fetchall()
    conn.close()
    
    if not schedules:
        await callback.message.edit_text("❌ Немає ручних графіків для видалення.")
        return
    
    kb = []
    for date, subq, guar, poss in schedules:
        text = f"{date} - {subq}"
        if guar: text += " (гарантовано)"
        if poss: text += " (можливо)"
        kb.append([InlineKeyboardButton(text=text, callback_data=f"delete_sched_{date}_{subq}")])
    
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="manual_back")])
    
    await callback.message.edit_text("🗑️ Оберіть графік для видалення:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data == "manual_view")
async def manual_view(callback: types.CallbackQuery):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, subqueue, guaranteed_text, possible_text FROM manual_schedules ORDER BY date, subqueue')
    schedules = cursor.fetchall()
    conn.close()
    
    if not schedules:
        await callback.message.edit_text("📋 Ручних графіків немає.")
        return
    
    msg = "📋 <b>РУЧНІ ГРАФІКИ:</b>\n\n"
    for date, subq, guar, poss in schedules:
        msg += f"📅 <b>{date}</b> - Черга <b>{subq}</b>\n"
        if guar:
            msg += f"  🔴 Гарантовано: {guar}\n"
        if poss:
            msg += f"  ⚪ Можливо: {poss}\n"
        msg += "\n"
    
    kb = [[InlineKeyboardButton(text="⬅️ Назад", callback_data="manual_back")]]
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "manual_back")
async def manual_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати графік", callback_data="manual_add")],
        [InlineKeyboardButton(text="📝 Редагувати графік", callback_data="manual_edit")],
        [InlineKeyboardButton(text="🗑️ Видалити графік", callback_data="manual_delete")],
        [InlineKeyboardButton(text="👁️ Переглянути графіки", callback_data="manual_view")]
    ])
    
    await callback.message.edit_text("🔧 <b>УПРАВЛІННЯ РУЧНИМИ ГРАФІКАМИ</b>\n\nОберіть дію:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ОБРОБНИКИ СТАНІВ ДЛЯ РУЧНИХ ГРАФІКІВ
@dp.message(ManualScheduleStates.waiting_for_date)
async def process_manual_date(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    
    # Перевіряємо формат дати
    try:
        datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неправильний формат дати. Використовуйте ДД.ММ.РРРР (наприклад, 15.12.2024)")
        return
    
    await state.update_data(date=date_str)
    await message.answer("📍 Введіть номер черги (наприклад, 1.1, 2.2):")
    await state.set_state(ManualScheduleStates.waiting_for_subqueue)

@dp.message(ManualScheduleStates.waiting_for_subqueue)
async def process_manual_subqueue(message: types.Message, state: FSMContext):
    subqueue = message.text.strip()
    
    # Перевіряємо, чи існує така черга
    valid_subqueues = ["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "3.1", "3.2", "3.3"]
    if subqueue not in valid_subqueues:
        await message.answer(f"❌ Неправильна черга. Допустимі значення: {', '.join(valid_subqueues)}")
        return
    
    await state.update_data(subqueue=subqueue)
    await message.answer("🔴 Введіть гарантовані відключення у форматі '10:00-12:00; 14:00-16:00' або залиште пустим:")
    await state.set_state(ManualScheduleStates.waiting_for_guaranteed)

@dp.message(ManualScheduleStates.waiting_for_guaranteed)
async def process_manual_guaranteed(message: types.Message, state: FSMContext):
    guaranteed = message.text.strip()
    await state.update_data(guaranteed=guaranteed)
    await message.answer("⚪ Введіть ймовірні відключення у форматі '10:00-12:00; 14:00-16:00' або залиште пустим:")
    await state.set_state(ManualScheduleStates.waiting_for_possible)

@dp.message(ManualScheduleStates.waiting_for_possible)
async def process_manual_possible(message: types.Message, state: FSMContext):
    possible = message.text.strip()
    await state.update_data(possible=possible)
    
    data = await state.get_data()
    
    # Перевіряємо, чи не порожні обидва поля
    if not data.get('guaranteed') and not data.get('possible'):
        await message.answer("❌ Принаймні одне поле (гарантовані або ймовірні відключення) має бути заповнене.")
        return
    
    # Показуємо підтвердження
    msg = f"📋 <b>ПІДТВЕРДЖЕННЯ ДОДАВАННЯ ГРАФІКА</b>\n\n"
    msg += f"📅 Дата: <b>{data['date']}</b>\n"
    msg += f"📍 Черга: <b>{data['subqueue']}</b>\n"
    if data.get('guaranteed'):
        msg += f"🔴 Гарантовано: <b>{data['guaranteed']}</b>\n"
    if data.get('possible'):
        msg += f"⚪ Можливо: <b>{data['possible']}</b>\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data="confirm_manual_add")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_manual")]
    ])
    
    await message.answer(msg, reply_markup=kb, parse_mode="HTML")
    await state.set_state(ManualScheduleStates.waiting_for_confirm)

@dp.callback_query(F.data == "confirm_manual_add")
async def confirm_manual_add(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Зберігаємо в базу
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO manual_schedules 
        (date, subqueue, guaranteed_text, possible_text, admin_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        data['date'], 
        data['subqueue'], 
        data.get('guaranteed', ''), 
        data.get('possible', ''), 
        callback.from_user.id,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    
    await state.clear()
    await callback.message.edit_text("✅ Ручний графік успішно додано!")
    await callback.answer()

@dp.callback_query(F.data == "cancel_manual")
async def cancel_manual(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Додавання графіка скасовано.")
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_sched_"))
async def edit_schedule(callback: types.CallbackQuery, state: FSMContext):
    # Розбираємо callback_data: edit_sched_DATE_SUBQUEUE
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("❌ Помилка в даних")
        return
    
    date_subq = parts[2]
    date, subq = date_subq.split("_", 1)
    
    # Отримуємо поточні дані
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT guaranteed_text, possible_text FROM manual_schedules WHERE date = ? AND subqueue = ?', (date, subq))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        await callback.answer("❌ Графік не знайдено")
        return
    
    guar, poss = result
    
    await state.update_data(edit_date=date, edit_subqueue=subq, current_guar=guar, current_poss=poss)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Редагувати гарантовані", callback_data="edit_guar")],
        [InlineKeyboardButton(text="⚪ Редагувати ймовірні", callback_data="edit_poss")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="manual_edit")]
    ])
    
    msg = f"📝 Редагування графіка {date} - {subq}\n\n"
    if guar:
        msg += f"🔴 Гарантовано: {guar}\n"
    if poss:
        msg += f"⚪ Можливо: {poss}\n"
    
    await callback.message.edit_text(msg, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "edit_guar")
async def edit_guaranteed(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current = data.get('current_guar', '')
    await callback.message.edit_text(f"🔴 Поточні гарантовані відключення: {current}\n\nВведіть нові гарантовані відключення:")
    await state.set_state(ManualScheduleStates.waiting_for_guaranteed)
    await callback.answer()

@dp.callback_query(F.data == "edit_poss")
async def edit_possible(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current = data.get('current_poss', '')
    await callback.message.edit_text(f"⚪ Поточні ймовірні відключення: {current}\n\nВведіть нові ймовірні відключення:")
    await state.set_state(ManualScheduleStates.waiting_for_possible)
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_sched_"))
async def delete_schedule_confirm(callback: types.CallbackQuery):
    # Розбираємо callback_data: delete_sched_DATE_SUBQUEUE
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("❌ Помилка в даних")
        return
    
    date_subq = parts[2]
    date, subq = date_subq.split("_", 1)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Видалити", callback_data=f"confirm_delete_{date}_{subq}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="manual_delete")]
    ])
    
    await callback.message.edit_text(f"🗑️ Видалити графік {date} - {subq}?", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete(callback: types.CallbackQuery):
    # Розбираємо callback_data: confirm_delete_DATE_SUBQUEUE
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("❌ Помилка в даних")
        return
    
    date_subq = parts[2]
    date, subq = date_subq.split("_", 1)
    
    # Видаляємо з бази
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM manual_schedules WHERE date = ? AND subqueue = ?', (date, subq))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ Графік {date} - {subq} видалено!")
    await callback.answer()

# ОБРОБНИКИ РЕДАГУВАННЯ ГРАФІКІВ
@dp.message(ManualScheduleStates.waiting_for_guaranteed, F.data == "edit_guar")
async def process_edit_guaranteed(message: types.Message, state: FSMContext):
    data = await state.get_data()
    guaranteed = message.text.strip()
    
    # Оновлюємо в базі
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE manual_schedules 
        SET guaranteed_text = ?, updated_at = ?
        WHERE date = ? AND subqueue = ?
    ''', (guaranteed, datetime.now().isoformat(), data['edit_date'], data['edit_subqueue']))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("✅ Гарантовані відключення оновлено!")

@dp.message(ManualScheduleStates.waiting_for_possible, F.data == "edit_poss")
async def process_edit_possible(message: types.Message, state: FSMContext):
    data = await state.get_data()
    possible = message.text.strip()
    
    # Оновлюємо в базі
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE manual_schedules 
        SET possible_text = ?, updated_at = ?
        WHERE date = ? AND subqueue = ?
    ''', (possible, datetime.now().isoformat(), data['edit_date'], data['edit_subqueue']))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("✅ Ймовірні відключення оновлено!")


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

def normalize_schedule_text(text):
    """Normalize schedule text for comparison: strip, replace 'до' with '-', normalize separators."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)  # multiple spaces to single
    text = re.sub(r'[–\-\—\−]', '-', text)  # normalize dashes
    text = re.sub(r',\s*з\s+', '; ', text)  # ', з ' to '; '  -- first!
    text = re.sub(r'з\s+', '', text)  # remove 'з '
    text = re.sub(r'\s+до\s+', '-', text)  # ' до ' to '-'
    text = re.sub(r';\s*$', '', text)  # remove trailing ;

    # Обробка OCR формату: "Вимкнено: 07:00-08:00, 14:00-15:00; Можливо вимкнено: 09:00-10:00"
    if "Вимкнено:" in text or "Можливо вимкнено:" in text:
        parts = []
        if "Вимкнено:" in text:
            off_part = text.split("Вимкнено:")[1].split(";")[0].strip()
            parts.append(off_part)
        if "Можливо вимкнено:" in text:
            possible_part = text.split("Можливо вимкнено:")[1].strip()
            parts.append(possible_part)
        text = "; ".join(parts)

    return text

async def monitor_job():
    """
    Моніторинг нових графіків з OCR парсингом і кешуванням
    """
    try:
        logging.info("Starting monitor job with OCR parsing")

        # Отримуємо дані з сайту
        all_data = await parse_hoe_smart()
        if not all_data:
            logging.info("No data parsed from site")
            return

        logging.info(f"Parsed data for dates: {list(all_data.keys())}")

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        # Завантажуємо кешовані розклади
        cached_schedules = load_cached_schedules()
        logging.info(f"Loaded cached schedules for dates: {list(cached_schedules.keys())}")

        now = datetime.now()
        current_date_str = now.strftime("%d.%m.%Y")
        updated_dates = []

        for date_key, data in all_data.items():
            try:
                # Пропускаємо минулі дати
                try:
                    date_dt = datetime.strptime(date_key, "%d.%m.%Y")
                except ValueError:
                    try:
                        date_dt = datetime.strptime(date_key, "%d.%m.%y")
                        date_dt = date_dt.replace(year=2000 + date_dt.year % 100)
                    except ValueError:
                        continue

                if date_dt.date() < now.date():
                    logging.info(f"Skipping past date {date_key}")
                    continue

                # Перевіряємо чи є зміни в графіку
                img_url = data.get('img', '')
                has_image = data.get('has_image', False)
                parsed_list = data.get('list', {})

                # Отримуємо кешований розклад для цієї дати
                cached_date_data = cached_schedules.get(date_key, {})

                # Визначаємо тип зміни
                is_new_schedule = date_key not in cached_schedules
                img_changed = cached_date_data.get('img_url', '') != img_url
                has_new_image = has_image and not cached_date_data.get('has_image', False)

                logging.info(f"Checking {date_key}: is_new={is_new_schedule}, img_changed={img_changed}, has_image={has_image}")

                if is_new_schedule or img_changed or has_new_image:
                    logging.info(f"Detected change for {date_key}, parsing with OCR")

                    # Парсимо графік через OCR
                    if has_image and img_url:
                        ocr_schedules = await parse_schedule_image(img_url)
                        logging.info(f"OCR parsed {len(ocr_schedules)} subqueues for {date_key}")

                        # Зберігаємо в кеш
                        for subqueue, schedule_text in ocr_schedules.items():
                            update_cached_schedule(date_key, subqueue, schedule_text, "full")

                        # Позначаємо що є оновлення
                        cached_schedules[date_key] = {
                            'img_url': img_url,
                            'has_image': True,
                            'last_updated': now.isoformat(),
                            'subqueues': list(ocr_schedules.keys())
                        }

                        updated_dates.append(date_key)

                        # Генеруємо годинники для всіх черг
                        for subqueue in ocr_schedules.keys():
                            schedule_text = ocr_schedules[subqueue]
                            generate_clock_image(subqueue, schedule_text, date_key)
                            logging.info(f"Generated clock for {subqueue} on {date_key}")

                    save_cached_schedules(cached_schedules)

                # Якщо є текстовий опис але немає зображення - використовуємо текст
                elif parsed_list and not has_image:
                    logging.info(f"Using text schedule for {date_key}")
                    for subqueue, schedule_text in parsed_list.items():
                        normalized_text = normalize_schedule_text(schedule_text)
                        update_cached_schedule(date_key, subqueue, normalized_text, "full")

                        # Генеруємо годинник
                        generate_clock_image(subqueue, normalized_text, date_key)

                    updated_dates.append(date_key)

            except Exception as e:
                logging.error(f"Error processing date {date_key}: {e}")
                continue

        # Зберігаємо оновлені кешовані розклади
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("cached_schedules", ?)',
                      (json.dumps(cached_schedules),))
        conn.commit()

        logging.info(f"Updated dates: {updated_dates}")

        # Тепер обробляємо сповіщення для сьогодні і завтра
        today_str = now.strftime("%d.%m.%Y")
        tomorrow = now + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%d.%m.%Y")

        # Отримуємо розклади для сповіщень
        today_schedules = {}
        tomorrow_schedules = {}

        for date_key in [today_str, tomorrow_str]:
            date_schedules = cached_schedules.get(date_key, {})
            if isinstance(date_schedules, dict) and 'subqueues' in date_schedules:
                # Отримуємо розклади з кешу
                for subqueue in date_schedules['subqueues']:
                    schedule_text = get_schedule_for_date(date_key, subqueue)
                    if schedule_text:
                        if date_key == today_str:
                            today_schedules[subqueue] = schedule_text
                        else:
                            tomorrow_schedules[subqueue] = schedule_text

        logging.info(f"Today schedules: {len(today_schedules)} subqueues")
        logging.info(f"Tomorrow schedules: {len(tomorrow_schedules)} subqueues")

        # Обробляємо сповіщення (залишаємо існуючу логіку але з новими даними)
        for sub_q in today_schedules.keys():
            try:
                time_text_today = today_schedules.get(sub_q, "")
                time_text_tomorrow = tomorrow_schedules.get(sub_q, "")

                # Збираємо всі інтервали для сьогодні і завтра
                combined_intervals = []

                # Інтервали сьогодні (гарантовані + можливі)
                intervals_today = parse_schedule_to_intervals(time_text_today)
                for start_hour, end_hour in intervals_today['guaranteed'] + intervals_today['possible']:
                    start_dt = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=start_hour)
                    end_dt = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=end_hour)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    combined_intervals.append((start_dt, end_dt))

                # Інтервали завтра
                intervals_tomorrow = parse_schedule_to_intervals(time_text_tomorrow)
                for start_hour, end_hour in intervals_tomorrow['guaranteed'] + intervals_tomorrow['possible']:
                    start_dt = datetime.combine(tomorrow.date(), datetime.min.time()) + timedelta(hours=start_hour)
                    end_dt = datetime.combine(tomorrow.date(), datetime.min.time()) + timedelta(hours=end_hour)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    combined_intervals.append((start_dt, end_dt))

                # Знаходимо точки зміни в найближчі 30 хв
                t30_dt = now + timedelta(minutes=30)
                user_alerts = {}  # uid -> list of (change_dt, is_shutdown, addr_names, is_possible)

                for start_dt, end_dt in combined_intervals:
                    # Визначаємо тип відключення (гарантоване чи можливе)
                    is_possible = any(
                        start_dt.hour >= start_hour and end_dt.hour <= end_hour
                        for start_hour, end_hour in intervals_today['possible'] + intervals_tomorrow['possible']
                    )

                    change_points = [(start_dt, True, is_possible), (end_dt, False, is_possible)]
                    for change_dt, is_shutdown, is_possible in change_points:
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
                                enabled_addrs = []
                                for addr_name in addr_list:
                                    addr_settings = get_user_notification_settings(uid, addr_name.strip())
                                    if addr_settings['notifications_enabled']:
                                        enabled_addrs.append(addr_name.strip())

                                if not enabled_addrs:
                                    continue

                                if uid not in user_alerts:
                                    user_alerts[uid] = []
                                user_alerts[uid].append((change_dt, is_shutdown, enabled_addrs, sub_q, is_possible))

                # Надсилаємо сповіщення користувачам
                for uid, alerts in user_alerts.items():
                    # Групуємо за часом
                    time_groups = {}
                    for change_dt, is_shutdown, addrs, subq, is_possible in alerts:
                        key = (change_dt, is_shutdown, is_possible)
                        if key not in time_groups:
                            time_groups[key] = []
                        time_groups[key].extend(addrs)

                    for (change_dt, is_shutdown, is_possible), addr_list in time_groups.items():
                        minutes_left = int((change_dt - now).total_seconds() / 60)
                        change_time_str = change_dt.strftime("%H:%M")
                        event_date = change_dt.strftime("%Y-%m-%d")

                        # Перевіряємо, чи вже надсилали
                        cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?',
                                       (uid, change_time_str, event_date))
                        if cursor.fetchone():
                            continue

                        if is_shutdown:
                            if is_possible:
                                alert_base = f"⚠️ <b>Увага! Можливе відключення світла</b>\n\nЧерез {minutes_left} хв ({change_time_str}) можливе припинення подачі електроенергії"
                            else:
                                alert_base = f"⚠️ <b>Увага! Відключення світла</b>\n\nЧерез {minutes_left} хв ({change_time_str}) подача електроенергії буде <b>припинена</b>"
                        else:
                            if is_possible:
                                alert_base = f"✅ <b>Можливе відновлення електроенергії</b>\n\nЧерез {minutes_left} хв ({change_time_str}) можливе відновлення подачі електроенергії"
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
        logging.info("Monitor job completed successfully")

    except Exception as e:
        logging.error(f"Error in monitor_job: {e}")
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
                # Skip past dates - don't send notifications for schedules that have already passed
                try:
                    date_dt = datetime.strptime(date_key, "%d.%m.%Y")
                except ValueError:
                    try:
                        date_dt = datetime.strptime(date_key, "%d.%m.%y")
                        date_dt = date_dt.replace(year=2000 + date_dt.year % 100)
                    except ValueError:
                        continue
                
                if date_dt.date() < now.date():
                    logging.info(f"Skipping past date {date_key}")
                    continue
                
                is_new = date_key not in known_schedules
                has_list_now = bool(data['list'])
                had_list = known_schedules.get(date_key, {}).get('has_list', False)
                old_list_raw = known_schedules.get(date_key, {}).get('list', {})
                old_list = {k: normalize_schedule_text(v) for k, v in old_list_raw.items()}
                new_list = {k: normalize_schedule_text(v) for k, v in data['list'].items()}
                list_changed = old_list != new_list
                img_changed = known_schedules.get(date_key, {}).get('img', '') != data['img']
                
                logging.info(f"Checking {date_key}: is_new={is_new}, list_changed={list_changed}, img_changed={img_changed}, has_list_now={has_list_now}, had_list={had_list}")
                
                if is_new or img_changed or list_changed or (not had_list and has_list_now):
                    logging.info(f"Detected change for {date_key}: is_new={is_new}, list_changed={list_changed}, img_changed={img_changed}, has_list_now={has_list_now}, had_list={had_list}")
                    
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
                        change_type = "img_updated" if not is_new else "new_schedule"
                    elif days_diff == 1:
                        msg_type = "new_tomorrow" if is_new else "update_tomorrow"
                        change_type = "new_schedule" if is_new else "img_updated"
                    else:
                        msg_type = "new_future" if is_new else "update_future"
                        change_type = "new_schedule" if is_new else "img_updated"
                    
                    # Send notifications to all users (since schedules are in images, we can't filter by subqueue)
                    user_ids = set()
                    for uid, addr_name, subq in all_user_addresses:
                        user_ids.add(uid)
                    
                    for uid in user_ids:
                        try:
                            # Check user notification settings
                            general_settings = get_user_notification_settings(uid)
                            if not general_settings['notifications_enabled']:
                                continue
                            
                            if msg_type in ["new_tomorrow", "new_future"]:
                                if general_settings['new_schedule_enabled']:
                                    caption = f"🆕 <b>НОВИЙ ГРАФІК!</b>\n\nГрафік на {date_key} вже доступний на сайті."
                                    await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                                    if not has_list_now:
                                        await bot.send_message(uid, "📝 <b>Зверніть увагу:</b> Детальні списки годин відключень будуть розписані трохи пізніше (зазвичай протягом години).", parse_mode="HTML")
                            elif msg_type == "update_today":
                                if general_settings['schedule_changes_enabled']:
                                    if list_changed and old_list and new_list:
                                        # Show what changed in schedules
                                        changed_subqueues = []
                                        for sq in set(old_list.keys()) | set(new_list.keys()):
                                            old_sched = old_list.get(sq, "")
                                            new_sched = new_list.get(sq, "")
                                            if old_sched != new_sched:
                                                changed_subqueues.append(f"{sq}: {old_sched} → {new_sched}")
                                        
                                        if changed_subqueues:
                                            caption = f"🔄 <b>ЗМІНИ В ГРАФІКУ!</b>\n\nГрафік на {date_key} було оновлено:\n" + "\n".join(changed_subqueues[:3])  # Limit to 3 changes
                                            await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                                        else:
                                            caption = f"🔄 <b>ОНОВЛЕННЯ ГРАФІКА!</b>\n\nГрафік на {date_key} було оновлено."
                                            await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                                    elif not had_list and has_list_now:
                                        # Lists appeared
                                        caption = f"📝 <b>ОНОВЛЕННЯ ГРАФІКА!</b>\n\nДетальні списки годин відключень на {date_key} тепер доступні."
                                        await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                                    else:
                                        # General update
                                        caption = f"🔄 <b>ОНОВЛЕННЯ ГРАФІКА!</b>\n\nГрафік на {date_key} було оновлено."
                                        await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                            elif msg_type == "update_tomorrow":
                                if general_settings['schedule_changes_enabled']:
                                    if has_list_now and not had_list:
                                        caption = f"📝 <b>ОНОВЛЕННЯ ГРАФІКА!</b>\n\nДетальні списки годин відключень на {date_key} тепер доступні."
                                        await bot.send_photo(uid, photo=data['img'], caption=caption, parse_mode="HTML")
                        except Exception as e:
                            logging.error(f"Failed to send notification to {uid}: {e}")
                        await asyncio.sleep(0.05)
                    
                    # Update known
                    known_schedules[date_key] = {
                        'img': data['img'],
                        'list': data['list'],
                        'has_list': has_list_now,
                        'raw_date': data['raw_date']
                    }
                else:
                    # No change, but ensure it's stored
                    if date_key not in known_schedules:
                        known_schedules[date_key] = {
                            'img': data['img'],
                            'list': data['list'],
                            'has_list': has_list_now,
                            'raw_date': data['raw_date']
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
                                
                                # Перевіряємо, чи вже надсилали - REMOVED HERE, moved to after grouping
                                # cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?', 
                                #                (uid, change_time_str, event_date))
                                # if cursor.fetchone():
                                #     continue
                                
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
                        
                        # Перевіряємо, чи вже надсилали для цього часу
                        cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?', 
                                       (uid, change_time_str, event_date))
                        if cursor.fetchone():
                            continue  # Вже надсилали сповіщення для цього часу
                        
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

@dp.message(BroadcastStates.waiting_for_message)
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