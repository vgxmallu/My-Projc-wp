import os
import re
import traceback
from datetime import datetime, timedelta
from pymongo import MongoClient
from pyrogram import Client, filters, enums
from pyrogram.types import Message, ChatPermissions
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "mod_ban_db"

mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
punishments_coll = db["punishments"]  # moderation logs

# ---------------- HELPERS ----------------
TIME_RE = re.compile(r"^(\d+)([smhd])$")  # seconds/minutes/hours/days


def parse_time_expr(expr: str) -> timedelta | None:
    """Parse '30s', '10m', '1h', '2d' -> timedelta or None."""
    if not expr:
        return None
    m = TIME_RE.fullmatch(expr.lower())
    if not m:
        return None
    v = int(m.group(1))
    unit = m.group(2)
    if unit == "s":
        return timedelta(seconds=v)
    if unit == "m":
        return timedelta(minutes=v)
    if unit == "h":
        return timedelta(hours=v)
    if unit == "d":
        return timedelta(days=v)
    return None


async def is_admin_with_restrict(client: Client, chat_id: int, user_id: int) -> bool:
    """Return True if user is owner or admin with can_restrict_members."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status == enums.ChatMemberStatus.OWNER:
            return True
        if member.status == enums.ChatMemberStatus.ADMINISTRATOR:
            priv = getattr(member, "privileges", None)
            if priv and getattr(priv, "can_restrict_members", False):
                return True
    except Exception:
        pass
    return False


async def extract_user_from_message(client: Client, message: Message, expect_time=False):
    """
    Returns tuple (target_user, timedelta_or_None, error_message_or_None)
    - If expect_time True: tries to find a time token among args; returns (user, timedelta, err)
    - If expect_time False: returns (user, None, err)
    """
    # If reply, target is replied user
    if message.reply_to_message and message.reply_to_message.from_user:
        # If expect_time also, time could be in command args
        if expect_time and len(message.command) > 1:
            # command: /tban 10m  OR /tban @user 10m (but if reply, target already known)
            # find time token in args
            time_td = None
            for token in message.command[1:]:
                td = parse_time_expr(token)
                if td:
                    time_td = td
                    break
            return message.reply_to_message.from_user, time_td, None
        return message.reply_to_message.from_user, None, None

    args = message.command[1:]  # tokens after command
    if not args:
        return None, None, "❌ You must reply to a user or pass a username/user id."

    # If we expect time (tban/tmute), tokens may be in any order: find time token and user token
    if expect_time:
        time_td = None
        user_token = None
        for token in args:
            td = parse_time_expr(token)
            if td and not time_td:
                time_td = td
            else:
                # token might be username or id
                if user_token is None:
                    user_token = token
        # If user_token None -> user not provided; error
        if user_token is None:
            return None, None, "❌ You must provide target username/user_id (or reply) and time (e.g. 10m)."

        # attempt to fetch user
        try:
            user = await client.get_users(user_token)
            return user, time_td, None
        except Exception as e:
            return None, None, f"❌ Could not find user: {user_token}"
    else:
        # simply treat first arg as user
        token = args[0]
        try:
            user = await client.get_users(token)
            return user, None, None
        except Exception:
            return None, None, f"❌ Could not find user: {token}"


def log_action(chat_id: int, target_id: int, action: str, by_id: int | None = None, until: datetime | None = None):
    doc = {
        "chat_id": chat_id,
        "target_id": target_id,
        "action": action,
        "by_id": by_id,
        "until": until,
        "time": datetime.utcnow(),
    }
    punishments_coll.insert_one(doc)


def build_mute_permissions():
    """
    Build a ChatPermissions object that mutes sending messages.
    Use only safe parameters (compatible across Pyrogram versions).
    """
    # Choose a conservative set of send-related flags
    params = {}
    # fields we try to use; only include if supported by ChatPermissions signature
    preferred = [
        "can_send_messages",
        "can_send_media_messages",
        "can_send_polls",
        "can_send_other_messages",  # some versions may not support; we'll try to include, but if fail we handle below
        "can_add_web_page_previews",
        "can_send_photos",
        "can_send_videos",
        "can_send_documents",
        "can_send_voice_notes",
        "can_send_video_notes",
    ]
    # Create dict of False for available attributes by attempting to construct safely
    # Simpler: try constructing ChatPermissions with the full dict and fallback on a smaller set on exception
    try:
        kwargs = {k: False for k in preferred}
        return ChatPermissions(**kwargs)
    except Exception:
        # fallback smaller set
        safe_fields = ["can_send_messages", "can_send_media_messages", "can_send_polls", "can_add_web_page_previews"]
        kwargs = {k: False for k in safe_fields}
        return ChatPermissions(**kwargs)


def build_unmute_permissions():
    # Allow sending basic items; use conservative set
    try:
        kwargs = {
            "can_send_messages": True,
            "can_send_media_messages": True,
            "can_send_polls": True,
            "can_add_web_page_previews": True,
        }
        return ChatPermissions(**kwargs)
    except Exception:
        # If even this fails, return ChatPermissions() which is default (may not grant perms)
        return ChatPermissions(can_send_messages=True)


# ---------------- COMMANDS ----------------
@app.on_message(filters.command("kickme") & filters.group)
async def cmd_kickme(client: Client, message: Message):
    try:
        user = message.from_user
        await client.ban_chat_member(message.chat.id, user.id)
        # immediate unban to allow rejoin
        await client.unban_chat_member(message.chat.id, user.id)
        log_action(message.chat.id, user.id, "kickme", by_id=user.id)
        await message.reply_text("👋 You kicked yourself. Goodbye!")
    except Exception as e:
        await message.reply_text(f"❌ Failed to kick you: {e}")


# Generic admin-only decorator replacement: we'll check per-command with helper
async def require_admin_and_restrict(client: Client, message: Message) -> bool:
    if not message.from_user:
        await message.reply_text("❌ Cannot verify the user.")
        return False
    ok = await is_admin_with_restrict(client, message.chat.id, message.from_user.id)
    if not ok:
        await message.reply_text("⚠️ This command is for admins/creator with *restrict* permission only.")
    return ok


@app.on_message(filters.command(["ban", "sban"]) & filters.group)
async def cmd_ban(client: Client, message: Message):
    if not await require_admin_and_restrict(client, message):
        return
    silent = message.command[0].lower() == "sban"

    target, _, err = await extract_user_from_message(client, message, expect_time=False)
    if err:
        if not silent:
            await message.reply_text(err)
        return

    try:
        await client.ban_chat_member(message.chat.id, target.id)
        log_action(message.chat.id, target.id, "sban" if silent else "ban", by_id=message.from_user.id)
        if not silent:
            await message.reply_text(f"🚫 Banned {target.mention}")
        else:
            # attempt to delete command message silently
            try:
                await message.delete()
            except Exception:
                pass
    except Exception as e:
        await message.reply_text(f"❌ Error banning user: {e}")


@app.on_message(filters.command("tban") & filters.group)
async def cmd_tban(client: Client, message: Message):
    if not await require_admin_and_restrict(client, message):
        return

    # need both target and time; supports reply or args in any order
    target, td, err = await extract_user_from_message(client, message, expect_time=True)
    if err:
        await message.reply_text(err)
        return
    if not td:
        await message.reply_text("❌ Invalid or missing time. Use e.g. 10m, 1h, 2d")
        return

    until = datetime.utcnow() + td
    try:
        await client.ban_chat_member(message.chat.id, target.id, until_date=until)
        log_action(message.chat.id, target.id, "tban", by_id=message.from_user.id, until=until)
        await message.reply_text(f"🚫 Temporarily banned {target.mention} until {until.isoformat()}")
    except Exception as e:
        await message.reply_text(f"❌ Error temp-banning user: {e}")


@app.on_message(filters.command(["unban"]) & filters.group)
async def cmd_unban(client: Client, message: Message):
    if not await require_admin_and_restrict(client, message):
        return

    # target may be provided or replied, unban requires a user id or username
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    else:
        if len(message.command) < 2:
            return await message.reply_text("Usage: /unban <user_id|@username> or reply to user message")
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("❌ Could not find that user.")

    try:
        await client.unban_chat_member(message.chat.id, user.id)
        log_action(message.chat.id, user.id, "unban", by_id=message.from_user.id)
        await message.reply_text(f"✅ Unbanned {user.mention}")
    except Exception as e:
        await message.reply_text(f"❌ Error unbanning: {e}")


@app.on_message(filters.command(["kick", "skick"]) & filters.group)
async def cmd_kick(client: Client, message: Message):
    if not await require_admin_and_restrict(client, message):
        return
    silent = message.command[0].lower() == "skick"

    target, _, err = await extract_user_from_message(client, message, expect_time=False)
    if err:
        if not silent:
            await message.reply_text(err)
        return

    try:
        # ban then unban -> kick
        await client.ban_chat_member(message.chat.id, target.id)
        await client.unban_chat_member(message.chat.id, target.id)
        log_action(message.chat.id, target.id, "skick" if silent else "kick", by_id=message.from_user.id)
        if not silent:
            await message.reply_text(f"👢 Kicked {target.mention}")
        else:
            try:
                await message.delete()
            except Exception:
                pass
    except Exception as e:
        await message.reply_text(f"❌ Error kicking user: {e}")


@app.on_message(filters.command(["mute"]) & filters.group)
async def cmd_mute(client: Client, message: Message):
    if not await require_admin_and_restrict(client, message):
        return

    target, _, err = await extract_user_from_message(client, message, expect_time=False)
    if err:
        return await message.reply_text(err)

    try:
        mute_perms = build_mute_permissions()
        await client.restrict_chat_member(message.chat.id, target.id, permissions=mute_perms)
        log_action(message.chat.id, target.id, "mute", by_id=message.from_user.id)
        await message.reply_text(f"🔇 Muted {target.mention}")
    except Exception as e:
        tb = traceback.format_exc()
        await message.reply_text(f"❌ Error muting: {e}\n\n{tb}")


@app.on_message(filters.command("tmute") & filters.group)
async def cmd_tmute(client: Client, message: Message):
    if not await require_admin_and_restrict(client, message):
        return

    target, td, err = await extract_user_from_message(client, message, expect_time=True)
    if err:
        await message.reply_text(err)
        return
    if not td:
        await message.reply_text("❌ Invalid or missing time (e.g. 10m, 1h).")
        return

    until = datetime.utcnow() + td
    try:
        mute_perms = build_mute_permissions()
        await client.restrict_chat_member(message.chat.id, target.id, permissions=mute_perms, until_date=until)
        log_action(message.chat.id, target.id, "tmute", by_id=message.from_user.id, until=until)
        await message.reply_text(f"🔇 Temporarily muted {target.mention} until {until.isoformat()}")
    except Exception as e:
        await message.reply_text(f"❌ Error temp-muting user: {e}")


@app.on_message(filters.command(["unmute"]) & filters.group)
async def cmd_unmute(client: Client, message: Message):
    if not await require_admin_and_restrict(client, message):
        return

    # target via reply or argument
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    else:
        if len(message.command) < 2:
            return await message.reply_text("Usage: /unmute <user_id|@username> or reply to user message")
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("❌ Could not find that user.")

    try:
        unmute_perms = build_unmute_permissions()
        await client.restrict_chat_member(message.chat.id, user.id, permissions=unmute_perms)
        log_action(message.chat.id, user.id, "unmute", by_id=message.from_user.id)
        await message.reply_text(f"✅ Unmuted {user.mention}")
    except Exception as e:
        await message.reply_text(f"❌ Error unmuting: {e}")


# ----------------- Moderation stats -----------------
@app.on_message(filters.command("modstats") & filters.group)
async def cmd_modstats(client: Client, message: Message):
    chat_id = message.chat.id
    pipeline = [
        {"$match": {"chat_id": chat_id}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}}
    ]
    rows = list(punishments_coll.aggregate(pipeline))
    if not rows:
        return await message.reply_text("📊 No moderation actions logged in this group yet.")

    actions = {r["_id"]: r["count"] for r in rows}
    text = (
        f"📊 **Moderation Stats for** {message.chat.title or message.chat.id}\n\n"
        f"🚫 Bans: {actions.get('ban', 0) + actions.get('sban', 0) + actions.get('tban', 0)}\n"
        f"👢 Kicks: {actions.get('kick', 0) + actions.get('skick', 0)}\n"
        f"🔇 Mutes: {actions.get('mute', 0) + actions.get('tmute', 0)}\n"
        f"✅ Unbans: {actions.get('unban', 0)}\n"
        f"✅ Unmutes: {actions.get('unmute', 0)}\n"
    )
    await message.reply_text(text)


