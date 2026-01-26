import asyncio
import aiohttp
import logging
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import os
from datetime import datetime, timedelta, timezone
from .image_processing import parse_table_colors
from utils.helpers import parse_schedule_to_intervals

async def parse_schedule_image(image_path_or_url):
    """
    Parse schedule from image.
    Returns dict {subqueue: schedule_text}
    """
    try:
        # Load image
        if image_path_or_url.startswith('http'):
            async with aiohttp.ClientSession() as session:
                async with session.get(image_path_or_url) as response:
                    image_data = await response.read()
                    nparr = np.frombuffer(image_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(image_path_or_url)

        if img is None:
            logging.error(f"Failed to load image: {image_path_or_url}")
            return {}

        # Convert to RGB for PIL
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)

        # OCR for text recognition (if needed for headers)
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # configure path

        # Main color parsing logic
        schedules = parse_table_colors(img)

        return schedules

    except Exception as e:
        logging.error(f"OCR parsing error: {e}")
        return {}

def generate_clock_image(subqueue, schedule_text, date_info=""):
    """
    Create clock image with outages
    schedule_text: combined schedule text like "Вимкнено: 01:00-02:00; Можливо вимкнено: 03:00-04:00"
    """
    # Create clock image
    os.makedirs('clocks', exist_ok=True)
    filename = f"clocks/{subqueue}_{date_info.replace('.', '_')}.png"

    # Clean old files (older than 24 hours) on each call
    now = datetime.now()
    for file in os.listdir('clocks'):
        filepath = os.path.join('clocks', file)
        if os.path.isfile(filepath):
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if (now - file_mtime).total_seconds() > 86400:  # 24 hours
                os.remove(filepath)

    size = 600
    img = Image.new('RGBA', (size, size), (220, 220, 220, 255))  # Light gray background
    draw = ImageDraw.Draw(img)

    center = size // 2
    radius = 250

    # Clock background with gradient
    for r in range(radius, 0, -1):
        alpha = int(255 * (1 - r / radius))
        color = (200, 220, 255, alpha)  # Soft blue
        draw.ellipse((center - r, center - r, center + r, center + r), fill=color)

    # Outer circle
    draw.ellipse((center - radius, center - radius, center + radius, center + radius),
                 outline=(100, 100, 100), width=3)

    # Try to load font
    try:
        font = ImageFont.truetype('arial.ttf', 32)
    except:
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 32)
        except:
            try:
                font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 32)
            except:
                font = ImageFont.load_default()

    # Hour marks
    for hour in range(24):
        angle = math.radians(hour * 15 - 90)  # 15 degrees per hour, 0 hours at top
        inner_r = radius - 20
        outer_r = radius - 10 if hour % 6 == 0 else radius - 5
        x1 = center + inner_r * math.cos(angle)
        y1 = center + inner_r * math.sin(angle)
        x2 = center + outer_r * math.cos(angle)
        y2 = center + outer_r * math.sin(angle)
        draw.line((x1, y1, x2, y2), fill=(50, 50, 50), width=2)

        # Hour numbers
        if True:  # Show all hours
            text_r = radius + 15  # Outside the clock circle
            x = center + text_r * math.cos(angle)
            y = center + text_r * math.sin(angle)
            bbox = draw.textbbox((0, 0), str(hour), font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            cx = x - text_width / 2
            cy = y - text_height / 2
            # Black outline
            draw.text((cx-1, cy-1), str(hour), fill=(0, 0, 0), font=font)
            draw.text((cx+1, cy-1), str(hour), fill=(0, 0, 0), font=font)
            draw.text((cx-1, cy+1), str(hour), fill=(0, 0, 0), font=font)
            draw.text((cx+1, cy+1), str(hour), fill=(0, 0, 0), font=font)
            # Main text white
            draw.text((cx, cy), str(hour), fill=(255, 255, 255), font=font)

    # Parse outage intervals from combined text
    intervals = parse_schedule_to_intervals(schedule_text)

    # Guaranteed outages - red
    for start_hour, end_hour in intervals['guaranteed']:
        try:
            start_angle = (start_hour * 15) - 90
            end_angle = (end_hour * 15) - 90

            if end_angle < start_angle:
                end_angle += 360

            # Draw guaranteed outage arc (red)
            draw.arc((center - radius + 20, center - radius + 20, center + radius - 20, center + radius - 20),
                     start=start_angle, end=end_angle, fill=(255, 100, 100), width=40)
            # Add outline
            draw.arc((center - radius + 20, center - radius + 20, center + radius - 20, center + radius - 20),
                     start=start_angle, end=end_angle, fill=None, outline=(0, 0, 0), width=4)
        except:
            continue

    # Possible outages - gray
    for start_hour, end_hour in intervals['possible']:
        try:
            start_angle = (start_hour * 15) - 90
            end_angle = (end_hour * 15) - 90

            if end_angle < start_angle:
                end_angle += 360

            # Draw possible outage arc (gray)
            draw.arc((center - radius + 60, center - radius + 60, center + radius - 60, center + radius - 60),
                     start=start_angle, end=end_angle, fill=(150, 150, 150), width=20)
            # Add outline
            draw.arc((center - radius + 60, center - radius + 60, center + radius - 60, center + radius - 60),
                     start=start_angle, end=end_angle, fill=None, outline=(0, 0, 0), width=2)
        except:
            continue

    # Draw current time hand (30 minutes ahead as requested)
    # Use Kyiv timezone (Europe/Kiev)
    kyiv_tz = timezone(timedelta(hours=2))  # UTC+2 for winter time, UTC+3 for summer
    # For more accurate timezone handling, we could use pytz if available
    try:
        import pytz
        kyiv_tz = pytz.timezone('Europe/Kiev')
    except ImportError:
        # Fallback to manual offset (will need to be updated for daylight saving)
        kyiv_tz = timezone(timedelta(hours=2))  # Assuming winter time
    
    current_time = datetime.now(kyiv_tz)
    # Take current hour, ignore minutes, add 30 minutes
    display_hour = current_time.hour
    display_minute = 30  # Always show :30
    
    # Debug: print time being used
    logging.info(f"Clock time hand: current Kyiv time {current_time.strftime('%H:%M:%S')} -> display {display_hour:02d}:{display_minute:02d}")

    # Calculate angle for display time (15 degrees per hour, 0.25 degrees per minute)
    time_angle = math.radians((display_hour * 15 + display_minute * 0.25) - 90)

    # Draw time hand
    hand_length = radius - 80  # Shorter than hour marks
    hand_x = center + hand_length * math.cos(time_angle)
    hand_y = center + hand_length * math.sin(time_angle)

    # Draw hand with shadow effect
    # Shadow
    shadow_offset = 2
    draw.line((center + shadow_offset, center + shadow_offset, hand_x + shadow_offset, hand_y + shadow_offset),
              fill=(100, 100, 100), width=6)
    # Main hand (bright blue)
    draw.line((center, center, hand_x, hand_y), fill=(0, 150, 255), width=6)
    # Center dot
    draw.ellipse((center - 8, center - 8, center + 8, center + 8), fill=(0, 150, 255))
    draw.ellipse((center - 4, center - 4, center + 4, center + 4), fill=(255, 255, 255))

    # Save image
    img.save(filename)
    return filename