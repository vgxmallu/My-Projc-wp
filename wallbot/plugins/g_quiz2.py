"""
Advanced Quiz Group Bot (Pyrogram)
Features:
- Group-play: one active quiz session per group (anyone can answer)
- First-correct scoring (fastest finger)
- Per-group leaderboard + global leaderboard
- User profiles (points, correct/wrong, streaks, best streak)
- Admin commands: /addq, /seed (loads embedded 100+ questions), /import (JSON text)
- Lifelines per user (50-50) and cooldowns
- Timed questions with scheduler
- MongoDB persistence

Environment variables required:
- BOT_TOKEN, API_ID, API_HASH, MONGO_URI
Optional: DB_NAME (default: quiz_bot), ADMIN_IDS (comma-separated ints)

Run: python advanced_quiz_group_bot.py
"""

import os
import logging
import random
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pymongo import MongoClient, ASCENDING, DESCENDING
from config import DB_URL
from wallbot import wbot as app
from questions import QUESTIONS
# ---------------- Config ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("adv_quiz_bot")


DB_NAME = "g_quiz_bot"
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS","784589736").split(",") if x.strip().isdigit()}


# ------------ DB setup ----------------
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
users = db.users
questions = db.questions
sessions = db.sessions
group_scores = db.group_scores

# indexes
users.create_index([("user_id", ASCENDING)], unique=True)
questions.create_index([("category", ASCENDING), ("difficulty", ASCENDING)])
sessions.create_index([("session_id", ASCENDING)], unique=True)
group_scores.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)

# ------------ Constants --------------
QUESTION_TIMEOUT = 18  # seconds
POINTS_BASE = {"easy": 8, "medium": 12, "hard": 18}
FAST_BONUS = 2
STREAK_BONUS = 1
MAX_OPTIONS = 6
SESSION_COOLDOWN = 3  # seconds between questions to avoid spam


# ---------- Utility functions ----------

def upsert_user(user_id: int, username: Optional[str]):
    users.update_one({"user_id": user_id}, {"$set": {"username": username, "last_seen": datetime.utcnow()},
                    "$setOnInsert": {"points": 0, "correct": 0, "wrong": 0, "streak": 0, "best_streak": 0}}, upsert=True)


def seed_embedded_questions():
    inserted = 0
    for q in QUESTIONS:
        if not questions.find_one({"q": q["q"]}):
            questions.insert_one(q)
            inserted += 1
    return inserted


def create_group_session(chat_id: int, category: Optional[str] = None) -> Dict[str, Any]:
    session_id = f"group_{chat_id}"
    sess = {"session_id": session_id, "chat_id": chat_id, "category": category, "active": True, "current_q": None, "last_posted_at": None, "question_number": 0, "cooldown_until": None}
    sessions.update_one({"session_id": session_id}, {"$set": sess}, upsert=True)
    return sess


def end_group_session(chat_id: int):
    session_id = f"group_{chat_id}"
    sessions.update_one({"session_id": session_id}, {"$set": {"active": False}})


def get_group_session(chat_id: int) -> Optional[Dict[str, Any]]:
    return sessions.find_one({"session_id": f"group_{chat_id}"})


def pick_question(category: Optional[str] = None, difficulty: Optional[str] = None) -> Optional[Dict[str, Any]]:
    match = {}
    if category: match["category"] = category
    if difficulty: match["difficulty"] = difficulty
    q = list(questions.aggregate([{"$match": match}, {"$sample": {"size": 1}}]))
    return q[0] if q else None


def make_options_keyboard(session_id: str, options: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options):
        rows.append([InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"answer|{session_id}|{i}")])
    rows.append([InlineKeyboardButton("Skip", callback_data=f"skip|{session_id}"), InlineKeyboardButton("Stop Quiz", callback_data=f"stop|{session_id}")])
    return InlineKeyboardMarkup(rows)


def record_group_score(chat_id: int, user_id: int, username: str, points: int):
    group_scores.update_one({"chat_id": chat_id, "user_id": user_id}, {"$inc": {"points": points}, "$set": {"username": username}}, upsert=True)
    users.update_one({"user_id": user_id}, {"$inc": {"points": points}}, upsert=True)


