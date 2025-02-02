
import logging
from os import environ, mkdir, path, sys
from dotenv import load_dotenv
from pyrogram import Client
import os
import time
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_CHATS

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
                "https://envs.sh/mcw.jpg",
                "**Wallpapers Bot is started** ✅",
            )
        LOGGER.info(f"\nWallpepers is ONLINE 🟢\n\n{BOT_INFO.username} Is Running 💨💥\n")

    async def stop(self, *args):
        await super().stop()
        LOGGER.info("Bot is OFFLINE 🔴")
