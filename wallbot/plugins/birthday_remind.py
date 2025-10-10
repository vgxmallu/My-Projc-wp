#!/usr/bin/env python3
"""
Birthday Reminder Bot (Pyrogram + MongoDB)

Features:
- /addbirthday [@user] YYYY-MM-DD  -> add birthday (if no mention, set for yourself)
- /rmbirthday [@user]              -> remove birthday
- /mybirthday                      -> show your birthday
- /listbirthdays                   -> list birthdays in this chat (or global)
- /subscribe                       -> subscribe this chat (private or group) to daily reminders (admins only in groups)
- /unsubscribe                     -> unsubscribe chat
- /profile [@user]                 -> show profile & wish stats
- /leaderboard                     -> top wishers (who sent wishes)
- When a birthday occurs, bot posts announcement with "🎉 Wish" button
- Users press /wish or tap button to mark they wished -> increments leaderboard
- All data stored in MongoDB
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from wallbot import wbot as app
from config import DB_URL


load_dotenv()

DB_NAME = os.getenv("DB_NAME", "birthday_bot_db")

# At which UTC hour the daily reminder routine runs (0-23)
REMINDER_HOUR_UTC = int(os.getenv("REMINDER_HOUR_UTC", "8"))
# background check interval (seconds)
TIMECHECK_INTERVAL = int(os.getenv("TIMECHECK_INTERVAL", "3600"))


mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
# lCollections
birthdays_col = db["birthdays"]           # { user_id, username, date: "YYYY-MM-DD", created_at }
subscriptions_col = db["subscriptions"]   # { chat_id, chat_title, enabled, created_at }
wishes_col = db["wishes"]                 # { user_id, username, wishes_count }
announcements_col = db["announcements"]   # optional: store today's announcements (for tracking)

# ---------- UTILITIES ----------
def parse_yyyy_mm_dd(text: str) -> Optional[datetime]:
    """Parse a date in YYYY-MM-DD and return a datetime.date (as datetime at midnight)."""
    try:
        parts = text.strip().split()
        date_str = parts[0]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

async def ensure_user_doc(user_id: int, username: Optional[str]):
    doc = await birthdays_col.find_one({"user_id": user_id})
    if not doc:
        # Do not create empty birthday doc by default; only when adding birthday.
        return None
    return doc

async def set_birthday(user_id: int, username: str, date_utc: datetime):
    """Store or update a user's birthday. date_utc is datetime at UTC midnight of their birthday date."""
    await birthdays_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "username": username, "date": date_utc.strftime("%Y-%m-%d"), "created_at": datetime.utcnow()}},
        upsert=True
    )

async def remove_birthday(user_id: int):
    res = await birthdays_col.delete_one({"user_id": user_id})
    return res.deleted_count > 0

async def get_birthday(user_id: int) -> Optional[Dict[str, Any]]:
    return await birthdays_col.find_one({"user_id": user_id})

async def list_birthdays(limit: int = 50) -> List[Dict[str, Any]]:
    cursor = birthdays_col.find().sort("date", 1).limit(limit)
    return await cursor.to_list(length=limit)

async def add_subscription(chat_id: int, chat_title: str):
    await subscriptions_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id, "chat_title": chat_title, "enabled": True, "created_at": datetime.utcnow()}},
        upsert=True
    )

async def remove_subscription(chat_id: int):
    res = await subscriptions_col.delete_one({"chat_id": chat_id})
    return res.deleted_count > 0

async def get_subscriptions() -> List[Dict[str, Any]]:
    cursor = subscriptions_col.find({"enabled": True})
    return await cursor.to_list(length=1000)

async def incr_wisher(user_id: int, username: str):
    await wishes_col.update_one(
        {"user_id": user_id},
        {"$set": {"username": username}, "$inc": {"wishes_count": 1}},
        upsert=True
    )

async def get_wisher(user_id: int) -> Optional[Dict[str, Any]]:
    return await wishes_col.find_one({"user_id": user_id})

async def top_wishers(limit: int = 10) -> List[Dict[str, Any]]:
    cursor = wishes_col.find().sort("wishes_count", -1).limit(limit)
    return await cursor.to_list(length=limit)

