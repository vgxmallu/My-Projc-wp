#!/usr/bin/env python3
"""
Mini Sudoku (5x5) Bot (Pyrogram + MongoDB)

Commands:
- /start       : intro
- /play        : start a new 5x5 puzzle in the group
- /profile     : show your stats
- /leaderboard : show global leaderboard

Controls:
- Tap a blank tile → choose a number (1..5) from inline keyboard
- Correct fill gives +3 points, incorrect gives -1
"""
import os
import random
import asyncio
import logging
from typing import List, Dict, Tuple, Any

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
)
from config import DB_URL
from wallbot import wbot as app
DB_NAME = os.getenv("DB_NAME", "sudoku5_db")



# MongoDB
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
users_col = db["users"]     # {_id: user_id, username, score, wins, games_played}
# games are kept in memory (active sessions). You may persist to DB if desired.

# In-memory active games per chat
# Structure: chat_id -> {
#   "message_id": int,
#   "puzzle": List[List[int]] (0 for blank),
#   "solution": List[List[int]],
#   "scores": {user_id: points_in_this_game},
#   "running": True,
# }
active_games: Dict[int, Dict[str, Any]] = {}
chat_locks: Dict[int, asyncio.Lock] = {}

# Game settings
GRID_N = 5
BLANKS = 10  # number of blanks to remove; tune for difficulty
CORRECT_POINTS = 3
WRONG_POINTS = -1


# ---------- Utilities ----------
def ensure_chat_lock(chat_id: int) -> None:
    if chat_id not in chat_locks:
        chat_locks[chat_id] = asyncio.Lock()


def rank_for_score(score: int) -> str:
    if score < 50:
        return "🥉 Bronze"
    if score < 150:
        return "🥈 Silver"
    if score < 400:
        return "🥇 Gold"
    return "💎 Diamond"


async def ensure_user_doc(user_id: int, username: str | None):
    await users_col.update_one(
        {"_id": user_id},
        {"$setOnInsert": {"_id": user_id, "username": username or "", "score": 0, "wins": 0, "games_played": 0},
         "$set": {"username": username or ""}},
        upsert=True,
    )


async def add_user_score(user_id: int, username: str | None, points: int):
    await ensure_user_doc(user_id, username)
    await users_col.update_one({"_id": user_id}, {"$inc": {"score": points}})


async def award_winner(user_id: int, username: str | None):
    await ensure_user_doc(user_id, username)
    await users_col.update_one({"_id": user_id}, {"$inc": {"wins": 1, "games_played": 1, "score": 10}})


async def get_leaderboard_text(limit: int = 10) -> str:
    cursor = users_col.find().sort("score", -1).limit(limit)
    lines = ["🏆 Leaderboard"]
    i = 1
    async for doc in cursor:
        uname = doc.get("username") or f"user{doc['_id']}"
        lines.append(f"{i}. {uname} — {int(doc.get('score',0))} pts (wins: {int(doc.get('wins',0))})")
        i += 1
    return "\n".join(lines)


# ---------- Latin square generator (5x5 solution) ----------
def generate_latin_square(n: int = GRID_N) -> List[List[int]]:
    """
    Generate a Latin square of size n (numbers 1..n).
    We'll build a base row and permute to get a full Latin square.
    """
    base = list(range(1, n + 1))
    solution = []
    for shift in range(n):
        row = base[shift:] + base[:shift]
        solution.append(row[:])
    # apply a random permutation of symbols to add variety
    perm = base[:]
    random.shuffle(perm)
    symbol_map = {i + 1: perm[i] for i in range(n)}
    for i in range(n):
        solution[i] = [symbol_map[val] for val in solution[i]]
    # optionally permute rows and columns to scramble further
    random.shuffle(solution)
    # transpose and permute columns similarly
    cols = list(zip(*solution))
    random.shuffle(cols)
    solution = [list(row) for row in zip(*cols)]
    return solution


def make_puzzle_from_solution(solution: List[List[int]], blanks: int = BLANKS) -> List[List[int]]:
    n = len(solution)
    puzzle = [row[:] for row in solution]
    all_positions = [(i, j) for i in range(n) for j in range(n)]
    random.shuffle(all_positions)
    # remove up to 'blanks' cells
    for (i, j) in all_positions[:blanks]:
        puzzle[i][j] = 0
    return puzzle


