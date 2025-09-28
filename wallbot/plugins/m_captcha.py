#!/usr/bin/env python3
"""
Captcha verification bot for Telegram groups (Pyrogram + MongoDB)

Features:
- On new member join, user is restricted (muted) and receives a captcha (math).
- User verifies by pressing the correct inline button. On success, user is unmuted.
- If user fails to verify within timeout -> permanently muted (long restrict).
- Admins can toggle captcha on/off and configure timeout/difficulty via inline UI.
- Uses MongoDB to store group settings and active captcha sessions.
"""

import os
import asyncio
import random
import time
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatPermissions,
)
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app
load_dotenv()

DB_NAME = "captcha_bot_db"


# --- MongoDB ---
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
settings_col = db["group_settings"]   # stores settings per chat: {chat_id, enabled, timeout, difficulty}
sessions_col = db["captcha_sessions"] # active sessions: {chat_id, user_id, answer_index, expires_at, solved, message_id, mode}

# --- Defaults ---
DEFAULT_TIMEOUT = 120        # seconds to solve captcha before permanent mute
PERMANENT_MUTE_SECONDS = 10 * 365 * 24 * 3600  # 10 years ~ 'forever'
DEFAULT_DIFFICULTY = "simple"  # "simple" or "hard"

# --- Utilities / helpers ---


async def ensure_group_settings(chat_id: int) -> Dict[str, Any]:
    """Get or create default settings for a chat."""
    doc = await settings_col.find_one({"chat_id": chat_id})
    if doc:
        return doc
    default = {"chat_id": chat_id, "enabled": True, "timeout": DEFAULT_TIMEOUT, "difficulty": DEFAULT_DIFFICULTY}
    await settings_col.insert_one(default)
    return default


async def set_group_setting(chat_id: int, key: str, value):
    await settings_col.update_one({"chat_id": chat_id}, {"$set": {key: value}}, upsert=True)


def generate_math_captcha(difficulty: str = "simple"):
    """
    Generate a math captcha and multiple choice options.
    simple: a + b (1-9)
    hard: a * b or a + b with larger numbers or mixed ops
    Returns: (question_text, options_list, answer_index)
    options are strings
    """
    if difficulty == "hard":
        # multiplication or combined ops
        op = random.choice(["*", "+", "-"])
        if op == "*":
            a = random.randint(2, 12)
            b = random.randint(2, 12)
            ans = a * b
            q = f"{a} × {b} = ?"
        elif op == "-":
            a = random.randint(10, 50)
            b = random.randint(1, 9)
            ans = a - b
            q = f"{a} − {b} = ?"
        else:
            a = random.randint(10, 99)
            b = random.randint(1, 99)
            ans = a + b
            q = f"{a} + {b} = ?"
    else:
        # simple addition
        a = random.randint(1, 9)
        b = random.randint(1, 9)
        ans = a + b
        q = f"{a} + {b} = ?"

    # create options
    options = {ans}
    while len(options) < 4:
        # propose distractors near the answer
        delta = random.choice([-3, -2, -1, 1, 2, 3, 4])
        fake = max(0, ans + delta)
        options.add(fake)
    options_list = list(options)
    random.shuffle(options_list)
    answer_index = options_list.index(ans)
    # stringify
    options_list = [str(x) for x in options_list]
    return q, options_list, answer_index


async def mute_member_temporarily(chat_id: int, user_id: int):
    """Mute (restrict) a user so they can't send messages until unmuted."""
    try:
        await app.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )
    except Exception as e:
        app.logger.warning(f"Could not mute user {user_id} in {chat_id}: {e}")


async def unmute_member(chat_id: int, user_id: int):
    """Restore send permissions for a user."""
    try:
        await app.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
    except Exception as e:
        app.logger.warning(f"Could not unmute user {user_id} in {chat_id}: {e}")


async def permamute_member(chat_id: int, user_id: int):
    """Permanently mute: restrict with a very long until_date."""
    try:
        await app.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
            until_date=int(time.time()) + PERMANENT_MUTE_SECONDS,
        )
    except Exception as e:
        app.logger.warning(f"Could not permamute user {user_id} in {chat_id}: {e}")


