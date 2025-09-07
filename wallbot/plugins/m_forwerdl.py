import datetime
import re
from pyrogram import Client, filters
from pyrogram.types import ChatPermissions, Message
from pymongo import MongoClient
from config import DB_URL
from wallbot import wbot as app


mongo = MongoClient(DB_URL)
db = mongo["forward_lock_db"]
settings = db["settings"]


# ─────────────────────────────
# HELPERS
# ─────────────────────────────
def parse_duration(duration: str) -> int:
    """
    Convert 10m / 2h / 1d into seconds
    """
    match = re.match(r"(\d+)([mhd])", duration.lower())
    if not match:
        return 600  # default 10 minutes
    num, unit = int(match[1]), match[2]
    if unit == "m":
        return num * 60
    if unit == "h":
        return num * 3600
    if unit == "d":
        return num * 86400
    return 600

def is_forward_lock_enabled(chat_id: int) -> dict:
    """
    Return forward lock settings for chat
    """
    chat = settings.find_one({"chat_id": chat_id})
    return chat if chat else {"enabled": False, "duration": 600}

def set_forward_lock(chat_id: int, status: bool, duration: int = 600):
    """
    Save settings to DB
    """
    settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": status, "duration": duration}},
        upsert=True
    )

async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

# ─────────────────────────────
# COMMANDS
# ─────────────────────────────
@app.on_message(filters.command("forwardlock") & filters.group)
async def forward_lock_toggle(client: Client, message: Message):
    if not message.from_user:
        return

    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("⚠️ Only admins can use this command!")

    if len(message.command) < 2:
        chat_settings = is_forward_lock_enabled(message.chat.id)
        status = "✅ Enabled" if chat_settings["enabled"] else "❌ Disabled"
        duration = chat_settings["duration"] // 60
        return await message.reply_text(
            f"🔒 **Forward Lock Settings**\n\n"
            f"Status: {status}\n"
            f"Duration: {duration} minutes\n\n"
            f"Usage:\n`/forwardlock on 10m`\n`/forwardlock off`"
        )

    option = message.command[1].lower()
    duration = 600  # default 10m

    if option == "on":
        if len(message.command) > 2:
            duration = parse_duration(message.command[2])
        set_forward_lock(message.chat.id, True, duration)
        await message.reply_text(
            f"✅ Forward lock has been **activated**!\n\n"
            f"⏱️ Mute duration: `{duration // 60} minutes`"
        )

    elif option == "off":
        set_forward_lock(message.chat.id, False)
        await message.reply_text("❌ Forward lock has been **deactivated**!")

    else:
        await message.reply_text("Usage:\n`/forwardlock on 10m`\n`/forwardlock off`")


# ─────────────────────────────
# FORWARD HANDLER
# ─────────────────────────────
@app.on_message(filters.forwarded & filters.group)
async def forward_handler(client: Client, message: Message):
    if not message.from_user:
        return

    chat_id = message.chat.id
    user = message.from_user
    chat_settings = is_forward_lock_enabled(chat_id)

    if not chat_settings["enabled"]:
        return

    if await is_admin(client, chat_id, user.id):
        return  # skip admins

    try:
        # Delete forwarded message
        await message.delete()

        # Calculate mute time
        mute_seconds = chat_settings.get("duration", 600)
        until = datetime.datetime.utcnow() + datetime.timedelta(seconds=mute_seconds)

        # Restrict user
        await client.restrict_chat_member(
            chat_id=chat_id,
            user_id=user.id,
            permissions=ChatPermissions(),  # mute
            until_date=until
        )

        # Notify group
        await message.reply_text(
            f"🚫 Forward is locked!\n\n👤 {user.mention} was temporarily muted for "
            f"**{mute_seconds // 60}m**!"
        )

    except Exception as e:
        print(f"[Error] forward_handler: {e}")

