import asyncio
import sys
import os

# Додаємо поточну директорію до шляху
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot_ocr_model import parse_schedule_image

async def test_ocr_parsing():
    """Тестування OCR парсингу на тестовому зображенні"""
    image_path = "test_schedule.png"

    if not os.path.exists(image_path):
        print(f"Файл {image_path} не знайдено")
        return

    print(f"Парсимо {image_path}...")
    schedules = await parse_schedule_image(image_path)

    print("Результати парсингу:")
    for subqueue, schedule in schedules.items():
        print(f"  Черга {subqueue}: {schedule}")

if __name__ == "__main__":
    asyncio.run(test_ocr_parsing())