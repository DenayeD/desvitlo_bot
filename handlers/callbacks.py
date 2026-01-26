from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.addresses import get_user_addresses, add_user_address, update_address_queue, set_main_address, delete_user_address
from database.users import update_user_queue
from database.notifications import get_user_notification_settings, set_user_notification_settings
from database.connection import get_db_connection
from formatting.keyboard_builder import get_queue_keyboard, get_address_selection_keyboard
from utils.schedule_sender import send_schedule_logic
from core.globals import bot
from core.states import AddressStates
import logging

router = Router()

@router.callback_query(F.data.startswith("set_q_"))
async def callback_set_queue(callback: types.CallbackQuery, state: FSMContext):
    subq = callback.data.replace("set_q_", "")
    current_state = await state.get_state()
    if current_state == "AddressStates:waiting_for_new_queue":
        # Adding new address
        data = await state.get_data()
        name = data['addr_name']
        try:
            add_user_address(callback.from_user.id, name, subq)
            await callback.message.edit_text(f"✅ <b>Успішно!</b>\nСтворено адресу <b>{name}</b> з чергою <b>{subq}</b>.", parse_mode="HTML")
            await state.clear()
        except ValueError as e:
            await callback.message.edit_text(f"❌ <b>Помилка:</b> {str(e)}", parse_mode="HTML")
            await state.clear()
    elif current_state == "AddressStates:waiting_for_edit_queue":
        # Editing existing address queue
        data = await state.get_data()
        addr_name = data['edit_addr_name']
        update_address_queue(callback.from_user.id, addr_name, subq)
        await callback.message.edit_text(f"✅ <b>Успішно!</b>\nЗмінено чергу для адреси <b>{addr_name}</b> на <b>{subq}</b>.", parse_mode="HTML")
        await state.clear()
    else:
        # Update main address queue
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
            # If no addresses, create "Дім"
            try:
                add_user_address(callback.from_user.id, "Дім", subq)
                set_main_address(callback.from_user.id, "Дім")
                await callback.message.edit_text(f"✅ <b>Успішно!</b>\nСтворено адресу <b>Дім</b> з чергою <b>{subq}</b>.", parse_mode="HTML")
                await send_schedule_logic(callback.from_user.id, subq, "today")
            except ValueError as e:
                await callback.message.edit_text(f"❌ <b>Помилка:</b> {str(e)}", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "addr_add")
async def addr_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введіть назву нової адреси (наприклад, 'Дім', 'Робота'):")
    await state.set_state(AddressStates.waiting_for_new_name)
    await callback.answer()

@router.callback_query(F.data == "settings_general")
async def settings_general(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    # Перевіряємо, чи існують загальні налаштування
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND address_name IS NULL', (user_id,))
            if cursor.fetchone()[0] == 0:
                # Ініціалізуємо загальні налаштування за замовчуванням
                set_user_notification_settings(user_id, None, True, True, True)
    except Exception as e:
        logging.error(f"Error initializing general settings: {e}")

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

@router.callback_query(F.data == "settings_back")
async def settings_back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    addresses = get_user_addresses(user_id)

    # Ініціалізуємо налаштування для всіх адрес, якщо вони не існують
    for name, _, _ in addresses:
        # Перевіряємо, чи існують налаштування для цієї адреси
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, name))
                if cursor.fetchone()[0] == 0:
                    # Ініціалізуємо налаштування за замовчуванням
                    set_user_notification_settings(user_id, name, True, True, True)
        except Exception as e:
            logging.error(f"Error initializing settings for address {name}: {e}")

    text = "⚙️ <b>Налаштування сповіщень бота</b>\n\n"
    text += "Оберіть, що налаштувати:\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Загальні сповіщення", callback_data="settings_general")],
    ])

    for name, _, _ in addresses:
        settings = get_user_notification_settings(user_id, name)
        status = "✅" if settings['notifications_enabled'] else "❌"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name} {status}", callback_data=f"toggle_addr_{name}")])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_addr_"))
