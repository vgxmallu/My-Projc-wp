#!/usr/bin/env python3
"""
Community Hero Bot — Advanced Community Stats + RPG System

Features:
- Tracks messages, words, media counts per user per chat
- XP system, ranks, achievements
- Leaderboards (daily, weekly, all-time) with inline UI
- Word cloud generation
- Weekly reset and champion announcement
- Admin commands to reset/enable/disable/export stats
- MongoDB persistence (motor)
"""

import os
import re
import io
import asyncio
import random
import datetime
from datetime import timezone, timedelta
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pyrogram import idle
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app

# Optional libs for visualization
try:
    import matplotlib.pyplot as plt
    from wordcloud import WordCloud
except Exception:
    WordCloud = None
    plt = None

load_dotenv()
DB_NAME = os.getenv("DB_NAME", "community_hero")
WEEKLY_RESET_WEEKDAY = int(os.getenv("WEEKLY_RESET_WEEKDAY", "6"))  # Sunday default
WEEKLY_RESET_HOUR_UTC = int(os.getenv("WEEKLY_RESET_HOUR_UTC", "0"))
DAILY_SUMMARY_HOUR_UTC = int(os.getenv("DAILY_SUMMARY_HOUR_UTC", "-1"))  # -1 to disable
TOP_N = int(os.getenv("TOP_N", "10"))


mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
# Collections
users_col = db["users"]           # { chat_id, user_id, username, xp, messages, words:[], media_counts{}, daily_xp, weekly_xp, achievements:[] }
chats_col = db["chats"]           # { chat_id, enabled, created_at }
meta_col = db["meta"]             # for tracking last weekly reset etc.

# ---------- XP / RANKS / ACHIEVEMENTS ----------
RANKS = [
    (0, "🥉 Bronze"),
    (500, "🥈 Silver"),
    (1500, "🥇 Gold"),
    (3500, "💎 Diamond"),
    (8000, "🔥 Legend"),
]

ACHIEVEMENTS = {
    "first_msg": {"name": "First Message", "desc": "Sent your first message", "xp": 10},
    "100_msgs": {"name": "Chatter", "desc": "Sent 100 messages", "xp": 100},
    "500_msgs": {"name": "Loyalist", "desc": "Sent 500 messages", "xp": 400},
    "weekly_champion": {"name": "Champion", "desc": "Won weekly leaderboard", "xp": 500},
}

# ---------- Helpers ----------
WORD_RE = re.compile(r"\b\w+\b", flags=re.UNICODE)

def get_rank_from_xp(xp: int) -> str:
    rank = RANKS[0][1]
    for threshold, name in RANKS:
        if xp >= threshold:
            rank = name
    return rank

def xp_progress_bar(xp: int) -> str:
    # show progress to next threshold
    thresholds = [t for t, _ in RANKS]
    next_threshold = None
    for t in thresholds:
        if xp < t:
            next_threshold = t
            break
    if next_threshold is None:
        return "█" * 10 + " MAX"
    fraction = xp / next_threshold
    filled = int(fraction * 10)
    return "█" * filled + "░" * (10 - filled) + f" {xp}/{next_threshold} XP"

async def ensure_chat_doc(chat_id: int):
    doc = await chats_col.find_one({"chat_id": chat_id})
    if not doc:
        doc = {"chat_id": chat_id, "enabled": True, "created_at": datetime.datetime.utcnow()}
        await chats_col.insert_one(doc)
    return doc

async def ensure_user(chat_id: int, user_id: int, username: str):
    u = await users_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if not u:
        u = {
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username or f"user{user_id}",
            "xp": 0,
            "messages": 0,
            "words": [],
            "media": {"photos": 0, "videos": 0, "voices": 0, "stickers": 0, "files": 0},
            "daily_xp": 0,
            "weekly_xp": 0,
            "achievements": [],
            "created_at": datetime.datetime.utcnow(),
            "last_active": datetime.datetime.utcnow(),
        }
        await users_col.insert_one(u)
    return u

# Achievements helper
async def grant_achievement(chat_id: int, user_id: int, key: str):
    ach = ACHIEVEMENTS.get(key)
    if not ach:
        return
    await users_col.update_one(
        {"chat_id": chat_id, "user_id": user_id, "achievements": {"$ne": key}},
        {"$push": {"achievements": key}, "$inc": {"xp": ach["xp"], "daily_xp": ach["xp"], "weekly_xp": ach["xp"]}}
    )

