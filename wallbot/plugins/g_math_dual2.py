#!/usr/bin/env python3
"""
Math Duel Bot (Pyrogram + motor)

Features:
- /math (group) -> rapid quiz (first correct wins)
- /duel (reply in group) -> challenge member; accept -> duel (2 players only)
- /math (private) -> play vs bot
- MongoDB stores user stats
- /profile, /leaderboard, ranks
- Concurrency control & stale-game cleanup
- All CallbackQuery handlers use filters.regex
"""

import os
import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional

from dotenv import load_dotenv
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL, LOG_CHANNEL
from main import wbot as app
load_dotenv()

DB_NAME = os.getenv("DB_NAME", "math_duel_db")
CLEANUP_SECONDS = int(os.getenv("CLEANUP_SECONDS", "120"))
TOP_N = int(os.getenv("TOP_N", "10"))

mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]

# ---------- In-memory game state ----------
GROUP_GAMES: Dict[int, Dict[str, Any]] = {}     # chat_id -> game
DUEL_GAMES: Dict[int, Dict[str, Any]] = {}      # chat_id -> duel state
PRIVATE_GAMES: Dict[int, Dict[str, Any]] = {}   # user_id -> private game

GAME_LOCK = asyncio.Lock()

# ---------- Utilities ----------
def make_problem(difficulty: int = 1) -> Tuple[str, int]:
    """Create a safe math problem with integer answer."""
    if difficulty == 1:
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        op = random.choice(["+", "-"])
    elif difficulty == 2:
        a = random.randint(2, 50)
        b = random.randint(2, 12)
        op = random.choice(["*", "+", "-"])
    else:
        a = random.randint(2, 100)
        b = random.randint(2, 20)
        op = random.choice(["*", "+", "-", "/"])

    if op == "/":
        # ensure integer division
        divisor = random.randint(2, 12)
        quotient = random.randint(2, 12)
        a = divisor * quotient
        question = f"{a} ÷ {divisor}"
        answer = quotient
    else:
        question = f"{a} {op} {b}"
        answer = eval(question)
    return question, int(answer)

def mk_options(correct: int) -> Tuple[list, int]:
    opts = {correct}
    while len(opts) < 4:
        delta = random.randint(1, max(3, abs(correct)//4 + 1))
        candidate = correct + random.choice([-delta, delta])
        opts.add(candidate)
    opts = list(opts)
    random.shuffle(opts)
    return opts, opts.index(correct)

async def ensure_user(user_id: int, username: Optional[str]):
    u = await users_col.find_one({"user_id": user_id})
    if not u:
        doc = {
            "user_id": user_id,
            "username": username or "",
            "score": 0,
            "wins": 0,
            "losses": 0,
            "games_played": 0,
            "created_at": datetime.utcnow()
        }
        await users_col.insert_one(doc)
        return doc
    # update username if changed
    if username and u.get("username") != username:
        await users_col.update_one({"user_id": user_id}, {"$set": {"username": username}})
    return u

async def award_win(user_id: int, points: int = 10):
    await users_col.update_one({"user_id": user_id},
                               {"$inc": {"score": points, "wins": 1, "games_played": 1}}, upsert=True)

async def award_loss(user_id: int):
    await users_col.update_one({"user_id": user_id}, {"$inc": {"losses": 1, "games_played": 1}}, upsert=True)

def quiz_keyboard(options: list, ctx: str) -> InlineKeyboardMarkup:
    buttons = []
    for i, v in enumerate(options):
        buttons.append([InlineKeyboardButton(str(v), callback_data=f"ans|{ctx}|{i}")])
    return InlineKeyboardMarkup(buttons)

def duel_invite_kb(chat_id: int, opponent_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Accept", callback_data=f"duel_accept|{chat_id}|{opponent_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"duel_decline|{chat_id}|{opponent_id}")]
    ])

# ---------- Commands ----------#
#@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await ensure_user(m.from_user.id, m.from_user.username or m.from_user.first_name)
    await m.reply_text(
        "🧠 *Math Duel Bot*\n\n"
        "• `/math` in group — rapid quiz (first correct wins).\n"
        "• Reply to a user's message with `/duel` in group — challenge them.\n"
        "• `/math` in private — play vs bot.\n"
        "• `/profile` — view stats. `/leaderboard` — top players.",
        parse_mode=enums.ParseMode.MARKDOWN
    )

