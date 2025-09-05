"""
Pyrogram Night Mode Bot (single-file)

Features:
- Per-chat "night mode" (do-not-disturb) with configurable start/end times.
- Settings persisted in MongoDB (using motor).
- Only chat admins can change settings.
- Commands:
  /night_on - enable night mode with current settings
  /night_off - disable night mode
  /set_night HH:MM HH:MM - set start and end (24h, UTC by default)
  /night_status - show current settings
  /set_tz OFFSET - set timezone offset in minutes (optional; e.g. +330 for IST)
  /night_panel - quick settings panel

Extra:
- Scheduled message at the start and end of night mode.

Environment variables required:
- BOT_TOKEN
- API_ID
- API_HASH
- MONGO_URI

Run: python pyrogram_night_mode.py

Note: This script assumes the bot is running in UTC unless chat timezone offset is set with /set_tz.
"""

import os
import asyncio
from typing import Optional, Tuple
from datetime import datetime, time, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import motor.motor_asyncio

from config import DB_URL
from wallbot import wbot as app
# ---------------------------
# Configuration (env vars)
# ---------------------------

DB_NAME = os.environ.get("DB_NAME", "gomez_games")
COLLECTION = "nightmode"

# ---------------------------
mongo = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
collection = db[COLLECTION]

def parse_hhmm(text: str) -> Optional[time]:
    try:
        parts = text.strip().split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0]) % 24
        m = int(parts[1]) % 60
        return time(h, m)
    except Exception:
        return None

async def get_settings(chat_id: int) -> dict:
    doc = await collection.find_one({"chat_id": chat_id})
    if not doc:
        # default settings
        doc = {
            "chat_id": chat_id,
            "enabled": False,
            "start": "22:00",  # default night start (UTC)
            "end": "07:00",    # default night end (UTC)
            "tz_offset": 0,     # minutes offset from UTC (can be set with /set_tz)
            "last_state": None  # track last night/day state
        }
        await collection.insert_one(doc)
    return doc

async def set_settings(chat_id: int, **kwargs):
    await collection.update_one({"chat_id": chat_id}, {"$set": kwargs}, upsert=True)

def time_in_range(start: time, end: time, now: time) -> bool:
    """Return True if now is in the interval [start, end) taking wraps into account."""
    if start <= end:
        return start <= now < end
    else:
        # Over midnight: e.g., 22:00 - 07:00
        return now >= start or now < end

async def is_now_night(chat_id: int) -> bool:
    s = await get_settings(chat_id)
    if not s.get("enabled"):
        return False
    tz_off = int(s.get("tz_offset", 0))
    now_utc = datetime.utcnow() + timedelta(minutes=tz_off)
    now_t = now_utc.time()
    start = parse_hhmm(s.get("start", "22:00"))
    end = parse_hhmm(s.get("end", "07:00"))
    if not start or not end:
        return False
    return time_in_range(start, end, now_t)

# ---------------------------
# Admin check
# ---------------------------
async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False

# ---------------------------
# Commands
# ---------------------------

