import logging
import os
import time
from os import environ, mkdir, path
from dotenv import load_dotenv
from pyrogram import Client, idle
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

from config import API_ID, API_HASH, BOT_TOKEN, AUTH_CHATS, DB_URL
from wallbot.plugins.word import load_words, load_common_words
#from wallbot.plugins.birthday_remind import birthday_check_loop, wishes_col, subscriptions_col, birthdays_col

formatter = logging.Formatter('%(levelname)s %(asctime)s - %(name)s - %(message)s')

fh = logging.FileHandler(f'{__name__}.log', 'w')
fh.setFormatter(formatter)
fh.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setFormatter(formatter)
ch.setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(fh)
logger.addHandler(ch)

botStartTime = time.time()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)


wbot = Client("games_gomez", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
        
    
        

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