# /math in group: rapid quiz
@app.on_message(filters.command("math") & filters.group)
async def cmd_math_group(_, m: Message):
    chat_id = m.chat.id
    async with GAME_LOCK:
        if chat_id in GROUP_GAMES:
            return await m.reply_text("A math round is already active in this chat. Wait a moment.")
        q, ans = make_problem(difficulty=1)
        opts, correct_index = mk_options(ans)
        ctx = f"group#{chat_id}#{int(datetime.utcnow().timestamp())}"
        GAME = {
            "ctx": ctx,
            "question": q,
            "answer": ans,
            "opts": opts,
            "correct_index": correct_index,
            "created_at": datetime.utcnow(),
            "winner": None,
            "message_id": None,
            "chat_id": chat_id
        }
        GROUP_GAMES[chat_id] = GAME

    kb = quiz_keyboard(opts, ctx)
    text = f"⚔️ Rapid Math — First correct wins!\n\n🧮 {q} = ?\nTap the correct answer."
    sent = await m.reply_text(text, reply_markup=kb, parse_mode=enums.ParseMode.MARKDOWN)
    GROUP_GAMES[chat_id]["message_id"] = sent.message_id

# /math in private: vs bot
@app.on_message(filters.command("math") & filters.private)
async def cmd_math_private(_, m: Message):
    uid = m.from_user.id
    async with GAME_LOCK:
        if uid in PRIVATE_GAMES:
            return await m.reply_text("You already have an ongoing private round. Finish it first.")
        q, ans = make_problem(difficulty=1)
        opts, correct_index = mk_options(ans)
        ctx = f"private#{uid}#{int(datetime.utcnow().timestamp())}"
        PRIVATE_GAMES[uid] = {
            "ctx": ctx,
            "question": q,
            "answer": ans,
            "opts": opts,
            "correct_index": correct_index,
            "created_at": datetime.utcnow(),
            "message_id": None,
            "user_id": uid
        }
    kb = quiz_keyboard(opts, ctx)
    sent = await m.reply_text(f"🤖 Play vs Bot\n\n🧮 {q} = ?\nChoose:", reply_markup=kb, parse_mode=enums.ParseMode.MARKDOWN)
    PRIVATE_GAMES[uid]["message_id"] = sent.message_id

# /duel in group (reply to someone)
@app.on_message(filters.command("duel") & filters.group)
async def cmd_duel(_, m: Message):
    if not m.reply_to_message or not m.reply_to_message.from_user:
        return await m.reply_text("Reply to the member you want to challenge with /duel.")
    challenger = m.from_user
    opponent = m.reply_to_message.from_user
    chat_id = m.chat.id

    if challenger.id == opponent.id:
        return await m.reply_text("You cannot challenge yourself.")

    async with GAME_LOCK:
        if chat_id in DUEL_GAMES:
            return await m.reply_text("A duel is already pending/active in this chat.")
        # create pending duel
        DUEL_GAMES[chat_id] = {
            "chat_id": chat_id,
            "challenger": challenger.id,
            "opponent": opponent.id,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "ctx": None,
            "message_id": None
        }

    kb = duel_invite_kb(chat_id, opponent.id)
    await m.reply_text(f"🏁 {challenger.mention} challenged {opponent.mention} — {opponent.mention}, accept?", reply_markup=kb)

# ---------- CallbackQuery handlers using filters.regex ----------

