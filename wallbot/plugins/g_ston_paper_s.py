#!/usr/bin/env python3
"""
Rock Paper Scissors Bot (Pyrogram + MongoDB)

Commands:
- /start
- /rps           -> play vs bot (or reply to someone to challenge them)
- /profile       -> show your profile
- /leaderboard   -> top players by XP

Author: Generated for you
"""

import os
import random
import asyncio
import secrets
from datetime import datetime
from typing import Dict, Any

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
)
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from main import wbot as app

load_dotenv()



# ---------- MongoDB ----------
mongo = AsyncIOMotorClient(DB_URL)
db = mongo["rps_db"]
users_col = db["users"]

# ---------- In-memory sessions ----------
# session_id -> {chat_id, type: 'bot'|'pvp', player1_id, player2_id (None if bot), moves: {uid: move}, message_id, created_at}
SESSIONS: Dict[str, Dict[str, Any]] = {}

# ---------- Game constants ----------
MOVES = ["🪨 Rock", "📄 Paper", "✂️ Scissors"]
MOVE_EMO = ["🪨", "📄", "✂️"]
WIN_MATRIX = {
    0: 2,  # rock beats scissors
    1: 0,  # paper beats rock
    2: 1,  # scissors beats paper
}

# XP awards
XP_WIN = 50
XP_TIE = 15
XP_LOSE = 5

# Rank thresholds (XP -> rank name); extend as desired
RANKS = [
    (0, "Novice"),
    (200, "Apprentice"),
    (500, "Warrior"),
    (1000, "Champion"),
    (2000, "Legend"),
    (4000, "Mythic"),
]


# ---------- Helpers: DB ----------
async def ensure_user(user_id: int, name: str):
    """Ensure a user doc exists and return it."""
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "name": name,
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "created_at": datetime.utcnow(),
        }
        await users_col.insert_one(user)
    return user


async def add_xp(user_id: int, xp: int):
    await users_col.update_one({"user_id": user_id}, {"$inc": {"xp": xp}})


async def add_result(user_id: int, win: int = 0, loss: int = 0, tie: int = 0):
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"wins": win, "losses": loss, "ties": tie}},
        upsert=True,
    )


async def get_profile(user_id: int):
    return await users_col.find_one({"user_id": user_id})


async def top_players(limit: int = 10):
    cursor = users_col.find().sort("xp", -1).limit(limit)
    return await cursor.to_list(length=limit)


def rank_from_xp(xp: int) -> str:
    cur = "Novice"
    for threshold, name in RANKS:
        if xp >= threshold:
            cur = name
    return cur


# ---------- UI helpers ----------
def moves_keyboard(session_id: str, allowed_user_id: int = None):
    """
    Build inline keyboard with 3 move buttons and a forfeit button.
    callback_data: rps|<session_id>|move|<move_index>|<user_id>
    forfeit callback_data: rps|<session_id>|forfeit|<user_id>
    """
    kb = [
        [
            InlineKeyboardButton(f"{MOVE_EMO[0]} Rock", callback_data=f"rps|{session_id}|move|0|{allowed_user_id}"),
            InlineKeyboardButton(f"{MOVE_EMO[1]} Paper", callback_data=f"rps|{session_id}|move|1|{allowed_user_id}"),
            InlineKeyboardButton(f"{MOVE_EMO[2]} Scissors", callback_data=f"rps|{session_id}|move|2|{allowed_user_id}"),
        ],
        [InlineKeyboardButton("🚪 Forfeit", callback_data=f"rps|{session_id}|forfeit|{allowed_user_id}")],
    ]
    return InlineKeyboardMarkup(kb)


# ---------- Game resolution ----------
def resolve_moves(m1: int, m2: int):
    """
    Return: 0 -> tie, 1 -> player1 wins, 2 -> player2 wins
    """
    if m1 == m2:
        return 0
    # if WIN_MATRIX[m1] == m2 -> player1 beats player2
    if WIN_MATRIX[m1] == m2:
        return 1
    return 2


