from .connection import get_db_connection
from .notifications import set_user_notification_settings

def get_user_addresses(user_id):
    """Get all user addresses"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, subqueue, is_main FROM addresses WHERE user_id = ? ORDER BY is_main DESC, name', (user_id,))
        addresses = cursor.fetchall()
        return addresses

def add_user_address(user_id, name, subqueue):
    """Add new address for user"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check if address with this name already exists
        cursor.execute('SELECT COUNT(*) FROM addresses WHERE user_id = ? AND name = ?', (user_id, name))
        if cursor.fetchone()[0] > 0:
            raise ValueError(f"Адреса з назвою '{name}' вже існує")

        cursor.execute('INSERT INTO addresses (user_id, name, subqueue, is_main) VALUES (?, ?, ?, 0)', (user_id, name, subqueue))
        # Initialize settings for new address
        cursor.execute('INSERT OR REPLACE INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, ?, 1, 1, 1)',
                       (user_id, name))
        conn.commit()

def update_address_name(user_id, old_name, new_name):
    """Update address name"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE addresses SET name = ? WHERE user_id = ? AND name = ?', (new_name, user_id, old_name))
        conn.commit()

def update_address_queue(user_id, name, new_subqueue):
    """Update address subqueue"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE addresses SET subqueue = ? WHERE user_id = ? AND name = ?', (new_subqueue, user_id, name))
        conn.commit()

def set_main_address(user_id, name):
    """Set address as main"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE addresses SET is_main = 0 WHERE user_id = ?', (user_id,))
        cursor.execute('UPDATE addresses SET is_main = 1 WHERE user_id = ? AND name = ?', (user_id, name))
        conn.commit()

def delete_user_address(user_id, name):
    """Delete user address"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Don't delete if it's the main address and there are others
        cursor.execute('SELECT COUNT(*) FROM addresses WHERE user_id = ?', (user_id,))
        count = cursor.fetchone()[0]
        if count > 1:
            cursor.execute('DELETE FROM addresses WHERE user_id = ? AND name = ?', (user_id, name))
            # If deleted was main, assign another as main
            cursor.execute('SELECT is_main FROM addresses WHERE user_id = ? AND name = ?', (user_id, name))
            was_main = cursor.fetchone()
            if was_main and was_main[0]:
                cursor.execute('UPDATE addresses SET is_main = 1 WHERE user_id = ? LIMIT 1', (user_id,))
            # Remove settings for this address
            cursor.execute('DELETE FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, name))
        conn.commit()

def get_all_user_addresses():
    """Get all user addresses for all users (for monitoring)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, name, subqueue FROM addresses ORDER BY user_id, name')
        addresses = cursor.fetchall()
        return addresses