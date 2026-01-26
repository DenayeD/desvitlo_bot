import cv2
import numpy as np
import json
import os

def parse_table_colors(img):
    """
    Analyze table colors in schedule image.
    Returns dict with schedule for each subqueue.
    """
    # Convert to HSV for better color analysis
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Define color ranges based on test_schedule.png analysis
    # Blue/cyan (no power) - RGB [143,170,220], HSV [109,89,220]
    blue_lower = np.array([100, 50, 100])
    blue_upper = np.array([120, 255, 255])

    # Gray (possibly off) - RGB [224,224,224], HSV [0,0,224]
    gray_lower = np.array([0, 0, 200])
    gray_upper = np.array([180, 30, 250])

    # White (power on) - RGB [255,255,255], HSV [0,0,255]
    white_lower = np.array([0, 0, 250])
    white_upper = np.array([180, 20, 255])

    height, width = img.shape[:2]

    # Load table settings
    try:
        settings_path = 'table_bounds.json'
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            table_left = settings.get('table_left', int(width * 0.05))
            table_right = settings.get('table_right', int(width * 0.95))
            table_top = settings.get('table_top', int(height * 0.15))
            table_bottom = settings.get('table_bottom', int(height * 0.95))
            cell_width = settings.get('cell_width', (table_right - table_left) // 24)
            cell_height = settings.get('cell_height', (table_bottom - table_top) // 12)
            rows = settings.get('rows', 12)  # subqueues vertically
            cols = settings.get('cols', 24)  # hours horizontally
        else:
            raise FileNotFoundError
    except:
        # Default settings
        rows = 12  # subqueues
        cols = 24  # hours
        table_top = int(height * 0.15)
        table_bottom = int(height * 0.95)
        table_left = int(width * 0.05)
        table_right = int(width * 0.95)
        cell_height = (table_bottom - table_top) // rows
        cell_width = (table_right - table_left) // cols

    schedules = {}

    for row in range(rows):
        subqueue = f"{row//2 + 1}.{row%2 + 1}"  # 1.1, 1.2, 2.1, 2.2, ...
        intervals_off = []  # guaranteed outages
        intervals_possible = []  # possible outages

        for col in range(cols):
            x1 = table_left + col * cell_width
            y1 = table_top + row * cell_height
            x2 = x1 + cell_width
            y2 = y1 + cell_height

            # Take central part of cell
            margin = 3
            cell_roi = img[y1+margin:y2-margin, x1+margin:x2-margin]
            if cell_roi.size == 0:
                continue

            # Convert to HSV
            hsv_cell = cv2.cvtColor(cell_roi, cv2.COLOR_BGR2HSV)

            # Count pixels of each color
            blue_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, blue_lower, blue_upper))
            gray_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, gray_lower, gray_upper))
            white_pixels = cv2.countNonZero(cv2.inRange(hsv_cell, white_lower, white_upper))

            total_pixels = cell_roi.size // 3

            # Determine dominant color
            max_pixels = max(blue_pixels, gray_pixels, white_pixels)

            if max_pixels / total_pixels > 0.3:  # more than 30% of pixels this color
                if blue_pixels == max_pixels:
                    status = "off"  # no power
                elif gray_pixels == max_pixels:
                    status = "possible"  # possibly off
                else:
                    status = "on"  # power on
            else:
                status = "on"  # default

            # Add intervals
            if status == "off":
                start_hour = col
                end_hour = col + 1
                intervals_off.append(f"{start_hour:02d}:00-{end_hour:02d}:00")
            elif status == "possible":
                start_hour = col
                end_hour = col + 1
                intervals_possible.append(f"{start_hour:02d}:00-{end_hour:02d}:00")

        # Form schedule text
        schedule_parts = []
        if intervals_off:
            schedule_parts.append("Вимкнено: " + ", ".join(intervals_off))
        if intervals_possible:
            schedule_parts.append("Можливо вимкнено: " + ", ".join(intervals_possible))

        if schedule_parts:
            schedules[subqueue] = "; ".join(schedule_parts)

    return schedules