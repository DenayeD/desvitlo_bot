import sqlite3
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('SELECT value FROM settings WHERE key = "known_schedules"')
res = cursor.fetchone()
print('Current known_schedules:', res[0] if res else 'None')
conn.close()