from os import mkdir, path

from wallbot import wbot

import asyncio
import logging
from pyrogram import idle


from pyrogram import Client
from wallbot.plugins.g_daily_brain import run_background_tasks

@wbot.on_start()
async def on_start(client):
    client.loop.create_task(run_background_tasks())
    print("✅ Background task started automatically when bot runs.")
    

if __name__ == "__main__":
    if not path.exists("cache"):
        mkdir("cache")
    wbot().run()
    asyncio.get_event_loop().run_until_complete(main())
