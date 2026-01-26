#!/usr/bin/env python3
"""
Electricity Checker Bot - Main entry point
"""

import asyncio
import logging
from core.bot import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())