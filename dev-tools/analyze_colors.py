import cv2
import numpy as np
from PIL import Image
import os

def analyze_schedule_colors(image_path):
    """
    Аналіз кольорів у графіку для налаштування діапазонів
    """
    if not os.path.exists(image_path):
        print(f"Файл {image_path} не знайдено")
        return

    img = cv2.imread(image_path)
    if img is None:
        print("Не вдалося завантажити зображення")
        return

    # Конвертуємо в HSV
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Показуємо зображення для вибору областей
    print("Клацніть на різних кольорах для аналізу...")
    print("Натисніть 'q' для виходу")

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            # Беремо колір пікселя
            bgr = img[y, x]
            hsv_pixel = hsv[y, x]

            print(f"Позиція ({x}, {y}):")
            print(f"  BGR: {bgr}")
            print(f"  HSV: {hsv_pixel}")
            print(f"  RGB: {bgr[::-1]}")  # BGR to RGB
            print("---")

    cv2.namedWindow('Schedule')
    cv2.setMouseCallback('Schedule', mouse_callback)

    while True:
        cv2.imshow('Schedule', img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()

    # Автоматичний аналіз - знаходимо домінуючі кольори
    print("\nАвтоматичний аналіз кольорів...")

    # Перетворюємо в список пікселів
    pixels = img.reshape(-1, 3)
    pixels_hsv = hsv.reshape(-1, 3)

    # Кластеризація кольорів (простий підхід)
    from sklearn.cluster import KMeans
    kmeans = KMeans(n_clusters=5, random_state=42)
    kmeans.fit(pixels)

    print("Знайдені домінуючі кольори:")
    for i, center in enumerate(kmeans.cluster_centers_):
        center = center.astype(int)
        hsv_center = cv2.cvtColor(np.uint8([[center]]), cv2.COLOR_BGR2HSV)[0][0]
        print(f"Кластер {i}: BGR{center}, HSV{hsv_center}")

if __name__ == "__main__":
    analyze_schedule_colors("test_schedule.png")