# Add XP and tally stats
async def add_activity(chat_id: int, user_id: int, username: str, text: Optional[str], media_type: Optional[str]=None):
    # ensure docs exist
    await ensure_chat_doc(chat_id)
    await ensure_user(chat_id, user_id, username)
    # compute XP: base + word_count + tiny random bonus (anti-spam: cap)
    word_count = len(WORD_RE.findall(text or "")) if text else 0
    base = 5
    xp_gain = base + min(word_count, 20)  # cap word reward
    # small random bonus to make it fun
    xp_gain += random.randint(0, 3)

    # anti-spam: if message very frequent? (not implemented heavy)
    await users_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {
            "$inc": {
                "xp": xp_gain,
                "messages": 1,
                "daily_xp": xp_gain,
                "weekly_xp": xp_gain,
            },
            "$set": {"username": username, "last_active": datetime.datetime.utcnow()},
            "$push": {"words": {"$each": WORD_RE.findall(text or "")}}
        },
        upsert=True
    )

    if media_type:
        field = f"media.{media_type}"
        await users_col.update_one({"chat_id": chat_id, "user_id": user_id}, {"$inc": {field: 1}})

    # achievements checks (simple)
    doc = await users_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if doc and doc.get("messages", 0) == 1:
        await grant_achievement(chat_id, user_id, "first_msg")
    if doc and doc.get("messages", 0) == 100:
        await grant_achievement(chat_id, user_id, "100_msgs")
    if doc and doc.get("messages", 0) == 500:
        await grant_achievement(chat_id, user_id, "500_msgs")

# ---------- Word cloud ----------
def generate_wordcloud_image(words: List[str]):
    if WordCloud is None or plt is None:
        raise RuntimeError("wordcloud/matplotlib not installed")
    if not words:
        raise RuntimeError("No words to generate cloud.")
    text = " ".join(words)
    wc = WordCloud(width=800, height=400, background_color="white").generate(text)
    buf = io.BytesIO()
    plt.figure(figsize=(12,6))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout(pad=0)
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf

# ---------- Leaderboards ----------
async def top_users(chat_id: int, period: str = "all", n: int = TOP_N):
    # period: 'daily' -> sort by daily_xp, 'weekly' -> weekly_xp, 'all' -> xp
    key = {"daily": "daily_xp", "weekly": "weekly_xp", "all": "xp"}.get(period, "xp")
    cursor = users_col.find({"chat_id": chat_id}).sort(key, -1).limit(n)
    return await cursor.to_list(length=n)

# ---------- Inline keyboards ----------
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 My Stats", callback_data="menu_mystats"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard")],
        [InlineKeyboardButton("☁️ Word Cloud", callback_data="menu_wordcloud"),
         InlineKeyboardButton("🛠 Admin", callback_data="menu_admin")],
    ])

def leaderboard_kb(chat_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Daily", callback_data=f"lb|{chat_id}|daily"),
         InlineKeyboardButton("Weekly", callback_data=f"lb|{chat_id}|weekly"),
         InlineKeyboardButton("All-time", callback_data=f"lb|{chat_id}|all")],
        [InlineKeyboardButton("Back", callback_data="menu_back")]
    ])

# ---------- Commands & Handlers ----------
@app.on_message(filters.command("yystart") & filters.private)
async def cmdgt_start(client: Client, message: Message):
    await message.reply_text(
        "👋 Community Hero Bot — gamify your group!\n\nUse /help to see available commands.",
        reply_markup=main_menu_kb()
    )

@app.on_message(filters.command("hettlp"))
async def cmd_ffhelp(_, m: Message):
    text = (
        "📘 *Community Hero Help*\n\n"
        "/mystats - show your stats (in group)\n"
        "/leaderboard - show leaderboard (in group)\n"
        "/wordcloud - create group word cloud\n"
        "/groupstats - group overview (admins)\n"
        "/resetstats - reset stats (admins)\n"
        "/enable_tracking / /disable_tracking - toggle tracking (admins)\n"
    )
    await m.reply_text(text)

@app.on_message(filters.group & ~filters.service)
async def on_message_track(_, message: Message):
    chat_id = message.chat.id
    # check chat enabled
    chat_doc = await chats_col.find_one({"chat_id": chat_id})
    if chat_doc and chat_doc.get("enabled") is False:
        return
    user = message.from_user
    if not user:
        return
    text = message.text or message.caption or ""
    media_type = None
    if message.photo:
        media_type = "photos"
    elif message.video:
        media_type = "videos"
    elif message.voice:
        media_type = "voices"
    elif message.sticker:
        media_type = "stickers"
    elif message.document:
        media_type = "files"
    await add_activity(chat_id, user.id, user.username or user.first_name or str(user.id), text, media_type)

