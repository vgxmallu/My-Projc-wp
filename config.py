from os import environ, mkdir, path, sys
from dotenv import load_dotenv
from pyrogram import Client
import os



# Mandatory Variable
API_ID = int(environ["API_ID"])
API_HASH = environ["API_HASH"]
BOT_TOKEN = environ["BOT_TOKEN"]
OWNER_ID = int(environ["OWNER_ID"])

# Optional Variable
SUDO_USERS = environ.get("SUDO_USERS", str(OWNER_ID)).split()
SUDO_USERS = [int(_x) for _x in SUDO_USERS]

AUTH_CHATS = environ.get("AUTH_CHATS").split()
AUTH_CHATS = [int(_x) for _x in AUTH_CHATS]
#LOG_CHANNEL = environ.get("LOG_CHANNEL")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "-1001997285269"))

#Broadcast
BROADCAST_AS_COPY = bool(os.environ.get("BROADCAST_AS_COPY", True))

#MongoDB
DB_URL = os.environ.get("DB_URL", "")
DB_NAME = os.environ.get("DB_NAME", "")

#Ai_Tools_API's
OPENAI_KEY = environ.get("OPENAI_KEY")

class Telegram:
    EMOJIS = [
        "👍", "👎", "❤️", "🔥", 
        "🥰", "👏", "🤩", "👌",
        "😍", "🐳", "❤‍🔥", "💯",
        "💔", "🍓", "👀", "😇",
        "🤗", "🤪", "🗿", "🆒",
        "💘", "😘", "😁", "🎉",
        "🙏", "❤️‍🔥", "🕊️", "⚡",
        "🙈", "😇", "🤪", "💘"
    ]
    EMOJIS_2 = [
        "❤‍🔥"
    ]