async def toggle_addr(callback: types.CallbackQuery):
    addr_name = callback.data.replace("toggle_addr_", "")
    user_id = callback.from_user.id

    settings = get_user_notification_settings(user_id, addr_name)
    new_val = not settings['notifications_enabled']
    set_user_notification_settings(user_id, addr_name, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])

    await callback.answer(f"Сповіщення для '{addr_name}' {'увімкнено' if new_val else 'вимкнено'}")

    # Оновлюємо повідомлення відразу
    addresses = get_user_addresses(user_id)

    text = "⚙️ <b>Налаштування сповіщень бота</b>\n\n"
    text += "Оберіть, що налаштувати:\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Загальні сповіщення", callback_data="settings_general")],
    ])

    for name, _, _ in addresses:
        settings = get_user_notification_settings(user_id, name)
        status = "✅" if settings['notifications_enabled'] else "❌"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name} {status}", callback_data=f"toggle_addr_{name}")])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# Address management handlers
@router.callback_query(F.data == "addr_edit_name")
async def addr_edit_name(callback: types.CallbackQuery):
    addresses = get_user_addresses(callback.from_user.id)
    if not addresses:
        await callback.message.edit_text("❌ У вас немає адрес для редагування.")
        return

    text = "✏️ <b>Оберіть адресу для зміни назви:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for name, subq, is_main in addresses:
        main_mark = " (основна)" if is_main else ""
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name}{main_mark}", callback_data=f"edit_name_{name}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="addr_back")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "addr_edit_queue")
async def addr_edit_queue(callback: types.CallbackQuery):
    addresses = get_user_addresses(callback.from_user.id)
    if not addresses:
        await callback.message.edit_text("❌ У вас немає адрес для зміни черги.")
        return

    text = "🔄 <b>Оберіть адресу для зміни черги:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for name, subq, is_main in addresses:
        main_mark = " (основна)" if is_main else ""
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name}: черга {subq}{main_mark}", callback_data=f"edit_queue_{name}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="addr_back")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "addr_set_main")
async def addr_set_main(callback: types.CallbackQuery):
    addresses = get_user_addresses(callback.from_user.id)
    if not addresses:
        await callback.message.edit_text("❌ У вас немає адрес.")
        return

    text = "⭐ <b>Оберіть адресу, яку зробити основною:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for name, subq, is_main in addresses:
        main_mark = " (основна)" if is_main else ""
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name}{main_mark}", callback_data=f"set_main_{name}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="addr_back")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "addr_delete")
async def addr_delete(callback: types.CallbackQuery):
    addresses = get_user_addresses(callback.from_user.id)
    if not addresses:
        await callback.message.edit_text("❌ У вас немає адрес для видалення.")
        return

    text = "🗑️ <b>Оберіть адресу для видалення:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for name, subq, is_main in addresses:
        main_mark = " (основна)" if is_main else ""
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name}{main_mark}", callback_data=f"delete_addr_{name}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="addr_back")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "addr_view_schedules")
async def addr_view_schedules(callback: types.CallbackQuery):
    addresses = get_user_addresses(callback.from_user.id)
    if not addresses:
        await callback.message.edit_text("❌ У вас немає адрес.")
        return

    text = "👀 <b>Оберіть адресу для перегляду графіка:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for name, subq, is_main in addresses:
        main_mark = " (основна)" if is_main else ""
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🏠 {name}: черга {subq}{main_mark}", callback_data=f"view_schedule_{name}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="addr_back")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "addr_back")
async def addr_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    addresses = get_user_addresses(callback.from_user.id)

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

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# Individual address action handlers
@router.callback_query(F.data.startswith("edit_name_"))
async def edit_name(callback: types.CallbackQuery, state: FSMContext):
    addr_name = callback.data.replace("edit_name_", "")
    await state.update_data(edit_addr_name=addr_name)
    await callback.message.edit_text(f"Введіть нову назву для адреси '{addr_name}':")
    await state.set_state(AddressStates.waiting_for_edit_name)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_queue_"))
