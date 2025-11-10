import asyncio, random
import os
import logging
from os import environ, mkdir, path, sys
from dotenv import load_dotenv
from pyrogram import Client
from aiohttp import ClientSession
import time
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from config import API_ID, API_HASH, BOT_TOKEN, DB_URL
from wallbot.plugins.word import load_words, load_common_words
from wallbot.plugins.g_amungus import cleanup_stale_games
from wallbot.plugins.g_daily_brain import run_background_tasks
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
LOGGER = logging.getLogger("WallBot")

class wbot(Client):
    def __init__(self):
        super().__init__(
            "wallbot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="wallbot"),
            workdir="./cache/",
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        LOGGER.info(f"✅ Bot @{me.username} started successfully!")

    async def stop(self, *args):
        await super().stop()
        LOGGER.info("🛑 Bot stopped cleanly.")

# ---------------- Database + Word Setup ----------------
DEV_LIST = [784589736]

client = AsyncIOMotorClient(DB_URL)
db = client["WordNWord"]
user_Collection = db["user"]
collection = db["word"]

WORD_LIST = set(load_words())
WORD_SET = set(WORD_LIST)
MEAN_WORD = load_common_words()
MEAN_WORD_SET = set(MEAN_WORD)

print(f"Loaded {len(WORD_SET)} words from the word list.")

loop = asyncio.get_event_loop()
loop.create_task(cleanup_stale_games())
print("🕵️ Amungus INFILTRATOR (Advanced Edition) running...")

loop = asyncio.get_event_loop()
loop.loop.create_task(run_background_tasks())
print("✅ Background task started automatically when bot runs.")
    

# Only define the bot — do NOT start it here
wbot.start()