# ---------- UI rendering ----------
def render_grid_markup(chat_id: int, puzzle: List[List[int]]) -> InlineKeyboardMarkup:
    """
    Build a GRID_N x GRID_N inline keyboard. Filled numbers are shown; blanks show '⬜'.
    Callback for blank: sudobtn|<chat_id>|<i>|<j>
    """
    rows = []
    for i in range(GRID_N):
        row = []
        for j in range(GRID_N):
            val = puzzle[i][j]
            if val == 0:
                label = "⬜"
                cb = f"sudobtn|{chat_id}|{i}|{j}"
            else:
                label = str(val)
                cb = f"noop"
            row.append(InlineKeyboardButton(label, callback_data=cb))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def render_number_buttons(chat_id: int, i: int, j: int) -> InlineKeyboardMarkup:
    """
    Provide number selection (1..GRID_N) for cell (i,j).
    Callback: sudofill|<chat_id>|<i>|<j>|<n>
    We arrange buttons in rows.
    """
    btns = []
    row = []
    for n in range(1, GRID_N + 1):
        row.append(InlineKeyboardButton(str(n), callback_data=f"sudofill|{chat_id}|{i}|{j}|{n}"))
        if len(row) == 5:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    return InlineKeyboardMarkup(btns)


# ---------- Command handlers ----------
@app.on_message(filters.command("sudostart"))
async def cmd_sjwjtart(_, message: Message):
    await ensure_user_doc(message.from_user.id, message.from_user.username)
    await message.reply(
        "🧩 Mini Sudoku (5×5)\n\n"
        "/play - start a new puzzle in this chat\n"
        "/profile - show your stats\n"
        "/leaderboard - show top players\n\n"
        "Tap blanks and choose a number from the inline buttons to fill.\n"
        "Correct fill: +3 pts, Wrong fill: -1 pt."
    )


@app.on_message(filters.command("sudo5x5profile"))
async def cmd_pnnrofile(_, message: Message):
    uid = message.from_user.id
    doc = await users_col.find_one({"_id": uid})
    if not doc:
        await ensure_user_doc(uid, message.from_user.username)
        doc = await users_col.find_one({"_id": uid})
    score = int(doc.get("score", 0))
    wins = int(doc.get("wins", 0))
    played = int(doc.get("games_played", 0))
    rank = rank_for_score(score)
    await message.reply(
        f"👤 Profile — {message.from_user.mention}\n\n"
        f"🏅 Rank: {rank}\n"
        f"📊 Score: {score}\n"
        f"✅ Wins: {wins}\n"
        f"🎮 Games played: {played}"
    )


@app.on_message(filters.command("sudo5x5leaderboard"))
async def cmd_leaderboard(_, message: Message):
    text = await get_leaderboard_text(10)
    await message.reply(text)


@app.on_message(filters.command("sudoku_5x5") & filters.group)
async def cmd_plasudoy(_, message: Message):
    """Start a new puzzle in this group chat."""
    chat_id = message.chat.id
    ensure_chat_lock(chat_id)
    lock = chat_locks[chat_id]

    async with lock:
        # Prevent multiple games per chat
        existing = active_games.get(chat_id)
        if existing and existing.get("running"):
            await message.reply("⚠️ A Sudoku game is already running in this chat.")
            return

        # Generate solution and puzzle
        solution = generate_latin_square(GRID_N)
        puzzle = make_puzzle_from_solution(solution, blanks=BLANKS)

        # store active game
        sent = await message.reply_text("⏳ Generating puzzle...")
        active_games[chat_id] = {
            "message_id": sent.id,
            "puzzle": puzzle,
            "solution": solution,
            "scores": {},   # per-user points for this game
            "running": True,
        }

        try:
            await sent.edit_text(
                f"🧩 Mini Sudoku (5×5)\nFill the blanks by tapping tiles.\nCorrect: +{CORRECT_POINTS} pts, Wrong: {WRONG_POINTS} pt",
                reply_markup=render_grid_markup(chat_id, puzzle),
            )
        except Exception:
            # fallback: send new message
            sent2 = await message.reply_text(
                f"🧩 Mini Sudoku (5×5)\nFill the blanks by tapping tiles.\nCorrect: +{CORRECT_POINTS} pts, Wrong: {WRONG_POINTS} pt",
                reply_markup=render_grid_markup(chat_id, puzzle),
            )
            active_games[chat_id]["message_id"] = sent2.id


# ---------- Callback handlers ----------
@app.on_callback_query(filters.regex(r"^sudobtn\|"))
async def cb_tile_press(client: Client, cq: CallbackQuery):
    """
    User tapped a blank tile: send number-selection inline keyboard.
    """
    try:
        _, chat_s, i_s, j_s = cq.data.split("|")
        chat_id = int(chat_s)
        i = int(i_s)
        j = int(j_s)
    except Exception:
        await cq.answer("Invalid tile data.", show_alert=True)
        return

    # Validate game and running state
    ensure_chat_lock(chat_id)
    lock = chat_locks[chat_id]
    async with lock:
        g = active_games.get(chat_id)
        if not g or not g.get("running"):
            await cq.answer("No active Sudoku here.", show_alert=True)
            return

        # verify tile is still blank
        puzzle = g["puzzle"]
        if i < 0 or i >= GRID_N or j < 0 or j >= GRID_N:
            await cq.answer("Invalid cell.", show_alert=True)
            return
        if puzzle[i][j] != 0:
            await cq.answer("This cell is already filled.", show_alert=False)
            return

        # present number buttons (as a reply to the chat message to keep UI)
        try:
            await cq.message.reply_text(
                f"{cq.from_user.first_name}, choose a number for cell ({i+1},{j+1}):",
                reply_markup=render_number_buttons(chat_id, i, j),
            )
            await cq.answer()  # no alert
        except Exception:
            await cq.answer("Could not show number buttons.", show_alert=True)


