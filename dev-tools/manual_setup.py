import cv2
import numpy as np
import json

def manual_table_setup(image_path):
    """
    Ручне налаштування таблиці з можливістю малювання сітки
    """
    img = cv2.imread(image_path)
    if img is None:
        print("Не вдалося завантажити зображення")
        return

    height, width = img.shape[:2]
    print(f"Розмір зображення: {width}x{height}")

    # Спробуємо завантажити існуючі налаштування
    try:
        with open('table_bounds.json', 'r') as f:
            bounds = json.load(f)
    except:
        bounds = {
            'left': int(width * 0.05),
            'right': int(width * 0.95),
            'top': int(height * 0.15),
            'bottom': int(height * 0.95)
        }

    # Налаштування сітки
    grid = {
        'rows': 12,  # черги
        'cols': 24,  # години
        'row_lines': [],  # Y координати горизонтальних ліній
        'col_lines': []   # X координати вертикальних ліній
    }

    # Ініціалізуємо рівномірну сітку
    for i in range(grid['rows'] + 1):
        y = bounds['top'] + i * (bounds['bottom'] - bounds['top']) // grid['rows']
        grid['row_lines'].append(y)

    for i in range(grid['cols'] + 1):
        x = bounds['left'] + i * (bounds['right'] - bounds['left']) // grid['cols']
        grid['col_lines'].append(x)

    mode = 'bounds'  # 'bounds' або 'grid'
    selected_line = None
    drag_start = None

    def draw_interface():
        display = img.copy()

        # Малюємо межі таблиці
        cv2.rectangle(display,
                     (bounds['left'], bounds['top']),
                     (bounds['right'], bounds['bottom']),
                     (0, 255, 0), 2)

        # Малюємо сітку
        for y in grid['row_lines']:
            cv2.line(display, (bounds['left'], y), (bounds['right'], y), (255, 0, 0), 1)
        for x in grid['col_lines']:
            cv2.line(display, (x, bounds['top']), (x, bounds['bottom']), (255, 0, 0), 1)

        # Інформація
        info = []
        info.append(f"Режим: {'межі' if mode == 'bounds' else 'сітка'}")
        info.append(f"Розмір таблиці: {bounds['right']-bounds['left']}x{bounds['bottom']-bounds['top']}")
        info.append(f"Сітка: {grid['cols']}x{grid['rows']}")
        info.append("Клавіші:")
        info.append("  'm' - змінити режим")
        info.append("  'r' - скинути сітку")
        info.append("  's' - зберегти")
        info.append("  'q' - вийти")

        for i, line in enumerate(info):
            cv2.putText(display, line, (10, 30 + i*25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            cv2.putText(display, line, (10, 30 + i*25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        return display

    def find_nearest_line(x, y):
        """Знаходить найближчу лінію для переміщення"""
        margin = 10

        # Перевіряємо межі
        if mode == 'bounds':
            if abs(x - bounds['left']) < margin:
                return 'left', bounds['left']
            if abs(x - bounds['right']) < margin:
                return 'right', bounds['right']
            if abs(y - bounds['top']) < margin:
                return 'top', bounds['top']
            if abs(y - bounds['bottom']) < margin:
                return 'bottom', bounds['bottom']

        # Перевіряємо лінії сітки
        elif mode == 'grid':
            for i, lx in enumerate(grid['col_lines']):
                if abs(x - lx) < margin:
                    return f'col_{i}', lx
            for i, ly in enumerate(grid['row_lines']):
                if abs(y - ly) < margin:
                    return f'row_{i}', ly

        return None, None

    def mouse_callback(event, x, y, flags, param):
        nonlocal selected_line, drag_start

        if event == cv2.EVENT_LBUTTONDOWN:
            selected_line, current_pos = find_nearest_line(x, y)
            if selected_line:
                drag_start = (x, y)

        elif event == cv2.EVENT_MOUSEMOVE and selected_line and drag_start:
            dx = x - drag_start[0]
            dy = y - drag_start[1]

            if mode == 'bounds':
                if 'left' in selected_line:
                    bounds['left'] = max(0, min(bounds['right']-50, bounds['left'] + dx))
                elif 'right' in selected_line:
                    bounds['right'] = max(bounds['left']+50, min(width, bounds['right'] + dx))
                elif 'top' in selected_line:
                    bounds['top'] = max(0, min(bounds['bottom']-50, bounds['top'] + dy))
                elif 'bottom' in selected_line:
                    bounds['bottom'] = max(bounds['top']+50, min(height, bounds['bottom'] + dy))

            elif mode == 'grid':
                if selected_line.startswith('col_'):
                    idx = int(selected_line.split('_')[1])
                    grid['col_lines'][idx] = max(bounds['left'], min(bounds['right'], grid['col_lines'][idx] + dx))
                elif selected_line.startswith('row_'):
                    idx = int(selected_line.split('_')[1])
                    grid['row_lines'][idx] = max(bounds['top'], min(bounds['bottom'], grid['row_lines'][idx] + dy))

            drag_start = (x, y)

        elif event == cv2.EVENT_LBUTTONUP:
            selected_line = None
            drag_start = None

    cv2.namedWindow('Manual Table Setup', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Manual Table Setup', 1200, 800)
    cv2.setMouseCallback('Manual Table Setup', mouse_callback)

    print("Ручне налаштування таблиці")
    print("Клікніть і тяніть лінії щоб їх перемістити")
    print("Клавіші: 'm' - змінити режим, 'r' - скинути сітку, 's' - зберегти, 'q' - вийти")

    while True:
        display = draw_interface()
        cv2.imshow('Manual Table Setup', display)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('m'):
            mode = 'grid' if mode == 'bounds' else 'bounds'
            print(f"Змінено режим на: {'сітка' if mode == 'grid' else 'межі'}")
        elif key == ord('r'):
            # Скинути сітку до рівномірної
            grid['row_lines'] = []
            grid['col_lines'] = []
            for i in range(grid['rows'] + 1):
                y = bounds['top'] + i * (bounds['bottom'] - bounds['top']) // grid['rows']
                grid['row_lines'].append(y)
            for i in range(grid['cols'] + 1):
                x = bounds['left'] + i * (bounds['right'] - bounds['left']) // grid['cols']
                grid['col_lines'].append(x)
            print("Сітку скинуто")
        elif key == ord('s'):
            # Зберігаємо налаштування
            settings = {
                'bounds': bounds,
                'grid': grid
            }
            with open('manual_table_settings.json', 'w') as f:
                json.dump(settings, f, indent=2)
            print("Налаштування збережено в manual_table_settings.json")

            # Також створюємо простий формат для використання в коді
            simple_bounds = {
                'table_left': bounds['left'],
                'table_right': bounds['right'],
                'table_top': bounds['top'],
                'table_bottom': bounds['bottom'],
                'cell_width': (bounds['right'] - bounds['left']) // grid['cols'],
                'cell_height': (bounds['bottom'] - bounds['top']) // grid['rows'],
                'rows': grid['rows'],
                'cols': grid['cols']
            }
            with open('table_bounds.json', 'w') as f:
                json.dump(simple_bounds, f, indent=2)
            print("Простий формат збережено в table_bounds.json")

    cv2.destroyAllWindows()

if __name__ == "__main__":
    manual_table_setup("test_schedule.png")