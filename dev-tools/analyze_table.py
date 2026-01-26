import cv2
import numpy as np

def analyze_table_structure(image_path):
    """Аналіз структури таблиці для визначення кількості рядків і колонок"""
    img = cv2.imread(image_path)
    if img is None:
        print("Не вдалося завантажити зображення")
        return

    height, width = img.shape[:2]
    print(f"Розмір зображення: {width}x{height}")

    # Конвертуємо в градації сірого для аналізу ліній
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Виявляємо горизонтальні лінії (рядки)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)

    # Виявляємо вертикальні лінії (колонки)
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    vertical_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel, iterations=2)

    # Поєднуємо лінії
    lines = cv2.add(horizontal_lines, vertical_lines)

    # Знаходимо контури (клітинки)
    contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Фільтруємо великі контури (клітинки таблиці)
    cell_contours = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > 50 and h > 20:  # мінімальний розмір клітинки
            cell_contours.append((x, y, w, h))

    print(f"Знайдено {len(cell_contours)} потенційних клітинок")

    # Групуємо по рядах (Y координата)
    rows = {}
    for x, y, w, h in cell_contours:
        row_key = y // 50  # групуємо з tolerance 50px
        if row_key not in rows:
            rows[row_key] = []
        rows[row_key].append((x, y, w, h))

    # Групуємо по колонках (X координата)
    cols = {}
    for row_cells in rows.values():
        for x, y, w, h in row_cells:
            col_key = x // 50  # групуємо з tolerance 50px
            if col_key not in cols:
                cols[col_key] = []
            cols[col_key].append((x, y, w, h))

    print(f"Приблизно {len(rows)} рядків і {len(cols)} колонок")

    # Показуємо результат
    img_with_contours = img.copy()
    cv2.drawContours(img_with_contours, [np.array([(x, y), (x+w, y), (x+w, y+h), (x, y+h)]) for x, y, w, h in cell_contours], -1, (0, 255, 0), 2)

    cv2.imshow('Detected Cells', img_with_contours)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    analyze_table_structure("test_schedule.png")