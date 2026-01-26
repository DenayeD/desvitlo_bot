import cv2
import numpy as np

def test_color_detection(image_path):
    """
    Тестування розпізнавання кольорів у вибраних областях
    """
    img = cv2.imread(image_path)
    if img is None:
        print("Не вдалося завантажити зображення")
        return

    # Завантажуємо межі таблиці якщо є
    try:
        import json
        with open('table_bounds.json', 'r') as f:
            table_bounds = json.load(f)
    except:
        # За замовчуванням
        height, width = img.shape[:2]
        table_bounds = {
            'top': int(height * 0.15),
            'bottom': int(height * 0.95),
            'left': int(width * 0.05),
            'right': int(width * 0.95)
        }

    # Діапазони кольорів
    blue_lower = np.array([100, 50, 100])
    blue_upper = np.array([120, 255, 255])
    gray_lower = np.array([0, 0, 200])
    gray_upper = np.array([180, 30, 250])
    white_lower = np.array([0, 0, 250])
    white_upper = np.array([180, 20, 255])

    rows, cols = 24, 12
    cell_height = (table_bounds['bottom'] - table_bounds['top']) // rows
    cell_width = (table_bounds['right'] - table_bounds['left']) // cols

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            # Знаходимо в якій клітинці клікнули
            if (table_bounds['left'] <= x <= table_bounds['right'] and
                table_bounds['top'] <= y <= table_bounds['bottom']):

                col = (x - table_bounds['left']) // cell_width
                row = (y - table_bounds['top']) // cell_height

                if 0 <= col < cols and 0 <= row < rows:
                    # Беремо область клітинки
                    x1 = table_bounds['left'] + col * cell_width
                    y1 = table_bounds['top'] + row * cell_height
                    x2 = x1 + cell_width
                    y2 = y1 + cell_height

                    cell_roi = img[y1+3:y2-3, x1+3:x2-3]
                    if cell_roi.size > 0:
                        hsv_cell = cv2.cvtColor(cell_roi, cv2.COLOR_BGR2HSV)

                        # Рахуємо кольори
                        blue_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, blue_lower, blue_upper))
                        gray_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, gray_lower, gray_upper))
                        white_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, white_lower, white_upper))

                        total_pixels = cell_roi.size // 3

                        # Визначаємо домінуючий колір
                        colors = [('Blue', blue_pixels), ('Gray', gray_pixels), ('White', white_pixels)]
                        dominant = max(colors, key=lambda x: x[1])

                        print(f"Клітинка ({row}, {col}) - Черга {(col//2)+1}.{col%2+1} Година {row:02d}:00")
                        print(f"  Blue: {blue_pixels} ({blue_pixels/total_pixels*100:.1f}%)")
                        print(f"  Gray: {gray_pixels} ({gray_pixels/total_pixels*100:.1f}%)")
                        print(f"  White: {white_pixels} ({white_pixels/total_pixels*100:.1f}%)")
                        print(f"  Домінуючий: {dominant[0]}")
                        print("---")

    # Малюємо сітку
    display_img = img.copy()
    cv2.rectangle(display_img,
                 (table_bounds['left'], table_bounds['top']),
                 (table_bounds['right'], table_bounds['bottom']),
                 (0, 255, 0), 2)

    # Малюємо сітку
    for i in range(cols + 1):
        x = table_bounds['left'] + i * cell_width
        cv2.line(display_img, (x, table_bounds['top']), (x, table_bounds['bottom']), (255, 0, 0), 1)

    for i in range(rows + 1):
        y = table_bounds['top'] + i * cell_height
        cv2.line(display_img, (table_bounds['left'], y), (table_bounds['right'], y), (255, 0, 0), 1)

    cv2.namedWindow('Color Test')
    cv2.setMouseCallback('Color Test', mouse_callback)

    print("Клікніть на клітинки щоб перевірити розпізнавання кольорів")
    print("Натисніть 'q' щоб вийти")

    while True:
        cv2.imshow('Color Test', display_img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_color_detection("test_schedule.png")