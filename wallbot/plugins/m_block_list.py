#!/usr/bin/env python3
"""
Blocklists module for Telegram groups (Pyrogram + MongoDB)

Commands (admin only):
- /addblocklist <trigger> <reason>
- /rmblocklist <trigger>
- /unblocklistall               (chat creator only)
- /blocklist                    (list chat blocklist)
- /blocklistmode <mode>         (nothing/ban/mute/kick/warn/tban/tmute)
- /blocklistdelete <yes/no/on/off>
- /setblocklistreason <reason>
- /resetblocklistreason

Behavior:
- Monitors text, captions and filenames.
- When an item matches, takes configured action and (optionally) deletes message.
- Stores settings and blocklist items in MongoDB.
"""

import os
import re
import shlex
import time
import asyncio
from typing import Optional

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired

load_dotenv()
DB_NAME = "blocklist_db"


mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
settings_col = db["blocklist_settings"]     # { chat_id, enabled, delete_messages, mode, default_reason, tban_secs, tmute_secs }
items_col = db["blocklist_items"]           # { chat_id, trigger, reason, added_by, ts }

# ---------- Defaults ----------
DEFAULT_MODE = "warn"     # default action
DEFAULT_DELETE = True
DEFAULT_TBAN_SECS = 24 * 3600    # 1 day
DEFAULT_TMUTE_SECS = 3600        # 1 hour

# Valid modes
VALID_MODES = {"nothing", "warn", "kick", "ban", "mute", "tban", "tmute"}

# ---------- Helpers ----------
async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

async def is_creator(chat_id: int, user_id: int) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status == "creator"
    except Exception:
        return False

async def get_settings(chat_id: int) -> dict:
    s = await settings_col.find_one({"chat_id": chat_id})
    if s:
        return s
    default = {
        "chat_id": chat_id,
        "enabled": True,
        "delete_messages": DEFAULT_DELETE,
        "mode": DEFAULT_MODE,
        "default_reason": None,
        "tban_secs": DEFAULT_TBAN_SECS,
        "tmute_secs": DEFAULT_TMUTE_SECS,
    }
    await settings_col.insert_one(default)
    return default

async def update_settings(chat_id: int, patch: dict):
    await settings_col.update_one({"chat_id": chat_id}, {"$set": patch}, upsert=True)

async def add_block_item(chat_id: int, trigger: str, reason: Optional[str], added_by: int):
    doc = {"chat_id": chat_id, "trigger": trigger, "reason": reason or None, "added_by": added_by, "ts": int(time.time())}
    await items_col.insert_one(doc)
    return doc

async def remove_block_item(chat_id: int, trigger: str):
    res = await items_col.delete_one({"chat_id": chat_id, "trigger": trigger})
    return res.deleted_count

async def list_block_items(chat_id: int):
    cursor = items_col.find({"chat_id": chat_id})
    return await cursor.to_list(length=1000)

async def clear_block_items(chat_id: int):
    await items_col.delete_many({"chat_id": chat_id})

# matching logic
def trigger_is_phrase(trigger: str) -> bool:
    # if trigger contains spaces -> treat as phrase
    return " " in trigger.strip()

def trigger_is_extension(trigger: str) -> bool:
    return trigger.startswith(".")

def compile_word_regex(token: str):
    # produce a regex that matches word boundary for ASCII-ish words; for emojis substring match will be used
    # escape token for regex
    esc = re.escape(token)
    return re.compile(rf"\b{esc}\b", flags=re.IGNORECASE)

