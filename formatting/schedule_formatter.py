import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config.constants import QUEUE_NAMES

def format_schedule_pretty(subqueue, guaranteed_text, possible_text, date_info):
    """Format schedule in pretty text format"""
    # Check current light status (guaranteed outages)
    from utils.helpers import check_light_status

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