import logging
import asyncio
from datetime import datetime

# Імпортуємо інструменти для роботи з БД та ботом
# Перевір, щоб шляхи відповідали твоїй структурі папок
from database.addresses import get_all_user_addresses
from database.notifications import get_user_notification_settings
from database.connection import get_db_connection
from core.globals import bot


async def send_schedule_notifications(changes):
    """
    Розподіляє сповіщення: 
    - Якщо дата сьогодні: термінова зміна графіка.
    - Якщо дата майбутня: анонс нового графіка + фото.
    """
    from database.addresses import get_all_user_addresses
    from database.notifications import get_user_notification_settings
    from core.globals import bot
    from datetime import datetime
    import asyncio

    now_date = datetime.now().strftime("%d.%m.%Y")
    
    # Збираємо всіх юзерів та їхні адреси
    all_addresses = get_all_user_addresses()
    
    # Групуємо дані: юзер -> дата_зміни -> список (addr_name, subq)
    user_updates = {}

    for date_str, subqueues in changes.items():
        for uid, addr_name, subq in all_addresses:
            if subq in subqueues:
                # Перевірка загальних налаштувань користувача
                gen_settings = get_user_notification_settings(uid)
                if not gen_settings.get('notifications_enabled'):
                    continue
                
                # Перевірка налаштувань конкретної адреси
                addr_settings = get_user_notification_settings(uid, addr_name)
                if not addr_settings.get('notifications_enabled'):
                    continue

                if uid not in user_updates:
                    user_updates[uid] = {}
                if date_str not in user_updates[uid]:
                    user_updates[uid][date_str] = []
                
                user_updates[uid][date_str].append((addr_name, subq))

    # Відправка сповіщень
    for uid, dates in user_updates.items():
        for date_str, info in dates.items():
            # info - це список кортежів [(назва, підчерга), ...]
            addrs_text = ", ".join([f"<b>{a}</b> (черга {s})" for a, s in info])
            
            try:
                if date_str == now_date:
                    # ТЕРМІНОВА ЗМІНА НА СЬОГОДНІ
                    text = (f"⚠️ <b>ТЕРМІНОВА ЗМІНА ГРАФІКА НА СЬОГОДНІ ({date_str})</b>\n\n"
                            f"Обленерго оновило дані для ваших адрес:\n{addrs_text}\n\n"
                            f"Будь ласка, перевірте новий розклад у боті.")
                    await bot.send_message(uid, text, parse_mode="HTML")
                
                else:
                    # НОВИЙ ГРАФІК НА ЗАВТРА (АБО МАЙБУТНЄ)
                    # Дістаємо URL фото з кешу для цієї дати
                    from utils.cache import get_cache_data
                    cache = get_cache_data()
                    img_url = cache.get(date_str, {}).get('img_url')

                    text = (f"📅 <b>НОВИЙ ГРАФІК НА {date_str}</b>\n\n"
                            f"З'явився розклад для ваших адрес:\n{addrs_text}")
                    
                    if img_url:
                        await bot.send_photo(uid, img_url, caption=text, parse_mode="HTML")
                    else:
                        await bot.send_message(uid, text, parse_mode="HTML")
                
                await asyncio.sleep(0.05) # Захист від Flood limit
            except Exception as e:
                logging.error(f"Error sending update to {uid} for {date_str}: {e}")

    logging.info("Mass schedule update notification finished")
