from aiogram import Router

# Import all handler modules
from . import commands, callbacks, messages

# Create main router
router = Router()

# Include all sub-routers
router.include_router(commands.router)
router.include_router(callbacks.router)
router.include_router(messages.router)