import sys
import os
sys.path.insert(0, os.getcwd())

# Тестуємо парсинг інтервалів
from bot_ocr_model import parse_schedule_to_intervals

# Тестуємо з даними з кешу
test_text = '03:00-04:00, 04:00-05:00, 05:00-06:00, 06:00-07:00, 07:00-08:00, 08:00-09:00, 11:00-12:00, 12:00-13:00, 13:00-14:00, 14:00-15:00, 15:00-16:00, 16:00-17:00, 19:00-20:00, 20:00-21:00, 21:00-22:00, 22:00-23:00, 23:00-24:00; 00:00-01:00'
intervals = parse_schedule_to_intervals(test_text)
print(f'Гарантовані: {intervals["guaranteed"]}')
print(f'Можливі: {intervals["possible"]}')

# Тестуємо генерацію годинника
from bot_ocr_model import generate_clock_image
filename = generate_clock_image('3.1', test_text, '26.01.2026')
print(f'Годинник згенеровано: {filename}')
print(f'Файл існує: {os.path.exists(filename)}')