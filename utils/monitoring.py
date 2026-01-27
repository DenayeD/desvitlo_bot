import asyncio
import aiohttp
import logging
import re
from datetime import datetime
from bs4 import BeautifulSoup
from config.settings import URL_PAGE

from notifications import send_schedule_notifications


async def send_upcoming_events_notifications():
    """Надсилає сповіщення про зміну статусів, групуючи адреси користувача"""
    logging.info("Starting send_upcoming_events_notifications check")
    try:
        from database.notifications import get_user_notification_settings
        from database.addresses import get_all_user_addresses
        from database.connection import get_db_connection
        from core.globals import bot
        from utils.cache import get_schedule_for_date
        from utils.helpers import parse_schedule_to_intervals
        from datetime import datetime, timedelta

        now = datetime.now()
        # Перевіряємо вікно навколо 30-хвилинної позначки
        check_times = [now + timedelta(minutes=m) for m in [25, 30, 35]]

        today_str = now.strftime("%d.%m.%Y")
        tomorrow_str = (now + timedelta(days=1)).strftime("%d.%m.%Y")

        # 1. Збираємо всіх активних користувачів
        subqueue_users = {} 
        user_general_settings = {} 
        
        all_addresses = get_all_user_addresses()
        for uid, addr_name, subq in all_addresses:
            if uid not in user_general_settings:
                user_general_settings[uid] = get_user_notification_settings(uid)
            
            if user_general_settings[uid].get('notifications_enabled'):
                addr_settings = get_user_notification_settings(uid, addr_name)
                if addr_settings.get('notifications_enabled'):
                    if subq not in subqueue_users:
                        subqueue_users[subq] = []
                    subqueue_users[subq].append((uid, addr_name))

        # 2. Визначаємо події для кожної підчерги
        # (uid, status_future, time) -> set of address_names
        pending_alerts = {}

        for sub_q, users in subqueue_users.items():
            if not users: continue

            intervals_today = parse_schedule_to_intervals(get_schedule_for_date(today_str, sub_q))
            intervals_tomorrow = parse_schedule_to_intervals(get_schedule_for_date(tomorrow_str, sub_q))

            def get_status_at_time(check_time):
                # Логіка визначення кольору (залишається твоя оригінальна)
                for start_h, end_h in intervals_today['guaranteed']:
                    s = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=start_h)
                    e = s + timedelta(hours=(end_h - start_h if end_h > start_h else end_h - start_h + 24))
                    if s <= check_time < e: return 'black'
                for start_h, end_h in intervals_today['possible']:
                    s = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=start_h)
                    e = s + timedelta(hours=(end_h - start_h if end_h > start_h else end_h - start_h + 24))
                    if s <= check_time < e: return 'grey'
                return 'white'

            status_now = get_status_at_time(now)
            
            for f_time in check_times:
                status_future = get_status_at_time(f_time)
                if status_future != status_now:
                    # Знайшли перехід!
                    event_time_str = f_time.strftime("%H:00") if f_time.minute > 45 else f_time.strftime("%H:%M")
                    event_date_str = f_time.strftime("%Y-%m-%d")
                    
                    # Формуємо базовий текст
                    msg = ""
                    if status_now == 'white' and status_future == 'grey': msg = "⚠️ <b>МОЖЛИВЕ ВІДКЛЮЧЕННЯ</b>"
                    elif status_now == 'white' and status_future == 'black': msg = "⚠️ <b>ВІДКЛЮЧЕННЯ ЕЛЕКТРОЕНЕРГІЇ</b>"
                    elif status_now == 'black' and status_future == 'white': msg = "✅ <b>ВІДНОВЛЕННЯ ЕЛЕКТРОЕНЕРГІЇ</b>"
                    elif status_now == 'grey' and status_future == 'black': msg = "⚠️ <b>ГАРАНТОВАНЕ ВІДКЛЮЧЕННЯ</b>"
                    elif status_now != 'white' and status_future == 'white': msg = "✅ <b>ВІДНОВЛЕННЯ ЕЛЕКТРОЕНЕРГІЇ</b>"
                    
                    if msg:
                        for uid, addr in users:
                            # Ключ групування: юзер + тип події + час
                            key = (uid, msg, event_time_str, event_date_str)
                            if key not in pending_alerts: pending_alerts[key] = set()
                            pending_alerts[key].add(addr)
                    break # Для цієї черги подію знайдено

        # 3. Відправка згрупованих сповіщень
        sent_count = 0
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for (uid, title, e_time, e_date), addrs in pending_alerts.items():
                # Перевірка на дублікат у базі
                cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?', 
                               (uid, e_time, e_date))
                if cursor.fetchone(): continue

                addr_str = ", ".join(addrs)
                full_message = f"{title}\n\nОрієнтовно о {e_time}\nАдреса: <b>{addr_str}</b>"

                try:
                    await bot.send_message(uid, full_message, parse_mode="HTML")
                    cursor.execute('INSERT INTO sent_alerts VALUES (?, ?, ?)', (uid, e_time, e_date))
                    sent_count += 1
                except Exception as e:
                    logging.error(f"Failed to send to {uid}: {e}")
                await asyncio.sleep(0.05)
            conn.commit()

        logging.info(f"Sent {sent_count} grouped notifications")
    except Exception as e:
        logging.error(f"Error in notifications: {e}")
        
async def parse_hoe_data():
    """Parse basic schedule data from HOE website"""
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
            logging.error(f"Error parsing: {e}")
            return None, None, None

async def parse_hoe_smart():
    """Smart parsing of HOE website with multiple dates support"""
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

                # Find all GVP image containers
                img_containers = soup.find_all('img', alt=re.compile(r'ГПВ'))
                logging.info(f"Found {len(img_containers)} GVP images")
                
                data_by_date = {}

                for img in img_containers:
                    # Extract date from alt (e.g. "ГПВ-17.01.26")
                    alt_text = img.get('alt', '')
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', alt_text)
                    if not date_match: continue

                    date_key = date_match.group(1)
                    # Format date to DD.MM.YYYY if needed
                    if len(date_key) == 8:  # DD.MM.YY
                        date_key = date_key[:6] + '20' + date_key[6:]

                    img_url = "https://hoe.com.ua" + img['src']

                    # Use OCR to parse schedule from image instead of HTML text
                    from ocr.parser import parse_schedule_image
                    schedules = await parse_schedule_image(img_url)

                    data_by_date[date_key] = {
                        'img_url': img_url,
                        'schedules': schedules,
                        'text_content': f"OCR parsed from image: {len(schedules)} schedules found"
                    }

                return data_by_date

        except Exception as e:
            logging.error(f"Error in smart parsing: {e}")
            return {}

async def monitor_job():
    """Monitor job for checking schedule updates"""
    logging.info("Monitor job executed")
    try:
        # Check for updates and only regenerate if changed
        from utils.cache import check_and_update_cache
        updated, changes = await check_and_update_cache()
        if updated:
            logging.info("Cache updated with new data, clocks regenerated")
            # Send notifications for changes
            await send_schedule_notifications(changes)
        else:
            logging.info("No changes detected, cache unchanged")
    except Exception as e:
        logging.error(f"Error in monitor job: {e}")