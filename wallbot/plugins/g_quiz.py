"""
Quiz Game Telegram Bot (Pyrogram)
Single-file implementation with MongoDB (pymongo), inline buttons only.

Features
- /start with quick actions
- User profiles (points, correct/incorrect, streaks)
- Leaderboard (top by points, weekly + all-time)
- Play quiz: choose Category + Difficulty, timed questions
- Inline-button only gameplay (A/B/C/D answers, Next/Skip/Quit)
- Lifeline: 50-50 (once per session) removes 2 wrong options
- Admin-only: /addq (add one question), /seed (load sample questions)
- Regex-based callback query handlers

Env vars required
- BOT_TOKEN
- API_ID
- API_HASH
- MONGO_URI
- DB_NAME (optional, default: quiz_bot)
- ADMIN_IDS (optional: comma-separated Telegram user IDs with admin power)

Run: python quiz_pyrogram_bot.py
"""

import os
import asyncio
import logging
import random
import time
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from config import DB_URL
from wallbot import wbot as app



logging.basicConfig(level=logging.INFO)
log = logging.getLogger("quizbot")

DB_NAME = "p_quiz_bot"
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "784589736").split(",") if x.strip().isdigit()}


# --------------------- DB ----------------------
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
users: Collection = db.users
questions: Collection = db.questions
sessions: Collection = db.sessions

# Indexes
users.create_index([("user_id", ASCENDING)], unique=True)
questions.create_index([("category", ASCENDING), ("difficulty", ASCENDING)])
sessions.create_index([("session_id", ASCENDING)], unique=True)
sessions.create_index([("user_id", ASCENDING), ("active", ASCENDING)])

# ------------------ Constants ------------------
DIFFICULTIES = ["easy", "medium", "hard"]
QUESTION_TIMEOUT_SECS = 25
SESSION_TIMEOUT_MINS = 30
POINTS_CORRECT = {"easy": 5, "medium": 10, "hard": 15}
POINTS_WRONG = 0
STREAK_BONUS = 2  # extra per consecutive correct after first
MAX_OPTIONS = 4

# ------------------ Helpers --------------------

def upsert_user(user_id: int, username: Optional[str]):
    users.update_one(
        {"user_id": user_id},
        {"$set": {"username": username, "last_seen": datetime.utcnow()},
         "$setOnInsert": {"points": 0, "correct": 0, "wrong": 0, "streak": 0, "best_streak": 0,
                           "weekly_points": 0, "weekly_reset": datetime.utcnow()}},
        upsert=True,
    )


def reset_weekly_if_needed(doc: Dict[str, Any]):
    if not doc:
        return
    wk = doc.get("weekly_reset")
    if not wk or (datetime.utcnow() - wk) > timedelta(days=7):
        users.update_one({"user_id": doc["user_id"]}, {"$set": {"weekly_points": 0, "weekly_reset": datetime.utcnow()}})


def ensure_categories() -> List[str]:
    return sorted(questions.distinct("category"))


def seed_examples() -> int:
    sample = [
        {
            "q": "What is the capital of France?",
            "options": ["Berlin", "Madrid", "Paris", "Rome"],
            "answer": 2,
            "category": "General Knowledge",
            "difficulty": "easy",
        },
        {
            "q": "2 + 2 * 2 = ?",
            "options": ["6", "8", "4", "2"],
            "answer": 0,
            "category": "Math",
            "difficulty": "easy",
        },
        {
            "q": "Who wrote '1984'?",
            "options": ["George Orwell", "Aldous Huxley", "Ray Bradbury", "J.K. Rowling"],
            "answer": 0,
            "category": "Literature",
            "difficulty": "medium",
        },
        {
            "q": "The chemical symbol for Gold is?",
            "options": ["Ag", "Au", "Gd", "Go"],
            "answer": 1,
            "category": "Science",
            "difficulty": "easy",
        },
        {
            "q": "In which year did the Apollo 11 land on the Moon?",
            "options": ["1965", "1969", "1971", "1973"],
            "answer": 1,
            "category": "History",
            "difficulty": "hard",
        },
    ]
    inserted = 0
    for s in sample:
        if not questions.find_one({"q": s["q"]}):
            questions.insert_one(s)
            inserted += 1
    return inserted