# Answers (all games): ans|<ctx>|<index>
@app.on_callback_query(filters.regex(r"^ans\|"))
async def cb_answer(_, cq: CallbackQuery):
    data = cq.data  # format ans|<ctx>|<idx>
    try:
        _, ctx, idx_s = data.split("|", 2)
        idx = int(idx_s)
    except Exception:
        return await cq.answer("Invalid data", show_alert=True)

    # Group rapid
    # ctx form: group#<chat_id>#<ts>
    if ctx.startswith("group#"):
        parts = ctx.split("#", 2)
        chat_id = int(parts[1])
        game = GROUP_GAMES.get(chat_id)
        if not game:
            return await cq.answer("This round is no longer active.", show_alert=True)
        if game.get("winner"):
            return await cq.answer("Round already finished.", show_alert=True)
        # check answer
        if idx == game["correct_index"]:
            user = cq.from_user
            game["winner"] = user.id
            await ensure_user(user.id, user.username or user.first_name)
            await award_win(user.id, points=10)
            # announce and edit
            try:
                await app.edit_message_text(chat_id, game["message_id"],
                                            f"🏆 {user.mention} answered correctly!\n\n🧮 {game['question']} = {game['answer']}\nThey win 10 points!",
                                            parse_mode=enums.ParseMode.MARKDOWN)
            except Exception:
                pass
            await cq.answer("✅ Correct — you win!", show_alert=False)
            # schedule cleanup
            asyncio.create_task(async_cleanup(lambda: GROUP_GAMES.pop(chat_id, None), delay=5))
        else:
            await cq.answer("❌ Incorrect.", show_alert=False)
        return

    # Private games ctx: private#<user_id>#<ts>
    if ctx.startswith("private#"):
        parts = ctx.split("#", 2)
        uid = int(parts[1])
        game = PRIVATE_GAMES.get(uid)
        if not game:
            return await cq.answer("Game expired.", show_alert=True)
        # only the owner can answer
        if cq.from_user.id != uid:
            return await cq.answer("This is another user's private game.", show_alert=True)
        if idx == game["correct_index"]:
            await ensure_user(uid, cq.from_user.username or cq.from_user.first_name)
            await award_win(uid, points=10)
            try:
                await cq.message.edit_text(f"✅ Correct! You beat the bot.\n\n🧮 {game['question']} = {game['answer']}\nYou gained 10 points.", parse_mode=enums.ParseMode.MARKDOWN)
            except Exception:
                pass
        else:
            await award_loss(uid)
            try:
                await cq.message.edit_text(f"❌ Incorrect.\n\n🧮 {game['question']} = {game['answer']}\nBetter luck next time.", parse_mode=enums.ParseMode.MARKDOWN)
            except Exception:
                pass
        PRIVATE_GAMES.pop(uid, None)
        return

    # Duel active ctx: duel#<chat_id>#<ts>
    if ctx.startswith("duel#"):
        _, chatid_s, _ = ctx.split("#", 2)
        chat_id = int(chatid_s)
        duel = DUEL_GAMES.get(chat_id)
        if not duel or duel.get("status") != "active":
            return await cq.answer("Duel not active.", show_alert=True)
        # only challenger/opponent may answer
        uid = cq.from_user.id
        if uid not in (duel["challenger"], duel["opponent"]):
            return await cq.answer("Only duel participants may answer.", show_alert=True)
        if duel.get("winner"):
            return await cq.answer("Duel already finished.", show_alert=True)
        if idx == duel["correct_index"]:
            winner = uid
            loser = duel["opponent"] if uid == duel["challenger"] else duel["challenger"]
            duel["winner"] = winner
            duel["status"] = "finished"
            # DB updates
            await ensure_user(winner, (await app.get_users(winner)).username if True else "")
            await ensure_user(loser, (await app.get_users(loser)).username if True else "")
            await award_win(winner, points=30)
            await award_loss(loser)
            # announce
            try:
                win_user = await app.get_users(winner)
                await cq.message.edit_text(f"⚔️ Duel finished! {win_user.mention} answered correctly and wins 30 points!", parse_mode=enums.ParseMode.MARKDOWN)
            except Exception:
                pass
            await cq.answer("🏆 You won!", show_alert=False)
            asyncio.create_task(async_cleanup(lambda: DUEL_GAMES.pop(chat_id, None), delay=5))
        else:
            await cq.answer("❌ Incorrect.", show_alert=False)
        return

    # fallback
    await cq.answer()

# Duel accept (only challenged user) - pattern: duel_accept|<chat_id>|<opponent_id>
@app.on_callback_query(filters.regex(r"^duel_accept\|"))
async def cb_duel_accept(_, cq: CallbackQuery):
    data = cq.data
    try:
        _, chat_id_s, opponent_s = data.split("|", 2)
        chat_id = int(chat_id_s)
        expected_user = int(opponent_s)
    except:
        return await cq.answer("Invalid data", show_alert=True)

    # only the challenged user may press
    if cq.from_user.id != expected_user:
        return await cq.answer("Only the challenged user may accept.", show_alert=True)

    async with GAME_LOCK:
        duel = DUEL_GAMES.get(chat_id)
        if not duel or duel.get("status") != "pending":
            return await cq.answer("No duel to accept.", show_alert=True)
        # prepare duel round
        q, ans = make_problem(difficulty=2)
        opts, correct_index = mk_options(ans)
        ctx = f"duel#{chat_id}#{int(datetime.utcnow().timestamp())}"
        duel.update({
            "status": "active",
            "ctx": ctx,
            "question": q,
            "answer": ans,
            "opts": opts,
            "correct_index": correct_index,
            "created_at": datetime.utcnow(),
            "message_id": None,
            "winner": None
        })
        DUEL_GAMES[chat_id] = duel

    kb = quiz_keyboard(opts, ctx)
    # mention players
    ch = duel["challenger"]
    op = duel["opponent"]
    try:
        ch_u = await app.get_users(ch)
        op_u = await app.get_users(op)
        text = f"⚔️ Duel started!\n\n{ch_u.mention} vs {op_u.mention}\n\n🧮 {q} = ?\nOnly the two duelists may answer."
    except:
        text = f"⚔️ Duel started!\n\n🧮 {q} = ?\nOnly the two duelists may answer."

    sent = await cq.message.edit_text(text, reply_markup=kb)
    duel["message_id"] = sent.message_id
    DUEL_GAMES[chat_id] = duel
    await cq.answer("Duel started — good luck!", show_alert=False)