@app.on_callback_query(filters.regex(r"^sudofill\|"))
async def cb_fill(client: Client, cq: CallbackQuery):
    """
    User selected a number for a specific blank cell.
    Callback format: sudofill|<chat_id>|<i>|<j>|<n>
    """
    try:
        _, chat_s, i_s, j_s, n_s = cq.data.split("|")
        chat_id = int(chat_s)
        i = int(i_s)
        j = int(j_s)
        chosen = int(n_s)
    except Exception:
        await cq.answer("Invalid data.", show_alert=True)
        return

    ensure_chat_lock(chat_id)
    lock = chat_locks[chat_id]

    async with lock:
        g = active_games.get(chat_id)
        if not g or not g.get("running"):
            await cq.answer("No active Sudoku.", show_alert=True)
            return

        puzzle = g["puzzle"]
        solution = g["solution"]

        # validate indices
        if not (0 <= i < GRID_N and 0 <= j < GRID_N and 1 <= chosen <= GRID_N):
            await cq.answer("Invalid selection.", show_alert=True)
            return

        # ensure cell is blank
        if puzzle[i][j] != 0:
            await cq.answer("Cell already filled.", show_alert=False)
            return

        user = cq.from_user
        uid = user.id

        # check correctness against solution
        correct_value = solution[i][j]
        if chosen == correct_value:
            # fill cell
            puzzle[i][j] = chosen
            # award points
            g["scores"][uid] = g["scores"].get(uid, 0) + CORRECT_POINTS
            # update persistent user score
            await add_user_score(uid, user.username or user.first_name, CORRECT_POINTS)
            response = f"✅ Correct! +{CORRECT_POINTS} pts"
            await cq.answer(response, show_alert=False)
        else:
            # wrong: penalize
            g["scores"][uid] = g["scores"].get(uid, 0) + WRONG_POINTS
            await add_user_score(uid, user.username or user.first_name, WRONG_POINTS)
            response = f"❌ Wrong! {WRONG_POINTS} pts"
            await cq.answer(response, show_alert=True)

        # update the board message markup to reflect filled cell
        try:
            msg_id = g.get("message_id")
            # edit the same message that shows the board; sometimes message id can be stale; ignore exceptions
            await client.edit_message_reply_markup(chat_id, msg_id, reply_markup=render_grid_markup(chat_id, puzzle))
        except Exception:
            # best-effort; ignore edit failures
            pass

        # check for completion
        complete = all(all(cell != 0 for cell in row) for row in puzzle)
        if complete:
            # finalize game
            g["running"] = False
            # compute winner by points in this game
            if g["scores"]:
                winner_uid, winner_pts = max(g["scores"].items(), key=lambda kv: kv[1])
                # award additional winner bonus
                await award_winner(winner_uid, (await client.get_users(winner_uid)).username if winner_uid else None)
                # mark games_played for all contributors
                for uid_in in g["scores"].keys():
                    await users_col.update_one({"_id": uid_in}, {"$inc": {"games_played": 1}})
                # prepare results summary
                sorted_scores = sorted(g["scores"].items(), key=lambda kv: kv[1], reverse=True)
                lines = [
                    f"🏁 Sudoku complete! Winner: <b>{(await client.get_users(winner_uid)).first_name}</b> (+bonus)",
                    "",
                    "📊 Scores in this game:"
                ]
                for uid_k, pts_k in sorted_scores:
                    uobj = await client.get_users(uid_k)
                    uname = uobj.first_name if uobj else f"user{uid_k}"
                    lines.append(f"- {uname}: {pts_k} pts")
                # update board message text to results
                try:
                    await client.edit_message_text(chat_id, g.get("message_id"), "\n".join(lines))
                except Exception:
                    await client.send_message(chat_id, "\n".join(lines))
            else:
                # nobody scored (unlikely)
                try:
                    await client.send_message(chat_id, "✅ Sudoku complete! No player scores recorded.")
                except Exception:
                    pass

            # cleanup active game
            active_games.pop(chat_id, None)


