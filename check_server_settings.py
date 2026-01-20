import sqlite3

conn = sqlite3.connect('server_users.db')
cursor = conn.cursor()

print("Записи з address_name = NULL (загальні налаштування):")
cursor.execute("SELECT user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE address_name IS NULL LIMIT 10")
rows = cursor.fetchall()
for row in rows:
    print(f"User: {row[0]}, Addr: {row[1]}, Notif: {row[2]}, New: {row[3]}, Changes: {row[4]}")

print("\nЗаписи з address_name != NULL (адресні налаштування):")
cursor.execute("SELECT user_id, address_name, notifications_enabled, new_schedule_enabled, schedule_changes_enabled FROM user_notifications WHERE address_name IS NOT NULL LIMIT 10")
rows = cursor.fetchall()
for row in rows:
    print(f"User: {row[0]}, Addr: {row[1]}, Notif: {row[2]}, New: {row[3]}, Changes: {row[4]}")

conn.close()