from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.addresses import get_user_addresses, add_user_address, update_address_queue, set_main_address, delete_user_address
from database.users import update_user_queue
from database.notifications import get_user_notification_settings, set_user_notification_settings
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
        add_user_address(callback.from_user.id, name, subq)
        await callback.message.edit_text(f"✅ <b>Успішно!</b>\nСтворено адресу <b>{name}</b> з чергою <b>{subq}</b>.", parse_mode="HTML")
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
            add_user_address(callback.from_user.id, "Дім", subq)
            set_main_address(callback.from_user.id, "Дім")
            await callback.message.edit_text(f"✅ <b>Успішно!</b>\nСтворено адресу <b>Дім</b> з чергою <b>{subq}</b>.", parse_mode="HTML")
            await send_schedule_logic(callback.from_user.id, subq, "today")
    await callback.answer()

@router.callback_query(F.data == "addr_add")
async def addr_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введіть назву нової адреси (наприклад, 'Дім', 'Робота'):")
    await state.set_state(AddressStates.waiting_for_new_name)
    await callback.answer()

@router.callback_query(F.data == "settings_general")
async def settings_general(callback: types.CallbackQuery):
    user_id = callback.from_user.id
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

@router.callback_query(F.data.startswith("settings_addr_"))
async def settings_addr(callback: types.CallbackQuery):
    addr_name = callback.data.replace("settings_addr_", "")
    user_id = callback.from_user.id
    
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
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_"))
async def toggle_setting(callback: types.CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    
    if data == "toggle_general_notifications":
        settings = get_user_notification_settings(user_id)
        logging.info(f"Before toggle: {settings}")
        new_val = not settings['notifications_enabled']
        set_user_notification_settings(user_id, None, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])
        await callback.answer(f"Сповіщення про відключення {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
        settings = get_user_notification_settings(user_id)
        logging.info(f"After toggle: {settings}")
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
        
    elif data == "toggle_general_new":
        settings = get_user_notification_settings(user_id)
        new_val = not settings['new_schedule_enabled']
        set_user_notification_settings(user_id, None, settings['notifications_enabled'], new_val, settings['schedule_changes_enabled'])
        await callback.answer(f"Сповіщення про нові графіки {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
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
        
    elif data == "toggle_general_changes":
        settings = get_user_notification_settings(user_id)
        new_val = not settings['schedule_changes_enabled']
        set_user_notification_settings(user_id, None, settings['notifications_enabled'], settings['new_schedule_enabled'], new_val)
        await callback.answer(f"Сповіщення про зміни в графіках {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
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
        
    elif data.startswith("toggle_addr_notifications_"):
        addr_name = data.replace("toggle_addr_notifications_", "")
        settings = get_user_notification_settings(user_id, addr_name)
        new_val = not settings['notifications_enabled']
        set_user_notification_settings(user_id, addr_name, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])
        await callback.answer(f"Сповіщення про відключення для '{addr_name}' {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
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
        
    elif data.startswith("toggle_addr_new_"):
        addr_name = data.replace("toggle_addr_new_", "")
        settings = get_user_notification_settings(user_id, addr_name)
        new_val = not settings['new_schedule_enabled']
        set_user_notification_settings(user_id, addr_name, settings['notifications_enabled'], new_val, settings['schedule_changes_enabled'])
        await callback.answer(f"Сповіщення про можливе відключення для '{addr_name}' {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
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
        
    elif data.startswith("toggle_addr_changes_"):
        addr_name = data.replace("toggle_addr_changes_", "")
        settings = get_user_notification_settings(user_id, addr_name)
        new_val = not settings['schedule_changes_enabled']
        set_user_notification_settings(user_id, addr_name, settings['notifications_enabled'], settings['new_schedule_enabled'], new_val)
        await callback.answer(f"Сповіщення про відновлення для '{addr_name}' {'увімкнено' if new_val else 'вимкнено'}")
        
        # Оновлюємо повідомлення відразу
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
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")#   A d d r e s s   m a n a g e m e n t   h a n d l e r s 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a   = =   " a d d r _ e d i t _ n a m e " ) 
 
 a s y n c   d e f   a d d r _ e d i t _ n a m e ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
         i f   n o t   a d d r e s s e s : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
       � !    �  X � !    �  �! � !   � � !  ! �  � �  V!S  �   !. " ) 
 
                 r e t u r n 
 
 
 
         t e x t   =   " 2Z?Q  < b >  [ �  � !! ! !
   �  �! � !!S   � � !   �  X!   Q    �  �   Q: < / b > \ n \ n " 
 
         k b   =   I n l i n e K e y b o a r d M a r k u p ( i n l i n e _ k e y b o a r d = [ ] ) 
 
 
 
         f o r   n a m e ,   s u b q ,   i s _ m a i n   i n   a d d r e s s e s : 
 
                 m a i n _ m a r k   =   "   (  U!  U   � ) "   i f   i s _ m a i n   e l s e   " " 
 
                 k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = f " @_�   { n a m e } { m a i n _ m a r k } " ,   c a l l b a c k _ d a t a = f " e d i t _ n a m e _ { n a m e } " ) ] ) 
 
 
 
         k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2� & ?Q   \ �  �  �  �" ,   c a l l b a c k _ d a t a = " a d d r _ b a c k " ) ] ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( t e x t ,   r e p l y _ m a r k u p = k b ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a   = =   " a d d r _ e d i t _ q u e u e " ) 
 
 a s y n c   d e f   a d d r _ e d i t _ q u e u e ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
         i f   n o t   a d d r e s s e s : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
       � !    �  X � !    �  �! � !   � � !   �  X!   Q  !!  � ! V Q. " ) 
 
                 r e t u r n 
 
 
 
         t e x t   =   " @_    < b >  [ �  � !! ! !
   �  �! � !!S   � � !   �  X!   Q  !!  � ! V Q: < / b > \ n \ n " 
 
         k b   =   I n l i n e K e y b o a r d M a r k u p ( i n l i n e _ k e y b o a r d = [ ] ) 
 
 
 
         f o r   n a m e ,   s u b q ,   i s _ m a i n   i n   a d d r e s s e s : 
 
                 m a i n _ m a r k   =   "   (  U!  U   � ) "   i f   i s _ m a i n   e l s e   " " 
 
                 k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = f " @_�   { n a m e } :   !!  � ! V �   { s u b q } { m a i n _ m a r k } " ,   c a l l b a c k _ d a t a = f " e d i t _ q u e u e _ { n a m e } " ) ] ) 
 
 
 
         k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2� & ?Q   \ �  �  �  �" ,   c a l l b a c k _ d a t a = " a d d r _ b a c k " ) ] ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( t e x t ,   r e p l y _ m a r k u p = k b ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a   = =   " a d d r _ s e t _ m a i n " ) 
 
 a s y n c   d e f   a d d r _ s e t _ m a i n ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
         i f   n o t   a d d r e s s e s : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
       � !    �  X � !    �  �! � !. " ) 
 
                 r e t u r n 
 
 
 
         t e x t   =   " 2� R  < b >  [ �  � !! ! !
   �  �! � !!S,   ! T!S   � ! U �  Q!  Q   U!  U   U!: < / b > \ n \ n " 
 
         k b   =   I n l i n e K e y b o a r d M a r k u p ( i n l i n e _ k e y b o a r d = [ ] ) 
 
 
 
         f o r   n a m e ,   s u b q ,   i s _ m a i n   i n   a d d r e s s e s : 
 
                 m a i n _ m a r k   =   "   (  U!  U   � ) "   i f   i s _ m a i n   e l s e   " " 
 
                 k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = f " @_�   { n a m e } { m a i n _ m a r k } " ,   c a l l b a c k _ d a t a = f " s e t _ m a i n _ { n a m e } " ) ] ) 
 
 
 
         k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2� & ?Q   \ �  �  �  �" ,   c a l l b a c k _ d a t a = " a d d r _ b a c k " ) ] ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( t e x t ,   r e p l y _ m a r k u p = k b ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a   = =   " a d d r _ d e l e t e " ) 
 
 a s y n c   d e f   a d d r _ d e l e t e ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
         i f   n o t   a d d r e s s e s : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
       � !    �  X � !    �  �! � !   � � !    Q � �  �  �   !. " ) 
 
                 r e t u r n 
 
 
 
         t e x t   =   " @_  ?Q  < b >  [ �  � !! ! !
   �  �! � !!S   � � !    Q � �  �  �   !: < / b > \ n \ n " 
 
         k b   =   I n l i n e K e y b o a r d M a r k u p ( i n l i n e _ k e y b o a r d = [ ] ) 
 
 
 
         f o r   n a m e ,   s u b q ,   i s _ m a i n   i n   a d d r e s s e s : 
 
                 m a i n _ m a r k   =   "   (  U!  U   � ) "   i f   i s _ m a i n   e l s e   " " 
 
                 k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = f " @_�   { n a m e } { m a i n _ m a r k } " ,   c a l l b a c k _ d a t a = f " d e l e t e _ a d d r _ { n a m e } " ) ] ) 
 
 
 
         k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2� & ?Q   \ �  �  �  �" ,   c a l l b a c k _ d a t a = " a d d r _ b a c k " ) ] ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( t e x t ,   r e p l y _ m a r k u p = k b ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a   = =   " a d d r _ v i e w _ s c h e d u l e s " ) 
 
 a s y n c   d e f   a d d r _ v i e w _ s c h e d u l e s ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
         i f   n o t   a d d r e s s e s : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
       � !    �  X � !    �  �! � !. " ) 
 
                 r e t u r n 
 
 
 
         t e x t   =   " @_   < b >  [ �  � !! ! !
   �  �! � !!S   � � !   W � ! �  V � ! �!S   V! � ! !  T � : < / b > \ n \ n " 
 
         k b   =   I n l i n e K e y b o a r d M a r k u p ( i n l i n e _ k e y b o a r d = [ ] ) 
 
 
 
         f o r   n a m e ,   s u b q ,   i s _ m a i n   i n   a d d r e s s e s : 
 
                 m a i n _ m a r k   =   "   (  U!  U   � ) "   i f   i s _ m a i n   e l s e   " " 
 
                 k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = f " @_�   { n a m e } :   !!  � ! V �   { s u b q } { m a i n _ m a r k } " ,   c a l l b a c k _ d a t a = f " v i e w _ s c h e d u l e _ { n a m e } " ) ] ) 
 
 
 
         k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2� & ?Q   \ �  �  �  �" ,   c a l l b a c k _ d a t a = " a d d r _ b a c k " ) ] ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( t e x t ,   r e p l y _ m a r k u p = k b ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a   = =   " a d d r _ b a c k " ) 
 
 a s y n c   d e f   a d d r _ b a c k ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ,   s t a t e :   F S M C o n t e x t ) : 
 
         a w a i t   s t a t e . c l e a r ( ) 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
 
 
         t e x t   =   " @_�   < b >    � !� !    �  �! � ! Q: < / b > \ n \ n " 
 
         f o r   n a m e ,   s u b q ,   i s _ m a i n   i n   a d d r e s s e s : 
 
                 m a i n _ m a r k   =   "   (  U!  U   � ) "   i f   i s _ m a i n   e l s e   " " 
 
                 t e x t   + =   f " 2^  < b > { n a m e } < / b > :   !!  � ! V �   { s u b q } { m a i n _ m a r k } \ n " 
 
 
 
         k b   =   I n l i n e K e y b o a r d M a r k u p ( i n l i n e _ k e y b o a r d = [ 
 
                 [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2["      U � � !  Q   �  �! � !!S" ,   c a l l b a c k _ d a t a = " a d d r _ a d d " ) ] , 
 
                 [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2Z?Q   �  �  � �  V!S  � !  Q    �  �  !S" ,   c a l l b a c k _ d a t a = " a d d r _ e d i t _ n a m e " ) ] , 
 
                 [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " @_       X!   Q!  Q  !!  � ! V!S" ,   c a l l b a c k _ d a t a = " a d d r _ e d i t _ q u e u e " ) ] , 
 
                 [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2� R    ! U �  Q!  Q   U!  U   U!" ,   c a l l b a c k _ d a t a = " a d d r _ s e t _ m a i n " ) ] , 
 
                 [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " @_  ?Q     Q � �  �  Q!  Q   �  �! � !!S" ,   c a l l b a c k _ d a t a = " a d d r _ d e l e t e " ) ] , 
 
                 [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " @_    _ � ! �  V � ! !S!  Q   V! � ! !  T Q" ,   c a l l b a c k _ d a t a = " a d d r _ v i e w _ s c h e d u l e s " ) ] 
 
         ] ) 
 
 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( t e x t ,   r e p l y _ m a r k u p = k b ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 #   I n d i v i d u a l   a d d r e s s   a c t i o n   h a n d l e r s 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a . s t a r t s w i t h ( " e d i t _ n a m e _ " ) ) 
 
 a s y n c   d e f   e d i t _ n a m e ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ,   s t a t e :   F S M C o n t e x t ) : 
 
         a d d r _ n a m e   =   c a l l b a c k . d a t a . r e p l a c e ( " e d i t _ n a m e _ " ,   " " ) 
 
         a w a i t   s t a t e . u p d a t e _ d a t a ( e d i t _ a d d r _ n a m e = a d d r _ n a m e ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( f "     �  �! ! !
    U !S    �  �  !S   � � !   �  �! � ! Q  ' { a d d r _ n a m e } ' : " ) 
 
         a w a i t   s t a t e . s e t _ s t a t e ( A d d r e s s S t a t e s . w a i t i n g _ f o r _ e d i t _ n a m e ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a . s t a r t s w i t h ( " e d i t _ q u e u e _ " ) ) 
 
 a s y n c   d e f   e d i t _ q u e u e ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r _ n a m e   =   c a l l b a c k . d a t a . r e p l a c e ( " e d i t _ q u e u e _ " ,   " " ) 
 
         t e x t   =   f " @_    < b >    X!   �   !!  � ! V Q   � � !   �  �! � ! Q  ' { a d d r _ n a m e } ' < / b > \ n \ n  [ �  � !! ! !
    U !S   W!  �!!  � ! V!S: " 
 
         k b   =   g e t _ q u e u e _ k e y b o a r d ( ) 
 
         k b . i n l i n e _ k e y b o a r d . a p p e n d ( [ I n l i n e K e y b o a r d B u t t o n ( t e x t = " 2� & ?Q   \ �  �  �  �" ,   c a l l b a c k _ d a t a = " a d d r _ e d i t _ q u e u e " ) ] ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( t e x t ,   r e p l y _ m a r k u p = k b ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a . s t a r t s w i t h ( " s e t _ m a i n _ " ) ) 
 
 a s y n c   d e f   s e t _ m a i n ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r _ n a m e   =   c a l l b a c k . d a t a . r e p l a c e ( " s e t _ m a i n _ " ,   " " ) 
 
         s e t _ m a i n _ a d d r e s s ( c a l l b a c k . f r o m _ u s e r . i d ,   a d d r _ n a m e ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( f " 2Z&   < b >  ! W! !�   U! < / b > \ n  R �! � ! �   < b > { a d d r _ n a m e } < / b >    !!  �   U  �  �   �   ! T   U!  U   � . " ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a . s t a r t s w i t h ( " d e l e t e _ a d d r _ " ) ) 
 
 a s y n c   d e f   d e l e t e _ a d d r ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r _ n a m e   =   c a l l b a c k . d a t a . r e p l a c e ( " d e l e t e _ a d d r _ " ,   " " ) 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
 
 
         #   C h e c k   i f   t h i s   i s   t h e   o n l y   a d d r e s s 
 
         i f   l e n ( a d d r e s s e s )   < =   1 : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
   \ �  X U �  �  Q  U    Q � �  �  Q!  Q  !  � Q !S   �  �! � !!S.     W U!!  � !  T!S   � U � �  !!  �   !  !� !S   �  �! � !!S. " ) 
 
                 r e t u r n 
 
 
 
         #   C h e c k   i f   t h i s   i s   m a i n   a d d r e s s 
 
         i s _ m a i n   =   a n y ( n a m e   = =   a d d r _ n a m e   a n d   i s _ m a i n   f o r   n a m e ,   _ ,   i s _ m a i n   i n   a d d r e s s e s ) 
 
         i f   i s _ m a i n : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
   \ �  X U �  �  Q  U    Q � �  �  Q!  Q   U!  U  !S   �  �! � !!S.     W U!!  � !  T!S   � ! U � ! ! !
  !  !� !S   �  �! � !!S   U!  U   U!. " ) 
 
                 r e t u r n 
 
 
 
         d e l e t e _ u s e r _ a d d r e s s ( c a l l b a c k . f r o m _ u s e r . i d ,   a d d r _ n a m e ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( f " 2Z&   < b >  ! W! !�   U! < / b > \ n  R �! � ! �   < b > { a d d r _ n a m e } < / b >     Q � �  �  �   � . " ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 
 
 @ r o u t e r . c a l l b a c k _ q u e r y ( F . d a t a . s t a r t s w i t h ( " v i e w _ s c h e d u l e _ " ) ) 
 
 a s y n c   d e f   v i e w _ s c h e d u l e ( c a l l b a c k :   t y p e s . C a l l b a c k Q u e r y ) : 
 
         a d d r _ n a m e   =   c a l l b a c k . d a t a . r e p l a c e ( " v i e w _ s c h e d u l e _ " ,   " " ) 
 
         a d d r e s s e s   =   g e t _ u s e r _ a d d r e s s e s ( c a l l b a c k . f r o m _ u s e r . i d ) 
 
         a d d r _ d a t a   =   n e x t ( ( s u b q   f o r   n a m e ,   s u b q ,   _   i n   a d d r e s s e s   i f   n a m e   = =   a d d r _ n a m e ) ,   N o n e ) 
 
 
 
         i f   n o t   a d d r _ d a t a : 
 
                 a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( " 2\
   R �! � ! �     �    �   �  ! � �   � . " ) 
 
                 r e t u r n 
 
 
 
         a w a i t   s e n d _ s c h e d u l e _ l o g i c ( c a l l b a c k . f r o m _ u s e r . i d ,   a d d r _ d a t a ,   " t o d a y " ) 
 
         a w a i t   c a l l b a c k . m e s s a g e . e d i t _ t e x t ( f " @_ 	    ! � ! !  T   � � !   �  �! � ! Q  < b > { a d d r _ n a m e } < / b >     �  �! ! �  �   U      U! U �  Q!! !    W U !  � U X �  �   !. " ,   p a r s e _ m o d e = " H T M L " ) 
 
         a w a i t   c a l l b a c k . a n s w e r ( ) 
 
 