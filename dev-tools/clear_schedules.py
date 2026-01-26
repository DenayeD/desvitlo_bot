import sqlite3
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('UPDATE settings SET value = "{}" WHERE key = "known_schedules"')
conn.commit()
conn.close()
print('Cleared known_schedules')