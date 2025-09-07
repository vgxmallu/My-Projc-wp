"""
Advanced Antiflood (Pyrogram v2.x) with MongoDB + stats
Fixes: use ChatPermissions from pyrogram.types (not enums.ChatPermissions)
"""

import re
import time
from datetime import datetime, timedelta
from pymongo import MongoClient
from pyrogram import Client, filters, enums
from pyrogram.types import Message, ChatPermissions
from config import DB_URL
from wallbot import wbot as app
# ---------------- CONFIG ----------------
DB_NAME = "floodwait_db"
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
settings_col = db["settings"]
stats_col = db["stats"]

# in-memory short-term message timestamps per user per chat
cache = {}

# ---------------- HELPERS ----------------
TIME_RE = re.compile(r"^(\d+)([smhd])$")


def parse_time(time_str: str):
    """Return timedelta for strings like 10m, 2h, 30s, 1d or None on invalid."""
    if not time_str:
        return None
    m = TIME_RE.match(time_str.lower())
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    if unit == "s":
        return timedelta(seconds=val)
    if unit == "m":
        return timedelta(minutes=val)
    if unit == "h":
        return timedelta(hours=val)
    if unit == "d":
        return timedelta(days=val)
    return None


async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Return True if user is owner or admin with restrict rights."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        # owner always allowed
        if member.status == enums.ChatMemberStatus.OWNER:
            return True
        # administrator: check privilege can_restrict_members
        if member.status == enums.ChatMemberStatus.ADMINISTRATOR:
            priv = getattr(member, "privileges", None)
            if priv and getattr(priv, "can_restrict_members", False):
                return True
    except Exception:
        pass
    return False


def get_settings(chat_id: int):
    """Return settings dict with defaults."""
    s = settings_col.find_one({"chat_id": chat_id})
    if not s:
        s = {"chat_id": chat_id, "limit": None, "mode": "mute", "time": None}
        settings_col.insert_one(s)
    return s


def set_settings(chat_id: int, **kwargs):
    settings_col.update_one({"chat_id": chat_id}, {"$set": kwargs}, upsert=True)


def update_stats(chat_id: int, action: str):
    """Increment punishment stat"""
    stats_col.update_one({"chat_id": chat_id}, {"$inc": {action: 1}}, upsert=True)


def get_stats(chat_id: int):
    d = stats_col.find_one({"chat_id": chat_id}) or {}
    return {
        "ban": d.get("ban", 0),
        "kick": d.get("kick", 0),
        "mute": d.get("mute", 0),
        "tmute": d.get("tmute", 0),
        "tban": d.get("tban", 0),
    }


# ---------------- COMMANDS ----------------
@app.on_message(filters.command(["flood"]) & filters.group)
async def flood_cmd(client: Client, message: Message):
    s = get_settings(message.chat.id)
    limit = s.get("limit")
    mode = s.get("mode")
    t = s.get("time")
    txt = f"🚨 Flood Settings:\n• Limit: `{limit if limit is not None else 'off'}`\n• Mode: `{mode}`"
    if t:
        txt += f"\n• Time: `{t}`"
    await message.reply(txt)


@app.on_message(filters.command("setflood") & filters.group)
async def setflood_cmd(client: Client, message: Message):
    if not message.from_user:
        return
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("⚠️ Only admins with restrict permission can do this!")

    if len(message.command) < 2:
        return await message.reply("Usage: /setflood [int|off] (example: /setflood 5  OR  /setflood off)")

    arg = message.command[1].lower()
    if arg in ("off", "no"):
        set_settings(message.chat.id, limit=None)
        return await message.reply("✅ Flood control disabled for this chat.")
    if arg.isdigit():
        limit = int(arg)
        set_settings(message.chat.id, limit=limit)
        return await message.reply(f"✅ Flood limit set to `{limit}` messages.")
    return await message.reply("❌ Invalid value. Use an integer like `5` or `off`.")


