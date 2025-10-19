import asyncio
import logging
from pyrogram import Client
from motor.motor_asyncio import AsyncIOMotorClient
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_CHATS, DB_URL

import aiohttp
from datetime import datetime, timezone

from wallbot.plugins.quots_shedul import build_quote, fetch_quote, now_utc

from wallbot.plugins.word import load_words, load_common_words
# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("WallBot")


# ---------------- Pyrogram Bot Class ----------------
class wbot(Client):
    def init(self):
        super().init(
            "wallbot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="wallbot/plugins"),
        )
        self.db = AsyncIOMotorClient(DB_URL)["wallbot_db"]
        self.dbq = AsyncIOMotorClient(DB_URL)["daily_quotes"]
        self.subs = self.dbq["subscriptions"]
      
    async def start(self):
        await super().start()
        me = await self.get_me()
        LOGGER.info(f"✅🎮Gomez games Bot started as {me.first_name} (@{me.username})")    
        await self._init_db()
        asyncio.create_task(self._quote_scheduler())  # <-- auto background task
        LOGGER.info("🕒 Background scheduler started automatically.")
        for chat in AUTH_CHATS:
            try:
                await self.send_message(chat, "✅ Bot is ow online!")
            except Exception as e:
                LOGGER.warning(f"Failed to send startup message to {chat}: {e}")

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
   # async def stop(self, *args):
   #     await super().stop()
   #     LOGGER.info("🔴 Bot stopped.")


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