# -------------- Quiz Session Model --------------

def new_session_id() -> str:
    return os.urandom(6).hex()


def get_active_session(user_id: int) -> Optional[Dict[str, Any]]:
    return sessions.find_one({"user_id": user_id, "active": True})


def create_session(user_id: int, category: str, difficulty: str) -> Dict[str, Any]:
    sess = {
        "session_id": new_session_id(),
        "user_id": user_id,
        "category": category,
        "difficulty": difficulty,
        "active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "q_index": 0,
        "correct": 0,
        "wrong": 0,
        "score": 0,
        "lifeline_5050": True,
        "current": None,  # filled by load_next_question
    }
    sessions.insert_one(sess)
    return sess


def end_session(sess: Dict[str, Any]):
    sessions.update_one({"session_id": sess["session_id"]}, {"$set": {"active": False, "updated_at": datetime.utcnow()}})


def load_random_question(category: str, difficulty: str) -> Optional[Dict[str, Any]]:
    qlist = list(questions.aggregate([
        {"$match": {"category": category, "difficulty": difficulty}},
        {"$sample": {"size": 1}}
    ]))
    return qlist[0] if qlist else None


def load_next_question(sess: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    q = load_random_question(sess["category"], sess["difficulty"])
    if not q:
        return None
    cur = {
        "q_id": str(q.get("_id")),
        "q": q["q"],
        "options": q["options"],
        "answer": int(q["answer"]),
        "deadline": datetime.utcnow() + timedelta(seconds=QUESTION_TIMEOUT_SECS),
        "revealed": False,
        "5050_applied": False,
    }
    sessions.update_one({"session_id": sess["session_id"]}, {"$set": {"current": cur, "updated_at": datetime.utcnow(), "q_index": sess["q_index"] + 1}})
    sess["current"] = cur
    sess["q_index"] += 1
    return cur


# --------------- Rendering Helpers --------------

def title_line(sess: Dict[str, Any]) -> str:
    return (f"Quiz — {sess['category']} • {sess['difficulty'].title()}\n"
            f"Q{sess['q_index']}  |  Score: {sess['score']}  |  ✅ {sess['correct']} / ❌ {sess['wrong']}")


def question_markup(sess: Dict[str, Any], cur: Dict[str, Any]) -> InlineKeyboardMarkup:
    opts = cur["options"]
    buttons = []
    for i, text in enumerate(opts):
        buttons.append([InlineKeyboardButton(f"{chr(65+i)}. {text}", callback_data=f"answer|{sess['session_id']}|{i}")])
    controls = [
        InlineKeyboardButton("Skip", callback_data=f"skip|{sess['session_id']}"),
        InlineKeyboardButton("50-50", callback_data=f"lifeline|5050|{sess['session_id']}") if sess.get("lifeline_5050", False) and not cur.get("5050_applied") else InlineKeyboardButton("50-50 ✓", callback_data="noop") ,
        InlineKeyboardButton("Quit", callback_data=f"quit|{sess['session_id']}")
    ]
    buttons.append(controls)
    return InlineKeyboardMarkup(buttons)


def next_markup(sess: Dict[str, Any]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Next Question", callback_data=f"next|{sess['session_id']}")],
                                 [InlineKeyboardButton("Quit", callback_data=f"quit|{sess['session_id']}")]])



