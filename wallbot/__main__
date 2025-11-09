import asyncio
import logging
from wallbot import wbot  # Import safely from __init__.py

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("WallBot")

async def main():
    try:
        await wbot.start()
        LOGGER.info("💫 WallBot is running... Press Ctrl+C to stop.")
        await asyncio.Event().wait()  # Keeps running
    except KeyboardInterrupt:
        LOGGER.warning("🛑 Keyboard interrupt received.")
    finally:
        await wbot.stop()
        LOGGER.info("👋 WallBot stopped cleanly.")

if __name__ == "__main__":
    asyncio.run(main())
