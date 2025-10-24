from os import mkdir, path

from wallbot import wbot

import asyncio
import logging
from pyrogram import idle

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("WallBot")

bot = wbot()

async def main():
    try:
        await bot.start()
        LOGGER.info("💫 WallBot is running... Press Ctrl+C to stop.")
        await idle()  # Keeps bot alive until SIGINT or stop command
    except Exception as e:
        LOGGER.error(f"❌ Error while running bot: {e}")
    finally:
        await bot.stop()
        LOGGER.info("👋 WallBot stopped cleanly.")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

