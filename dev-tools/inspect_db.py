import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables:", tables)

for table in tables:
    print(f"\nTable: {table}")
    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    print(f"Rows: {len(rows)}")
    if rows:
        print("Sample rows:", rows[:5])  # first 5

conn.close()