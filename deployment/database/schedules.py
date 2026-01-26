import logging
from .connection import get_connection

def init_manual_schedules_table():
    """Create manual schedules table if it doesn't exist"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS manual_schedules (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                subqueue TEXT NOT NULL,
                guaranteed_text TEXT,
                possible_text TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                UNIQUE(date, subqueue)
            )
        ''')
        conn.commit()
        conn.close()
        logging.info("Manual schedules table initialized")
    except Exception as e:
        logging.error(f"Error creating manual_schedules table: {e}")

def get_manual_schedule(date, subqueue):
    """Get manual schedule for date and subqueue"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT guaranteed_text, possible_text, admin_id, created_at
            FROM manual_schedules
            WHERE date = ? AND subqueue = ?
        ''', (date, subqueue))
        res = cursor.fetchone()
        conn.close()
        if res:
            return {
                'guaranteed_text': res[0] or '',
                'possible_text': res[1] or '',
                'created_by': res[2],
                'created_at': res[3]
            }
        return None
    except Exception as e:
        logging.error(f"Error getting manual schedule for {date}, {subqueue}: {e}")
        return None

def set_manual_schedule(date, subqueue, guaranteed_text, possible_text, user_id):
    """Create or update manual schedule"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO manual_schedules
            (date, subqueue, guaranteed_text, possible_text, admin_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (date, subqueue, guaranteed_text, possible_text, user_id))
        conn.commit()
        conn.close()
        logging.info(f"Manual schedule set for {date}, {subqueue} by user {user_id}")
        return True
    except Exception as e:
        logging.error(f"Error setting manual schedule: {e}")
        return False

def delete_manual_schedule(date, subqueue):
    """Delete manual schedule"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM manual_schedules
            WHERE date = ? AND subqueue = ?
        ''', (date, subqueue))
        conn.commit()
        conn.close()
        logging.info(f"Manual schedule deactivated for {date}, {subqueue}")
        return True
    except Exception as e:
        logging.error(f"Error deleting manual schedule: {e}")
        return False

def get_combined_schedule(date, subqueue, site_schedule_text=None):
    """Get combined schedule: guaranteed from site + possible from manual"""
    guaranteed = ''
    possible = ''

    # Get manual schedule first
    manual = get_manual_schedule(date, subqueue)
    if manual:
        guaranteed = manual['guaranteed_text']
        possible = manual['possible_text']

    # If no manual schedule or empty guaranteed, try to get from site data
    if not guaranteed and site_schedule_text:
        # Parse site schedule text: "guaranteed_part; possible_part"
        if ';' in site_schedule_text:
            parts = site_schedule_text.split(';', 1)
            guaranteed = parts[0].strip()
            if len(parts) > 1:
                possible = parts[1].strip()
        else:
            # If no semicolon, treat all as guaranteed
            guaranteed = site_schedule_text.strip()

    return {
        'guaranteed': guaranteed,
        'possible': possible,
        'source': 'manual' if manual else ('site' if site_schedule_text else 'none')
    }