import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app

mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client["antispam_bot"]
settings_col = db["username_antispam"]
warns_col = db["user_warns"]



# ------------------- HELPERS -------------------
async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except:
        return False

async def get_settings(chat_id: int) -> dict:
    settings = await settings_col.find_one({"chat_id": chat_id})
    if not settings:
        settings = {"chat_id": chat_id, "enabled": False, "punishment": "warn"}
        await settings_col.insert_one(settings)
    return settings

async def update_settings(chat_id: int, data: dict):
    await settings_col.update_one({"chat_id": chat_id}, {"$set": data}, upsert=True)

async def apply_punishment(message: Message, punishment: str):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if punishment == "warn":
        user_warns = await warns_col.find_one({"chat_id": chat_id, "user_id": user_id}) or {"warns": 0}
        warns = user_warns.get("warns", 0) + 1
        await warns_col.update_one({"chat_id": chat_id, "user_id": user_id}, {"$set": {"warns": warns}}, upsert=True)
        await message.reply_text(f"⚠️ {message.from_user.mention} warned! Total warns: {warns}")

    elif punishment == "kick":
        try:
            await app.kick_chat_member(chat_id, user_id)
            await asyncio.sleep(1)
            await app.unban_chat_member(chat_id, user_id)
            await message.reply_text(f"👢 {message.from_user.mention} was kicked for spam.")
        except Exception as e:
            await message.reply_text(f"❌ Failed to kick: {e}")

    elif punishment == "ban":
        try:
            await app.kick_chat_member(chat_id, user_id)
            await message.reply_text(f"🚫 {message.from_user.mention} was banned for spam.")
        except Exception as e:
            await message.reply_text(f"❌ Failed to ban: {e}")

    elif punishment == "mute":
        try:
            await app.restrict_chat_member(chat_id, user_id, permissions={})
            await message.reply_text(f"🔇 {message.from_user.mention} was muted for spam.")
        except Exception as e:
            await message.reply_text(f"❌ Failed to mute: {e}")

# ------------------- COMMAND HANDLER -------------------

@app.on_message(filters.command("username_antispam") & filters.group)
async def usernambe_antispam_cmd(client, message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only admins can manage this setting.")

    settings = await get_settings(message.chat.id)
    status = "✅ Enabled" if settings["enabled"] else "❌ Disabled"
    punishment = settings["punishment"].capitalize()

    buttons = [
        [InlineKeyboardButton(f"Status: {status}", callback_data=f"ua_toggle_{int(not settings['enabled'])}")],
        [
            InlineKeyboardButton("⚠️ Warn", callback_data="ua_set_warn"),
            InlineKeyboardButton("👢 Kick", callback_data="ua_set_kick"),
        ],
        [
            InlineKeyboardButton("🚫 Ban", callback_data="ua_set_ban"),
            InlineKeyboardButton("🔇 Mute", callback_data="ua_set_mute"),
        ]
    ]

    await message.reply_text(
        f"🔧 **Username Antispam Settings**\n\nStatus: {status}\nPunishment: {punishment}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"ua_"))
async def callbhack_handler(client, callback_query):
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id

    if not await is_admin(chat_id, user_id):
        return await callback_query.answer("❌ Only admins can change this.", show_alert=True)

    data = callback_query.data

    if data.startswith("ua_toggle_"):
        enabled = bool(int(data.split("_")[2]))
        await update_settings(chat_id, {"enabled": enabled})
        await callback_query.answer("✅ Updated!")
        await username_antispam_cmd(client, callback_query.message)

    elif data.startswith("ua_set_"):
        punishment = data.split("_")[2]
        await update_settings(chat_id, {"punishment": punishment})
        await callback_query.answer(f"✅ Punishment set to {punishment.capitalize()}")
        await username_antispam_cmd(client, callback_query.message)

# ------------------- SPAM DETECTION -------------------

USERNAME_REGEX = re.compile(r"(@[a-zA-Z0-9_]{4,}|t\.me/[a-zA-Z0-9_]{4,})", re.IGNORECASE)

@app.on_message(filters.group, group=5)
async def detect_userbname_spam(client, message: Message):
    if not message.from_user or message.sender_chat:
        return

    settings = await get_settings(message.chat.id)
    if not settings["enabled"]:
        return

    text = message.text or message.caption or ""
    if USERNAME_REGEX.search(text):
        await apply_punishment(message, settings["punishment"])
        try:
            await message.delete()
        except:
            pass
