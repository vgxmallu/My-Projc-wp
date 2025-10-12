import asyncio
import logging
from pyrogram import Client
from motor.motor_asyncio import AsyncIOMotorClient
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_CHATS, DB_URL
from wallbot.plugins.word import load_words, load_common_words
# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("WallBot")

# ---------------- Pyrogram Bot Class ----------------
class wbot(Client):
    def __init__(self):
        super().__init__(
            "wallbot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="wallbot/plugins"),
        )
        self.db = AsyncIOMotorClient(DB_URL)["wallbot_db"]

    async def start(self):
        await super().start()
        me = await self.get_me()
        LOGGER.info(f"✅ Bot started as {me.first_name} (@{me.username})")
        for chat in AUTH_CHATS:
            try:
                await self.send_message(chat, "✅ Bot is now online!")
            except Exception as e:
                LOGGER.warning(f"Failed to send startup message to {chat}: {e}")

    async def stop(self, *args):
        await super().stop()
        LOGGER.info("🔴 Bot stopped.")


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

