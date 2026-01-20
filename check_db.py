import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Перевіряємо таблицю
cursor.execute('SELECT COUNT(*) FROM user_notifications')
count = cursor.fetchone()[0]
print(f'Всього записів у user_notifications: {count}')

if count > 0:
    cursor.execute('SELECT * FROM user_notifications LIMIT 5')
    records = cursor.fetchall()
    print('Приклади записів:')
    for record in records:
        print(f'  User: {record[0]}, Address: {record[1]}, Outage: {record[2]}, New: {record[3]}, Changes: {record[4]}')

# Перевіряємо структуру таблиці
cursor.execute('PRAGMA table_info(user_notifications)')
columns = cursor.fetchall()
print('Колонки таблиці:')
for col in columns:
    print(f'  {col[1]} ({col[2]})')

conn.close()