#!/usr/bin/env python3
"""
Database Inspector for Electricity Checker Bot
Shows detailed statistics and user information from the bot's database.

Usage: python db_inspector.py [database_file]
If no database file is specified, uses 'users.db' in current directory.
"""

import sqlite3
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

def print_help():
    print("Database Inspector for Electricity Checker Bot")
    print("Usage: python db_inspector.py [database_file] [options]")
    print("If no database file is specified, uses 'users.db'")
    print("\nOptions:")
    print("  --multi-address    Show only users with multiple addresses")
    print("\nShows:")
    print("- General statistics (users, addresses, notifications)")
    print("- Distribution by subqueues")
    print("- Detailed user information with addresses and settings")
    print("- Recent alerts from the last day")

def print_user_info(user_id, addresses):
    print(f"\nКористувач {user_id}:")

    for name, subqueue, is_main, notif_en, new_sched_en, sched_changes_en in addresses:
        marker = " [ОСНОВНА]" if is_main else ""
        print(f"  '{name or 'Основна'}'{marker}: черга {subqueue}")

        if notif_en is not None:
            print(f"    Сповіщення: {'УВІМКНЕНО' if notif_en else 'ВИМКНЕНО'}")
            print(f"    Нові графіки: {'УВІМКНЕНО' if new_sched_en else 'ВИМКНЕНО'}")
            print(f"    Зміни графіків: {'УВІМКНЕНО' if sched_changes_en else 'ВИМКНЕНО'}")
        else:
            print("    Налаштування: за замовчуванням")

def inspect_database(db_file, multi_address=False):
    if not os.path.exists(db_file):
        print(f"ПОМИЛКА: Файл бази даних '{db_file}' не знайдено!")
        return

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        print("=== ЗАГАЛЬНА СТАТИСТИКА ===")

        # Users and addresses
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM addresses')
        total_users = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM addresses')
        total_addresses = cursor.fetchone()[0]

        print(f"Користувачів: {total_users}")
        print(f"Адрес: {total_addresses}")

        # Notifications settings
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_notifications')
        users_with_config = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_notifications WHERE notifications_enabled = 1')
        users_with_notifications = cursor.fetchone()[0]

        print(f"З налаштованими сповіщеннями: {users_with_config}")
        print(f"З увімкненими сповіщеннями: {users_with_notifications}")

        # Alerts
        cursor.execute('SELECT COUNT(*) FROM sent_alerts')
        total_alerts = cursor.fetchone()[0]
        print(f"Загалом сповіщень: {total_alerts}")

        print("\n=== РОЗПОДІЛ ПО ЧЕРГАХ ===")
        cursor.execute('SELECT subqueue, COUNT(*) FROM addresses GROUP BY subqueue ORDER BY subqueue')
        for subq, count in cursor.fetchall():
            print(f"  {subq}: {count} адрес")

        print("\n=== КОРИСТУВАЧІ ===")
        if multi_address:
            print("(Тільки користувачі з декількома адресами)")
        
        # Build query based on multi_address flag
        where_clause = ""
        if multi_address:
            where_clause = "WHERE a.user_id IN (SELECT user_id FROM addresses GROUP BY user_id HAVING COUNT(*) > 1)"
        
        query = f'''
            SELECT
                a.user_id,
                a.name,
                a.subqueue,
                a.is_main,
                n.notifications_enabled,
                n.new_schedule_enabled,
                n.schedule_changes_enabled
            FROM addresses a
            LEFT JOIN user_notifications n ON a.user_id = n.user_id
                AND (a.name = n.address_name OR (a.name IS NULL AND n.address_name IS NULL))
            {where_clause}
            ORDER BY a.user_id, a.is_main DESC, a.name
        '''
        
        cursor.execute(query)

        current_user = None
        user_addresses = []

        for row in cursor.fetchall():
            user_id, name, subqueue, is_main, notif_en, new_sched_en, sched_changes_en = row

            if user_id != current_user:
                if current_user is not None:
                    # Print previous user info
                    print_user_info(current_user, user_addresses)
                    user_addresses = []

                current_user = user_id

            user_addresses.append((name, subqueue, is_main, notif_en, new_sched_en, sched_changes_en))

        # Print last user
        if current_user is not None:
            print_user_info(current_user, user_addresses)

        print("\n=== НЕДАВНІ СПОВІЩЕННЯ ===")
        cursor.execute('''
            SELECT user_id, event_time, event_date, COUNT(*) as count
            FROM sent_alerts
            WHERE event_date >= ?
            GROUP BY user_id, event_time, event_date
            ORDER BY event_date DESC, event_time DESC
            LIMIT 5
        ''', ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),))

        alerts = cursor.fetchall()
        if alerts:
            for user_id, event_time, event_date, count in alerts:
                print(f"  {user_id}: {event_date} {event_time} ({count} разів)")
        else:
            print("  Немає сповіщень за останній день")

        conn.close()
        print("\nГОТОВО!")

    except Exception as e:
        print(f"ПОМИЛКА: {e}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
        print_help()
        return

    db_file = 'users.db'
    multi_address = False
    
    # Parse arguments
    for arg in sys.argv[1:]:
        if arg == '--multi-address':
            multi_address = True
        elif not arg.startswith('--'):
            db_file = arg
    
    inspect_database(db_file, multi_address)

if __name__ == '__main__':
    main()