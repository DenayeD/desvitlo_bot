import asyncio
import aiohttp
import logging
import re
from datetime import datetime
from bs4 import BeautifulSoup
from config.settings import URL_PAGE

async def send_upcoming_events_notifications():
    """Send notifications for upcoming status transitions in next 30 minutes"""
    logging.info("Starting send_upcoming_events_notifications check")
    try:
        from database.notifications import get_user_notification_settings
        from database.addresses import get_all_user_addresses
        from database.connection import get_db_connection
        from core.globals import bot
        from utils.cache import get_schedule_for_date
        from utils.helpers import parse_schedule_to_intervals
        import asyncio
        from datetime import datetime, timedelta

        now = datetime.now()
        # Check for transitions in the next 25-35 minutes window
        # We'll check every minute to catch all possible transitions
        check_times = [now + timedelta(minutes=minutes) for minutes in range(25, 36)]

        # Get today and tomorrow dates
        today_str = now.strftime("%d.%m.%Y")
        tomorrow = now + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%d.%m.%Y")

        # Get all subqueues and users
        subqueue_users = {}  # subq -> list of (uid, addr_names)
        user_general_settings = {}  # uid -> general_settings (cache)
        
        all_addresses = get_all_user_addresses()
        for uid, addr_name, subq in all_addresses:
            if subq not in subqueue_users:
                subqueue_users[subq] = []
            
            # Cache general settings to avoid multiple DB queries for same user
            if uid not in user_general_settings:
                user_general_settings[uid] = get_user_notification_settings(uid)
            
            general_settings = user_general_settings[uid]
            if general_settings['notifications_enabled']:
                addr_settings = get_user_notification_settings(uid, addr_name)
                if addr_settings['notifications_enabled']:
                    subqueue_users[subq].append((uid, addr_name))

        # For each subqueue, determine current and future status for multiple time points
        user_grouped_alerts = {}  # (uid, message, event_time, event_date) -> list of addr_names

        for sub_q, users in subqueue_users.items():
            if not users:
                continue

            # Get schedules
            time_text_today = get_schedule_for_date(today_str, sub_q)
            time_text_tomorrow = get_schedule_for_date(tomorrow_str, sub_q)

            # Parse intervals
            intervals_today = parse_schedule_to_intervals(time_text_today)
            intervals_tomorrow = parse_schedule_to_intervals(time_text_tomorrow)

            # Function to get status at a given time
            def get_status_at_time(check_time):
                # Check today intervals
                for start_h, end_h in intervals_today['guaranteed']:
                    start_dt = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=start_h)
                    end_dt = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=end_h)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    if start_dt <= check_time < end_dt:
                        return 'black'  # guaranteed outage
                
                for start_h, end_h in intervals_today['possible']:
                    start_dt = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=start_h)
                    end_dt = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=end_h)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    if start_dt <= check_time < end_dt:
                        return 'grey'  # possible outage
                
                # Check tomorrow intervals
                for start_h, end_h in intervals_tomorrow['guaranteed']:
                    start_dt = datetime.combine(tomorrow.date(), datetime.min.time()) + timedelta(hours=start_h)
                    end_dt = datetime.combine(tomorrow.date(), datetime.min.time()) + timedelta(hours=end_h)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    if start_dt <= check_time < end_dt:
                        return 'black'
                
                for start_h, end_h in intervals_tomorrow['possible']:
                    start_dt = datetime.combine(tomorrow.date(), datetime.min.time()) + timedelta(hours=start_h)
                    end_dt = datetime.combine(tomorrow.date(), datetime.min.time()) + timedelta(hours=end_h)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    if start_dt <= check_time < end_dt:
                        return 'grey'
                
                return 'white'  # power on

            # Get current status
            status_now = get_status_at_time(now)
            
            # Find the nearest transition in the 25-35 minute window
            nearest_transition = None
            nearest_time = None
            
            for future_time in check_times:
                status_future = get_status_at_time(future_time)
                
                if status_future != status_now:
                    # Found a transition
                    if nearest_transition is None or future_time < nearest_time:
                        nearest_transition = (status_now, status_future)
                        nearest_time = future_time
            
            # Send notification for the nearest transition found
            if nearest_transition:
                status_now, status_future = nearest_transition
                minutes_left = int((nearest_time - now).total_seconds() / 60)
                
                message = None
                if status_now == 'white' and status_future == 'grey':
                    message = f"⚠️ <b>Увага! Можливе відключення світла</b>\n\nЧерез {minutes_left} хв можливе припинення подачі електроенергії."
                elif status_now == 'white' and status_future == 'black':
                    message = f"⚠️ <b>Увага! Відключення світла</b>\n\nЧерез {minutes_left} хв подача електроенергії буде припинена."
                elif status_now == 'black' and status_future == 'grey':
                    message = f"✅ <b>Можливе відновлення електроенергії</b>\n\nЧерез {minutes_left} хв можливе відновлення подачі електроенергії."
                elif status_now == 'black' and status_future == 'white':
                    message = f"✅ <b>Відновлення електроенергії</b>\n\nЧерез {minutes_left} хв подача електроенергії буде відновлена."
                elif status_now == 'grey' and status_future == 'black':
                    message = f"⚠️ <b>Підтверджено відключення світла</b>\n\nЧерез {minutes_left} хв подача електроенергії буде припинена."
                elif status_now == 'grey' and status_future == 'white':
                    message = f"✅ <b>Відновлення електроенергії</b>\n\nЧерез {minutes_left} хв подача електроенергії буде відновлена."

                if message:
                    event_time = nearest_time.strftime("%H:%M")
                    event_date = nearest_time.strftime("%Y-%m-%d")
                    
                    for uid, addr_name in users:
                        key = (uid, message, event_time, event_date)
                        if key not in user_grouped_alerts:
                            user_grouped_alerts[key] = []
                        user_grouped_alerts[key].append(addr_name)

        # Send alerts, checking for duplicates
        sent_count = 0
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for (uid, message, event_time, event_date), addr_list in user_grouped_alerts.items():
                # Check if already sent
                cursor.execute('SELECT 1 FROM sent_alerts WHERE user_id=? AND event_time=? AND event_date=?',
                               (uid, event_time, event_date))
                if cursor.fetchone():
                    continue
                
                # Format addresses text
                if len(addr_list) == 1:
                    addr_text = addr_list[0]
                else:
                    addr_text = ", ".join(addr_list)
                
                # Send message
                full_message = f"{message}\n\nАдреса: <b>{addr_text}</b>."
                try:
                    await bot.send_message(uid, full_message, parse_mode="HTML")
                    cursor.execute('INSERT INTO sent_alerts VALUES (?, ?, ?)', (uid, event_time, event_date))
                    sent_count += 1
                except Exception as e:
                    logging.error(f"Failed to send alert to {uid}: {e}")
                await asyncio.sleep(0.05)
            
            conn.commit()

        logging.info(f"Sent {sent_count} upcoming event notifications")

        # Clean up old alerts
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sent_alerts WHERE event_date < ?', (now.strftime("%Y-%m-%d"),))
            conn.commit()

    except Exception as e:
        logging.error(f"Error in send_upcoming_events_notifications: {e}")

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