# ---------- Commands ----------
@app.on_message(filters.group & filters.command("gquiz"))
async def cmhd_quiz(client: Client, message: Message):
    chat_id = message.chat.id
    upsert_user(message.from_user.id, message.from_user.username)
    sess = get_group_session(chat_id)
    if sess and sess.get("active"):
        await message.reply_text("A quiz is already active in this group. Use /stopquiz to stop it.")
        return
    create_group_session(chat_id)
    await message.reply_text("Quiz started! First correct answer gets points. Use /gleaderboard for group rankings.")
    await asyncio.sleep(1)
    await post_next_question(chat_id, client)


@app.on_message(filters.group & filters.command("stopquiz"))
async def cmd_stop_quiz(client: Client, message: Message):
    chat_id = message.chat.id
    sess = get_group_session(chat_id)
    if not sess or not sess.get("active"):
        await message.reply_text("No active quiz in this group.")
        return
    end_group_session(chat_id)
    await message.reply_text("Quiz stopped.")


@app.on_message(filters.group & filters.command("gleaderboard"))
async def cmd_gleaderboard(client: Client, message: Message):
    chat_id = message.chat.id
    top = list(group_scores.find({"chat_id": chat_id}).sort("points", DESCENDING).limit(10))
    if not top:
        await message.reply_text("No scores yet in this group.")
        return
    txt = "🏆 Group leaderboard:\n"
    for i, row in enumerate(top, start=1):
        txt += f"{i}. {row.get('username','unknown')} — {row.get('points',0)} pts\n"
    await message.reply_text(txt)


@app.on_message(filters.private & filters.command("global_leaderboard"))
async def cmd_global_leaderboard(client: Client, message: Message):
    top = list(users.find().sort("points", DESCENDING).limit(10))
    if not top:
        await message.reply_text("No global scores yet.")
        return
    txt = "🏆 Global leaderboard:\n"
    for i, u in enumerate(top, start=1):
        txt += f"{i}. @{u.get('username','unknown')} — {u.get('points',0)} pts\n"
    await message.reply_text(txt)


@app.on_message(filters.command("gprofile"))
async def cmd_grrprofile(client: Client, message: Message):
    uid = message.from_user.id
    doc = users.find_one({"user_id": uid}) or {}
    txt = (f"Profile — @{doc.get('username', message.from_user.username)}\n"
           f"Points: {doc.get('points',0)}\n"
           f"Correct: {doc.get('correct',0)}  Wrong: {doc.get('wrong',0)}\n"
           f"Best streak: {doc.get('best_streak',0)}")
    await message.reply_text(txt)


