import asyncio
import re
import time
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pymongo import MongoClient
from datetime import timedelta, datetime
from config import DB_URL
from wallbot import wbot as app

mongo = MongoClient(DB_URL)
db = mongo["antiflood_db"]
settings_col = db["settings"]
stats_col = db["stats"]
cache = {}  # flood tracking


# ──────────────────────
# HELPERS
# ──────────────────────
def parse_time(time_str: str):
    match = re.match(r"(\d+)([smhd])", time_str)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "s":
        return timedelta(seconds=value)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)


async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
            if getattr(member.privileges, "can_restrict_members", False) or member.status == enums.ChatMemberStatus.OWNER:
                return True
    except Exception:
        pass
    return False


def get_settings(chat_id: int):
    data = settings_col.find_one({"chat_id": chat_id})
    if not data:
        data = {"chat_id": chat_id, "limit": 5, "mode": "mute", "time": None}
        settings_col.insert_one(data)
    return data


# ──────────────────────
# COMMANDS
# ──────────────────────

def update_stats(chat_id: int, action: str):
    stats_col.update_one(
        {"chat_id": chat_id},
        {"$inc": {action: 1}},
        upsert=True
    )

def get_stats(chat_id: int):
    data = stats_col.find_one({"chat_id": chat_id}) or {}
    return {
        "ban": data.get("ban", 0),
        "kick": data.get("kick", 0),
        "mute": data.get("mute", 0),
        "tmute": data.get("tmute", 0),
        "tban": data.get("tban", 0),
    }

# ──────────────────────
# COMMAND: floodstats
# ──────────────────────
@app.on_message(filters.command("floodstats") & filters.group)
async def floodstats_cmd(client: Client, message: Message):
    stats = get_stats(message.chat.id)
    txt = (
        f"📊 **Flood Punishment Stats**\n\n"
        f"🚫 Bans: `{stats['ban']}`\n"
        f"👢 Kicks: `{stats['kick']}`\n"
        f"🔇 Mutes: `{stats['mute']}`\n"
        f"⏱️ Temp Mutes: `{stats['tmute']}`\n"
        f"⏱️ Temp Bans: `{stats['tban']}`"
    )
    await message.reply(txt)

@app.on_message(filters.command(["flood", "flood@"]))
async def flood_cmd(client: Client, message: Message):
    chat_id = message.chat.id
    settings = get_settings(chat_id)
    limit, mode, t = settings["limit"], settings["mode"], settings["time"]
    txt = f"🚨 **Flood Control Settings**\n\n⚙️ Limit: `{limit}`\n🔧 Mode: `{mode}`"
    if t:
        txt += f"\n⏱️ Duration: {t}"
    await message.reply(txt)


@app.on_message(filters.command("setflood") & filters.group)
async def setflood_cmd(client: Client, message: Message):
    chat_id, user_id = message.chat.id, message.from_user.id
    if not await is_admin(client, chat_id, user_id):
        return await message.reply("⚠️ Only admins with restrict rights can do this!")

    if len(message.command) < 2:
        return await message.reply("Usage: `/setflood [int|off]`")

    arg = message.command[1].lower()
    if arg == "off" or arg == "no":
        settings_col.update_one({"chat_id": chat_id}, {"$set": {"limit": None}}, upsert=True)
        return await message.reply("✅ Flood control disabled.")

    if arg.isdigit():
        limit = int(arg)
        settings_col.update_one({"chat_id": chat_id}, {"$set": {"limit": limit}}, upsert=True)
        return await message.reply(f"✅ Flood limit set to {limit} messages.")
    await message.reply("❌ Invalid input. Use an integer or `off`.")


@app.on_message(filters.command("floodmode") & filters.group)
async def floodmode_cmd(client: Client, message: Message):
    chat_id, user_id = message.chat.id, message.from_user.id
    if not await is_admin(client, chat_id, user_id):
        return await message.reply("⚠️ Only admins with restrict rights can do this!")

    if len(message.command) < 2:
        return await message.reply("Usage: `/floodmode [mode] [time]`\nModes: ban, kick, mute, tban, tmute")

    mode = message.command[1].lower()
    time_arg = message.command[2] if len(message.command) > 2 else None

    if mode not in ["ban", "kick", "mute", "tban", "tmute"]:
        return await message.reply("❌ Invalid mode! Use: ban, kick, mute, tban, tmute")

    duration = None
    if mode in ["tmute", "tban"]:
        if not time_arg:
            return await message.reply("❌ You must specify a time for temporary actions!")
        duration = parse_time(time_arg)
        if not duration:
            return await message.reply("❌ Invalid time format. Example: 10m, 2h")

    settings_col.update_one({"chat_id": chat_id}, {"$set": {"mode": mode, "time": time_arg}}, upsert=True)
    await message.reply(f"✅ Flood mode set to `{mode}` {f'for {time_arg}' if time_arg else ''}.")


@app.on_message(filters.command("admincache") & filters.group)
async def admincache_cmd(client: Client, message: Message):
    await message.reply("🔄 Admin cache refreshed (actually handled dynamically).")


# ──────────────────────
# ANTIFLOOD DETECTION
# ──────────────────────
@app.on_message(filters.group & ~filters.service)
async def flood_check(client: Client, message: Message):
    user_id, chat_id = message.from_user.id, message.chat.id
    settings = get_settings(chat_id)
    limit, mode, t = settings.get("limit"), settings.get("mode"), settings.get("time")

    if not limit:
        return  # flood control off

    now = time.time()
    user_key = f"{chat_id}_{user_id}"
    msgs = cache.get(user_key, [])
    msgs = [ts for ts in msgs if now - ts < 5]  # last 5 sec
    msgs.append(now)
    cache[user_key] = msgs

    if len(msgs) > limit:
        try:
            if mode == "ban":
                await client.ban_chat_member(chat_id, user_id)
                await message.reply(f"🚫 User {message.from_user.mention} banned for flooding!")
            elif mode == "kick":
                await client.ban_chat_member(chat_id, user_id)
                await client.unban_chat_member(chat_id, user_id)
                await message.reply(f"👢 User {message.from_user.mention} kicked for flooding!")
            elif mode == "mute":
                await client.restrict_chat_member(chat_id, user_id, enums.ChatPermissions())
                await message.reply(f"🔇 User {message.from_user.mention} muted for flooding!")
            elif mode == "tmute":
                duration = parse_time(t)
                until = datetime.utcnow() + duration
                await client.restrict_chat_member(chat_id, user_id, enums.ChatPermissions(), until_date=until)
                await message.reply(f"🔇 User {message.from_user.mention} muted for {t}!")
            elif mode == "tban":
                duration = parse_time(t)
                until = datetime.utcnow() + duration
                await client.ban_chat_member(chat_id, user_id, until_date=until)
                await message.reply(f"🚫 User {message.from_user.mention} banned for {t}!")
        except Exception as e:
            await message.reply(f"❌ Error applying flood punishment: {e}")

        cache[user_key] = []  # reset