@app.on_message(filters.command("floodmode") & filters.group)
async def floodmode_cmd(client: Client, message: Message):
    if not message.from_user:
        return
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("⚠️ Only admins with restrict permission can do this!")

    if len(message.command) < 2:
        return await message.reply("Usage: /floodmode [mode] [time]\nModes: ban, kick, mute, tban, tmute")

    mode = message.command[1].lower()
    if mode not in ("ban", "kick", "mute", "tban", "tmute"):
        return await message.reply("❌ Invalid mode. Supported: ban, kick, mute, tban, tmute")

    time_arg = message.command[2] if len(message.command) > 2 else None
    if mode in ("tmute", "tban"):
        if not time_arg:
            return await message.reply("❌ You must provide a time for temporary actions (eg. 10m, 1h).")
        td = parse_time(time_arg)
        if not td:
            return await message.reply("❌ Invalid time format. Use: 30s, 10m, 1h, 1d")
        set_settings(message.chat.id, mode=mode, time=time_arg)
        return await message.reply(f"✅ Flood mode set to `{mode}` for `{time_arg}`.")
    else:
        set_settings(message.chat.id, mode=mode, time=None)
        return await message.reply(f"✅ Flood mode set to `{mode}`.")


@app.on_message(filters.command("admincache") & filters.group)
async def admincache_cmd(client: Client, message: Message):
    # we rely on get_chat_member each call so explicit cache is not needed,
    # but keep command for compatibility
    await message.reply("🔁 Admin cache refreshed (no persistent cache used).")


@app.on_message(filters.command("floodstats") & filters.group)
async def floodstats_cmd(client: Client, message: Message):
    st = get_stats(message.chat.id)
    txt = (
        "📊 Flood Punishment Stats\n\n"
        f"🚫 Bans: `{st['ban']}`\n"
        f"👢 Kicks: `{st['kick']}`\n"
        f"🔇 Mutes: `{st['mute']}`\n"
        f"⏱️ Temp Mutes: `{st['tmute']}`\n"
        f"⏱️ Temp Bans: `{st['tban']}`"
    )
    await message.reply(txt)


# ---------------- ANTIFLOOD DETECTION ----------------
# policy: count messages in a short window (e.g. 5 seconds).
WINDOW_SECONDS = 5

@app.on_message(filters.group & ~filters.service, group=5)
async def flood_check(client: Client, message: Message):
    # ignore service messages / deleted / anonymous
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    s = get_settings(chat_id)
    limit = s.get("limit")
    mode = s.get("mode")
    time_str = s.get("time")  # e.g. "10m"

    # if flood disabled
    if not limit:
        return

    now_ts = time.time()
    key = f"{chat_id}_{user_id}"
    # keep timestamps only in last WINDOW_SECONDS
    arr = cache.get(key, [])
    arr = [t for t in arr if now_ts - t < WINDOW_SECONDS]
    arr.append(now_ts)
    cache[key] = arr

    if len(arr) > limit:
        # before applying punishment, skip admins
        if await is_admin(client, chat_id, user_id):
            cache[key] = []
            return

        try:
            # Mute permissions object (no send rights)
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

            if mode == "ban":
                await client.ban_chat_member(chat_id=chat_id, user_id=user_id)
                update_stats(chat_id, "ban")
                await message.reply(f"🚫 {message.from_user.mention} banned for flooding!")
            elif mode == "kick":
                await client.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await client.unban_chat_member(chat_id=chat_id, user_id=user_id)
                update_stats(chat_id, "kick")
                await message.reply(f"👢 {message.from_user.mention} kicked for flooding!")
            elif mode == "mute":
                await client.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=mute_perms)
                update_stats(chat_id, "mute")
                await message.reply(f"🔇 {message.from_user.mention} muted for flooding!")
            elif mode == "tmute":
                td = parse_time(time_str)
                if not td:
                    # fallback: mute 10 minutes
                    td = timedelta(minutes=10)
                until = datetime.utcnow() + td
                await client.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=mute_perms, until_date=until)
                update_stats(chat_id, "tmute")
                await message.reply(f"🔇 {message.from_user.mention} temp-muted for `{time_str}`!")
            elif mode == "tban":
                td = parse_time(time_str)
                if not td:
                    td = timedelta(minutes=10)
                until = datetime.utcnow() + td
                await client.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until)
                update_stats(chat_id, "tban")
                await message.reply(f"🚫 {message.from_user.mention} temp-banned for `{time_str}`!")
        except Exception as e:
            # best-effort: report the exception to chat for admin debugging
            await message.reply(f"❌ Error applying flood punishment: {e}")

        # reset the user's message timestamps
        cache[key] = []
