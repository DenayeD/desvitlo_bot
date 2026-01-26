import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re

URL_PAGE = 'https://hoe.com.ua/page/pogodinni-vidkljuchennja'

async def parse_hoe_smart():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL_PAGE, timeout=15) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                img_containers = soup.find_all('img', alt=re.compile(r'ГПВ'))
                data_by_date = {}

                for img in img_containers:
                    alt_text = img.get('alt', '')
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', alt_text)
                    if not date_match: continue

                    date_key = date_match.group(1)
                    if len(date_key.split('.')[-1]) == 2:
                        date_key = date_key[:-2] + '20' + date_key[-2:]

                    img_url = 'https://hoe.com.ua' + img['src']

                    # Витягуємо timestamp з назви файлу для порівняння свіжості
                    filename = img_url.split('/')[-1]  # file20260124035522426.png
                    timestamp = 0
                    if filename.startswith('file') and filename.endswith('.png'):
                        # file20260124035522426.png -> 20260124035522426
                        ts_str = filename[4:-4]  # remove 'file' and '.png'
                        try:
                            # Це timestamp в форматі YYYYMMDDHHMMSSmmm
                            timestamp = int(ts_str)
                        except ValueError:
                            timestamp = 0

                    schedules = {}
                    ul = img.find_next('ul')
                    if ul:
                        for li in ul.find_all('li'):
                            li_text = li.get_text()
                            match = re.search(r'підчерга (\d\.\d) [–\-\—\−] (.*)', li_text)
                            if match:
                                subq, schedule = match.groups()
                                schedules[subq] = schedule.strip()

                    # Якщо для цієї дати вже є запис, порівнюємо за timestamp (свіжіший виграє)
                    if date_key not in data_by_date or timestamp > data_by_date[date_key].get('timestamp', 0):
                        data_by_date[date_key] = {
                            'img': img_url,
                            'list': schedules,
                            'raw_date': alt_text,
                            'has_image': True,
                            'timestamp': timestamp
                        }

                print('Parsed data (with timestamps):')
                for date, data in data_by_date.items():
                    print(f'  {date}: {data["raw_date"]} - {data["img"].split("/")[-1]} (ts: {data["timestamp"]})')
                    print(f'    Schedules: {len(data["list"])} items')

                return data_by_date
        except Exception as e:
            print(f'Error: {e}')
            return {}

result = asyncio.run(parse_hoe_smart())