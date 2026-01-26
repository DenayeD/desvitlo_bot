import sqlite3

# Перевіряємо server_users.db
conn = sqlite3.connect('server_users.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Таблиці в server_users.db:")
for table in tables:
    print(f"  {table[0]}")

# Перевіряємо, чи є таблиця user_notifications
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_notifications'")
if cursor.fetchone():
    print("\n✅ Таблиця user_notifications існує")
    cursor.execute("SELECT COUNT(*) FROM user_notifications")
    count = cursor.fetchone()[0]
    print(f"Записів у user_notifications: {count}")
else:
    print("\n❌ Таблиця user_notifications НЕ існує!")

conn.close()

# Перевіряємо users.db для порівняння
print("\n" + "="*50)
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Таблиці в users.db:")
for table in tables:
    print(f"  {table[0]}")

cursor.execute("SELECT COUNT(*) FROM user_notifications")
count = cursor.fetchone()[0]
print(f"Записів у user_notifications: {count}")

conn.close()