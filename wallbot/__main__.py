
import asyncio
from wallbot import wbot
from pyrogram import idle

async def main():
    await wbot.start()
    print("✅ WallBot is online")
    await idle()
    await wbot.stop()

if __name__ == "__main__":
    asyncio.run(main())
