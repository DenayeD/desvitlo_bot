import logging
import asyncio
from datetime import datetime
from database.addresses import get_all_user_addresses
from database.notifications import get_user_notification_settings
from database.connection import get_db_connection
from core.globals import bot

async def send_schedule_notifications(changes):
    """
    Розподіляє сповіщення про зміну графіків.
    """
    logging.info(f"Starting mass notification for: {changes}")
    
    now_date = datetime.now().strftime("%d.%m.%Y")
    all_addresses = get_all_user_addresses()
    user_updates = {}

    # 1. Групуємо дані
    for date_str, subqueues in changes.items():
        # changes тепер має вигляд {'дата': {'new': [черги], 'changed': [черги]}} 
        # або просто {'дата': [черги]} залежно від версії cache.py
        
        # Визначаємо список підчерг (обробка обох форматів)
        target_subqueues = subqueues if isinstance(subqueues, list) else (subqueues.get('new', []) + subqueues.get('changed', []))
        
        for uid, addr_name, subq in all_addresses:
            if subq in target_subqueues:
                gen_settings = get_user_notification_settings(uid)
                if not gen_settings or not gen_settings.get('notifications_enabled'):
                    continue

                addr_settings = get_user_notification_settings(uid, addr_name)
                if not addr_settings or not addr_settings.get('notifications_enabled'):
                    continue

                if uid not in user_updates:
                    user_updates[uid] = {}
                if date_str not in user_updates[uid]:
                    user_updates[uid][date_str] = []

                user_updates[uid][date_str].append((addr_name, subq))

    # 2. Відправка сповіщень
    from utils.cache import get_cache_data
    cache = get_cache_data()

    for uid, dates in user_updates.items():
        for date_str, info in dates.items():
            addrs_text = ", ".join([f"<b>{a}</b> ({s})" for a, s in info])

            try:
                if date_str == now_date:
                    text = (f"⚠️ <b>ЗМІНА ГРАФІКА НА СЬОГОДНІ ({date_str})</b>\n\n"
                            f"Оновлено дані для:\n{addrs_text}")
                    await bot.send_message(uid, text, parse_mode="HTML")
                else:
                    # Дістаємо URL картинки з нашого нового ключа global_img
                    img_url = cache.get("global_img", {}).get(date_str)

                    text = (f"📅 <b>НОВИЙ ГРАФІК НА {date_str}</b>\n\n"
                            f"Розклад для адрес:\n{addrs_text}")

                    if img_url:
                        await bot.send_photo(uid, img_url, caption=text, parse_mode="HTML")
                    else:
                        await bot.send_message(uid, text, parse_mode="HTML")

                await asyncio.sleep(0.05) 
            except Exception as e:
                logging.error(f"Error sending to {uid}: {e}")

    logging.info("Mass schedule update notification finished")