def announce_keyboard(user_id: int):
    # for announcements include a Wish button; callback: birthday_wish|<user_id>
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎉 Wish", callback_data=f"birthday_wish|{user_id}")],
        [InlineKeyboardButton("🔁 Remind me in 1 hour", callback_data=f"remind_me|{user_id}|60")]
    ])

# ---------- COMMAND HANDLERS ----------
@app.on_message(filters.command("brtstart") & filters.private)
async def cmd_sgftart(client: Client, message: Message):
    await message.reply_text(
        "🎂 *Birthday Reminder Bot*\n\n"
        "Commands:\n"
        "/addbirthday [@user] YYYY-MM-DD — add birthday (if no mention, set for yourself)\n"
        "/rmbirthday [@user] — remove birthday\n"
        "/mybirthday — show your birthday\n"
        "/listbirthdays — list stored birthdays\n"
        "/subscribe — subscribe this chat to daily reminders (in groups admin only)\n"
        "/unsubscribe — unsubscribe this chat\n"
        "/profile [@user] — show profile and wish stats\n"
        "/leaderboard — top wishers\n\n"
        "The bot sends daily reminders at the configured hour (UTC).",
        parse_mode="markdown"
    )

@app.on_message(filters.command("addbirthday"))
async def cmd_addbirthday(client: Client, message: Message):
    """
    Usage:
    /addbirthday YYYY-MM-DD            -> sets your birthday
    /addbirthday @username YYYY-MM-DD  -> sets birthday for mentioned user (admin only in group)
    """
    # identify target user and date string
    if len(message.command) < 2:
        return await message.reply_text("Usage: /addbirthday [@user] YYYY-MM-DD")

    # detect mention (reply to user or explicit mention)
    target_user = None
    date_token = None

    # If replied to user, prefer that
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        if len(message.command) >= 2:
            date_token = message.command[1]
    else:
        # check entities for mention or text_mention
        if message.entities:
            # look for mention or text_mention entity
            for ent in message.entities:
                if ent.type in ("text_mention", "mention"):
                    # for text_mention we have user directly; for mention we need username -> try to find user in chat
                    if ent.type == "text_mention":
                        target_user = ent.user
                        break
                    elif ent.type == "mention":
                        # entity text looks like @username
                        mention_text = message.text[ent.offset: ent.offset + ent.length]
                        try:
                            users = await client.get_users(mention_text)
                            target_user = users if hasattr(users, "id") else None
                            break
                        except Exception:
                            target_user = None
            # If a mention was present, date token probably next token
        # If first token after command looks like a username (starts with @)
        if not target_user:
            if len(message.command) >= 2 and message.command[1].startswith("@"):
                # attempt to resolve username
                uname = message.command[1]
                try:
                    u = await client.get_users(uname)
                    target_user = u
                    # date should be next token
                    if len(message.command) >= 3:
                        date_token = message.command[2]
                except Exception:
                    return await message.reply_text("Could not resolve that username. Use reply or exact username.")
            else:
                # no mention, date token is first arg, target is message.from_user
                target_user = message.from_user
                date_token = message.command[1]

    if not target_user:
        target_user = message.from_user

    if not date_token:
        return await message.reply_text("Please provide a date in format YYYY-MM-DD")

    date_parsed = parse_yyyy_mm_dd(date_token)
    if not date_parsed:
        return await message.reply_text("Invalid date format. Use YYYY-MM-DD (e.g. 1995-07-23).")

    # authorized to set birthday for others? if in group, require admin
    if target_user.id != message.from_user.id and message.chat.type != "private":
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply_text("Only group admins may set birthdays for other users.")

    # store date as UTC midnight (we only need month-day each year except for future schedule)
    date_utc_midnight = date_parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    username = target_user.username or (target_user.first_name or str(target_user.id))

    await set_birthday(target_user.id, username, date_utc_midnight)
    await message.reply_text(f"✅ Birthday set for {username} → `{date_utc_midnight.strftime('%Y-%m-%d')}`", parse_mode="markdown")

