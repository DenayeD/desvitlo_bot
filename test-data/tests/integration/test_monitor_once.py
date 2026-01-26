import asyncio
import sys
import os
sys.path.append(os.path.dirname(__file__))

from bot import parse_hoe_smart, monitor_job

async def test_monitor():
    print("Testing monitor job...")
    await monitor_job()
    print("Monitor job completed")

if __name__ == "__main__":
    asyncio.run(test_monitor())