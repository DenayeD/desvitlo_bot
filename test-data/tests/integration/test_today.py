import asyncio
import sys
import os
sys.path.append(os.path.dirname(__file__))

from bot import parse_hoe_smart
from datetime import datetime

async def test_today_schedule():
    print("Testing today's schedule parsing...")
    all_data = await parse_hoe_smart()

    target_dt = datetime.now()
    date_str = target_dt.strftime("%d.%m.%Y")
    short_date = target_dt.strftime("%d.%m.%y")

    data = all_data.get(date_str) or all_data.get(short_date)

    if data:
        print(f"Found data for today ({date_str}):")
        print(f"  Raw date: {data['raw_date']}")
        print(f"  Image URL: {data['img']}")
        print(f"  Has '-new' in alt: {'-new' in data['raw_date']}")
        print(f"  Schedules: {len(data['list'])} items")
    else:
        print(f"No data found for today ({date_str})")

if __name__ == "__main__":
    asyncio.run(test_today_schedule())