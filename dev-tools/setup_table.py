import cv2
import numpy as np
import json

def interactive_table_setup(image_path):
    """
    Інтерактивний інструмент для налаштування меж таблиці
    """
    img = cv2.imread(image_path)
    if img is None:
        print("Не вдалося завантажити зображення")
        return

    height, width = img.shape[:2]
    print(f"Розмір зображення: {width}x{height}")

    # Початкові значення меж
    table_bounds = {
        'top': int(height * 0.15),
        'bottom': int(height * 0.95),
        'left': int(width * 0.05),
        'right': int(width * 0.95)
    }

    # Створюємо копію для малювання
    display_img = img.copy()

    def draw_bounds():
        nonlocal display_img
        display_img = img.copy()
        # Малюємо прямокутник меж таблиці
        cv2.rectangle(display_img,
                     (table_bounds['left'], table_bounds['top']),
                     (table_bounds['right'], table_bounds['bottom']),
                     (0, 255, 0), 2)

        # Малюємо лінії сітки
        rows, cols = 24, 12
        cell_height = (table_bounds['bottom'] - table_bounds['top']) // rows
        cell_width = (table_bounds['right'] - table_bounds['left']) // cols

        # Вертикальні лінії
        for i in range(cols + 1):
            x = table_bounds['left'] + i * cell_width
            cv2.line(display_img, (x, table_bounds['top']), (x, table_bounds['bottom']), (255, 0, 0), 1)

        # Горизонтальні лінії
        for i in range(rows + 1):
            y = table_bounds['top'] + i * cell_height
            cv2.line(display_img, (table_bounds['left'], y), (table_bounds['right'], y), (255, 0, 0), 1)

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            # Перевіряємо, чи клікнули біля меж
            margin = 20
            if abs(y - table_bounds['top']) < margin:
                table_bounds['top'] = y
            elif abs(y - table_bounds['bottom']) < margin:
                table_bounds['bottom'] = y
            elif abs(x - table_bounds['left']) < margin:
                table_bounds['left'] = x
            elif abs(x - table_bounds['right']) < margin:
                table_bounds['right'] = x
            draw_bounds()

    cv2.namedWindow('Table Setup')
    cv2.setMouseCallback('Table Setup', mouse_callback)

    draw_bounds()

    print("Інструкції:")
    print("- Клікніть біля меж таблиці щоб їх перемістити")
    print("- Натисніть 's' щоб зберегти налаштування")
    print("- Натисніть 'q' щоб вийти")

    while True:
        cv2.imshow('Table Setup', display_img)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('s'):
            # Зберігаємо налаштування
            with open('table_bounds.json', 'w') as f:
                json.dump(table_bounds, f, indent=2)
            print(f"Налаштування збережено в table_bounds.json: {table_bounds}")

    cv2.destroyAllWindows()

if __name__ == "__main__":
    interactive_table_setup("test_schedule.png")