# ---------- /mystats ----------
@app.on_message(filters.command("myg_stats") & filters.group)
async def cmd_mysrrtats(_, message: Message):
    chat_id = message.chat.id
    uid = message.from_user.id
    doc = await users_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not doc:
        return await message.reply_text("No stats yet for you in this chat. Start chatting to earn XP!")
    rank = get_rank_from_xp(doc["xp"])
    progress = xp_progress_bar(doc["xp"])
    achs = doc.get("achievements", [])
    text = (
        f"👤 {message.from_user.mention}\n\n"
        f"🏅 Rank: {rank}\n"
        f"⭐ XP: {doc['xp']}\n"
        f"📈 Progress: {progress}\n\n"
        f"💬 Messages: {doc.get('messages',0)}\n"
        f"🗣 Unique words: {len(set(doc.get('words',[])))}\n"
        f"🎖 Achievements: {', '.join([ACHIEVEMENTS[k]['name'] for k in achs]) if achs else 'None'}"
    )
    await message.reply_text(text, reply_markup=leaderboard_kb(chat_id))

# ---------- /leaderboard ----------
@app.on_message(filters.command("gwleaderboard") & filters.group)
async def cmtd_leaderboard(_, message: Message):
    chat_id = message.chat.id
    top = await top_users(chat_id, "weekly", TOP_N)
    if not top:
        return await message.reply_text("No players yet in this chat.")
    text = "🏆 Weekly Leaderboard\n\n"
    for i, u in enumerate(top, 1):
        text += f"{i}. {u.get('username','User')} — {u.get('weekly_xp',0)} XP\n"
    await message.reply_text(text, reply_markup=leaderboard_kb(chat_id))

# ---------- /wordcloud ----------
@app.on_message(filters.command("wordcloud") & filters.group)
async def cmd_wordcloud(_, message: Message):
    chat_id = message.chat.id
    # collect words
    cursor = users_col.find({"chat_id": chat_id})
    words = []
    async for u in cursor:
        words.extend(u.get("words", []))
    if not words:
        return await message.reply_text("No words recorded yet to create a word cloud.")
    try:
        buf = generate_wordcloud_image(words)
        await message.reply_photo(buf, caption="☁️ Group Word Cloud")
    except Exception as e:
        await message.reply_text(f"Error generating word cloud: {e}")

# ---------- /groupstats ----------
@app.on_message(filters.command("ggroupstats") & filters.group)
async def cmd_ffgroupstats(_, message: Message):
    # admin only
    member = await app.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.reply_text("Only group admins can view group stats.")
    chat_id = message.chat.id
    total_users = await users_col.count_documents({"chat_id": chat_id})
    total_msgs = 0
    total_xp = 0
    async for u in users_col.find({"chat_id": chat_id}):
        total_msgs += u.get("messages", 0)
        total_xp += u.get("xp", 0)
    text = (
        f"📊 Group Stats\n\n"
        f"👥 Tracked users: {total_users}\n"
        f"💬 Total messages: {total_msgs}\n"
        f"⭐ Total XP: {total_xp}\n"
    )
    await message.reply_text(text)

# ---------- Admin commands ----------
@app.on_message(filters.command("resetstats") & filters.group)
async def cmd_resetstats(_, message: Message):
    member = await app.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.reply_text("Only group admins can reset stats.")
    await users_col.delete_many({"chat_id": message.chat.id})
    await message.reply_text("✅ All stats reset for this chat.")

@app.on_message(filters.command("enable_tracking") & filters.group)
async def cmd_enable(_, message: Message):
    member = await app.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.reply_text("Only admins can enable tracking.")
    await chats_col.update_one({"chat_id": message.chat.id}, {"$set": {"enabled": True}}, upsert=True)
    await message.reply_text("✅ Tracking enabled for this chat.")

@app.on_message(filters.command("disable_tracking") & filters.group)
async def cmd_disable(_, message: Message):
    member = await app.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.reply_text("Only admins can disable tracking.")
    await chats_col.update_one({"chat_id": message.chat.id}, {"$set": {"enabled": False}}, upsert=True)
    await message.reply_text("⛔ Tracking disabled for this chat.")