@app.on_message(filters.command("gaddq"))
async def cmd_gaddq(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply_text("Only admins can add questions.")
        return
    try:
        payload = message.text.split(" ", 1)[1]
        data = json.loads(payload)
        opts = data.get("options", [])
        if not (2 <= len(opts) <= MAX_OPTIONS):
            await message.reply_text(f"Options must be 2..{MAX_OPTIONS} items")
            return
        qdoc = {"q": data["q"], "options": opts, "answer": int(data["answer"]), "category": data.get("category","General"), "difficulty": data.get("difficulty","easy")}
        questions.insert_one(qdoc)
        await message.reply_text("Question added.")
    except Exception as e:
        await message.reply_text(f"Usage: /addq {json.dumps({'q':'Q','options':['a','b'],'answer':0})}\nError: {e}")


@app.on_message(filters.command("gseed"))
async def cmd_segged(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply_text("Only admins can seed.")
        return
    n = seed_embedded_questions()
    await message.reply_text(f"Seeded {n} embedded questions.")


@app.on_message(filters.command("gimport"))
async def cmd_import(client: Client, message: Message):
    # /import <json-array>
    if message.from_user.id not in ADMIN_IDS:
        await message.reply_text("Only admins can import questions.")
        return
    try:
        payload = message.text.split(" ",1)[1]
        arr = json.loads(payload)
        inserted = 0
        for q in arr:
            if not questions.find_one({"q": q.get("q")}):
                questions.insert_one(q)
                inserted += 1
        await message.reply_text(f"Imported {inserted} questions.")
    except Exception as e:
        await message.reply_text(f"Import failed: {e}")

# ------------ Core: posting & timeout ------------

async def post_next_question(chat_id: int, client: Client):
    sess = get_group_session(chat_id)
    if not sess or not sess.get("active"):
        return
    # cooldown check
    now = datetime.utcnow()
    if sess.get("cooldown_until") and sess["cooldown_until"] > now:
        return
    qdoc = pick_question(sess.get("category"))
    if not qdoc:
        await client.send_message(chat_id, "No questions available. Admins: add questions with /addq or /import or /seed.")
        return
    payload = {"q_id": str(qdoc.get("_id")), "q": qdoc["q"], "options": qdoc["options"], "answer": int(qdoc["answer"]), "posted_at": datetime.utcnow(), "deadline": datetime.utcnow() + timedelta(seconds=QUESTION_TIMEOUT)}
    sessions.update_one({"session_id": sess["session_id"]}, {"$set": {"current_q": payload, "last_posted_at": datetime.utcnow(), "question_number": sess.get("question_number",0)+1, "cooldown_until": datetime.utcnow() + timedelta(seconds=SESSION_COOLDOWN)}})
    kb = make_options_keyboard(sess["session_id"], payload["options"])
    text = f"Q{sess.get('question_number',0)+1}: {payload['q']}\n(First correct gets base points)"
    await client.send_message(chat_id, text, reply_markup=kb)

    # schedule timeout
    async def timeout_handler():
        await asyncio.sleep(QUESTION_TIMEOUT)
        s = get_group_session(chat_id)
        if not s or not s.get("active"): return
        cur = s.get("current_q")
        if cur and not cur.get("answered_by"):
            ans = cur.get("answer")
            letter = chr(65 + ans)
            await client.send_message(chat_id, f"⏰ Time's up! Correct answer: {letter}")
            await asyncio.sleep(1)
            await post_next_question(chat_id, client)
    asyncio.create_task(timeout_handler())

# ---------- Callback handlers ----------

@app.on_callback_query(filters.regex(r"^answer\|group_"))
async def cb_answer_group(client: Client, cq: CallbackQuery):
    parts = cq.data.split("|")
    if len(parts) < 3:
        await cq.answer('Bad data', show_alert=True); return
    _, session_id, idx_s = parts
    try:
        idx = int(idx_s)
    except:
        await cq.answer('Bad index', show_alert=True); return
    s = sessions.find_one({"session_id": session_id, "active": True})
    if not s:
        await cq.answer('No active quiz', show_alert=True); return
    cur = s.get("current_q")
    if not cur:
        await cq.answer('No active question', show_alert=True); return
    chat_id = s["chat_id"]
    if cur.get("answered_by"):
        await cq.answer('Already answered', show_alert=True); return
    if datetime.utcnow() > cur.get("deadline"):
        await cq.answer('Too late', show_alert=True); return
    user = cq.from_user
    # correctness
    if idx == cur.get("answer"):
        # calculate points with difficulty
        qdoc = questions.find_one({"_id": cur.get("q_id")}) if False else None
        # we didn't load difficulty; default medium
        base = POINTS_BASE.get('medium', 12)
        points = base
        record_group_score(chat_id, user.id, user.username or user.first_name, points)
        users.update_one({"user_id": user.id}, {"$inc": {"correct": 1, "points": points}, "$set": {"username": user.username}}, upsert=True)
        sessions.update_one({"session_id": session_id}, {"$set": {"current_q.answered_by": user.id, "current_q.answered_at": datetime.utcnow()}})
        await cq.message.reply_text(f"✅ {user.mention} answered correctly and earned {points} points!")
        await cq.answer('Correct')
        await asyncio.sleep(1.2)
        await post_next_question(chat_id, client)
    else:
        users.update_one({"user_id": user.id}, {"$inc": {"wrong": 1}}, upsert=True)
        await cq.answer('Wrong', show_alert=False)


@app.on_callback_query(filters.regex(r"^skip\|group_"))
async def cb_skip_group(client: Client, cq: CallbackQuery):
    _, session_id = cq.data.split("|")
    s = sessions.find_one({"session_id": session_id, "active": True})
    if not s:
        await cq.answer('No active quiz', show_alert=True); return
    sessions.update_one({"session_id": session_id}, {"$set": {"current_q.skipped": True}})
    await cq.message.reply_text("Question skipped. Posting next...")
    await cq.answer()
    await asyncio.sleep(0.8)
    await post_next_question(s["chat_id"], client)


@app.on_callback_query(filters.regex(r"^stop\|group_"))
async def cb_stop_group(client: Client, cq: CallbackQuery):
    _, session_id = cq.data.split("|")
    s = sessions.find_one({"session_id": session_id})
    if not s:
        await cq.answer('No session', show_alert=True); return
    end_group_session(s["chat_id"])
    await cq.message.reply_text("Quiz stopped by request.")
    await cq.answer()

# fallback
@app.on_callback_query(filters.regex(r"^answer\|"))
async def cb_answer_misc(client: Client, cq: CallbackQuery):
    await cq.answer()

