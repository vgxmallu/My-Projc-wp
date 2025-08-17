
import logging
from os import environ, mkdir, path, sys
from dotenv import load_dotenv
from pyrogram import Client
import os
import time
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_CHATS, DB_URL
from wallbot.plugins.word import load_words, load_common_words
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from wallbot.plugins.rss import feed_checker



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

# Log
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)


async def check_feeds():
    """Check all feeds for new entries"""
    feeds = await get_feeds()
    if not feeds:
        return
    
    print(f"\nChecking {len(feeds)} feeds at {datetime.now().isoformat()}")
    
    for feed in feeds:
        print(f"Processing feed: {feed['title']}")
        await process_feed(feed)
        await asyncio.sleep(2)  # Delay between feeds


class wbot(Client):
    def __init__(self):
        name = self.__class__.__name__.lower()
        super().__init__(
            ":memory:",
            plugins=dict(root="wallbot/plugins"),
            workdir="./cache/",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            sleep_threshold=30,
        )

    async def start(self):
        global BOT_INFO
        await super().start()
        BOT_INFO = await self.get_me()
        if not path.exists("/tmp/thumbnails/"):
            mkdir("/tmp/thumbnails/")
        for chat in AUTH_CHATS:
            await self.send_photo(
                chat,
                "https://files.catbox.moe/endqeo.jpg",
                "**my Test Bot is started** ✅",
            )
        LOGGER.info(f"\nTest is ONLINE 🟢\n\n{BOT_INFO.username} Is Running 💨💥\n")

    async def stop(self, *args):
        await super().stop()
        LOGGER.info("Bot is OFFLINE 🔴")

async def main():    
    #await app.start()
    print("Bot started")
    asyncio.create_task(feed_checker())
    # Keep the application running
    while True:
        await asyncio.sleep(3600)  # Sleep for 1 hour

loop = asyncio.get_event_loop()
loop.run_until_complete(main())


DEV_LIST = [784589736]

client = AsyncIOMotorClient(DB_URL)
db = client['WordNWord']
user_Collection = db['user']
collection = db['word']

WORD_LIST = set(load_words())
WORD_SET = set(WORD_LIST)
MEAN_WORD = load_common_words()
MEAN_WORD_SET = set(MEAN_WORD)

print(f"Loaded {len(WORD_SET)} words from the word list.")