async def is_admin_with_permission(client: Client, chat_id: int, user_id: int, permission: str):
    """Check if a user is an admin with a specific permission."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            if permission == 'can_restrict_members':
                return member.privileges and member.privileges.can_restrict_members
        return False
    except UserNotParticipant:
        return False

# ---------- Commands (admin-only) ----------
@app.on_message(filters.command("addblocklist") & filters.group)
async def cmd_addblocklist(client, message: Message):
    # parse: trigger reason
    # allow quoted triggers using shlex.split
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    text = message.text or ""
    try:
        parts = shlex.split(text, posix=True)[1:]  # skip command
    except Exception:
        parts = text.split()[1:]

    if not parts:
        return await message.reply_text("Usage: /addblocklist [trigger] [reason optional]\nYou may quote triggers with spaces like: \n/addblocklist \"bad sentence\" reason here")

    trigger = parts[0]
    reason = " ".join(parts[1:]).strip() if len(parts) > 1 else None

    # store trigger as-is (case-insensitive matching later)
    existing = await items_col.find_one({"chat_id": message.chat.id, "trigger": trigger})
    if existing:
        return await message.reply_text("⚠️ This trigger is already blocklisted in this chat.")

    await add_block_item(message.chat.id, trigger, reason, message.from_user.id)
    await message.reply_text(f"✅ Added blocklist trigger: `{trigger}`\nReason: `{reason}`" if reason else f"✅ Added blocklist trigger: `{trigger}`")

@app.on_message(filters.command("rmblocklist") & filters.group)
async def cmd_rmblocklist(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    text = message.text or ""
    try:
        parts = shlex.split(text, posix=True)[1:]
    except Exception:
        parts = text.split()[1:]

    if not parts:
        return await message.reply_text("Usage: /rmblocklist [trigger]")

    trigger = parts[0]
    deleted = await remove_block_item(message.chat.id, trigger)
    if deleted:
        await message.reply_text(f"✅ Removed blocklist trigger: `{trigger}`")
    else:
        await message.reply_text(f"⚠️ No trigger `{trigger}` found in this chat.")

@app.on_message(filters.command("unblocklistall") & filters.group)
async def cmd_unblocklistall(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    await clear_block_items(message.chat.id)
    await message.reply_text("✅ All blocklist triggers have been removed for this chat.")

@app.on_message(filters.command("blocklist") & filters.group)
async def cmd_blocklist(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    items = await list_block_items(message.chat.id)
    if not items:
        return await message.reply_text("📭 No blocklist items in this chat.")
    lines = []
    for it in items:
        trig = it["trigger"]
        reason = it.get("reason") or "-"
        lines.append(f"`{trig}` — {reason}")
    text = "📜 Blocklist items:\n\n" + "\n".join(lines)
    await message.reply_text(text)

@app.on_message(filters.command("blocklistmode") & filters.group)
async def cmd_blocklistmode(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text(f"Usage: /blocklistmode <mode>\nValid modes: {', '.join(VALID_MODES)}")
    mode = parts[1].strip().lower()
    if mode not in VALID_MODES:
        return await message.reply_text(f"❌ Invalid mode. Valid: {', '.join(VALID_MODES)}")
    await update_settings(message.chat.id, {"mode": mode})
    await message.reply_text(f"✅ Blocklist mode set to `{mode}`")

@app.on_message(filters.command("blocklistdelete") & filters.group)
async def cmd_blocklistdelete(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /blocklistdelete <on|off|yes|no>")
    val = parts[1].strip().lower()
    enabled = val in ("on", "yes", "true", "1")
    await update_settings(message.chat.id, {"delete_messages": bool(enabled)})
    await message.reply_text(f"✅ Delete blocklisted messages set to `{enabled}`")

@app.on_message(filters.command("setblocklistreason") & filters.group)
async def cmd_setblocklistreason(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    reason = (message.text or "").split(maxsplit=1)
    if len(reason) < 2:
        return await message.reply_text("Usage: /setblocklistreason <reason text>")
    await update_settings(message.chat.id, {"default_reason": reason[1].strip()})
    await message.reply_text("✅ Default blocklist reason updated.")

@app.on_message(filters.command("resetblocklistreason") & filters.group)
async def cmd_resetblocklistreason(client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin_with_permission(client, chat_id, user_id, 'can_restrict_members'):
        await message.reply_text("👮‍♂️ You need to be an admin with 'Restrict Members' permission to use this command.")
        return
    await update_settings(message.chat.id, {"default_reason": None})
    await message.reply_text("✅ Default blocklist reason reset.")

# ---------- Moderation actions ----------
async def do_warn(chat_id: int, user_id: int, reason: Optional[str]):
    # simple warn (send a message)
    try:
        await app.send_message(chat_id, f"⚠️ [user](tg://user?id={user_id}) warned. Reason: {reason or 'blocklist'}", parse_mode="markdown")
    except Exception:
        pass

async def do_kick(chat_id: int, user_id: int):
    try:
        await app.ban_chat_member(chat_id, user_id)
        # unban immediately to simulate kick
        await asyncio.sleep(1)
        await app.unban_chat_member(chat_id, user_id)
    except Exception:
        pass

async def do_ban(chat_id: int, user_id: int):
    try:
        await app.ban_chat_member(chat_id, user_id)
    except Exception:
        pass

async def do_mute(chat_id: int, user_id: int, until_ts: Optional[int] = None):
    # restrict send permissions
    perms = {
        "can_send_messages": False,
        "can_send_media_messages": False,
        "can_send_other_messages": False,
        "can_add_web_page_previews": False,
    }
    try:
        await app.restrict_chat_member(chat_id, user_id, permissions=perms, until_date=until_ts)
    except Exception:
        pass

# ---------- Message checking ----------
async def check_message_for_block(chat_id: int, message: Message):
    settings = await get_settings(chat_id)
    if not settings.get("enabled", True):
        return False  # not processed

    # gather text sources to check: text, caption, file_name of document/audio/video, sticker emoji? etc.
    sources = []
    if message.text:
        sources.append(message.text)
    if message.caption:
        sources.append(message.caption)
    # filenames
    fname = None
    if message.document:
        fname = getattr(message.document, "file_name", None)
    elif message.audio:
        fname = getattr(message.audio, "file_name", None)
    elif message.video:
        fname = getattr(message.video, "file_name", None)
    elif message.voice:
        fname = getattr(message.voice, "file_name", None)
    if fname:
        sources.append(fname)
    # also check sticker emoji (stickers have emoji attribute)
    if message.sticker:
        emoji = getattr(message.sticker, "emoji", None)
        if emoji:
            sources.append(emoji)

    if not sources:
        return False

    # compile blocklist triggers for this chat
    items = await list_block_items(chat_id)
    if not items:
        return False

    text_combined = " \n ".join(sources)

    for it in items:
        trig = it["trigger"]
        trig_low = trig.lower()
        # extension match
        if trigger_is_extension(trig):
            # check filename endings
            if any(s and s.lower().endswith(trig_low) for s in sources if isinstance(s, str)):
                return it
            continue

        # phrase contains space -> substring search (case-insensitive)
        if trigger_is_phrase(trig):
            if trig_low in text_combined.lower():
                return it
            continue

        # token/word match (use word boundaries)
        # for emoji or non-word chars, word boundary may fail; fallback to substring
        try:
            regex = compile_word_regex(trig)
            if regex.search(text_combined):
                return it
        except re.error:
            # fallback substring
            if trig_low in text_combined.lower():
                return it

    return False

# ---------- Main message handler ----------
@app.on_message(filters.group, group=5)
async def on_message_handler(_, message: Message):
    if not message.from_user or message.sender_chat:
        return

    # only check if module enabled and there are items
    match = await check_message_for_block(message.chat.id, message)
    if not match:
        return

    # matched blocklist item
    trig = match["trigger"]
    item_reason = match.get("reason")
    settings = await get_settings(message.chat.id)
    reason = item_reason or settings.get("default_reason") or "Blocklist matched"

    # delete message if configured
    if settings.get("delete_messages", True):
        try:
            await message.delete()
        except Exception:
            pass

    mode = settings.get("mode", DEFAULT_MODE)
    uid = message.from_user.id
    cid = message.chat.id

    if mode == "nothing":
        # do nothing besides optional delete
        try:
            await app.send_message(cid, f"⚠️ Blocked `{trig}` from {message.from_user.mention}", parse_mode="markdown")
        except Exception:
            pass
        return

    if mode == "warn":
        await do_warn(cid, uid, reason)
        return

    if mode == "kick":
        await do_kick(cid, uid)
        return

    if mode == "ban":
        await do_ban(cid, uid)
        return

    if mode == "mute":
        await do_mute(cid, uid, None)
        return

    if mode == "tban":
        expires = int(time.time()) + settings.get("tban_secs", DEFAULT_TBAN_SECS)
        await do_ban(cid, uid)  # using ban with unban scheduled
        # schedule unban after duration (best-effort)
        async def lift_ban(chat_id, user_id, delay):
            await asyncio.sleep(delay)
            try:
                await app.unban_chat_member(chat_id, user_id)
            except Exception:
                pass
        asyncio.create_task(lift_ban(cid, uid, settings.get("tban_secs", DEFAULT_TBAN_SECS)))
        return

    if mode == "tmute":
        expires = int(time.time()) + settings.get("tmute_secs", DEFAULT_TMUTE_SECS)
        await do_mute(cid, uid, expires)
        return

