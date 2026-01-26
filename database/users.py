from .connection import get_connection

def update_user_queue(user_id, subqueue):
    """Update or insert user queue"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, subqueue) VALUES (?, ?)', (user_id, subqueue))
    conn.commit()
    conn.close()

def get_user_subqueue(user_id):
    """Get user's main address subqueue"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT subqueue FROM addresses WHERE user_id = ? AND is_main = 1', (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None