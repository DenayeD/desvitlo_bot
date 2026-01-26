import asyncio
import sqlite3
import json
import aiohttp
from bs4 import BeautifulSoup
import re
import logging

logging.basicConfig(level=logging.INFO)

URL_PAGE = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"

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
                    
                    # Оскільки розклади зберігаються тільки в зображеннях, а не в HTML тексті,
                    # ми просто зберігаємо інформацію про зображення
                    # Пізніше можна додати OCR для розпізнавання тексту з зображень
                    
                    data_by_date[date_key] = {
                        "img": img_url,
                        "list": {},  # Порожній, бо розклади не в HTML
                        "raw_date": alt_text,
                        "has_image": True
                    }
                return data_by_date
        except Exception as e:
            print(f"Парсинг error: {e}")
            return {}

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

async def test_monitor():
    # Initialize DB if needed
    init_db()

    # Clear known_schedules for testing
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE settings SET value = "{}" WHERE key = "known_schedules"')
    conn.commit()

    # Load current known_schedules (should be empty)
    cursor.execute('SELECT value FROM settings WHERE key = "known_schedules"')
    res = cursor.fetchone()
    known_schedules = json.loads(res[0]) if res and res[0] else {}
    print(f"Initial known_schedules: {known_schedules}")

    # Parse current data
    all_data = await parse_hoe_smart()
    print(f"Parsed data: {list(all_data.keys())}")

    # Simulate the detection logic
    for date_key, data in all_data.items():
        is_new = date_key not in known_schedules
        has_image_now = data.get('has_image', True)
        had_image = known_schedules.get(date_key, {}).get('has_image', False)
        old_img = known_schedules.get(date_key, {}).get('img', '')
        new_img = data['img']
        img_changed = old_img != new_img

        print(f"Date {date_key}: is_new={is_new}, img_changed={img_changed}")

        if is_new or img_changed or (not had_image and has_image_now):
            print(f"Would send notification for {date_key}")
            known_schedules[date_key] = {
                'img': data['img'],
                'list': data['list'],
                'has_image': has_image_now,
                'raw_date': data['raw_date']
            }

    # Save updated
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("known_schedules", ?)', (json.dumps(known_schedules),))
    conn.commit()
    conn.close()

    print(f"Final known_schedules: {known_schedules}")

if __name__ == "__main__":
    asyncio.run(test_monitor())