import logging
from .connection import get_db_connection

def get_user_notification_settings(user_id, address_name=None):
    """Get notification settings for user and optional address"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if address_name is None:
                # General settings
                cursor.execute('SELECT notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE user_id = ? AND address_name IS NULL', (user_id,))
            else:
                # Settings for specific address
                cursor.execute('SELECT notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, address_name))
            res = cursor.fetchone()
            logging.info(f"Get settings for user {user_id}, addr {address_name}: {res}")
            if res:
                return {
                    'notifications_enabled': res[0],
                    'new_schedule_enabled': res[1],
                    'schedule_changes_enabled': res[2]
                }
            else:
                # Default settings
                logging.info(f"No row found for user {user_id}, addr {address_name}, returning defaults")
                return {
                    'notifications_enabled': True,
                    'new_schedule_enabled': True,
                    'schedule_changes_enabled': True
                }
    except Exception as e:
        logging.error(f"Error getting notification settings for user {user_id}, addr {address_name}: {e}")
        return {
            'notifications_enabled': True,
            'new_schedule_enabled': True,
            'schedule_changes_enabled': True
        }

def set_user_notification_settings(user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled):
    """Set notification settings for user and optional address"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Convert boolean values to integers explicitly
            notifications_enabled = int(notifications_enabled)
            new_schedule_enabled = int(new_schedule_enabled)
            schedule_changes_enabled = int(schedule_changes_enabled)

            logging.info(f"Setting notifications for user {user_id}, addr {address_name}: {notifications_enabled}, {new_schedule_enabled}, {schedule_changes_enabled}")

            # Use INSERT OR REPLACE to avoid race conditions
            cursor.execute('INSERT OR REPLACE INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, ?, ?, ?, ?)',
                           (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled))

            conn.commit()
            logging.info(f"Successfully set notifications for user {user_id}, addr {address_name}")
    except Exception as e:
        logging.error(f"Error setting notification settings for user {user_id}, addr {address_name}: {e}")
        raise

def init_user_notification_settings(user_id):
    """Initialize default notification settings for user"""
    from .addresses import get_user_addresses

    # Initialize default settings for user addresses
    addresses = get_user_addresses(user_id)
    for name, _, _ in addresses:
        settings = get_user_notification_settings(user_id, name)
        if not settings:  # If none exist, set defaults
            set_user_notification_settings(user_id, name, True, True, True)
    # General settings
    settings = get_user_notification_settings(user_id)
    if not settings:
        set_user_notification_settings(user_id, None, True, True, True)