import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re

URL_PAGE = 'https://hoe.com.ua/page/pogodinni-vidkljuchennja'

async def check_all_images():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL_PAGE, timeout=15) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                img_containers = soup.find_all('img', alt=re.compile(r'ГПВ'))

                print("All images found on site:")
                for img in img_containers:
                    alt_text = img.get('alt', '')
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', alt_text)
                    if date_match:
                        date_key = date_match.group(1)
                        if len(date_key.split('.')[-1]) == 2:
                            date_key = date_key[:-2] + '20' + date_key[-2:]
                        img_url = 'https://hoe.com.ua' + img['src']
                        print(f"  {date_key}: {alt_text} - {img_url.split('/')[-1]}")
        except Exception as e:
            print(f'Error: {e}')

result = asyncio.run(check_all_images())