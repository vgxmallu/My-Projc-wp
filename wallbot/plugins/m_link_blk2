import re
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions, CallbackQuery
from pymongo import MongoClient
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "link_blk_db"
COLLECTION = "link_protection"

# ------------------ INIT ------------------
mongo_client = MongoClient(DB_URL)
db = mongo_client[DB_NAME]
col = db[COLLECTION]

# ------------------ DEFAULT SETTINGS ------------------
default_settings = {
    "module_enabled": True,
    "warns_limit": 3,
    "punishments": ["warn", "kick", "ban", "mute"],  # punishment sequence
    "warn_duration": 86400,  # time in seconds after which warns reset (1 day)
    "warns": {}
}

# ------------------ UTILITIES ------------------
def get_group_settings(chat_id):
    settings = col.find_one({"chat_id": chat_id})
    if not settings:
        settings = default_settings.copy()
        settings["chat_id"] = chat_id
        settings["warns"] = {}
        col.insert_one(settings)
    return settings

def update_group_settings(chat_id, key, value):
    col.update_one({"chat_id": chat_id}, {"$set": {key: value}}, upsert=True)

def reset_old_warns(chat_id):
    settings = get_group_settings(chat_id)
    warns = settings.get("warns", {})
    now = time.time()
    changed = False
    for user_id, data in list(warns.items()):
        timestamp = data.get("timestamp", 0)
        if now - timestamp > settings.get("warn_duration", 86400):
            warns.pop(user_id)
            changed = True
    if changed:
        col.update_one({"chat_id": chat_id}, {"$set": {"warns": warns}})

# ------------------ REGEX FOR TELEGRAM LINKS ------------------
TELEGRAM_LINK_REGEX = re.compile(r"(t\.me\/\w+|telegram\.me\/\w+|t\.me\/joinchat\/\w+)", re.IGNORECASE)

# ------------------ PUNISH USER ------------------
async def punish_user(message: Message, punishment_type=None):
    user_id = message.from_user.id
    chat_id = message.chat.id
    settings = get_group_settings(chat_id)

    reset_old_warns(chat_id)
    warns = settings.get("warns", {})

    if not punishment_type or punishment_type == "warn":
        warns.setdefault(str(user_id), {"count": 0, "timestamp": time.time()})
        warns[str(user_id)]["count"] += 1
        warns[str(user_id)]["timestamp"] = time.time()
        col.update_one({"chat_id": chat_id}, {"$set": {"warns": warns}})
        limit = settings.get("warns_limit", 3)
        await message.reply_text(f"⚠️ {message.from_user.mention} warned! ({warns[str(user_id)]['count']}/{limit})")
        if warns[str(user_id)]["count"] >= limit:
            punishment_to_apply = settings.get("punishments", ["warn"])[-1]  # last punishment
            return await punish_user(message, punishment_to_apply)

    elif punishment_type == "kick":
        try:
            await message.chat.kick_member(user_id)
            await message.reply_text(f"❌ {message.from_user.mention} has been kicked!")
        except Exception:
            await message.reply_text(f"❌ Cannot kick {message.from_user.mention}.")
    elif punishment_type == "ban":
        try:
            await message.chat.ban_member(user_id)
            await message.reply_text(f"⛔ {message.from_user.mention} has been banned!")
        except Exception:
            await message.reply_text(f"⛔ Cannot ban {message.from_user.mention}.")
    elif punishment_type == "mute":
        try:
            mute_perms = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
            await message.chat.restrict_member(user_id, mute_perms)
            await message.reply_text(f"🔇 {message.from_user.mention} has been muted!")
        except Exception:
            await message.reply_text(f"🔇 Cannot mute {message.from_user.mention}.")

# ------------------ MESSAGE HANDLER ------------------
@app.on_message(filters.regex(TELEGRAM_LINK_REGEX) & filters.group)
async def link_blocker(client: Client, message: Message):
    chat_id = message.chat.id
    settings = get_group_settings(chat_id)
    if not settings.get("module_enabled", True):
        return
    await punish_user(message, settings.get("punishments", ["warn"])[0])

# ------------------ COMMAND MENU ------------------
@app.on_message(filters.command("linkblock") & filters.group)
async def link_modblule_menu(client: Client, message: Message):
    settings = get_group_settings(message.chat.id)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Enable", callback_data="enable_module"),
            InlineKeyboardButton("Disable", callback_data="disable_module")
        ],
        [
            InlineKeyboardButton("Punish: Warn", callback_data="set_warn"),
            InlineKeyboardButton("Punish: Kick", callback_data="set_kick")
        ],
        [
            InlineKeyboardButton("Punish: Ban", callback_data="set_ban"),
            InlineKeyboardButton("Punish: Mute", callback_data="set_mute")
        ],
        [
            InlineKeyboardButton("Set Warn Limit", callback_data="set_warn_limit")
        ]
    ])
    await message.reply_text("📌 Link Protection Module Settings:", reply_markup=keyboard)

# ------------------ CALLBACK QUERY HANDLER ------------------
@app.on_callback_query(filters.regex(".*"))
async def calbloklback_handler(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    data = query.data

    if data == "enable_module":
        update_group_settings(chat_id, "module_enabled", True)
        await query.answer("✅ Module Enabled")
    elif data == "disable_module":
        update_group_settings(chat_id, "module_enabled", False)
        await query.answer("❌ Module Disabled")
    elif data == "set_warn":
        update_group_settings(chat_id, "punishments", ["warn"])
        await query.answer("⚠️ Punishment set to WARN")
    elif data == "set_kick":
        update_group_settings(chat_id, "punishments", ["kick"])
        await query.answer("❌ Punishment set to KICK")
    elif data == "set_ban":
        update_group_settings(chat_id, "punishments", ["ban"])
        await query.answer("⛔ Punishment set to BAN")
    elif data == "set_mute":
        update_group_settings(chat_id, "punishments", ["mute"])
        await query.answer("🔇 Punishment set to MUTE")
    elif data == "set_warn_limit":
        # Here we can prompt user to reply with new limit
        await query.message.reply_text("Please reply with the new warn limit (number):")

# ------------------ WARN LIMIT SETTER ------------------
@app.on_message(filters.reply & filters.group)
async def warn_lbimit_setter(client: Client, message: Message):
    if not message.reply_to_message:
        return
    text = message.text
    chat_id = message.chat.id
    try:
        limit = int(text)
        update_group_settings(chat_id, "warns_limit", limit)
        await message.reply_text(f"✅ Warn limit set to {limit}")
    except ValueError:
        await message.reply_text("❌ Invalid number! Please send an integer.")
