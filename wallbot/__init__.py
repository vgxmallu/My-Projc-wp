
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_CHATS, DB_URL
from wallbot.plugins.word import load_words, load_common_words
#from wallbot.plugins.birthday_remind import birthday_check_loop, wishes_col, subscriptions_col, birthdays_col
import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

from pyrogram import Client, idle, errors, enums
from motor.motor_asyncio import AsyncIOMotorClient

# ---------------- Load Env ----------------
load_dotenv()


OWNER_ID = "784589736"

# ---------------- Logging ----------------
LOG_FORMAT = "%(levelname)s [%(asctime)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler("bot.log", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
LOGGER = logging.getLogger("BotStarter")

# Suppress lower-level logs from Pyrogram
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ---------------- Database ----------------
if not DB_URL:
    LOGGER.critical("DB_URL not configured. Exiting.")
    sys.exit(1)

mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["botdb"]

# (You can use `db.users`, `db.chats`, etc.)

# ---------------- Bot Class ----------------
class wbot(Client):
    def __init__(self):
        super().__init__(
            name="my_bot",  # session name
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),  # folder for plugin modules
            workdir="./cache",
            sleep_threshold=30,
        )
        self.db = db
        self.start_time = None

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.start_time = asyncio.get_event_loop().time()
        LOGGER.info(f"🟢 Bot started as {me.username} (ID: {me.id})")

        # Ensure necessary directories
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path("/tmp/thumbnails").mkdir(parents=True, exist_ok=True)

        # Send startup notification
        for chat_id in AUTH_CHATS:
            try:
                await self.send_message(chat_id, f"✅ {me.mention()} is now online.")
            except errors.FloodWait as e:
                LOGGER.warning(f"FloodWait waiting: {e.x} seconds")
                await asyncio.sleep(e.x)
            except Exception as e:
                LOGGER.warning(f"Could not send startup message to {chat_id}: {e}")

        # Run your custom startup tasks
        await self.on_startup()

    async def on_startup(self):
        """Override this to create indexes, spawn background tasks, etc."""
        try:
            await self.db.users.create_index("user_id", unique=True)
            await self.db.chats.create_index("chat_id", unique=True)
            LOGGER.info("✅ MongoDB indexes created.")
        except Exception as e:
            LOGGER.warning(f"Could not create indexes: {e}")

        # Example: start a background task
        self.loop.create_task(self.background_loop())

    async def background_loop(self):
        """Example periodic task."""
        while True:
            try:
                LOGGER.debug("Running periodic task …")
                # your logic here
                await asyncio.sleep(300)  # run every 5 min
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.error(f"Error in background loop: {e}")

    async def stop(self, *args):
        await super().stop()
        LOGGER.info("🔴 Bot stopped gracefully.")


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


