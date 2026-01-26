import logging
import os
from datetime import datetime, timedelta
from aiogram import types
from core.globals import bot
from utils.monitoring import parse_hoe_smart
from utils.cache import get_schedule_for_date, update_cached_schedule
from utils.helpers import check_light_status, format_all_periods, normalize_schedule_text, parse_schedule_to_intervals
from ocr.parser import generate_clock_image

async def send_schedule_logic(chat_id, subqueue, day_type="today", is_update=False):
    """Send schedule logic for a specific chat and subqueue"""
    target_dt = datetime.now() if day_type == "today" else datetime.now() + timedelta(days=1)
    date_str = target_dt.strftime("%d.%m.%Y")

    # Get schedule from cache
    schedule_text = get_schedule_for_date(date_str, subqueue)

    # If not in cache, try to get from site
    if not schedule_text:
        all_data = await parse_hoe_smart()
        short_date = target_dt.strftime("%d.%m.%y")
        data = all_data.get(date_str) or all_data.get(short_date)

        if data and data.get('schedules'):
            schedule_text = normalize_schedule_text(data['schedules'].get(subqueue, ""))
            # Save to cache
            if schedule_text:
                update_cached_schedule(date_str, subqueue, schedule_text, "full")

    # Get site data for image
    all_data = await parse_hoe_smart()
    short_date = target_dt.strftime("%d.%m.%y")
    data = all_data.get(date_str) or all_data.get(short_date)

    img_url = data['img_url'] if data else None

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

    # Form message
    intervals = parse_schedule_to_intervals(schedule_text)

    if day_type == "today":
        # Check light status only for guaranteed outages
        guaranteed_text = "; ".join([f"{start:02d}:00-{end:02d}:00" for start, end in intervals['guaranteed']])
        light_now = check_light_status(guaranteed_text)
        status = "🟢 Електропостачання увімкнене" if light_now else "🔴 Електропостачання вимкнене"
        msg = f"<b>{status}</b>\n━━━━━━━━━━━━━━━\n"
    else:
        msg = "━━━━━━━━━━━━━━━\n"

    msg += f"📅 <b>Графік на {date_str}</b>\n📍 Підчерга: <b>{subqueue}</b>\n\n"

    # Format all periods in one block
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

    # Generate clock with combined text
    # Check if clock already exists
    date_formatted = date_str.replace('.', '_')
    clock_filename = f"clocks/{subqueue}_{date_formatted}.png"
    
    if not os.path.exists(clock_filename):
        # Generate clock if it doesn't exist
        clock_file = generate_clock_image(subqueue, schedule_text, date_formatted)
    else:
        # Use existing clock
        clock_file = clock_filename

    try:
        await bot.send_photo(chat_id, photo=types.FSInputFile(clock_file), caption=msg, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Failed to send clock to {chat_id}: {e}")
        # Fallback to site image or just text
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