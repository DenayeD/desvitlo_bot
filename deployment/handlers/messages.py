from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.addresses import get_user_addresses, update_address_name
from database.users import get_user_subqueue
from database.notifications import init_user_notification_settings, get_user_notification_settings
import sqlite3
import asyncio
import logging
from datetime import datetime

from formatting.keyboard_builder import get_queue_keyboard, get_main_menu
from utils.schedule_sender import send_schedule_logic
from utils.monitoring import parse_hoe_smart
from core.states import AddressStates, BroadcastStates
from core.globals import bot
from config.settings import ADMIN_USER_ID

router = Router()

@router.message(F.text == "📅 Графік на сьогодні")
async def show_my_schedule(message: types.Message, state: FSMContext):
    await state.clear()
    subq = get_user_subqueue(message.from_user.id)
    if not subq:
        await message.answer("Оберіть чергу 👇", reply_markup=get_queue_keyboard())
    else:
        await send_schedule_logic(message.from_user.id, subq, "today")

@router.message(F.text == "🗓️ Графік на завтра")
async def show_tomorrow_schedule(message: types.Message, state: FSMContext):
    await state.clear()
    subq = get_user_subqueue(message.from_user.id)
    if not subq:
        await message.answer("Оберіть чергу 👇", reply_markup=get_queue_keyboard())
    else:
        await send_schedule_logic(message.from_user.id, subq, "tomorrow")

@router.message(F.text == "⚙️ Змінити чергу")
async def change_q(message: types.Message):
    await message.answer("Оберіть нову підчергу:", reply_markup=get_queue_keyboard())

@router.message(AddressStates.waiting_for_new_name)
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

@router.message(AddressStates.waiting_for_new_queue)
async def process_new_addr_queue(message: types.Message, state: FSMContext):
    # Це буде оброблено через callback, але якщо текст, ігноруємо
    pass

@router.message(AddressStates.waiting_for_edit_name)
async def process_edit_addr_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    old_name = data['edit_addr_name']
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

@router.message(F.text == "🏠 Керування адресами")
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

@router.message(F.text == "☕ Підтримати бота")
async def support(message: types.Message):
    text = (
        "☕ <b>Підтримка проєкту ДеСвітло?</b>\n\n"
        "Бот працює на хмарному сервері. Кожен донат допомагає проєкту жити!\n\n"
        "💳 <b>Номер банки:</b> <code>4874 1000 2365 9678</code>\n"
        "🔗 [Посилання на Банку](https://send.monobank.ua/jar/WAXs1bH5s)\n\n"
        "Дякую за підтримку! ❤️"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

@router.message(F.text == "👨‍💻 Зв'язок з розробником")
async def contact_dev(message: types.Message):
    await message.answer("📝 З будь-яких питань пишіть розробнику: @denayed")

@router.message(F.text == "⚙️ Налаштування бота")
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
        settings = get_user_notification_settings(user_id, name)
        status = "✅" if settings['notifications_enabled'] else "❌"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name} {status}", callback_data=f"toggle_addr_{name}")])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "📊 Загальний графік")
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
        img_url = data['img_url']
        try:
            await bot.send_photo(message.from_user.id, photo=img_url, caption=f"📊 Загальний графік на {current_date_str}")
        except Exception as e:
            logging.error(f"Failed to send general schedule: {e}")
            await message.answer("❌ Помилка при відправці графіка.")
    else:
        # Якщо сьогодні немає, беремо перший доступний
        for date_key, data in all_data.items():
            img_url = data['img_url']
            try:
                await bot.send_photo(message.from_user.id, photo=img_url, caption=f"📊 Загальний графік на {date_key}")
                break
            except Exception as e:
                logging.error(f"Failed to send general schedule: {e}")

@router.message(BroadcastStates.waiting_for_message)
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