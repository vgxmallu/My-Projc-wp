import asyncio
import logging
import aiohttp
from datetime import datetime, timezone
from pyrogram import Client
from motor.motor_asyncio import AsyncIOMotorClient
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_CHATS, DB_URL
from wallbot.plugins.word import load_words, load_common_words

from wallbot.plugins.quots_shedul import build_quote, fetch_quote, now_utc


DB_NAME = os.getenv("DB_NAME", "daily_quotes")


# ---------------- Logging ----------------

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("DailyQuotesBot")
# ---------------- Pyrogram Bot Class ----------------
# ---------------- BOT CLASS ----------------
class GomezGamesbot(Client):
    def __init__(self):
        super().__init__(
            "daily_quotes_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),  # optional plugin dir
        )
        self.db = AsyncIOMotorClient(DB_URL)[DB_NAME]
        self.subs = self.db["subscriptions"]

    async def start(self):
        await super().start()
        me = await self.get_me()
        LOG.info(f"✅ Logged in as {me.first_name} (@{me.username})")
        await self._init_db()
        asyncio.create_task(self._quote_scheduler())  # <-- auto background task
        LOG.info("🕒 Background scheduler started automatically.")

    async def _init_db(self):
        try:
            await self.subs.create_index("chat_id", unique=True)
        except Exception:
            pass

    async def _quote_scheduler(self):
        """Auto-running background task"""
        LOG.info("📅 Quote scheduler active (UTC)")
        while True:
            try:
                now = now_utc()
                hhmm = f"{now.hour:02d}:{now.minute:02d}"
                cursor = self.subs.find({"enabled": True, "send_time": hhmm})
                subs = await cursor.to_list(length=None)
                if subs:
                    q = await fetch_quote()
                    if not q:
                        LOG.warning("No quote fetched.")
                    else:
                        msg = build_quote(q)
                        for s in subs:
                            try:
                                await self.send_message(s["chat_id"], msg, parse_mode="html")
                            except Exception as e:
                                LOG.warning(f"Failed to send quote to {s['chat_id']}: {e}")
                await asyncio.sleep(30)
            except Exception as e:
                LOG.exception(f"Error in scheduler: {e}")
                await asyncio.sleep(60)

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

wbot = GomezGamesbot()
