
from os import mkdir, path
import sys
import asyncio
from wallbot import wbot 

async def main():
    wbot = wbot()
    await wbot.start()
    await idle()  # wait until Ctrl+C or SIGTERM
    await wbot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Bot shutting down...")
