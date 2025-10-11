import asyncio
import logging
from wallbot import wbot

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("WallBot")

async def main():
    bot = wbot()
    try:
        await bot.start()
        LOGGER.info("💫 WallBot is running... Press Ctrl+C to stop.")
        await asyncio.Event().wait()  # Keeps it alive
    except KeyboardInterrupt:
        LOGGER.info("🛑 Keyboard interrupt received.")
    finally:
        await bot.stop()
        LOGGER.info("👋 WallBot stopped cleanly.")

if __name__ == "__main__":
    asyncio.run(main())