# ---------- Commands ----------
@app.on_message(filters.command("rpsstart"))
async def cmjd_start(_, message: Message):
    user = message.from_user
    await ensure_user(user.id, user.first_name or user.username or str(user.id))
    await message.reply_text(
        "🎮 Welcome to *Path of RPS*!\n\n"
        "Commands:\n"
        "/rps — play Rock-Paper-Scissors (reply to a user to challenge them)\n"
        "/profile — show your stats\n"
        "/leaderboard — show top players\n\n"
        "Tap the inline buttons to play. Enjoy!",
    )


@app.on_message(filters.command("rpsprofile"))
async def cmrpsd_profile(_, message: Message):
    user = message.from_user
    await ensure_user(user.id, user.first_name or user.username or str(user.id))
    profile = await get_profile(user.id)
    xp = profile.get("xp", 0)
    name = profile.get("name", user.first_name or user.username or str(user.id))
    wins = profile.get("wins", 0)
    losses = profile.get("losses", 0)
    ties = profile.get("ties", 0)
    rank = rank_from_xp(xp)
    await message.reply_text(
        f"👤 {name}\n"
        f"🏅 Rank: {rank}\n"
        f"✨ XP: {xp}\n"
        f"🏆 Wins: {wins} | ❌ Losses: {losses} | ➖ Ties: {ties}"
    )


@app.on_message(filters.command("rpsleaderboard"))
async def cmdrps_leaderboard(_, message: Message):
    top = await top_players(10)
    if not top:
        return await message.reply_text("No players yet — be the first to play!")
    text = "🏆 Top Players (by XP):\n\n"
    for i, p in enumerate(top, start=1):
        text += f"{i}. {p.get('name','User')} — XP {p.get('xp',0)} | Wins {p.get('wins',0)}\n"
    await message.reply_text(text)


@app.on_message(filters.command("rps") & filters.group)
async def cmdj_rps_group(_, message: Message):
    """
    /rps in a group:
    - If replied to a user -> challenge that user (advanced PvP)
    - Otherwise -> play vs bot (simple)
    """
    challenger = message.from_user
    await ensure_user(challenger.id, challenger.first_name or challenger.username or str(challenger.id))

    # If reply_to_message -> challenge that user
    if message.reply_to_message and message.reply_to_message.from_user:
        opponent = message.reply_to_message.from_user
        if opponent.id == challenger.id:
            return await message.reply_text("You can't challenge yourself — try /rps without replying to play vs the bot.")
        await ensure_user(opponent.id, opponent.first_name or opponent.username or str(opponent.id))

        # create PvP session
        sid = secrets.token_hex(8)
        sess = {
            "session_id": sid,
            "chat_id": message.chat.id,
            "type": "pvp",
            "player1_id": challenger.id,
            "player2_id": opponent.id,
            "moves": {},  # uid -> move_index
            "message_id": None,
            "created_at": datetime.utcnow(),
        }
        SESSIONS[sid] = sess

        invite_text = (
            f"⚔️ *RPS Challenge!*\n\n"
            f"{challenger.mention} challenged {opponent.mention} to Rock-Paper-Scissors!\n\n"
            f"Both players: press your move below. First to choose is fine; when both choose, result shows."
        )

        reply = await message.reply_text(invite_text, reply_markup=moves_keyboard(sid, challenger.id))
        # Edit message to show opponent's allowed id in buttons? We'll allow both, but validate in callback.
        sess["message_id"] = reply.message_id
        # For opponent convenience, also send buttons that are valid for them by editing keyboard with their id in callback_data
        # Send second message tagging opponent with keyboard targeted to them
        await message.reply_text(f"{opponent.mention}, it's your turn — press a move:", reply_markup=moves_keyboard(sid, opponent.id))

        # Set a timeout: if not finished in 120s, cancel
        asyncio.create_task(_session_timeout_watcher(sid, timeout=120))
        return

    # Otherwise play vs bot (simple)
    sid = secrets.token_hex(8)
    sess = {
        "session_id": sid,
        "chat_id": message.chat.id,
        "type": "bot",
        "player1_id": challenger.id,
        "player2_id": None,
        "moves": {},
        "message_id": None,
        "created_at": datetime.utcnow(),
    }
    SESSIONS[sid] = sess
    invite_text = (
        f"🎮 *RPS vs Bot*\n\n"
        f"{challenger.mention}, choose your move vs me!"
    )
    reply = await message.reply_text(invite_text, reply_markup=moves_keyboard(sid, challenger.id))
    sess["message_id"] = reply.message_id
    asyncio.create_task(_session_timeout_watcher(sid, timeout=60))


