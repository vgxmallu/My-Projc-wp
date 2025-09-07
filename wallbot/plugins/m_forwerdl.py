from pyrogram import Client, filters
from pyrogram.types import ChatPermissions, Message
from pymongo import MongoClient
import asyncio
import datetime
from config import DB_URL
from wallbot import wbot as app

# ─────────────────────────────
# CONFIG
# ─────────────────────────────

mongo = MongoClient(DB_URL)
db = mongo["forward_lock_db"]
settings = db["settings"]

# ─────────────────────────────
# HELPERS
# ─────────────────────────────
def is_forward_lock_enabled(chat_id: int) -> bool:
    chat = settings.find_one({"chat_id": chat_id})
    return chat and chat.get("forward_lock", False)

def set_forward_lock(chat_id: int, status: bool):
    settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"forward_lock": status}},
        upsert=True
    )

async def is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

# ─────────────────────────────
# COMMANDS
# ─────────────────────────────
@app.on_message(filters.command("forwardlock") & filters.group)
async def forward_lock_toggle(client, message: Message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("⚠️ Only admins can change forward-lock settings!")

    if len(message.command) < 2:
        return await message.reply("Usage:\n`/forwardlock on`\n`/forwardlock off`")

    option = message.command[1].lower()
    if option == "on":
        set_forward_lock(message.chat.id, True)
        await message.reply("✅ Forward lock has been **activated** in this group!")
    elif option == "off":
        set_forward_lock(message.chat.id, False)
        await message.reply("❌ Forward lock has been **deactivated** in this group!")
    else:
        await message.reply("Usage:\n`/forwardlock on`\n`/forwardlock off`")

# ─────────────────────────────
# FORWARD HANDLER
# ─────────────────────────────
@app.on_message(filters.forwarded & filters.group)
async def forward_handler(client, message: Message):
    chat_id = message.chat.id
    user = message.from_user

    # Skip if disabled
    if not is_forward_lock_enabled(chat_id):
        return

    # Skip admins
    if await is_admin(client, chat_id, user.id):
        return

    try:
        # Delete forwarded message
        await message.delete()

        # Mute violator for 10 minutes
        until = message.date + datetime.timedelta(minutes=10)
        await app.restrict_chat_member(
            chat_id=chat_id,
            user_id=user.id,
            permissions=ChatPermissions(),
            until_date=until
        )

        # Notify group
        await message.reply_text(
            f"🚫 Forward is locked!\n\n👤 {user.mention} was temporarily muted for **10m**!"
        )

    except Exception as e:
        print(f"Error: {e}")
