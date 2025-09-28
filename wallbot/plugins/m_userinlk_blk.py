from pyrogram import Client, types, filters
from pymongo import MongoClient
import re
import asyncio
from datetime import datetime
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, ChatPermissions
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from config import DB_URL
from wallbot import wbot as app



# -----------------------------
# MongoDB Setup
# -----------------------------
mongo = MongoClient("DB_URL")
db = mongo["telegram_bot"]
settings_collection = db["username_antispam_settings"]
warns_collection = db["username_warns"]



# -----------------------------
# Helper Functions
# -----------------------------
def get_group_settings(chat_id: int) -> dict:
    """Retrieve or create default settings for a group."""
    settings = settings_collection.find_one({"chat_id": chat_id})
    if not settings:
        settings = {
            "chat_id": chat_id,
            "enabled": True,
            "punishment": "warn",
            "mute_duration": 300,  # default 5 minutes
            "spam_keywords": ["spam", "bot", "fake"]  # default spam username keywords
        }
        settings_collection.insert_one(settings)
    return settings

def set_group_settings(chat_id: int, field: str, value):
    """Update a field in group settings."""
    settings_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {field: value}},
        upsert=True
    )

async def punish_user(chat_id: int, user_id: int, punishment: str, mute_duration: int = None):
    """Apply punishment to the user."""
    try:
        if punishment == "warn":
            warns_collection.update_one(
                {"chat_id": chat_id, "user_id": user_id},
                {"$inc": {"count": 1}, "$set": {"last_warn": datetime.utcnow()}},
                upsert=True
            )
            warn_data = warns_collection.find_one({"chat_id": chat_id, "user_id": user_id})
            return warn_data.get("count", 1)
        elif punishment == "mute":
            duration = mute_duration or 300
            await app.restrict_chat_member(
                chat_id,
                user_id,
                permissions=types.ChatPermissions(can_send_messages=False)
            )
            asyncio.create_task(unmute_after(chat_id, user_id, duration))
        elif punishment == "kick":
            await app.kick_chat_member(chat_id, user_id)
        elif punishment == "ban":
            await app.ban_chat_member(chat_id, user_id)
    except Exception as e:
        print(f"Failed to punish user {user_id}: {e}")

async def unmute_after(chat_id: int, user_id: int, duration: int):
    """Automatically unmute a user after a given duration."""
    await asyncio.sleep(duration)
    try:
        await app.restrict_chat_member(
            chat_id,
            user_id,
            permissions=types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_stickers=True,
                can_send_animations=True,
                can_send_polls=True,
                can_add_web_page_previews=True,
            )
        )
        print(f"User {user_id} unmuted in chat {chat_id}")
    except Exception as e:
        print(f"Failed to unmute user {user_id}: {e}")

async def is_admin(chat_id: int, user_id: int) -> bool:
    """Check if a user is admin or creator."""
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

async def show_menu(chat_id: int, message=None):
    """Show inline button menu for admin settings."""
    settings = get_group_settings(chat_id)
    enabled_text = "✅ Enabled" if settings["enabled"] else "❌ Disabled"
    punishment = settings.get("punishment", "warn")

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Enable" if not settings["enabled"] else "Disable",
                    callback_data=f"toggle_enable:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton("Warn", callback_data=f"set_punishment:{chat_id}:warn"),
                InlineKeyboardButton("Mute", callback_data=f"set_punishment:{chat_id}:mute"),
                InlineKeyboardButton("Kick", callback_data=f"set_punishment:{chat_id}:kick"),
                InlineKeyboardButton("Ban", callback_data=f"set_punishment:{chat_id}:ban"),
            ]
        ]
    )

    if message:
        await message.edit_text(
            f"Username AntiSpam Settings:\nStatus: {enabled_text}\nPunishment: {punishment}",
            reply_markup=keyboard
        )
    else:
        await app.send_message(
            chat_id,
            f"Username AntiSpam Settings:\nStatus: {enabled_text}\nPunishment: {punishment}",
            reply_markup=keyboard
        )

# -----------------------------
# Callback Queries
# -----------------------------
@app.on_callback_query(filters.regex(r"toggle_enable:\d+"))
async def toggle_enable(client, query):
    chat_id = int(query.data.split(":")[1])
    if not await is_admin(chat_id, query.from_user.id):
        return await query.answer("Only admins can use this!", show_alert=True)
    settings = get_group_settings(chat_id)
    new_state = not settings["enabled"]
    set_group_settings(chat_id, "enabled", new_state)
    await query.answer(f"Module {'Enabled' if new_state else 'Disabled'}!")
    await show_menu(chat_id, query.message)

@app.on_callback_query(filters.regex(r"set_punishment:\d+:\w+"))
async def set_punishment(client, query):
    parts = query.data.split(":")
    chat_id = int(parts[1])
    if not await is_admin(chat_id, query.from_user.id):
        return await query.answer("Only admins can use this!", show_alert=True)
    punishment = parts[2]
    set_group_settings(chat_id, "punishment", punishment)
    await query.answer(f"Punishment set to {punishment}")
    await show_menu(chat_id, query.message)

# -----------------------------
# Detect Username Spam
# -----------------------------
@app.on_message(filters.group)
async def detect_username_spam(client, message):
    chat_id = message.chat.id
    settings = get_group_settings(chat_id)
    if not settings["enabled"]:
        return

    username = (message.from_user.username or "").lower()
    spam_keywords = settings.get("spam_keywords", [])

    if any(keyword in username for keyword in spam_keywords):
        punishment = settings.get("punishment", "warn")
        mute_duration = settings.get("mute_duration", 300)
        warn_count = await punish_user(chat_id, message.from_user.id, punishment, mute_duration)
        await message.delete()
        if punishment == "warn":
            await message.reply_text(f"{message.from_user.mention} warned for spammy username! Total warnings: {warn_count}")

# -----------------------------
# Main Admin Command to Open Menu
# -----------------------------
@app.on_message(filters.command("username_antispam") & filters.group)
async def majrin_menu(client, message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("Only admins can use this command!")
    await show_menu(message.chat.id)