# Also allow playing in private chats (vs bot)
@app.on_message(filters.command("rps") & filters.private)
async def cmdb_rps_private(_, message: Message):
    challenger = message.from_user
    await ensure_user(challenger.id, challenger.first_name or challenger.username or str(challenger.id))
    sid = secrets.token_hex(8)
    sess = {
        "session_id": sid,
        "chat_id": message.chat.id,
        "type": "bot",
        "player1_id": challenger.id,
        "player2_id": None,
        "moves": {},
        "message_id": None,
        "created_at": datetime.utcnow(),
    }
    SESSIONS[sid] = sess
    reply = await message.reply_text("🎮 Choose your move vs the Bot:", reply_markup=moves_keyboard(sid, challenger.id))
    sess["message_id"] = reply.message_id
    asyncio.create_task(_session_timeout_watcher(sid, timeout=60))


# ---------- Callback handler ----------
@app.on_callback_query(filters.regex(r"^rps\|"))
async def rps_hcallback(_, query: CallbackQuery):
    """
    callback_data format:
      rps|<session_id>|move|<move_index>|<allowed_user_id>
      rps|<session_id>|forfeit|<allowed_user_id>
    """
    parts = query.data.split("|")
    if len(parts) < 4:
        return await query.answer("Invalid data.", show_alert=True)

    _, sid, action = parts[:3]
    if sid not in SESSIONS:
        return await query.answer("This game session expired or is invalid.", show_alert=True)

    session = SESSIONS[sid]
    chat_id = session["chat_id"]
    caller = query.from_user
    allowed_user_id = None
    try:
        allowed_user_id = int(parts[-1])
    except Exception:
        allowed_user_id = None

    # validate who can press:
    # For bot games only player1 should be allowed.
    if session["type"] == "bot":
        if caller.id != session["player1_id"]:
            return await query.answer("Only the player who started the game can press these buttons.", show_alert=True)
    else:
        # pvp: only player1 or player2 can press
        if caller.id not in (session["player1_id"], session["player2_id"]):
            return await query.answer("Only the two players can press these buttons.", show_alert=True)

    # handle forfeit
    if action == "forfeit":
        # allowed_user_id is the original allowed ID in the button (we included it when building keyboard)
        if caller.id not in (session["player1_id"], session["player2_id"]):
            return await query.answer("You cannot forfeit this game.", show_alert=True)
        # determine winner: other player (or bot)
        if session["type"] == "bot":
            # user forfeited vs bot -> loss
            await _conclude_session_forfeit(sid, caller.id)
            await query.message.edit_text(f"🚪 {caller.mention} forfeited. Bot wins.")
            return await query.answer("You forfeited.")
        else:
            other = session["player2_id"] if caller.id == session["player1_id"] else session["player1_id"]
            await _conclude_session_forfeit(sid, caller.id, other_id=other)
            await query.message.edit_text(f"🚪 {caller.mention} forfeited. <a href='tg://user?id={other}'>Opponent</a> wins.", disable_web_page_preview=True)
            return await query.answer("You forfeited.")

    # handle move
    if action == "move":
        try:
            move_idx = int(parts[3])
        except Exception:
            return await query.answer("Invalid move.", show_alert=True)

        # record move
        session["moves"][caller.id] = move_idx
        await query.answer(f"You chose {MOVES[move_idx]}", show_alert=False)

        # if bot game -> generate bot move and resolve
        if session["type"] == "bot":
            bot_move = random.randint(0, 2)
            user_move = session["moves"].get(session["player1_id"])
            if user_move is None:
                # shouldn't happen — user must have just made a move
                user_move = move_idx
            # resolve
            res = resolve_moves(user_move, bot_move)  # 0 tie,1 player wins,2 bot wins
            # update DB
            await ensure_user(session["player1_id"], query.from_user.first_name or query.from_user.username or str(query.from_user.id))
            if res == 0:
                await add_xp(session["player1_id"], XP_TIE)
                await add_result(session["player1_id"], tie=1)
                text = f"🤝 Tie! You both chose {MOVE_EMO[user_move]}.\nXP +{XP_TIE}"
            elif res == 1:
                await add_xp(session["player1_id"], XP_WIN)
                await add_result(session["player1_id"], win=1)
                text = f"🏆 You win! {MOVE_EMO[user_move]} beats {MOVE_EMO[bot_move]}\nXP +{XP_WIN}"
            else:
                await add_xp(session["player1_id"], XP_LOSE)
                await add_result(session["player1_id"], loss=1)
                text = f"💥 You lose! {MOVE_EMO[bot_move]} beats {MOVE_EMO[user_move]}\nXP +{XP_LOSE}"

            # finalize and remove session
            try:
                await query.message.edit_text(f"🎮 RPS vs Bot Result\n\n{query.from_user.mention}\n\n{text}")
            except Exception:
                pass
            del SESSIONS[sid]
            return

        # pvp: check if both moves present
        if session["type"] == "pvp":
            if session["player1_id"] in session["moves"] and session["player2_id"] in session["moves"]:
                m1 = session["moves"][session["player1_id"]]
                m2 = session["moves"][session["player2_id"]]
                result = resolve_moves(m1, m2)  # 0 tie,1 p1 wins,2 p2 wins

                # update DB and build result text
                await ensure_user(session["player1_id"], "")  # ensure docs exist
                await ensure_user(session["player2_id"], "")

                if result == 0:
                    await add_xp(session["player1_id"], XP_TIE)
                    await add_xp(session["player2_id"], XP_TIE)
                    await add_result(session["player1_id"], tie=1)
                    await add_result(session["player2_id"], tie=1)
                    text = f"🤝 It's a tie! {MOVE_EMO[m1]} vs {MOVE_EMO[m2]}\nBoth +{XP_TIE} XP"
                elif result == 1:
                    await add_xp(session["player1_id"], XP_WIN)
                    await add_xp(session["player2_id"], XP_LOSE)
                    await add_result(session["player1_id"], win=1)
                    await add_result(session["player2_id"], loss=1)
                    text = (
                        f"🏆 {session['player1_id']} wins! {MOVE_EMO[m1]} beats {MOVE_EMO[m2]}\n"
                        f"<a href='tg://user?id={session['player1_id']}'>Player 1</a> +{XP_WIN} XP, "
                        f"<a href='tg://user?id={session['player2_id']}'>Player 2</a> +{XP_LOSE} XP"
                    )
                else:
                    await add_xp(session["player2_id"], XP_WIN)
                    await add_xp(session["player1_id"], XP_LOSE)
                    await add_result(session["player2_id"], win=1)
                    await add_result(session["player1_id"], loss=1)
                    text = (
                        f"🏆 {session['player2_id']} wins! {MOVE_EMO[m2]} beats {MOVE_EMO[m1]}\n"
                        f"<a href='tg://user?id={session['player2_id']}'>Player 2</a> +{XP_WIN} XP, "
                        f"<a href='tg://user?id={session['player1_id']}'>Player 1</a> +{XP_LOSE} XP"
                    )

                # build human-friendly display with mentions
                try:
                    p1_mention = (await app.get_users(session["player1_id"])).mention
                except Exception:
                    p1_mention = f"Player 1 ({session['player1_id']})"
                try:
                    p2_mention = (await app.get_users(session["player2_id"])).mention
                except Exception:
                    p2_mention = f"Player 2 ({session['player2_id']})"

                result_text = (
                    f"⚔️ RPS Result\n\n"
                    f"{p1_mention} chose {MOVE_EMO[m1]}\n"
                    f"{p2_mention} chose {MOVE_EMO[m2]}\n\n"
                )
                if result == 0:
                    result_text += f"🤝 It's a tie! Both gained {XP_TIE} XP"
                elif result == 1:
                    result_text += f"🏆 {p1_mention} wins! +{XP_WIN} XP\n{p2_mention} +{XP_LOSE} XP"
                else:
                    result_text += f"🏆 {p2_mention} wins! +{XP_WIN} XP\n{p1_mention} +{XP_LOSE} XP"

                # edit original messages to show outcome
                try:
                    await query.message.edit_text(result_text, disable_web_page_preview=True)
                except Exception:
                    pass
                # remove session
                del SESSIONS[sid]
                return

        # not ready yet (waiting for other player)
        await query.message.reply_text("Waiting for the other player to choose...", quote=True)
        return

    # fallback
    return await query.answer("Unknown action.", show_alert=True)