async def edit_queue(callback: types.CallbackQuery, state: FSMContext):
    addr_name = callback.data.replace("edit_queue_", "")
    await state.update_data(edit_addr_name=addr_name)
    text = f"🔄 <b>Зміна черги для адреси '{addr_name}'</b>\n\nОберіть нову підчергу:"
    kb = get_queue_keyboard()
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="addr_edit_queue")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(AddressStates.waiting_for_edit_queue)
    await callback.answer()

@router.callback_query(F.data.startswith("set_main_"))
async def set_main(callback: types.CallbackQuery):
    addr_name = callback.data.replace("set_main_", "")
    set_main_address(callback.from_user.id, addr_name)
    await callback.message.edit_text(f"✅ <b>Успішно!</b>\nАдреса <b>{addr_name}</b> встановлена як основна.", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("delete_addr_"))
async def delete_addr(callback: types.CallbackQuery):
    addr_name = callback.data.replace("delete_addr_", "")
    addresses = get_user_addresses(callback.from_user.id)

    # Check if this is the only address
    if len(addresses) <= 1:
        await callback.message.edit_text("❌ Неможливо видалити єдину адресу. Спочатку додайте іншу адресу.")
        return

    # Check if this is main address
    is_main = any(name == addr_name and is_main for name, _, is_main in addresses)
    if is_main:
        await callback.message.edit_text("❌ Неможливо видалити основну адресу. Спочатку зробіть іншу адресу основною.")
        return

    delete_user_address(callback.from_user.id, addr_name)
    await callback.message.edit_text(f"✅ <b>Успішно!</b>\nАдреса <b>{addr_name}</b> видалена.", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("view_schedule_"))
async def view_schedule(callback: types.CallbackQuery):
    addr_name = callback.data.replace("view_schedule_", "")
    addresses = get_user_addresses(callback.from_user.id)
    addr_data = next((subq for name, subq, _ in addresses if name == addr_name), None)

    if not addr_data:
        await callback.message.edit_text("❌ Адреса не знайдена.")
        return

    await send_schedule_logic(callback.from_user.id, addr_data, "today")
    await callback.message.edit_text(f"📊 Графік для адреси <b>{addr_name}</b> надіслано в особисті повідомлення.", parse_mode="HTML")
    await callback.answer()

# General toggle handlers
@router.callback_query(F.data == "toggle_general_notifications")
async def toggle_general_notifications(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id)
    new_val = not settings['notifications_enabled']
    set_user_notification_settings(user_id, None, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])
    await callback.answer(f"Загальні сповіщення {'увімкнено' if new_val else 'вимкнено'}")

    # Refresh the menu
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

@router.callback_query(F.data == "toggle_general_new")
async def toggle_general_new(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id)
    new_val = not settings['new_schedule_enabled']
    set_user_notification_settings(user_id, None, settings['notifications_enabled'], new_val, settings['schedule_changes_enabled'])
    await callback.answer(f"Сповіщення про нові графіки {'увімкнено' if new_val else 'вимкнено'}")

    # Refresh the menu
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

@router.callback_query(F.data == "toggle_general_changes")
async def toggle_general_changes(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id)
    new_val = not settings['schedule_changes_enabled']
    set_user_notification_settings(user_id, None, settings['notifications_enabled'], settings['new_schedule_enabled'], new_val)
    await callback.answer(f"Сповіщення про зміни в графіках {'увімкнено' if new_val else 'вимкнено'}")

    # Refresh the menu
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