@app.on_message(filters.command("night_on") & (filters.group | filters.channel))
async def cmd_night_on(client: Client, message: Message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("Only chat admins can change night mode settings.")
        return
    await set_settings(message.chat.id, enabled=True)
    await message.reply_text("🌙 Night mode enabled for this chat.")

@app.on_message(filters.command("night_off") & (filters.group | filters.channel))
async def cmd_night_off(client: Client, message: Message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("Only chat admins can change night mode settings.")
        return
    await set_settings(message.chat.id, enabled=False)
    await message.reply_text("🌞 Night mode disabled for this chat.")

@app.on_message(filters.command("set_night") & (filters.group | filters.channel))
async def cmd_set_night(client: Client, message: Message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("Only chat admins can change night mode settings.")
        return
    if len(message.command) < 3:
        await message.reply_text("Usage: /set_night HH:MM HH:MM\nExample: /set_night 22:00 07:00")
        return
    start_text = message.command[1]
    end_text = message.command[2]
    start = parse_hhmm(start_text)
    end = parse_hhmm(end_text)
    if not start or not end:
        await message.reply_text("Could not parse times. Use HH:MM 24-hour format.")
        return
    await set_settings(message.chat.id, start=start_text, end=end_text)
    await message.reply_text(f"Night time set: {start_text} → {end_text} (UTC by default)")

@app.on_message(filters.command("set_tz") & (filters.group | filters.channel))
async def cmd_set_tz(client: Client, message: Message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("Only chat admins can change night mode settings.")
        return
    if len(message.command) < 2:
        await message.reply_text("Usage: /set_tz OFFSET_IN_MINUTES\nExample (for IST): /set_tz 330")
        return
    try:
        offset = int(message.command[1])
    except ValueError:
        await message.reply_text("Please provide offset as integer minutes, e.g. 330 for IST (+5:30).")
        return
    await set_settings(message.chat.id, tz_offset=offset)
    await message.reply_text(f"Timezone offset set to {offset} minutes from UTC.")

@app.on_message(filters.command("night_status") & (filters.group | filters.channel))
async def cmd_night_status(client: Client, message: Message):
    s = await get_settings(message.chat.id)
    text = (
        f"🌙 Night Mode: {'Enabled' if s.get('enabled') else 'Disabled'}\n"
        f"Start: {s.get('start')}\n"
        f"End: {s.get('end')}\n"
        f"TZ offset (mins): {s.get('tz_offset')}\n"
    )
    await message.reply_text(text)

# ---------------------------
# Behavior: suppress/auto-reply during night
# ---------------------------
@app.on_message(filters.group & ~filters.command)
async def handle_group_messages(client: Client, message: Message):
    if await is_now_night(message.chat.id):
        try:
            await message.reply_text("🌙 The chat is in Night Mode. Please avoid sending non-urgent messages until day time.")
        except Exception:
            pass

# ---------------------------
# Inline quick toggle (for convenience)
# ---------------------------
@app.on_callback_query(filters.regex(r"^toggle_night:(on|off)$"))
async def cb_toggle_night(client: Client, query):
    chat_id = int(query.message.chat.id)
    user_id = int(query.from_user.id)
    if not await is_user_admin(client, chat_id, user_id):
        await query.answer("Only admins can toggle night mode.", show_alert=True)
        return
    mode = query.data.split(":", 1)[1]
    if mode == "on":
        await set_settings(chat_id, enabled=True)
        await query.answer("Night mode enabled")
    else:
        await set_settings(chat_id, enabled=False)
        await query.answer("Night mode disabled")
    await query.message.edit_reply_markup(
        InlineKeyboardMarkup([
            [InlineKeyboardButton("Enable", callback_data="toggle_night:on"), InlineKeyboardButton("Disable", callback_data="toggle_night:off")]
        ])
    )

# ---------------------------
# Helper to create a settings panel (for admins)
# ---------------------------
@app.on_message(filters.command("night_panel") & (filters.group | filters.channel))
async def cmd_night_panel(client: Client, message: Message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("Only chat admins can open the night panel.")
        return
    s = await get_settings(message.chat.id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Enable", callback_data="toggle_night:on"), InlineKeyboardButton("Disable", callback_data="toggle_night:off")],
    ])
    await message.reply_text(
        f"🌙 Night Mode Settings:\nEnabled: {s.get('enabled')}\nStart: {s.get('start')}\nEnd: {s.get('end')}\nTZ offset: {s.get('tz_offset')}",
        reply_markup=kb
    )

# ---------------------------
# Scheduled notifier task
# ---------------------------
async def scheduled_notifier():
    await app.start()  # ensure client is running
    while True:
        async for chat in collection.find({"enabled": True}):
            chat_id = chat["chat_id"]
            now_is_night = await is_now_night(chat_id)
            last_state = chat.get("last_state")
            if now_is_night and last_state != "night":
                try:
                    await app.send_message(chat_id, "🌙 Night mode has started. Good night!")
                except Exception:
                    pass
                await set_settings(chat_id, last_state="night")
            elif not now_is_night and last_state != "day":
                try:
                    await app.send_message(chat_id, "🌞 Night mode has ended. Good morning!")
                except Exception:
                    pass
                await set_settings(chat_id, last_state="day")
        await asyncio.sleep(60)  # check every minute