# ---------- Timeout & Forfeit helpers ----------
async def _session_timeout_watcher(sid: str, timeout: int = 60):
    """Auto-cancel session if not finished in `timeout` seconds."""
    await asyncio.sleep(timeout)
    if sid not in SESSIONS:
        return
    session = SESSIONS.get(sid)
    # if no moves or only one move -> consider it timed out
    moves = session.get("moves", {})
    if session["type"] == "bot":
        # if player didn't move -> timeout, delete session
        if session["player1_id"] not in moves:
            try:
                # find message and edit
                await app.send_message(session["chat_id"], "⌛ RPS session timed out.")
            except Exception:
                pass
            del SESSIONS[sid]
            return
    else:
        # pvp
        p1 = session["player1_id"]
        p2 = session["player2_id"]
        # if both moved already handled elsewhere
        if p1 in moves and p2 in moves:
            return
        # if only one moved -> treat as forfeit after timeout: the mover wins
        if p1 in moves and p2 not in moves:
            mover = p1
            other = p2
        elif p2 in moves and p1 not in moves:
            mover = p2
            other = p1
        else:
            # nobody moved -> cancel
            try:
                await app.send_message(session["chat_id"], "⌛ RPS challenge timed out (no moves).")
            except Exception:
                pass
            del SESSIONS[sid]
            return

        # award mover a win (forfeit)
        await add_xp(mover, XP_WIN)
        await add_result(mover, win=1)
        await add_xp(other, XP_LOSE)
        await add_result(other, loss=1)
        try:
            await app.send_message(session["chat_id"], f"⌛ Time's up — <a href='tg://user?id={mover}'>winner</a> wins by timeout.", disable_web_page_preview=True)
        except Exception:
            pass
        del SESSIONS[sid]


async def _conclude_session_forfeit(sid: str, forfeiter_id: int, other_id: int = None):
    """
    Handle a forfeit: forfeiter loses, other wins (or bot wins).
    """
    session = SESSIONS.get(sid)
    if not session:
        return
    if session["type"] == "bot":
        # forfeiter loses
        await add_xp(forfeiter_id, XP_LOSE)
        await add_result(forfeiter_id, loss=1)
    else:
        if other_id is None:
            return
        await add_xp(forfeiter_id, XP_LOSE)
        await add_result(forfeiter_id, loss=1)
        await add_xp(other_id, XP_WIN)
        await add_result(other_id, win=1)
    # remove session
    if sid in SESSIONS:
        del SESSIONS[sid]

