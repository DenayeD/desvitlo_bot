import sqlite3

def get_user_notification_settings(user_id, address_name=None):
    try:
        conn = sqlite3.connect('users.db')  # Використовуємо правильну БД
        cursor = conn.cursor()
        if address_name is None:
            # Загальні налаштування
            cursor.execute('SELECT notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE user_id = ? AND address_name IS NULL', (user_id,))
        else:
            # Налаштування для конкретної адреси
            cursor.execute('SELECT notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, address_name))
        res = cursor.fetchone()
        conn.close()
        if res:
            return {
                'notifications_enabled': res[0],
                'new_schedule_enabled': res[1],
                'schedule_changes_enabled': res[2]
            }
        else:
            # Дефолтні налаштування
            return {
                'notifications_enabled': True,
                'new_schedule_enabled': True,
                'schedule_changes_enabled': True
            }
    except Exception as e:
        print(f"Error getting notification settings: {e}")
        return {
            'notifications_enabled': True,
            'new_schedule_enabled': True,
            'schedule_changes_enabled': True
        }

def set_user_notification_settings(user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled):
    try:
        conn = sqlite3.connect('users.db')  # Використовуємо правильну БД
        cursor = conn.cursor()
        # Перетворюємо булеві значення в цілі числа явно
        notifications_enabled = int(notifications_enabled)
        new_schedule_enabled = int(new_schedule_enabled)
        schedule_changes_enabled = int(schedule_changes_enabled)
        cursor.execute('INSERT OR REPLACE INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, ?, ?, ?, ?)',
                       (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled))
        conn.commit()
        conn.close()
        print(f"Set settings for user {user_id}, addr {address_name}: {notifications_enabled}, {new_schedule_enabled}, {schedule_changes_enabled}")
    except Exception as e:
        print(f"Error setting notification settings: {e}")

# Тестуємо
user_id = 175902519

print("Початкові налаштування:")
settings = get_user_notification_settings(user_id)
print(settings)

print("\nЗмінюємо notifications_enabled на протилежне:")
new_val = not settings['notifications_enabled']
print(f"new_val = {new_val}")
set_user_notification_settings(user_id, None, new_val, settings['new_schedule_enabled'], settings['schedule_changes_enabled'])

print("\nНалаштування після зміни:")
settings_after = get_user_notification_settings(user_id)
print(settings_after)

print(f"\nЧи змінилося? {settings['notifications_enabled'] != settings_after['notifications_enabled']}")