def build_captcha_markup(chat_id: int, user_id: int, session_id: str, options: list):
    """
    Build inline keyboard for captcha options.
    callback_data format: captcha|<session_id>|<chat_id>|<user_id>|<option_index>
    session_id is generated to ensure uniqueness among concurrent sessions.
    """
    rows = []
    for i, opt in enumerate(options):
        cb = f"captcha|{session_id}|{chat_id}|{user_id}|{i}"
        rows.append([InlineKeyboardButton(opt, callback_data=cb)])
    # add admin quick buttons
    rows.append(
        [
            InlineKeyboardButton("✅ Verified by Admin", callback_data=f"captcha_adminverify|{session_id}|{chat_id}|{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"captcha_cancel|{session_id}|{chat_id}|{user_id}"),
        ]
    )
    return InlineKeyboardMarkup(rows)


# --- Handlers ---

@app.on_message(filters.command("captcha_settings") & filters.group)
async def captcha_settings_cmd(_, message: Message):
    """Admin UI to show and toggle captcha settings for the chat."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    # check admin
    #await app.get_chat_member(chat_id: Union[int, str], user_id: int)
    member = await app.get_chat_member(chat_id=chat_id, user_id=user_id)
    if member.status not in ("administrator", "creator"):
        return await message.reply("🚫 Only group admins can change captcha settings.")

    settings = await ensure_group_settings(chat_id)
    enabled = settings.get("enabled", True)
    timeout = settings.get("timeout", DEFAULT_TIMEOUT)
    difficulty = settings.get("difficulty", DEFAULT_DIFFICULTY)

    text = (
        f"🛡️ Captcha Settings for this group\n\n"
        f"Status: {'✅ Enabled' if enabled else '❌ Disabled'}\n"
        f"Timeout: {timeout} seconds\n"
        f"Difficulty: {difficulty}\n\n"
        "Use the buttons below to change settings."
    )

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Toggle ON/OFF", callback_data=f"cfg_toggle|{chat_id}")],
            [InlineKeyboardButton("⏱ Timeout: " + str(timeout), callback_data=f"cfg_timeout|{chat_id}")],
            [InlineKeyboardButton("⚙️ Difficulty: " + difficulty, callback_data=f"cfg_difficulty|{chat_id}")],
            [InlineKeyboardButton("📊 Active sessions", callback_data=f"cfg_sessions|{chat_id}")],
        ]
    )
    await message.reply(text, reply_markup=kb)


@app.on_callback_query(filters.regex(r"^cfg_"))
async def cfg_callback(_, cq: CallbackQuery):
    """Handle configuration UI callbacks (admin-only)."""
    data = cq.data.split("|")
    cmd = data[0]  # e.g. cfg_toggle, cfg_timeout, cfg_difficulty, cfg_sessions
    chat_id = int(data[1])

    # ensure requester is admin in chat
    try:
        member = await app.get_chat_member(chat_id, cq.from_user.id)
    except Exception:
        return await cq.answer("Could not verify admin status.", show_alert=True)
    if member.status not in ("administrator", "creator"):
        return await cq.answer("🚫 Admins only.", show_alert=True)

    if cmd == "cfg_toggle":
        new = not (await ensure_group_settings(chat_id))["enabled"]
        await set_group_setting(chat_id, "enabled", new)
        await cq.answer(f"Module {'enabled' if new else 'disabled'}.", show_alert=True)
        await cq.message.edit_text(f"⚙️ Captcha module is now: {'✅ ON' if new else '❌ OFF'}")

    elif cmd == "cfg_timeout":
        # present quick options for timeout
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("30s", callback_data=f"cfg_settimeout|{chat_id}|30"),
                 InlineKeyboardButton("60s", callback_data=f"cfg_settimeout|{chat_id}|60")],
                [InlineKeyboardButton("120s", callback_data=f"cfg_settimeout|{chat_id}|120"),
                 InlineKeyboardButton("300s", callback_data=f"cfg_settimeout|{chat_id}|300")],
            ]
        )
        await cq.message.edit_text("Select timeout (seconds):", reply_markup=kb)

    elif cmd == "cfg_difficulty":
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("simple", callback_data=f"cfg_setdifficulty|{chat_id}|simple"),
                 InlineKeyboardButton("hard", callback_data=f"cfg_setdifficulty|{chat_id}|hard")]
            ]
        )
        await cq.message.edit_text("Select difficulty:", reply_markup=kb)

    elif cmd == "cfg_sessions":
        # list active sessions for this chat
        cursor = sessions_col.find({"chat_id": chat_id, "solved": False})
        lines = []
        async for s in cursor:
            uid = s["user_id"]
            expires = s.get("expires_at", 0)
            remaining = max(0, int(expires - time.time())) if expires else "N/A"
            lines.append(f"- user {uid} session expires in: {remaining}s")
        if not lines:
            await cq.answer("No active sessions.", show_alert=True)
            return await cq.message.edit_text("No active captcha sessions.")
        await cq.message.edit_text("Active sessions:\n\n" + "\n".join(lines))

    else:
        await cq.answer("Unknown cmd", show_alert=True)


@app.on_callback_query(filters.regex(r"^cfg_settimeout\|"))
async def cfg_settimeout_cb(_, cq: CallbackQuery):
    _, chat_id_s, timeout_s = cq.data.split("|")
    chat_id = int(chat_id_s)
    timeout = int(timeout_s)
    # admin check
    member = await app.get_chat_member(chat_id, cq.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await cq.answer("Admins only.", show_alert=True)
    await set_group_setting(chat_id, "timeout", timeout)
    await cq.answer(f"Timeout set to {timeout}s", show_alert=True)
    await cq.message.edit_text(f"Timeout updated: {timeout} seconds")


@app.on_callback_query(filters.regex(r"^cfg_setdifficulty\|"))
async def cfg_setdiff_cb(_, cq: CallbackQuery):
    _, chat_id_s, diff = cq.data.split("|")
    chat_id = int(chat_id_s)
    member = await app.get_chat_member(chat_id, cq.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await cq.answer("Admins only.", show_alert=True)
    if diff not in ("simple", "hard"):
        return await cq.answer("Invalid difficulty.", show_alert=True)
    await set_group_setting(chat_id, "difficulty", diff)
    await cq.answer(f"Difficulty set to {diff}", show_alert=True)
    await cq.message.edit_text(f"Difficulty updated: {diff}")


@app.on_message(filters.new_chat_members)
async def on_new_member(_, message: Message):
    """
    Handler when new members join the group.
    Mute them, create captcha session, send captcha message with inline buttons,
    and set a timeout task to permamute if not solved.
    """
    chat_id = message.chat.id
    settings = await ensure_group_settings(chat_id)
    if not settings.get("enabled", True):
        return

    timeout = settings.get("timeout", DEFAULT_TIMEOUT)
    difficulty = settings.get("difficulty", DEFAULT_DIFFICULTY)

    for user in message.new_chat_members:
        # skip bots
        if user.is_bot:
            continue

        # Ensure bot has permission to restrict
        try:
            bot_member = await app.get_chat_member(chat_id, (await app.get_me()).id)
            if not bot_member.can_restrict_members:
                await message.reply("⚠️ I need admin rights with permission to restrict members to run captcha.")
                return
        except Exception:
            pass

        # Mute the user immediately
        await mute_member_temporarily(chat_id, user.id)

        # Generate captcha
        q_text, options, ans_index = generate_math_captcha(difficulty)
        session_id = f"{chat_id}_{user.id}_{int(time.time())}_{random.randint(1000,9999)}"
        expires_at = time.time() + timeout

        # send captcha message (visible to all) with buttons
        captcha_msg = await message.reply(
            f"🛡️ Welcome {user.mention}!\nTo avoid spam/bots, please solve this captcha within {timeout} seconds:\n\n{q_text}",
            reply_markup=build_captcha_markup(chat_id, user.id, session_id, options),
        )

        # store session in DB
        await sessions_col.insert_one(
            {
                "session_id": session_id,
                "chat_id": chat_id,
                "user_id": user.id,
                "answer_index": int(ans_index),
                "options": options,
                "message_id": captcha_msg.message_id,
                "created_at": int(time.time()),
                "expires_at": int(expires_at),
                "solved": False,
                "mode": "math",
            }
        )

        # start timeout watcher
        asyncio.create_task(_captcha_timeout_watcher(session_id, chat_id, user.id, expires_at))


async def _captcha_timeout_watcher(session_id: str, chat_id: int, user_id: int, expires_at: float):
    """Background watcher: if not solved by expires_at, make permanent mute."""
    await asyncio.sleep(max(0, expires_at - time.time()))
    session = await sessions_col.find_one({"session_id": session_id})
    if not session:
        return
    if session.get("solved"):
        return
    # not solved -> permanent mute
    try:
        await permamute_member(chat_id, user_id)
    except Exception:
        pass
    # mark session as solved: false and expired
    await sessions_col.update_one({"session_id": session_id}, {"$set": {"solved": False, "expired": True}})
    # notify admins in chat
    try:
        await app.send_message(chat_id, f"🚨 {user_mention(user_id)} failed captcha and was muted permanently.")
    except Exception:
        pass


def user_mention(user_id: int) -> str:
    return f"[user](tg://user?id={user_id})"


@app.on_callback_query(filters.regex(r"^captcha\|"))
async def captcha_cb(_, cq: CallbackQuery):
    """
    Callback when a user presses a captcha option.
    callback_data format: captcha|<session_id>|<chat_id>|<user_id>|<option_index>
    Only the target user or admins can answer.
    """
    parts = cq.data.split("|")
    if len(parts) != 5:
        return await cq.answer("Invalid data", show_alert=True)

    _, session_id, chat_id_s, user_id_s, opt_index_s = parts
    chat_id = int(chat_id_s)
    user_id = int(user_id_s)
    opt_index = int(opt_index_s)
    actor = cq.from_user

    # load session
    session = await sessions_col.find_one({"session_id": session_id})
    if not session:
        return await cq.answer("This captcha is no longer active.", show_alert=True)

    # Only the targeted new user or admins can interact (admin buttons are separate; but keep check)
    if actor.id != user_id:
        # allow admins to press (they may verify)
        try:
            member = await app.get_chat_member(chat_id, actor.id)
            if member.status not in ("administrator", "creator"):
                return await cq.answer("This captcha isn't for you.", show_alert=True)
        except Exception:
            return await cq.answer("This captcha isn't for you.", show_alert=True)

    # check expiration
    if time.time() > session.get("expires_at", 0):
        return await cq.answer("Time expired.", show_alert=True)

    # check answer
    if opt_index == int(session["answer_index"]):
        # correct
        await sessions_col.update_one({"session_id": session_id}, {"$set": {"solved": True, "solved_by": actor.id, "solved_at": int(time.time())}})
        # unmute user
        try:
            await unmute_member(chat_id, user_id)
        except Exception:
            pass
        # edit captcha message to show success
        try:
            await cq.message.edit_text(f"✅ {user_mention(user_id)} passed the captcha (verified).")
        except Exception:
            pass
        await cq.answer("Correct! You are now unmuted.", show_alert=True)
    else:
        # wrong
        await cq.answer("❌ Wrong answer.", show_alert=True)
        # Optionally, you could reduce remaining attempts stored in session; here we keep full timeout.

@app.on_callback_query(filters.regex(r"^captcha_adminverify\|"))
async def captcha_admin_verify_cb(_, cq: CallbackQuery):
    """
    Admin: verify the user manually (unmute).
    Callback format: captcha_adminverify|<session_id>|<chat_id>|<user_id>
    """
    _, session_id, chat_id_s, user_id_s = cq.data.split("|")
    chat_id = int(chat_id_s)
    user_id = int(user_id_s)
    # verify admin
    try:
        member = await app.get_chat_member(chat_id, cq.from_user.id)
    except Exception:
        return await cq.answer("Could not verify admin status.", show_alert=True)
    if member.status not in ("administrator", "creator"):
        return await cq.answer("Admins only.", show_alert=True)

    # mark solved and unmute
    await sessions_col.update_one({"session_id": session_id}, {"$set": {"solved": True, "solved_by": cq.from_user.id, "solved_at": int(time.time())}})
    try:
        await unmute_member(chat_id, user_id)
    except Exception:
        pass
    try:
        await cq.message.edit_text(f"✅ {user_mention(user_id)} was verified by admin {cq.from_user.mention}.")
    except Exception:
        pass
    await cq.answer("User unmuted by admin.", show_alert=True)


@app.on_callback_query(filters.regex(r"^captcha_cancel\|"))
async def captcha_cancel_cb(_, cq: CallbackQuery):
    """
    Admin: cancel session (unmute or delete session).
    """
    _, session_id, chat_id_s, user_id_s = cq.data.split("|")
    chat_id = int(chat_id_s)
    user_id = int(user_id_s)
    # admin check
    try:
        member = await app.get_chat_member(chat_id, cq.from_user.id)
    except Exception:
        return await cq.answer("Could not verify admin status.", show_alert=True)
    if member.status not in ("administrator", "creator"):
        return await cq.answer("Admins only.", show_alert=True)

    # remove session and optionally unmute (or keep muted if admin wants)
    await sessions_col.delete_one({"session_id": session_id})
    try:
        await cq.message.edit_text(f"⚠️ Captcha for {user_mention(user_id)} canceled by admin.")
    except Exception:
        pass
    await cq.answer("Captcha canceled.", show_alert=True)


# --- Helper command to show active sessions in chat (admin) ---
@app.on_message(filters.command("captcha_sessions") & filters.group)
async def cmd_sessions(_, message: Message):
    chat_id = message.chat.id
    member = await app.get_chat_member(chat_id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.reply("🚫 Admins only.")
    cursor = sessions_col.find({"chat_id": chat_id, "solved": False})
    lines = []
    async for s in cursor:
        uid = s["user_id"]
        remaining = max(0, int(s.get("expires_at", 0) - time.time()))
        lines.append(f"- {user_mention(uid)} expires in {remaining}s (session {s['session_id']})")
    if not lines:
        await message.reply("No active captcha sessions.")
    else:
        await message.reply("Active sessions:\n" + "\n".join(lines))