# Address-specific toggle handlers
@router.callback_query(F.data.startswith("toggle_addr_notifications_"))
async def toggle_addr_notifications(callback: types.CallbackQuery):
    addr_name = callback.data.replace("toggle_addr_notifications_", "")
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id, addr_name)
    new_val = not settings['notifications_enabled']
    set_user_notification_settings(user_id, addr_name, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])
    await callback.answer(f"Сповіщення про відключення для '{addr_name}' {'увімкнено' if new_val else 'вимкнено'}")

    # Refresh the address settings menu
    settings = get_user_notification_settings(user_id, addr_name)
    text = f"🏠 <b>Налаштування для адреси '{addr_name}'</b>\n\n"
    text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n"
    text += f"Можливе відключення: {'✅ Увімкнено' if settings['new_schedule_enabled'] else '❌ Вимкнено'}\n"
    text += f"Відновлення електропостачання: {'✅ Увімкнено' if settings['schedule_changes_enabled'] else '❌ Вимкнено'}\n\n"
    text += "Оберіть, що змінити:"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data=f"toggle_addr_notifications_{addr_name}")],
        [InlineKeyboardButton(text="⚠️ Можливе відключення", callback_data=f"toggle_addr_new_{addr_name}")],
        [InlineKeyboardButton(text="🔄 Відновлення електропостачання", callback_data=f"toggle_addr_changes_{addr_name}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("toggle_addr_new_"))
async def toggle_addr_new(callback: types.CallbackQuery):
    addr_name = callback.data.replace("toggle_addr_new_", "")
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id, addr_name)
    new_val = not settings['new_schedule_enabled']
    set_user_notification_settings(user_id, addr_name, settings['notifications_enabled'], new_val, settings['schedule_changes_enabled'])
    await callback.answer(f"Сповіщення про можливе відключення для '{addr_name}' {'увімкнено' if new_val else 'вимкнено'}")

    # Refresh the address settings menu
    settings = get_user_notification_settings(user_id, addr_name)
    text = f"🏠 <b>Налаштування для адреси '{addr_name}'</b>\n\n"
    text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n"
    text += f"Можливе відключення: {'✅ Увімкнено' if settings['new_schedule_enabled'] else '❌ Вимкнено'}\n"
    text += f"Відновлення електропостачання: {'✅ Увімкнено' if settings['schedule_changes_enabled'] else '❌ Вимкнено'}\n\n"
    text += "Оберіть, що змінити:"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data=f"toggle_addr_notifications_{addr_name}")],
        [InlineKeyboardButton(text="⚠️ Можливе відключення", callback_data=f"toggle_addr_new_{addr_name}")],
        [InlineKeyboardButton(text="🔄 Відновлення електропостачання", callback_data=f"toggle_addr_changes_{addr_name}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("toggle_addr_changes_"))
async def toggle_addr_changes(callback: types.CallbackQuery):
    addr_name = callback.data.replace("toggle_addr_changes_", "")
    user_id = callback.from_user.id
    settings = get_user_notification_settings(user_id, addr_name)
    new_val = not settings['schedule_changes_enabled']
    set_user_notification_settings(user_id, addr_name, settings['notifications_enabled'], settings['new_schedule_enabled'], new_val)
    await callback.answer(f"Сповіщення про відновлення для '{addr_name}' {'увімкнено' if new_val else 'вимкнено'}")

    # Refresh the address settings menu
    settings = get_user_notification_settings(user_id, addr_name)
    text = f"🏠 <b>Налаштування для адреси '{addr_name}'</b>\n\n"
    text += f"Сповіщення про відключення: {'✅ Увімкнено' if settings['notifications_enabled'] else '❌ Вимкнено'}\n"
    text += f"Можливе відключення: {'✅ Увімкнено' if settings['new_schedule_enabled'] else '❌ Вимкнено'}\n"
    text += f"Відновлення електропостачання: {'✅ Увімкнено' if settings['schedule_changes_enabled'] else '❌ Вимкнено'}\n\n"
    text += "Оберіть, що змінити:"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сповіщення про відключення", callback_data=f"toggle_addr_notifications_{addr_name}")],
        [InlineKeyboardButton(text="⚠️ Можливе відключення", callback_data=f"toggle_addr_new_{addr_name}")],
        [InlineKeyboardButton(text="🔄 Відновлення електропостачання", callback_data=f"toggle_addr_changes_{addr_name}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_back")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")