# ------------------- Commands -------------------
@app.on_message(filters.private & filters.command("p_startqz"))
async def starqzt_cmd(client: Client, m: Message):
    upsert_user(m.from_user.id, m.from_user.username)
    cats = ensure_categories()
    if not cats:
        cats = ["General Knowledge", "Science", "Math", "History", "Literature"]
    kb = [
        [InlineKeyboardButton("Play Quiz", callback_data="menu|play")],
        [InlineKeyboardButton("Profile", callback_data=f"profile|{m.from_user.id}"), InlineKeyboardButton("Leaderboard", callback_data="leaderboard|all")]
    ]
    await m.reply_text(
        "Welcome to Quiz Bot!\nChoose Play to start a session, or view your profile/leaderboard.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


@app.on_message(filters.private & filters.command(["p_qzprofile"]))
async def profile_cmd(client: Client, m: Message):
    doc = users.find_one({"user_id": m.from_user.id}) or {}
    reset_weekly_if_needed(doc)
    text = (f"Profile — @{m.from_user.username}\n"
            f"Points: {doc.get('points',0)} (Weekly: {doc.get('weekly_points',0)})\n"
            f"Correct: {doc.get('correct',0)}  Wrong: {doc.get('wrong',0)}\n"
            f"Current streak: {doc.get('streak',0)}  Best streak: {doc.get('best_streak',0)}")
    await m.reply_text(text)


@app.on_message(filters.private & filters.command(["p_qzleaderboard"]))
async def leaderboard_cmd(client: Client, m: Message):
    await send_leaderboard(m.chat.id, scope="all")


@app.on_message(filters.private & filters.command(["p_addq"]))
async def addq_cmd(client: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text("Only admins can add questions.")
        return
    try:
        # /addq {json}
        payload = m.text.split(" ", 1)[1]
        data = json.loads(payload)
        # required fields: q, options(list of 4), answer(index), category, difficulty
        if not (isinstance(data.get("options"), list) and 2 <= len(data["options"]) <= 6):
            await m.reply_text("Invalid options. Provide 2-6 options.")
            return
        data["answer"] = int(data["answer"])  # ensure index
        questions.insert_one({
            "q": data["q"],
            "options": data["options"],
            "answer": data["answer"],
            "category": data.get("category", "General Knowledge"),
            "difficulty": data.get("difficulty", "easy"),
        })
        await m.reply_text("Question added ✅")
    except Exception as e:
        await m.reply_text(f"Usage: /addq {{json}}\nExample: /addq {{\"q\":\"2+2?\", \"options\":[\"3\",\"4\"], \"answer\":1, \"category\":\"Math\", \"difficulty\":\"easy\"}}\nError: {e}")


@app.on_message(filters.private & filters.command(["p_seed"]))
async def seed_cmd(client: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text("Only admins can seed.")
        return
    n = seed_examples()
    await m.reply_text(f"Seeded {n} questions.")


# ----------------- Callback Menus ----------------
@app.on_callback_query(filters.regex(r"^menu\|play$"))
async def menu_play_cb(client: Client, cq: CallbackQuery):
    cats = ensure_categories() or ["General Knowledge", "Science", "Math", "History", "Literature"]
    rows = []
    for c in cats:
        rows.append([InlineKeyboardButton(c[:32], callback_data=f"choosecat|{c}")])
    rows.append([InlineKeyboardButton("Cancel", callback_data="noop")])
    await cq.message.reply_text("Choose a category:", reply_markup=InlineKeyboardMarkup(rows))
    await cq.answer()


@app.on_callback_query(filters.regex(r"^choosecat\|"))
async def choose_cat_cb(client: Client, cq: CallbackQuery):
    _, cat = cq.data.split("|", 1)
    rows = [[InlineKeyboardButton(d.title(), callback_data=f"choosediff|{cat}|{d}") for d in DIFFICULTIES],
            [InlineKeyboardButton("Cancel", callback_data="noop")]]
    await cq.message.reply_text(f"Category: {cat}\nPick difficulty:", reply_markup=InlineKeyboardMarkup(rows))
    await cq.answer()


@app.on_callback_query(filters.regex(r"^choosediff\|"))
async def choose_diff_cb(client: Client, cq: CallbackQuery):
    _, cat, diff = cq.data.split("|", 2)
    upsert_user(cq.from_user.id, cq.from_user.username)
    sess = get_active_session(cq.from_user.id)
    if sess:
        end_session(sess)
    sess = create_session(cq.from_user.id, cat, diff)
    cur = load_next_question(sess)
    if not cur:
        await cq.message.reply_text("No questions available for this selection. Ask an admin to /seed.")
        await cq.answer()
        return
    await cq.message.reply_text(
        title_line(sess) + f"\n\n{cur['q']}",
        reply_markup=question_markup(sess, cur)
    )
    await cq.answer("Quiz started!")


# ------------------ Gameplay Cbs ----------------
@app.on_callback_query(filters.regex(r"^answer\|"))
async def answer_cb(client: Client, cq: CallbackQuery):
    _, sid, idx_s = cq.data.split("|")
    idx = int(idx_s)
    sess = sessions.find_one({"session_id": sid, "active": True})
    if not sess:
        await cq.answer("Session ended.", show_alert=True)
        return
    if sess["user_id"] != cq.from_user.id:
        await cq.answer("Not your session.", show_alert=True)
        return
    cur = sess.get("current")
    if not cur:
        await cq.answer("No current question.")
        return
    # timeout check
    if datetime.utcnow() > cur["deadline"]:
        # mark wrong due to timeout
        sessions.update_one({"session_id": sid}, {"$set": {"current.revealed": True}})
        await cq.message.reply_text("⏰ Time's up!", reply_markup=next_markup(sess))
        await cq.answer()
        return

    correct_idx = int(cur["answer"])
    user_doc = users.find_one({"user_id": cq.from_user.id}) or {}
    reset_weekly_if_needed(user_doc)

    if idx == correct_idx:
        diff = sess["difficulty"]
        points = POINTS_CORRECT.get(diff, 10)
        # streak bonus
        streak = user_doc.get("streak", 0) + 1
        bonus = max(0, streak - 1) * STREAK_BONUS
        total_points = points + bonus
        users.update_one({"user_id": cq.from_user.id}, {
            "$inc": {
                "points": total_points,
                "weekly_points": total_points,
                "correct": 1,
            },
            "$set": {"streak": streak, "best_streak": max(streak, user_doc.get("best_streak", 0))}
        })
        sessions.update_one({"session_id": sid}, {"$inc": {"score": total_points, "correct": 1}, "$set": {"current.revealed": True}})
        await cq.message.reply_text(f"✅ Correct! +{total_points} points")
    else:
        users.update_one({"user_id": cq.from_user.id}, {"$inc": {"wrong": 1}, "$set": {"streak": 0}})
        sessions.update_one({"session_id": sid}, {"$inc": {"wrong": 1}, "$set": {"current.revealed": True}})
        correct_letter = chr(65 + correct_idx)
        await cq.message.reply_text(f"❌ Wrong. Correct answer: {correct_letter}")

    await cq.message.reply_text(title_line(sess), reply_markup=next_markup(sess))
    await cq.answer()


@app.on_callback_query(filters.regex(r"^next\|"))
async def next_cb(client: Client, cq: CallbackQuery):
    _, sid = cq.data.split("|")
    sess = sessions.find_one({"session_id": sid, "active": True})
    if not sess or sess["user_id"] != cq.from_user.id:
        await cq.answer("Session not found.", show_alert=True)
        return
    # session inactivity timeout
    if datetime.utcnow() - sess.get("updated_at", datetime.utcnow()) > timedelta(minutes=SESSION_TIMEOUT_MINS):
        end_session(sess)
        await cq.answer("Session expired.", show_alert=True)
        return
    cur = load_next_question(sess)
    if not cur:
        await cq.message.reply_text("No more questions available. Try another category/difficulty.")
        await cq.answer()
        return
    await cq.message.reply_text(title_line(sess) + f"\n\n{cur['q']}", reply_markup=question_markup(sess, cur))
    await cq.answer()


@app.on_callback_query(filters.regex(r"^lifeline\|5050\|"))
async def lifeline_5050_cb(client: Client, cq: CallbackQuery):
    _, _, sid = cq.data.split("|")
    sess = sessions.find_one({"session_id": sid, "active": True})
    if not sess or sess["user_id"] != cq.from_user.id:
        await cq.answer("Session not found.", show_alert=True)
        return
    cur = sess.get("current")
    if not cur or cur.get("5050_applied"):
        await cq.answer("Already used.", show_alert=True)
        return
    answer_idx = int(cur["answer"])
    opts = list(range(len(cur["options"])) )
    wrongs = [i for i in opts if i != answer_idx]
    remove = set(random.sample(wrongs, k=min(2, len(wrongs))))
    new_options = [o for i, o in enumerate(cur["options"]) if i == answer_idx or i not in remove]
    # remap answer index after removal
    new_answer_idx = [i for i, o in enumerate(new_options) if o == cur["options"][answer_idx]][0]
    cur["options"] = new_options
    cur["answer"] = new_answer_idx
    cur["5050_applied"] = True
    sessions.update_one({"session_id": sid}, {"$set": {"current": cur, "lifeline_5050": False, "updated_at": datetime.utcnow()}})
    await cq.message.reply_text("🎯 50-50 used! Two wrong options removed.")
    await cq.message.reply_text(title_line(sess) + f"\n\n{cur['q']}", reply_markup=question_markup(sess, cur))
    await cq.answer()


@app.on_callback_query(filters.regex(r"^skip\|"))
async def skip_cb(client: Client, cq: CallbackQuery):
    _, sid = cq.data.split("|")
    sess = sessions.find_one({"session_id": sid, "active": True})
    if not sess or sess["user_id"] != cq.from_user.id:
        await cq.answer("Session not found.", show_alert=True)
        return
    cur = load_next_question(sess)
    if not cur:
        await cq.message.reply_text("No more questions available.")
        await cq.answer()
        return
    await cq.message.reply_text(title_line(sess) + f"\n\n{cur['q']}", reply_markup=question_markup(sess, cur))
    await cq.answer("Skipped")


@app.on_callback_query(filters.regex(r"^quit\|"))
async def quit_cb(client: Client, cq: CallbackQuery):
    _, sid = cq.data.split("|")
    sess = sessions.find_one({"session_id": sid, "active": True})
    if not sess or sess["user_id"] != cq.from_user.id:
        await cq.answer("Session not found.", show_alert=True)
        return
    end_session(sess)
    await cq.message.reply_text("Session ended. Thanks for playing!")
    await cq.answer()


@app.on_callback_query(filters.regex(r"^leaderboard\|(all|weekly)$"))
async def leaderboard_cb(client: Client, cq: CallbackQuery):
    scope = cq.data.split("|")[1]
    if scope == "weekly":
        top = users.find().sort("weekly_points", DESCENDING).limit(10)
        header = "🏆 Weekly Leaderboard"
        button_swap = InlineKeyboardButton("All-time", callback_data="leaderboard|all")
    else:
        top = users.find().sort("points", DESCENDING).limit(10)
        header = "🏆 All-time Leaderboard"
        button_swap = InlineKeyboardButton("Weekly", callback_data="leaderboard|weekly")
    rows = [f"{i+1}. @{u.get('username','unknown')} — {u.get('weekly_points' if scope=='weekly' else 'points',0)}" for i, u in enumerate(top)]
    kb = InlineKeyboardMarkup([[button_swap]])
    await cq.message.reply_text(header + "\n" + ("\n".join(rows) if rows else "No players yet."), reply_markup=kb)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^profile\|"))
async def profile_cb(client: Client, cq: CallbackQuery):
    _, uid = cq.data.split("|")
    uid = int(uid)
    doc = users.find_one({"user_id": uid}) or {}
    reset_weekly_if_needed(doc)
    text = (f"Profile — @{doc.get('username','unknown')}\n"
            f"Points: {doc.get('points',0)} (Weekly: {doc.get('weekly_points',0)})\n"
            f"Correct: {doc.get('correct',0)}  Wrong: {doc.get('wrong',0)}\n"
            f"Current streak: {doc.get('streak',0)}  Best streak: {doc.get('best_streak',0)}")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Leaderboard", callback_data="leaderboard|all")]])
    await cq.message.reply_text(text, reply_markup=kb)
    await cq.answer()


@app.on_callback_query(filters.regex(r"^noop$"))
async def noop_cb(client: Client, cq: CallbackQuery):
    await cq.answer()


