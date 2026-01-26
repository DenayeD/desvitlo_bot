import asyncio
import aiohttp
import logging
import re
from bs4 import BeautifulSoup
from config.settings import URL_PAGE

async def parse_hoe_data():
    """Parse basic schedule data from HOE website"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL_PAGE, timeout=15) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                img_tag = soup.find('img', alt=re.compile(r'ГПВ'))
                date_str = img_tag['alt'] if img_tag else "Графік відключень"
                img_url = "https://hoe.com.ua" + img_tag['src'] if img_tag else None
                page_text = soup.get_text()
                patterns = re.findall(r"підчерга (\d\.\d) [–-] (.*?)(?:;|\n|$)", page_text)
                schedules = {p[0]: p[1].strip() for p in patterns}
                return date_str, schedules, img_url
        except Exception as e:
            logging.error(f"Error parsing: {e}")
            return None, None, None

async def parse_hoe_smart():
    """Smart parsing of HOE website with multiple dates support"""
    logging.info("Parsing site...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL_PAGE, timeout=15) as response:
                html = await response.text()
                # Use lxml if available for better performance
                try:
                    soup = BeautifulSoup(html, 'lxml')
                except:
                    soup = BeautifulSoup(html, 'html.parser')

                # Find all GVP image containers
                img_containers = soup.find_all('img', alt=re.compile(r'ГПВ'))
                logging.info(f"Found {len(img_containers)} GVP images")
                
                data_by_date = {}

                for img in img_containers:
                    # Extract date from alt (e.g. "ГПВ-17.01.26")
                    alt_text = img.get('alt', '')
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', alt_text)
                    if not date_match: continue

                    date_key = date_match.group(1)
                    # Format date to DD.MM.YYYY if needed
                    if len(date_key) == 8:  # DD.MM.YY
                        date_key = date_key[:6] + '20' + date_key[6:]

                    img_url = "https://hoe.com.ua" + img['src']

                    # Use OCR to parse schedule from image instead of HTML text
                    from ocr.parser import parse_schedule_image
                    schedules = await parse_schedule_image(img_url)

                    data_by_date[date_key] = {
                        'img_url': img_url,
                        'schedules': schedules,
                        'text_content': f"OCR parsed from image: {len(schedules)} schedules found"
                    }

                return data_by_date

        except Exception as e:
            logging.error(f"Error in smart parsing: {e}")
            return {}

async def monitor_job():
    """Monitor job for checking schedule updates"""
    logging.info("Monitor job executed")
    try:
        # Check for updates and only regenerate if changed
        from utils.cache import check_and_update_cache
        updated = await check_and_update_cache()
        if updated:
            logging.info("Cache updated with new data, clocks regenerated")
        else:
            logging.info("No changes detected, cache unchanged")
    except Exception as e:
        logging.error(f"Error in monitor job: {e}")