@app.on_message(filters.command("rmbirthday"))
async def cmd_rmbirthday(client: Client, message: Message):
    # Remove birthday for self or mentioned user
    target_user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    elif len(message.command) >= 2 and message.command[1].startswith("@"):
        try:
            target_user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("Could not resolve username.")
    else:
        target_user = message.from_user

    # authorization if removing other's birthday in group
    if target_user.id != message.from_user.id and message.chat.type != "private":
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply_text("Only group admins may remove birthdays of others.")

    ok = await remove_birthday(target_user.id)
    if ok:
        await message.reply_text(f"✅ Removed birthday for {target_user.first_name or target_user.username}.")
    else:
        await message.reply_text("No birthday found for that user.")

@app.on_message(filters.command("mybirthday"))
async def cmd_mybirthday(_, message: Message):
    doc = await get_birthday(message.from_user.id)
    if not doc:
        return await message.reply_text("You have not set your birthday. Use /addbirthday YYYY-MM-DD")
    await message.reply_text(f"🎂 Your birthday: `{doc['date']}`", parse_mode="markdown")

@app.on_message(filters.command("listbirthdays"))
async def cmd_listbirthdays(_, message: Message):
    docs = await list_birthdays(limit=100)
    if not docs:
        return await message.reply_text("No birthdays stored yet.")
    text_lines = ["🎂 *Stored Birthdays:*"]
    for d in docs:
        name = d.get("username") or d.get("user_id")
        date = d.get("date")
        text_lines.append(f"- {name}: `{date}`")
    await message.reply_text("\n".join(text_lines), parse_mode="markdown")

