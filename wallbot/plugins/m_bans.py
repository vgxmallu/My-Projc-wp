import re
import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import ChatPermissions, Message
from pymongo import MongoClient
from config import DB_URL
from wallbot import wbot as app



mongo = MongoClient(DB_URL)
db = mongo["moderation_bot"]
punishments = db["punishments"]  # logs of bans/mutes etc.

# ──────────────────────────────
# HELPERS
# ──────────────────────────────
def parse_time(timestr: str):
    """
    Parse 5m, 2h, 3d into datetime.timedelta
    """
    unit = timestr[-1]
    value = int(timestr[:-1])
    if unit == "m":
        return datetime.timedelta(minutes=value)
    elif unit == "h":
        return datetime.timedelta(hours=value)
    elif unit == "d":
        return datetime.timedelta(days=value)
    else:
        raise ValueError("Invalid time format. Use m/h/d.")

async def get_target_user(msg: Message):
    """Extract target user from reply or command args"""
    if msg.reply_to_message:
        return msg.reply_to_message.from_user
    elif len(msg.command) > 1:
        return await app.get_users(msg.command[1])
    return None

async def is_admin(chat_id, user_id):
    member = await app.get_chat_member(chat_id, user_id)
    return member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]

def log_action(chat_id, user_id, action, until_date=None, by=None):
    punishments.insert_one({
        "chat_id": chat_id,
        "user_id": user_id,
        "action": action,
        "until_date": until_date,
        "by": by,
        "time": datetime.datetime.utcnow()
    })

mute_perms = ChatPermissions(can_send_messages=False)

# ──────────────────────────────
# COMMANDS
# ──────────────────────────────
@app.on_message(filters.group & filters.command("kickme"))
async def kickme(_, msg: Message):
    try:
        await msg.chat.kick_member(msg.from_user.id)
        await msg.chat.unban_member(msg.from_user.id)  # Allow rejoin
        await msg.reply("👋 You kicked yourself.")
    except Exception as e:
        await msg.reply(f"❌ Error: {e}")

@app.on_message(filters.group & filters.command(["ban", "sban", "tban", "unban", "kick", "skick", "mute", "tmute", "unmute"]))
async def btmoderation(_, msg: Message):
    chat_id = msg.chat.id
    user_id = msg.from_user.id

    # Admin check
    if not await is_admin(chat_id, user_id):
        return await msg.reply("⚠️ Only admins can use this command!")

    cmd = msg.command[0].lower()
    target = await get_target_user(msg)
    if not target and cmd not in ["unban", "unmute"]:
        return await msg.reply("Reply to a user or pass @username/user_id")

    silent = cmd.startswith("s")
    reason = " ".join(msg.command[2:]) if len(msg.command) > 2 else None

    try:
        if cmd == "ban" or cmd == "sban":
            await app.ban_chat_member(chat_id, target.id)
            log_action(chat_id, target.id, "ban", by=user_id)
            if not silent:
                await msg.reply(f"🚫 Banned {target.mention}")

        elif cmd == "tban":
            if len(msg.command) < 3:
                return await msg.reply("Usage: /tban @user 5m")
            until = datetime.datetime.utcnow() + parse_time(msg.command[2])
            await app.ban_chat_member(chat_id, target.id, until_date=until)
            log_action(chat_id, target.id, "tban", until, by=user_id)
            await msg.reply(f"🚫 Temporarily banned {target.mention} until {until}")

        elif cmd == "unban":
            user = await get_target_user(msg)
            if not user and len(msg.command) > 1:
                user = await app.get_users(msg.command[1])
            await app.unban_chat_member(chat_id, user.id)
            log_action(chat_id, user.id, "unban", by=user_id)
            await msg.reply(f"✅ Unbanned {user.mention}")

        elif cmd == "kick" or cmd == "skick":
            await app.ban_chat_member(chat_id, target.id)
            await app.unban_chat_member(chat_id, target.id)
            log_action(chat_id, target.id, "kick", by=user_id)
            if not silent:
                await msg.reply(f"👢 Kicked {target.mention}")

        elif cmd == "mute":
            await app.restrict_chat_member(chat_id, target.id, permissions=mute_perms)
            log_action(chat_id, target.id, "mute", by=user_id)
            await msg.reply(f"🔇 Muted {target.mention}")

        elif cmd == "tmute":
            if len(msg.command) < 3:
                return await msg.reply("Usage: /tmute @user 10m")
            until = datetime.datetime.utcnow() + parse_time(msg.command[2])
            await app.restrict_chat_member(chat_id, target.id, permissions=mute_perms, until_date=until)
            log_action(chat_id, target.id, "tmute", until, by=user_id)
            await msg.reply(f"🔇 Temporarily muted {target.mention} until {until}")

        elif cmd == "unmute":
            user = await get_target_user(msg)
            if not user and len(msg.command) > 1:
                user = await app.get_users(msg.command[1])
            await app.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=True))
            log_action(chat_id, user.id, "unmute", by=user_id)
            await msg.reply(f"✅ Unmuted {user.mention}")

    except Exception as e:
        await msg.reply(f"❌ Error: {e}")

# ──────────────────────────────
# MODERATION STATS COMMAND
# ──────────────────────────────
@app.on_message(filters.group & filters.command("modstats"))
async def modstats(_, msg: Message):
    chat_id = msg.chat.id

    # Count punishments in this group
    pipeline = [
        {"$match": {"chat_id": chat_id}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}}
    ]
    results = list(punishments.aggregate(pipeline))

    if not results:
        return await msg.reply("📊 No moderation actions logged yet in this group.")

    # Format stats
    actions = {r["_id"]: r["count"] for r in results}
    text = f"📊 **Moderation Stats for {msg.chat.title}**\n\n"
    text += f"🚫 Bans: {actions.get('ban', 0) + actions.get('sban', 0) + actions.get('tban', 0)}\n"
    text += f"👢 Kicks: {actions.get('kick', 0) + actions.get('skick', 0)}\n"
    text += f"🔇 Mutes: {actions.get('mute', 0) + actions.get('tmute', 0)}\n"
    text += f"✅ Unbans: {actions.get('unban', 0)}\n"
    text += f"✅ Unmutes: {actions.get('unmute', 0)}\n"

    await msg.reply(text)
