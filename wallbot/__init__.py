

import os
import logging
from os import environ, mkdir, path, sys
from dotenv import load_dotenv
from pyrogram import Client
from aiohttp import ClientSession
import time
from dotenv import load_dotenv

from config import API_ID, API_HASH, BOT_TOKEN, DB_URL, AUTH_CHATS





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
            plugins=dict(root=f"{name}/plugins"),
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
                "https://files.catbox.moe/80bcxh.jpg",
                "**GimezGames Bot as Started.**🎮✅",
            )
        LOGGER.info(f"GomezGamesbot STARTED AS {BOT_INFO.username}\n")

    async def stop(self, *args):
        await super().stop()
        LOGGER.info("Gomezgames STOPPED BRO.")