# ---------- Callbacks for inline menu ----------
@app.on_callback_query(filters.regex(r"^menu_"))
async def cb_menu(_, cq: CallbackQuery):
    data = cq.data
    if data == "menu_mystats":
        # get chat and user; craft reply via similar to /mystats
        chat_id = cq.message.chat.id
        uid = cq.from_user.id
        doc = await users_col.find_one({"chat_id": chat_id, "user_id": uid})
        if not doc:
            return await cq.answer("No stats yet for you.", show_alert=True)
        txt = f"👤 {cq.from_user.mention}\n🏅 {get_rank_from_xp(doc['xp'])}\n⭐ XP: {doc['xp']}\nMessages: {doc.get('messages',0)}"
        return await cq.answer(txt, show_alert=True)
    if data == "menu_leaderboard":
        return await cq.message.reply_text("Use /leaderboard in group to view.")
    if data == "menu_wordcloud":
        return await cq.message.reply_text("Use /wordcloud to generate a word cloud.")
    if data == "menu_admin":
        return await cq.answer("Admin tools are via commands (/groupstats, /resetstats, /enable_tracking, /disable_tracking).", show_alert=True)
    if data == "menu_back":
        return await cq.message.edit_reply_markup(main_menu_kb())

@app.on_callback_query(filters.regex(r"^lb\|"))
async def cb_lb(_, cq: CallbackQuery):
    # format: lb|<chat_id>|<period>
    try:
        _, chat_id_s, period = cq.data.split("|", 2)
        chat_id = int(chat_id_s)
    except:
        return await cq.answer("Invalid", show_alert=True)
    top = await top_users(chat_id, period, TOP_N)
    if not top:
        return await cq.answer("No players yet.", show_alert=True)
    text = f"🏆 {period.title()} Leaderboard\n\n"
    for i, u in enumerate(top, 1):
        score_key = {"daily": "daily_xp", "weekly": "weekly_xp", "all": "xp"}[period]
        text += f"{i}. {u.get('username','User')} — {u.get(score_key,0)} XP\n"
    try:
        await cq.message.edit_text(text, reply_markup=leaderboard_kb(chat_id))
    except:
        await cq.answer(text, show_alert=True)

# ---------- Background tasks: weekly reset and daily summary ----------
async def weekly_reset_and_champion():
    """Runs continuously and performs weekly reset at configured weekday/hour (UTC)."""
    while True:
        now = datetime.datetime.utcnow()
        # compute next run time: find next occurrence of WEEKLY_RESET_WEEKDAY at hour WEEKLY_RESET_HOUR_UTC
        days_ahead = (WEEKLY_RESET_WEEKDAY - now.weekday()) % 7
        target = (now + timedelta(days=days_ahead)).replace(hour=WEEKLY_RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=7)
        wait = (target - now).total_seconds()
        await asyncio.sleep(wait + 1)  # sleep until then
        # For each chat, compute weekly champion and reset weekly_xp
        chats = await chats_col.find().to_list(length=None)
        for chat in chats:
            cid = chat["chat_id"]
            # find top weekly_xp
            top = await users_col.find({"chat_id": cid}).sort("weekly_xp", -1).limit(1).to_list(1)
            if top:
                champ = top[0]
                # award champion achievement / xp
                await grant_achievement(cid, champ["user_id"], "weekly_champion")
                # announce
                try:
                    await app.send_message(cid, f"🏆 Weekly Champion: @{champ.get('username','User')} — {champ.get('weekly_xp',0)} XP\nBonus awarded!")
                except Exception:
                    pass
            # reset weekly_xp
            await users_col.update_many({"chat_id": cid}, {"$set": {"weekly_xp": 0}})
        # small delay before next loop
        await asyncio.sleep(2)

async def daily_summary_task():
    """Optionally send a short daily summary to chats at DAILY_SUMMARY_HOUR_UTC (if enabled)."""
    if DAILY_SUMMARY_HOUR_UTC < 0:
        return
    while True:
        now = datetime.datetime.utcnow()
        # next run today at hour if not passed else tomorrow
        target = now.replace(hour=DAILY_SUMMARY_HOUR_UTC, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        await asyncio.sleep(wait + 1)
        chats = await chats_col.find({"enabled": True}).to_list(length=None)
        for chat in chats:
            cid = chat["chat_id"]
            # top today by daily_xp
            top = await users_col.find({"chat_id": cid}).sort("daily_xp", -1).limit(3).to_list(3)
            total_msgs = await users_col.count_documents({"chat_id": cid, "messages": {"$gte": 1}})
            if not top:
                continue
            text = "📅 Daily Summary\n\n"
            for i, u in enumerate(top, 1):
                text += f"{i}. @{u.get('username','User')} — {u.get('daily_xp',0)} XP\n"
            text += f"\nTracked users today: {total_msgs}"
            try:
                await app.send_message(cid, text)
            except Exception:
                pass
        # reset daily_xp
        for chat in chats:
            await users_col.update_many({"chat_id": chat["chat_id"]}, {"$set": {"daily_xp": 0}})
        await asyncio.sleep(2)

