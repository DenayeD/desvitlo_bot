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
                    
                    schedules = {}
                    ul = img.find_next('ul')
                    if ul:
                        for li in ul.find_all('li'):
                            li_text = li.get_text()
                            match = re.search(r'підчерга (\d\.\d) [–\-\—\−] (.*)', li_text)
                            if match:
                                subq, schedule = match.groups()
                                schedules[subq] = schedule.strip()
                    
                    is_new_version = '-new' in alt_text
                    
                    if date_key not in data_by_date or (is_new_version and '-new' not in data_by_date[date_key]['raw_date']):
                        data_by_date[date_key] = {
                            'img': img_url,
                            'list': schedules,
                            'raw_date': alt_text,
                            'has_image': True
                        }
                
                print('Parsed data:')
                for date, data in data_by_date.items():
                    print(f'  {date}: {data["raw_date"]} - {data["img"].split("/")[-1]}')
                    print(f'    Schedules: {len(data["list"])} items')
                
                return data_by_date
        except Exception as e:
            print(f'Error: {e}')
            return {}

result = asyncio.run(parse_hoe_smart())