import cv2
import numpy as np
import asyncio
import json

def parse_table_colors(img):
    """
    Аналіз кольорів таблиці графіку.
    Повертає словник з розкладом для кожної черги.
    """
    # Конвертуємо в HSV для кращого аналізу кольорів
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Визначаємо діапазони кольорів на основі аналізу test_schedule.png
    # Синій/бірюзовий (немає світла) - RGB [143,170,220], HSV [109,89,220]
    blue_lower = np.array([100, 50, 100])  # нижній діапазон для синього
    blue_upper = np.array([120, 255, 255])  # верхній діапазон для синього

    # Сірий (можливо вимкнуть) - RGB [224,224,224], HSV [0,0,224]
    gray_lower = np.array([0, 0, 200])  # низька насиченість, висока яскравість
    gray_upper = np.array([180, 30, 250])

    # Білий (буде світло) - RGB [255,255,255], HSV [0,0,255]
    white_lower = np.array([0, 0, 250])  # дуже висока яскравість
    white_upper = np.array([180, 20, 255])

    height, width = img.shape[:2]

    # Спробуємо завантажити налаштування
    try:
        with open('table_bounds.json', 'r') as f:
            settings = json.load(f)
        table_left = settings.get('table_left', int(width * 0.05))
        table_right = settings.get('table_right', int(width * 0.95))
        table_top = settings.get('table_top', int(height * 0.15))
        table_bottom = settings.get('table_bottom', int(height * 0.95))
        cell_width = settings.get('cell_width', (table_right - table_left) // 24)  # 24 години
        cell_height = settings.get('cell_height', (table_bottom - table_top) // 12)  # 12 черг
        rows = settings.get('rows', 12)  # черги по вертикалі
        cols = settings.get('cols', 24)  # години по горизонталі
        print(f"Завантажено налаштування: {cols}x{rows} клітинок (години x черги)")
    except:
        # Налаштування за замовчуванням
        rows = 12  # черги
        cols = 24  # години
        table_top = int(height * 0.15)
        table_bottom = int(height * 0.95)
        table_left = int(width * 0.05)
        table_right = int(width * 0.95)
        cell_height = (table_bottom - table_top) // rows
        cell_width = (table_right - table_left) // cols
        print("Використано налаштування за замовчуванням: 24x12 (години x черги)")

    schedules = {}

    for row in range(rows):
        subqueue = f"{row//2 + 1}.{row%2 + 1}"  # 1.1, 1.2, 2.1, 2.2, ...
        intervals_off = []  # гарантовані відключення
        intervals_possible = []  # можливі відключення
        
        for col in range(cols):
            x1 = table_left + col * cell_width
            y1 = table_top + row * cell_height
            x2 = x1 + cell_width
            y2 = y1 + cell_height
            
            # Беремо центральну частину клітинки
            margin = 3
            cell_roi = img[y1+margin:y2-margin, x1+margin:x2-margin]
            if cell_roi.size == 0:
                continue
                
            # Конвертуємо в HSV
            hsv_cell = cv2.cvtColor(cell_roi, cv2.COLOR_BGR2HSV)
            
            # Рахуємо пікселі кожного кольору
            blue_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, blue_lower, blue_upper))
            gray_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, gray_lower, gray_upper))
            white_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, white_lower, white_upper))
            
            total_pixels = cell_roi.size // 3
            
            # Визначаємо домінуючий колір
            max_pixels = max(blue_pixels, gray_pixels, white_pixels)
            
            if max_pixels / total_pixels > 0.3:  # більше 30% пікселів цього кольору
                if blue_pixels == max_pixels:
                    status = "off"  # немає світла
                elif gray_pixels == max_pixels:
                    status = "possible"  # можливо
                else:
                    status = "on"  # буде світло
            else:
                status = "on"  # за замовчуванням
            
            # Додаємо інтервали
            if status == "off":
                start_hour = col
                end_hour = col + 1
                intervals_off.append(f"{start_hour:02d}:00-{end_hour:02d}:00")
            elif status == "possible":
                start_hour = col
                end_hour = col + 1
                intervals_possible.append(f"{start_hour:02d}:00-{end_hour:02d}:00")
        
        # Формуємо текст розкладу
        schedule_parts = []
        if intervals_off:
            schedule_parts.append("Вимкнено: " + ", ".join(intervals_off))
        if intervals_possible:
            schedule_parts.append("Можливо вимкнено: " + ", ".join(intervals_possible))
        
        if schedule_parts:
            schedules[subqueue] = "; ".join(schedule_parts)

    return schedules

async def parse_schedule_image(image_path):
    """Парсинг графіку з зображення"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"Не вдалося завантажити зображення: {image_path}")
            return {}

        schedules = parse_table_colors(img)
        return schedules

    except Exception as e:
        print(f"OCR парсинг error: {e}")
        return {}

async def main():
    image_path = "test_schedule.png"
    schedules = await parse_schedule_image(image_path)

    print("Результати парсингу:")
    for subqueue, schedule in schedules.items():
        print(f"  Черга {subqueue}: {schedule}")

if __name__ == "__main__":
    asyncio.run(main())