# Duel decline: duel_decline|<chat_id>|<opponent>
@app.on_callback_query(filters.regex(r"^duel_decline\|"))
async def cb_duel_decline(_, cq: CallbackQuery):
    data = cq.data
    try:
        _, chat_id_s, opponent_s = data.split("|", 2)
        chat_id = int(chat_id_s)
        expected_user = int(opponent_s)
    except:
        return await cq.answer("Invalid data", show_alert=True)

    if cq.from_user.id != expected_user:
        return await cq.answer("Only the challenged user may decline.", show_alert=True)

    async with GAME_LOCK:
        DUEL_GAMES.pop(chat_id, None)
    try:
        await cq.message.edit_text("❌ Duel declined.")
    except:
        pass
    await cq.answer("You declined the duel.", show_alert=False)

# Next button (optional) used by future flows: next|<ctx>
@app.on_callback_query(filters.regex(r"^next\|"))
async def cb_next(_, cq: CallbackQuery):
    # This bot currently serves new problems via /math or /duel accepts.
    await cq.answer("Use /math or /duel to start a new round.", show_alert=False)

# ---------- Cleanup helpers ----------
async def async_cleanup(func, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        func()
    except Exception:
        LOG.exception("Cleanup error")

async def stale_games_cleaner():
    LOG.info("Stale cleaner starting. CLEANUP_SECONDS=%s", CLEANUP_SECONDS)
    while True:
        await asyncio.sleep(max(10, CLEANUP_SECONDS // 3))
        try:
            now = datetime.utcnow()
            # groups
            to_remove = []
            for cid, g in list(GROUP_GAMES.items()):
                if (now - g.get("created_at", now)).total_seconds() > CLEANUP_SECONDS:
                    to_remove.append(cid)
                    try:
                        await app.edit_message_text(g["chat_id"], g["message_id"], "⚠️ Round timed out (no correct answers).")
                    except:
                        pass
            for cid in to_remove:
                GROUP_GAMES.pop(cid, None)
            # duels
            to_remove = []
            for cid, g in list(DUEL_GAMES.items()):
                if (now - g.get("created_at", now)).total_seconds() > CLEANUP_SECONDS:
                    to_remove.append(cid)
                    try:
                        if g.get("message_id"):
                            await app.edit_message_text(g["chat_id"], g["message_id"], "⚠️ Duel timed out.")
                    except:
                        pass
            for cid in to_remove:
                DUEL_GAMES.pop(cid, None)
            # privates
            to_remove = []
            for uid, g in list(PRIVATE_GAMES.items()):
                if (now - g.get("created_at", now)).total_seconds() > CLEANUP_SECONDS:
                    to_remove.append(uid)
            for uid in to_remove:
                PRIVATE_GAMES.pop(uid, None)
        except Exception:
            LOG.exception("Stale cleaner error")

# ---------- Profile & Leaderboard ----------
@app.on_message(filters.command("mathdprofile"))
async def cmd_mathddhprofile(_, m: Message):
    uid = m.from_user.id
    user = await users_col.find_one({"user_id": uid})
    if not user:
        await ensure_user(uid, m.from_user.username or m.from_user.first_name)
        user = await users_col.find_one({"user_id": uid})
    text = (
        f"👤 {m.from_user.mention}\n"
        f"⭐ Score: {user.get('score',0)}\n"
        f"🏆 Wins: {user.get('wins',0)}\n"
        f"💔 Losses: {user.get('losses',0)}\n"
        f"🎮 Games played: {user.get('games_played',0)}"
    )
    await m.reply_text(text, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("mathdleaderboard"))
async def cmd_leamathdderboard(_, m: Message):
    top = await users_col.find().sort("score", -1).limit(TOP_N).to_list(length=TOP_N)
    if not top:
        return await m.reply_text("No players yet.")
    lines = ["🏅 Leaderboard — Top players"]
    for i, u in enumerate(top, 1):
        uname = u.get("username") or str(u.get("user_id"))
        lines.append(f"{i}. {uname} — {u.get('score',0)} pts (wins: {u.get('wins',0)})")
    await m.reply_text("\n".join(lines), parse_mode=enums.ParseMode.MARKDOWN)

""""
# ---------- Startup / Shutdown ----------
@app.on_start()
async def on_start():
    # ensure index
    try:
        await users_col.create_index("user_id", unique=True)
    except Exception:
        pass
    LOG.info("Math Duel Bot started")
    # start stale cleaner
    asyncio.create_task(stale_games_cleaner())

@app.on_stop()
async def on_stop():
    LOG.info("Stopping Math Duel Bot...")

# ---------- Run ----------
if __name__ == "__main__":
    app.run()
"""
