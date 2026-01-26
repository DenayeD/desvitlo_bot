import sqlite3
import os
import logging
from contextlib import contextmanager

def get_db_path():
    """Get the database file path from environment or default"""
    return os.getenv('DATABASE_PATH', 'users.db')

@contextmanager
def get_db_connection():
    """Context manager for database connections with proper cleanup"""
    conn = None
    try:
        conn = sqlite3.connect(get_db_path(), timeout=30.0)
        yield conn
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def get_connection():
    """Get database connection with timeout to avoid locking (deprecated, use get_db_connection)"""
    return sqlite3.connect(get_db_path(), timeout=30.0)

def init_db():
    """Initialize the database with all required tables"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Users table
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, subqueue TEXT)')

    # User addresses table
    cursor.execute('''CREATE TABLE IF NOT EXISTS addresses (
        user_id INTEGER,
        name TEXT,
        subqueue TEXT,
        is_main BOOLEAN DEFAULT 0,
        PRIMARY KEY (user_id, name)
    )''')

    # Global settings (last schedule date)
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')

    # Notification history (to avoid duplicates)
    cursor.execute('CREATE TABLE IF NOT EXISTS sent_alerts (user_id INTEGER, event_time TEXT, event_date TEXT)')

    # Notification settings
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_notifications (
        user_id INTEGER,
        address_name TEXT,
        notifications_enabled BOOLEAN DEFAULT 1,
        new_schedule_enabled BOOLEAN DEFAULT 1,
        schedule_changes_enabled BOOLEAN DEFAULT 1,
        PRIMARY KEY (user_id, address_name)
    )''')

    # Manual schedules for admins
    cursor.execute('''CREATE TABLE IF NOT EXISTS manual_schedules (
        date TEXT,
        subqueue TEXT,
        guaranteed_text TEXT,
        possible_text TEXT,
        admin_id INTEGER,
        created_at TEXT,
        updated_at TEXT,
        PRIMARY KEY (date, subqueue)
    )''')

    # Migrate existing users
    cursor.execute('SELECT user_id, subqueue FROM users WHERE subqueue IS NOT NULL')
    existing_users = cursor.fetchall()
    for user_id, subqueue in existing_users:
        # Check if addresses already exist for this user
        cursor.execute('SELECT COUNT(*) FROM addresses WHERE user_id = ?', (user_id,))
        if cursor.fetchone()[0] == 0:
            # Add main address "Дім"
            cursor.execute('INSERT INTO addresses (user_id, name, subqueue, is_main) VALUES (?, ?, ?, 1)', (user_id, 'Дім', subqueue))

    # Initialize settings for all users
    cursor.execute('SELECT DISTINCT user_id FROM users')  # All users, not just those with addresses
    all_users = cursor.fetchall()
    for (user_id,) in all_users:
        # General settings
        cursor.execute('SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND address_name IS NULL', (user_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, NULL, 1, 1, 1)', (user_id,))
        # Settings for addresses
        cursor.execute('SELECT name FROM addresses WHERE user_id = ?', (user_id,))
        addresses = cursor.fetchall()
        for (name,) in addresses:
            cursor.execute('SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND address_name = ?', (user_id, name))
            if cursor.fetchone()[0] == 0:
                cursor.execute('INSERT INTO user_notifications (user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled) VALUES (?, ?, 1, 1, 1)', (user_id, name))

    conn.commit()
    conn.close()

def get_connection():
    """Get database connection with timeout to avoid locking"""
    return sqlite3.connect(get_db_path(), timeout=30.0)