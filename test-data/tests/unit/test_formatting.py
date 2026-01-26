import sys
import os
sys.path.insert(0, os.getcwd())

# Тестуємо нову функцію форматування
from bot_ocr_model import parse_schedule_to_intervals, format_outages_compact, merge_consecutive_intervals

# Тестові дані - розклад для черги 3.1
test_text = '03:00-04:00, 04:00-05:00, 05:00-06:00, 06:00-07:00, 07:00-08:00, 08:00-09:00, 11:00-12:00, 12:00-13:00, 13:00-14:00, 14:00-15:00, 15:00-16:00, 16:00-17:00, 19:00-20:00, 20:00-21:00, 21:00-22:00, 22:00-23:00, 23:00-24:00; 00:00-01:00'

print("Оригінальний текст розкладу:")
print(test_text)
print()

# Парсимо інтервали
intervals = parse_schedule_to_intervals(test_text)
print("Розібрані інтервали:")
print(f"Гарантовані: {intervals['guaranteed']}")
print(f"Можливі: {intervals['possible']}")
print()

# Тестуємо об'єднання
merged_guaranteed = merge_consecutive_intervals(intervals['guaranteed'])
merged_possible = merge_consecutive_intervals(intervals['possible'])
print("Після об'єднання:")
print(f"Гарантовані: {merged_guaranteed}")
print(f"Можливі: {merged_possible}")
print()

# Тестуємо форматування
formatted = format_outages_compact(intervals)
print("Форматований вивід:")
print(" | ".join(formatted))
print()
print("🔴 - гарантовано немає світла | 🟡 - можливо немає світла")