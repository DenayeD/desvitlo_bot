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
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")