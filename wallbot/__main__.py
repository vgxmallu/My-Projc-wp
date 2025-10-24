from os import mkdir, path

from wallbot import wbot

import asyncio
import logging
from pyrogram import idle

if __name__ == "__main__":
    if not path.exists("cache"):
        mkdir("cache")
    wbot().run()
    asyncio.get_event_loop().run_until_complete(main())
