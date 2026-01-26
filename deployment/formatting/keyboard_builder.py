from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database.addresses import get_user_addresses

def get_queue_keyboard():
    """Create queue selection keyboard"""
    builder = []
    for i in range(1, 7):
        builder.append([InlineKeyboardButton(text=f"{i}.1", callback_data=f"set_q_{i}.1"),
                        InlineKeyboardButton(text=f"{i}.2", callback_data=f"set_q_{i}.2")])
    builder.append([InlineKeyboardButton(text="🔍 Дізнатись свою чергу", url="https://hoe.com.ua/shutdown/queue")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_address_selection_keyboard(user_id, action_prefix):
    """Create address selection keyboard for user"""
    addresses = get_user_addresses(user_id)
    builder = []
    for name, subq, is_main in addresses:
        main_mark = " ⭐" if is_main else ""
        builder.append([InlineKeyboardButton(text=f"{name} (черга {subq}){main_mark}", callback_data=f"{action_prefix}_{name}")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_main_menu():
    """Create main menu keyboard"""
    kb = [
        [KeyboardButton(text="📅 Графік на сьогодні"), KeyboardButton(text="🗓️ Графік на завтра")],
        [KeyboardButton(text="📊 Загальний графік")],
        [KeyboardButton(text="🏠 Керування адресами"), KeyboardButton(text="⚙️ Налаштування бота")],
        [KeyboardButton(text="☕ Підтримати бота"), KeyboardButton(text="👨‍💻 Зв'язок з розробником")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)