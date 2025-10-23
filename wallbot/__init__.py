import asyncio
import logging
from pyrogram import Client
from motor.motor_asyncio import AsyncIOMotorClient
from config import API_ID, API_HASH, BOT_TOKEN, DB_URL
from wallbot.plugins.word import load_words, load_common_words

import time
from asyncio import get_event_loop
from logging import ERROR, INFO, StreamHandler, basicConfig, getLogger, handlers

from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from async_pymongo import AsyncClient
from pymongo import MongoClient
from motor import motor_asyncio

from aiohttp import ClientSession


# enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("log.txt"), logging.StreamHandler()],
    level=logging.INFO,
)

LOGGER = logging.getLogger(__name__)

getLogger("pyrogram").setLevel(ERROR)



mongo = motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo["Gomezgames"]

#Telethon bot
#tle = TelegramClient("telethn", API_ID, API_HASH, flood_sleep_threshold=0).start(bot_token=BOT_TOKEN)
#print("⚫⚪TELETHON IS STARTED...⚫⚪")

# Pyrogram Bot Client
wbot = Client(
    "Gomezgames",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    mongodb=dict(connection=AsyncClient(DB_URL), remove_peers=True),
    sleep_threshold=180,
    app_version="MissKatyPyro Stable",
    workers=50,
    max_concurrent_transmissions=4,
)
BOT_ID = wbot.me.id
BOT_NAME = wbot.me.first_name
BOT_USERNAME = wbot.me.username
wbot.db = AsyncClient(DB_URL)
LOGGER.info(f"✅ Bot started as {BOT_NAME} (@{BOT_USERNAME}) My Goms {BOT_ID}")


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
# ---------------- Database + Word Setup ----------------


#jobstores = {
#    "default": MongoDBJobStore(
#        client=MongoClient(DATABASE_URI), database=DATABASE_NAME, collection="nightmode"
#    )
#}
#scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=TZ)

wbot.start()