@app.on_message(filters.command("bsubscribe"))
async def cmd_subscribe(client: Client, message: Message):
    chat = message.chat
    if chat.type in ("group", "supergroup"):
        # require admin
        member = await client.get_chat_member(chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply_text("Only group admins can enable reminders in this chat.")
    title = chat.title or chat.first_name or str(chat.id)
    await add_subscription(chat.id, title)
    await message.reply_text(f"✅ This chat will receive birthday reminders at {REMINDER_HOUR_UTC:02d}:00 UTC daily.")

@app.on_message(filters.command("bunsubscribe"))
async def cmd_unsubscribe(client: Client, message: Message):
    chat = message.chat
    # require admin in groups
    if chat.type in ("group", "supergroup"):
        member = await client.get_chat_member(chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.reply_text("Only group admins can disable reminders in this chat.")
    ok = await remove_subscription(chat.id)
    if ok:
        await message.reply_text("✅ Unsubscribed from birthday reminders.")
    else:
        await message.reply_text("This chat was not subscribed.")

@app.on_message(filters.command("hbd_profile"))
async def cmd_prhbrofile(_, message: Message):
    # /profile or /profile @user
    target = message.from_user
    if len(message.command) >= 2 and message.command[1].startswith("@"):
        try:
            u = await app.get_users(message.command[1])  # may raise
            target = u
        except Exception:
            target = message.from_user

    b = await get_birthday(target.id)
    w = await get_wisher(target.id)
    lines = [f"👤 *{target.first_name or target.username}*"]
    if b:
        lines.append(f"🎂 Birthday: `{b['date']}`")
    else:
        lines.append("🎂 Birthday: not set")
    if w:
        lines.append(f"🎁 Wishes sent: {w.get('wishes_count',0)}")
    else:
        lines.append("🎁 Wishes sent: 0")
    await message.reply_text("\n".join(lines), parse_mode="markdown")

@app.on_message(filters.command("lhbdeaderboard"))
async def cmd_lejfaderboard(_, message: Message):
    top = await top_wishers(10)
    if not top:
        return await message.reply_text("No wishers yet.")
    lines = ["🏆 *Wish Leaderboard*"]
    for i, u in enumerate(top, 1):
        lines.append(f"{i}. {u.get('username','User')} — {u.get('wishes_count',0)} wishes")
    await message.reply_text("\n".join(lines), parse_mode="markdown")

# ---------- CALLBACKS (Wish button & remind me) ----------
@app.on_callback_query(filters.regex(r"^birthday_wish\|"))
async def cb_birthday_wish(client: Client, cq):
    # format: birthday_wish|<user_id>
    try:
        _, target_id_s = cq.data.split("|", 1)
        target_id = int(target_id_s)
    except:
        return await cq.answer("Invalid data", show_alert=True)

    # increment wisher for the person who clicked
    wisher = cq.from_user
    await incr_wisher(wisher.id, wisher.username or wisher.first_name or str(wisher.id))
    await cq.answer("🎉 You wished! Counted in leaderboard.", show_alert=False)
    try:
        await cq.message.reply_text(f"💬 {wisher.mention} wished a happy birthday to user {target_id}.")
    except:
        pass

@app.on_callback_query(filters.regex(r"^remind_me\|"))
async def cb_remind_me(client: Client, cq):
    # remind_me|<user_id>|<minutes>
    try:
        _, target_id_s, minutes_s = cq.data.split("|")
        minutes = int(minutes_s)
        target_id = int(target_id_s)
    except:
        return await cq.answer("Invalid data", show_alert=True)
    # schedule a one-off reminder to the clicking user in `minutes`
    reminder_time = datetime.utcnow() + timedelta(minutes=minutes)
    user_chat_id = cq.from_user.id
    asyncio.create_task(_delayed_personal_reminder(user_chat_id, target_id, minutes))
    await cq.answer(f"✅ I'll remind you in {minutes} minutes.", show_alert=True)

async def _delayed_personal_reminder(chat_id: int, target_user_id: int, minutes: int):
    await asyncio.sleep(minutes * 60)
    try:
        await app.send_message(chat_id, f"⏰ Reminder: Don't forget to wish the birthday person (id {target_user_id})!")
    except Exception:
        pass

# ---------- BACKGROUND REMINDER TASK ----------
async def birthday_check_loop():
    """
    Periodic loop that runs every TIMECHECK_INTERVAL seconds.
    It checks current UTC date and if hour >= REMINDER_HOUR_UTC and we haven't sent today's reminders, it:
      - Finds birthdays matching today's month/day
      - Sends announcement to all subscribed chats
    """
    logger.info("Birthday check loop started (utc hour %s)", REMINDER_HOUR_UTC)
    last_run_date = None

    while True:
        try:
            now = datetime.utcnow().replace(tzinfo=timezone.utc)
            today_ymd = now.strftime("%Y-%m-%d")
            # We only run once per day when hour >= REMINDER_HOUR_UTC
            if now.hour >= REMINDER_HOUR_UTC:
                if last_run_date != today_ymd:
                    # run today's announcements
                    logger.info("Running birthday announcements for %s", today_ymd)
                    # find birthdays with month-day matching today
                    all_birthdays = await birthdays_col.find().to_list(length=10000)
                    # collect matches
                    matches = []
                    for b in all_birthdays:
                        try:
                            b_date = datetime.strptime(b["date"], "%Y-%m-%d")
                            if (b_date.month, b_date.day) == (now.month, now.day):
                                matches.append(b)
                        except Exception:
                            continue

                    if matches:
                        subs = await get_subscriptions()
                        if not subs:
                            logger.info("No subscriptions registered; skipping sends.")
                        else:
                            # For each matched birthday, announce in all subscribed chats
                            for b in matches:
                                target_uid = b["user_id"]
                                target_name = b.get("username") or str(target_uid)
                                announce_text = f"🎉 *Birthday Alert!* 🎂\nIt's *{target_name}*'s birthday today ({b['date']})!\nSay hello and wish them a happy birthday!"
                                kb = announce_keyboard(target_uid)
                                for s in subs:
                                    chat_id = s["chat_id"]
                                    try:
                                        await app.send_message(chat_id, announce_text, parse_mode="markdown", reply_markup=kb)
                                    except Exception as e:
                                        logger.exception("Failed to send announcement to chat %s: %s", chat_id, e)
                                # Optionally record announcement in DB (for future reference)
                                try:
                                    await announcements_col.insert_one({"user_id": target_uid, "username": target_name, "date": today_ymd, "sent_at": datetime.utcnow()})
                                except Exception:
                                    pass

                    last_run_date = today_ymd
                else:
                    logger.debug("Already ran announcements for today (%s)", today_ymd)
            else:
                logger.debug("Current hour %s < REMINDER_HOUR_UTC %s: waiting", now.hour, REMINDER_HOUR_UTC)
        except Exception:
            logger.exception("Error in birthday_check_loop")
        await asyncio.sleep(TIMECHECK_INTERVAL)
