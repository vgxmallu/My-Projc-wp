#!/usr/bin/env python3
"""
Mini Sudoku (5x5) Telegram Game Bot (Pyrogram + Motor)

Features:
- /sudoku to start a round
- First user to tap Start becomes the player (only they can play)
- Inline keyboard grid for board; tap a cell -> numeric keypad (1..5, clear)
- /endgame or Finish button validates solution; /giveup reveals the answer
- MongoDB stores games and user stats
- Stale-game cleanup
- All callback handlers use filters.regex
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from dotenv import load_dotenv
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from config import DB_URL
from wallbot import wbot as app
load_dotenv()

DB_NAME = os.getenv("DB_NAME", "sudokuu_db")
CLEANUP_SECONDS = int(os.getenv("CLEANUP_SECONDS", "300"))  # seconds before a game is stale
POINTS_WIN = int(os.getenv("POINTS_WIN", "100"))
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["games"]    # stores active/past games
users_col = db["users"]    # stores user stats

# ---------- In-memory small lock ----------
GAME_LOCK = asyncio.Lock()

# ---------- Predefined puzzles (5x5)
# Each puzzle: tuple(board, solution)
# board: list of 5 lists containing 0 for empty or 1..5 filled
# solution: list of 5 lists of final digits 1..5
# Add more puzzles if desired.
PUZZLES: List[Tuple[List[List[int]], List[List[int]]]] = [
    # Puzzle 1
    (
        # board (0 = empty)
        [
            [0, 2, 0, 5, 0],
            [3, 0, 5, 0, 4],
            [0, 5, 0, 2, 0],
            [4, 0, 1, 0, 3],
            [0, 3, 0, 4, 0],
        ],
        # solution
        [
            [1,2,4,5,0],  # placeholder row (will be replaced by valid solution)
            [3,1,5,0,4],
            [5,5,3,2,1],
            [4,2,1,5,3],
            [2,3,4,4,5]
        ]
    ),
    # NOTE: For safety and correctness, we include properly solved puzzles below.
    # Example real puzzle:
    (
        [
            [0, 2, 0, 5, 0],
            [3, 0, 5, 0, 4],
            [0, 5, 0, 2, 0],
            [4, 0, 1, 0, 3],
            [0, 3, 0, 4, 0],
        ],
        [
            [1,2,4,5,3],
            [3,1,5,0,4],  # this file will be fixed below by examples
            [5,5,3,2,1],  # duplicate example rows above -- replace with real puzzles below
            [4,2,1,0,3],
            [2,3,0,4,5]
        ]
    ),
]

# The above placeholders are for structure only. We'll instead supply a set of correct puzzles now:
PUZZLES = [
    # Puzzle A (valid 5x5)
    (
        [
            [0, 2, 0, 5, 0],
            [3, 0, 5, 0, 4],
            [0, 5, 0, 2, 0],
            [4, 0, 1, 0, 3],
            [0, 3, 0, 4, 0],
        ],
        [
            [1,2,4,5,3],
            [3,1,5,0,4],  # this is invalid (0) — we'll avoid zeros in solutions
            [5,5,3,2,1],
            [4,2,1,0,3],
            [2,3,0,4,5]
        ]
    ),
]

# To make this safe and correct, we'll provide a small set of VALID 5x5 sudoku puzzles and their solutions.
# 5x5 sudoku variants can be defined with regions; to avoid complex generator code, we embed 3 correct puzzles below.
PUZZLES = [
    # Puzzle 1
    (
        [
            [0, 2, 0, 5, 0],
            [3, 0, 5, 0, 4],
            [0, 5, 0, 2, 0],
            [4, 0, 1, 0, 3],
            [0, 3, 0, 4, 0],
        ],
        [
            [1,2,4,5,3],
            [3,1,5,0,4],  # This placeholder will be replaced below -- we'll not rely on this set programmatically.
            [5,5,3,2,1],
            [4,2,1,5,3],
            [2,3,5,4,1]
        ]
    ),
]

# Real approach: Instead of mis-specified puzzles above, we'll include a small curated valid set below.
# NOTE: Mini-sudoku 5x5 isn't standardized like 9x9; most 5x5 variants use unconventional regions.
# For reliability, we will use *Latin-square* constraints: each row and each column must contain digits 1..5 exactly once.
# That is sufficient for a playable mini-sudoku variant (no block regions).
VALID_PUZZLES = [
    # puzzle 1 (0 = empty)
    (
        [
            [0, 2, 0, 5, 0],
            [3, 0, 5, 0, 4],
            [0, 5, 0, 2, 0],
            [4, 0, 1, 0, 3],
            [0, 3, 0, 4, 0],
        ],
        [
            [1,2,4,5,3],
            [3,1,5,0,4],  # this row has a 0 -> invalid, fix below
            [5,5,3,2,1],  # invalid
        ]
    )
]

# The previous blocks above were attempts — to avoid confusion, we'll ship a correct curated set here:

VALID_PUZZLES = [
    # Puzzle A (Latin-square solution)
    (
        # initial board
        [
            [0, 2, 0, 5, 0],
            [3, 0, 5, 0, 4],
            [0, 5, 0, 2, 0],
            [4, 0, 1, 0, 3],
            [0, 3, 0, 4, 0],
        ],
        # solution
        [
            [1,2,4,5,3],
            [3,1,5,0,4],  # still invalid; we need a truly valid solution set
        ]
    )
]

# ---------- To avoid shipping invalid puzzles, we'll programmatically generate a few random Latin-square solutions (5x5),
# and then produce boards by removing some numbers. This ensures correctness.

def generate_latin_square(n: int = 5) -> List[List[int]]:
    """Generate a random n x n Latin square (rows and cols contain 1..n)."""
    base = list(range(1, n+1))
    import random
    # start with a known Latin square (cyclic)
    square = [[((i + j) % n) + 1 for j in range(n)] for i in range(n)]
    # perform random row and column swaps and symbol permutations
    for _ in range(100):
        # swap two rows
        a, b = random.sample(range(n), 2)
        square[a], square[b] = square[b], square[a]
    for _ in range(100):
        a, b = random.sample(range(n), 2)
        for r in range(n):
            square[r][a], square[r][b] = square[r][b], square[r][a]
    # symbol permutation
    perm = list(range(1, n+1))
    random.shuffle(perm)
    mapping = {i+1: perm[i] for i in range(n)}
    for r in range(n):
        for c in range(n):
            square[r][c] = mapping[square[r][c]]
    return square

def make_puzzles_from_latin(n: int = 5, count: int = 6, remove_min: int = 8, remove_max: int = 12):
    """Create puzzles: generate 'count' Latin squares, remove between remove_min and remove_max cells randomly."""
    import random
    puzzles = []
    for _ in range(count):
        sol = generate_latin_square(n)
        board = [row.copy() for row in sol]
        to_remove = random.randint(remove_min, remove_max)
        coords = [(r,c) for r in range(n) for c in range(n)]
        random.shuffle(coords)
        for i in range(to_remove):
            r,c = coords[i]
            board[r][c] = 0
        puzzles.append((board, sol))
    return puzzles

# create puzzles programmatically
PUZZLES = make_puzzles_from_latin(n=5, count=8, remove_min=8, remove_max=14)


# ---------- Helper / UI builders ----------

def render_cell_label(value: int, r: int, c: int) -> str:
    """Return a display label for a cell."""
    if value == 0:
        return "·"
    return str(value)

def build_board_kb(board: List[List[int]], game_id: str, locked_cells: Optional[List[Tuple[int,int]]] = None) -> InlineKeyboardMarkup:
    """
    Build a 5x5 inline keyboard for the board.
    Each button callback: cell|<game_id>|<r>|<c>
    """
    rows = []
    for r in range(5):
        row_buttons = []
        for c in range(5):
            label = render_cell_label(board[r][c], r, c)
            # if locked cell (original clue) show as disabled (callback noop)
            cb = f"cell|{game_id}|{r}|{c}"
            row_buttons.append(InlineKeyboardButton(label, callback_data=cb))
        rows.append(row_buttons)
    # last control row: Finish / Give Up / Cancel
    ctrl_row = [
        InlineKeyboardButton("✅ Finish", callback_data=f"finish|{game_id}"),
        InlineKeyboardButton("🧾 Give Up", callback_data=f"giveup|{game_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{game_id}")
    ]
    rows.append(ctrl_row)
    return InlineKeyboardMarkup(rows)

def build_numpad_kb(game_id: str, r: int, c: int) -> InlineKeyboardMarkup:
    """
    Build numeric keypad 1..5 and a Clear button.
    Callback: num|<game_id>|<r>|<c>|<n>   (n = 0 for clear)
    """
    btns = []
    for n in range(1,6):
        btns.append(InlineKeyboardButton(str(n), callback_data=f"num|{game_id}|{r}|{c}|{n}"))
    # arrange 3 + 2 + clear
    kb = [
        [btns[0], btns[1], btns[2]],
        [btns[3], btns[4], InlineKeyboardButton("⌫", callback_data=f"num|{game_id}|{r}|{c}|0")]
    ]
    return InlineKeyboardMarkup(kb)

# ---------- DB helpers (users) ----------

async def ensure_user(user_id: int, username: Optional[str] = ""):
    """Create user doc if missing, update username."""
    now = datetime.utcnow()
    doc = await users_col.find_one({"user_id": user_id})
    if not doc:
        doc = {
            "user_id": user_id,
            "username": username or "",
            "score": 0,
            "wins": 0,
            "losses": 0,
            "games_played": 0,
            "created_at": now
        }
        await users_col.insert_one(doc)
    else:
        if username and doc.get("username") != username:
            await users_col.update_one({"user_id": user_id}, {"$set": {"username": username}})
    return doc

async def award_win(user_id: int, points: int = POINTS_WIN):
    await users_col.update_one({"user_id": user_id}, {"$inc": {"score": points, "wins": 1, "games_played": 1}}, upsert=True)

async def award_loss(user_id: int):
    await users_col.update_one({"user_id": user_id}, {"$inc": {"losses": 1, "games_played": 1}}, upsert=True)

# ---------- Validation helpers ----------

def board_is_complete(board: List[List[int]]) -> bool:
    """Return True if no zeros present."""
    return all(all(cell != 0 for cell in row) for row in board)

def board_equals_solution(board: List[List[int]], sol: List[List[int]]) -> bool:
    return board == sol

def board_is_valid_partial(board: List[List[int]]) -> bool:
    """Check Latin-square constraints: rows and columns contain no duplicates among non-zero entries."""
    n = 5
    for r in range(n):
        seen = set()
        for c in range(n):
            v = board[r][c]
            if v == 0: continue
            if v < 1 or v > n: return False
            if v in seen: return False
            seen.add(v)
    for c in range(n):
        seen = set()
        for r in range(n):
            v = board[r][c]
            if v == 0: continue
            if v in seen: return False
            seen.add(v)
    return True

# ---------- Commands ----------

#@app.on_message(filters.command("start") & filters.private)
async def cmd_art(_, m: Message):
    await ensure_user(m.from_user.id, m.from_user.username or m.from_user.first_name)
    text = (
        "🧩 <b>Mini Sudoku (5×5)</b>\n\n"
        "• Use /sudoku to start a round.\n"
        "• First user to press Start becomes the player — only that player may make moves.\n"
        "• Tap a cell → choose a number (1–5) or clear.\n"
        "• Press Finish to validate your board and claim victory.\n"
    )
    await m.reply_text(text, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("sudoku5x5"))
async def cmd_sudfivoku(_, m: Message):
    """Start a new game in the chat."""
    chat_id = m.chat.id
    # ensure no active game in this chat
    existing = await games_col.find_one({"chat_id": chat_id, "active": True})
    if existing:
        return await m.reply_text("A Sudoku round is already active in this chat. Wait for it to finish or /cancel it.")

    # pick puzzle
    import random
    puzzle_board, solution = random.choice(PUZZLES)
    # deep copy
    board = [row.copy() for row in puzzle_board]
    # build db doc
    now = datetime.utcnow()
    game_doc = {
        "chat_id": chat_id,
        "active": True,
        "creator_id": m.from_user.id,
        "player_id": None,
        "player_username": None,
        "board": board,
        "clues": [[1 if val != 0 else 0 for val in row] for row in board],  # locked cells
        "solution": solution,
        "created_at": now,
        "last_update": now,
        "message_id": None
    }
    res = await games_col.insert_one(game_doc)
    gid = str(res.inserted_id)

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Start (become player)", callback_data=f"start|{gid}")]])
    sent = await m.reply_text("🧩 Mini Sudoku (5×5)\nTap Start to become the player — only that player may make moves.", reply_markup=kb)
    await games_col.update_one({"_id": res.inserted_id}, {"$set": {"message_id": sent.id}})
    LOG.info("Created game %s in chat %s", gid, chat_id)

@app.on_message(filters.command("sudokuprofile"))
async def cmd_prsudokofile(_, m: Message):
    uid = m.from_user.id
    doc = await users_col.find_one({"user_id": uid})
    if not doc:
        await ensure_user(uid, m.from_user.username or m.from_user.first_name)
        doc = await users_col.find_one({"user_id": uid})
    text = (
        f"👤 {m.from_user.mention}\n"
        f"⭐ Score: {doc.get('score',0)}\n"
        f"🏆 Wins: {doc.get('wins',0)}\n"
        f"💔 Losses: {doc.get('losses',0)}\n"
        f"🎮 Games played: {doc.get('games_played',0)}"
    )
    await m.reply_text(text, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("sudokuleaderboard"))
async def cmd_leadggerboard(_, m: Message):
    top = await users_col.find().sort("score", -1).limit(10).to_list(length=10)
    if not top:
        return await m.reply_text("No players yet.")
    lines = ["🏅 Leaderboard — Top players"]
    for i,u in enumerate(top, start=1):
        lines.append(f"{i}. {u.get('username') or u.get('user_id')} — {u.get('score',0)} pts (wins: {u.get('wins',0)})")
    await m.reply_text("\n".join(lines), parse_mode=enums.ParseMode.HTML)

# ---------- Callback handlers (filters.regex) ----------

@app.on_callback_query(filters.regex(r"^start\|"))
async def cb_start(_, cq: CallbackQuery):
    """User presses start to become player"""
    data = cq.data  # start|<game_id>
    try:
        _, gid = data.split("|",1)
        game_oid = ObjectId(gid)
    except Exception:
        return await cq.answer("Invalid game id.", show_alert=True)

    game = await games_col.find_one({"_id": game_oid, "active": True})
    if not game:
        return await cq.answer("Game not found or already finished.", show_alert=True)

    if game.get("player_id"):
        if game["player_id"] != cq.from_user.id:
            return await cq.answer("Someone already is the player for this round.", show_alert=True)
        else:
            return await cq.answer("You are already the player.", show_alert=False)

    # assign player (first-come)
    await games_col.update_one({"_id": game_oid}, {"$set": {"player_id": cq.from_user.id, "player_username": cq.from_user.username or cq.from_user.first_name, "last_update": datetime.utcnow()}})
    game = await games_col.find_one({"_id": game_oid})

    # show board with numpad disabled until player taps a cell
    kb = build_board_kb(game["board"], gid)
    try:
        await cq.message.edit_text(f"🎯 Player: {cq.from_user.mention}\nNow you can tap empty cells to place numbers.", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
    except Exception:
        # fallback send
        await cq.message.reply_text("Now you can tap empty cells to place numbers.", reply_markup=kb)
    await cq.answer("You are the player — good luck!", show_alert=False)

@app.on_callback_query(filters.regex(r"^cell\|"))
async def cb_cell(_, cq: CallbackQuery):
    """Cell selected, show numpad. Only player can interact."""
    data = cq.data  # cell|<game_id>|r|c
    try:
        _, gid, rs, cs = data.split("|",3)
        r = int(rs); c = int(cs)
        game_oid = ObjectId(gid)
    except Exception:
        return await cq.answer("Invalid data.", show_alert=True)

    game = await games_col.find_one({"_id": game_oid, "active": True})
    if not game:
        return await cq.answer("Game not active.", show_alert=True)

    # only the player can open numpad
    player = game.get("player_id")
    if player != cq.from_user.id:
        return await cq.answer("Only the player who started the round may play.", show_alert=True)

    # don't allow editing clues
    if game.get("clues", [])[r][c] == 1:
        return await cq.answer("This is a clue cell and cannot be changed.", show_alert=True)

    # present numpad
    kb = build_numpad_kb(gid, r, c)
    try:
        await cq.message.answer_text(f"Select number for cell ({r+1},{c+1}) — tap a number or ⌫ to clear.", reply_markup=kb)
    except Exception:
        # fallback: edit message (less ideal)
        try:
            await cq.message.edit_text("Select number:", reply_markup=kb)
        except:
            pass
    await cq.answer()

@app.on_callback_query(filters.regex(r"^num\|"))
async def cb_num(_, cq: CallbackQuery):
    """User picks a number for a cell: num|<game_id>|r|c|n"""
    data = cq.data
    try:
        _, gid, rs, cs, ns = data.split("|",4)
        r = int(rs); c = int(cs); n = int(ns)
        game_oid = ObjectId(gid)
    except Exception:
        return await cq.answer("Invalid data.", show_alert=True)

    game = await games_col.find_one({"_id": game_oid, "active": True})
    if not game:
        return await cq.answer("Game not active.", show_alert=True)

    # only player allowed
    if game.get("player_id") != cq.from_user.id:
        return await cq.answer("Only the player may enter numbers.", show_alert=True)

    # cannot edit clues
    if game.get("clues", [])[r][c] == 1:
        return await cq.answer("Cannot change a clue cell.", show_alert=True)

    # apply number (0 = clear)
    board = game.get("board")
    board[r][c] = n if n != 0 else 0

    # basic validity check (no duplicate in row/col)
    if not board_is_valid_partial(board):
        # revert change
        await games_col.update_one({"_id": game_oid}, {"$set": {"board": game["board"], "last_update": datetime.utcnow()}})
        await cq.answer("That move creates a duplicate in row/column — invalid.", show_alert=True)
        return

    # save board
    await games_col.update_one({"_id": game_oid}, {"$set": {"board": board, "last_update": datetime.utcnow()}})

    # update main board message if exists
    try:
        if game.get("message_id"):
            kb = build_board_kb(board, gid)
            await app.edit_message_reply_markup(game["chat_id"], game["message_id"], reply_markup=kb)
    except Exception:
        pass

    # immediate feedback if board complete
    if board_is_complete(board):
        # fetch solution
        sol = game.get("solution")
        if board_equals_solution(board, sol):
            # win
            await ensure_user(cq.from_user.id, cq.from_user.username or cq.from_user.first_name)
            await award_win(cq.from_user.id, points=POINTS_WIN)
            await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "last_update": datetime.utcnow(), "finished_by": cq.from_user.id, "finished_at": datetime.utcnow()}})
            try:
                await cq.message.reply_text(f"🏆 Congrats {cq.from_user.mention}! You solved the puzzle and earned {POINTS_WIN} points.", parse_mode=enums.ParseMode.HTML)
            except:
                pass
            await cq.answer("Correct! You solved the puzzle.", show_alert=False)
            return
        else:
            # complete but wrong
            await ensure_user(cq.from_user.id, cq.from_user.username or cq.from_user.first_name)
            await award_loss(cq.from_user.id)
            await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "last_update": datetime.utcnow(), "finished_by": None, "finished_at": datetime.utcnow(), "failed": True}})
            try:
                await cq.message.reply_text(f"✖️ The board is complete but incorrect. Puzzle ended.", parse_mode=enums.ParseMode.HTML)
            except:
                pass
            await cq.answer("Board complete but incorrect. Round ended.", show_alert=True)
            return

    await cq.answer("Number placed.", show_alert=False)

@app.on_callback_query(filters.regex(r"^finish\|"))
async def cb_finish(_, cq: CallbackQuery):
    """Finish button pressed: validate board"""
    data = cq.data
    try:
        _, gid = data.split("|",1)
        game_oid = ObjectId(gid)
    except:
        return await cq.answer("Invalid game id.", show_alert=True)

    game = await games_col.find_one({"_id": game_oid})
    if not game or not game.get("active"):
        return await cq.answer("Game not active.", show_alert=True)

    # only player may finish
    if game.get("player_id") != cq.from_user.id:
        return await cq.answer("Only the player's owner may finish the game.", show_alert=True)

    board = game.get("board")
    sol = game.get("solution")

    if not board_is_complete(board):
        return await cq.answer("Board is not complete yet.", show_alert=True)

    if board_equals_solution(board, sol):
        await ensure_user(cq.from_user.id, cq.from_user.username or cq.from_user.first_name)
        await award_win(cq.from_user.id, points=POINTS_WIN)
        await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "finished_by": cq.from_user.id, "finished_at": datetime.utcnow(), "last_update": datetime.utcnow()}})
        try:
            await cq.message.reply_text(f"🏆 {cq.from_user.mention} solved the puzzle! +{POINTS_WIN} points.", parse_mode=enums.ParseMode.HTML)
        except:
            pass
        await cq.answer("Correct! You win.", show_alert=False)
    else:
        await ensure_user(cq.from_user.id, cq.from_user.username or cq.from_user.first_name)
        await award_loss(cq.from_user.id)
        await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "failed": True, "last_update": datetime.utcnow()}})
        try:
            await cq.message.reply_text(f"✖️ The solution is incorrect. Round ended.", parse_mode=enums.ParseMode.HTML)
        except:
            pass
        await cq.answer("Incorrect solution. Round ended.", show_alert=True)

@app.on_callback_query(filters.regex(r"^giveup\|"))
async def cb_giveup(_, cq: CallbackQuery):
    """Player gives up: reveal solution and record loss"""
    data = cq.data
    try:
        _, gid = data.split("|",1)
        game_oid = ObjectId(gid)
    except:
        return await cq.answer("Invalid game id.", show_alert=True)

    game = await games_col.find_one({"_id": game_oid})
    if not game or not game.get("active"):
        return await cq.answer("Game not active.", show_alert=True)

    # only player or admin may give up on behalf
    player = game.get("player_id")
    allowed = False
    if cq.from_user.id == player:
        allowed = True
    else:
        # group admin allowed
        try:
            member = await app.get_chat_member(game["chat_id"], cq.from_user.id)
            if member.status in ("administrator","creator"):
                allowed = True
        except Exception:
            allowed = False
    if not allowed:
        return await cq.answer("Only the player or a group admin may give up.", show_alert=True)

    # reveal solution and mark loss
    sol = game.get("solution")
    await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "finished_by": None, "failed": True, "last_update": datetime.utcnow()}})
    try:
        # replace board display with solution
        kb = build_board_kb(sol, gid)
        await app.edit_message_text(game["chat_id"], game["message_id"], f"🧾 Puzzle solution revealed.", reply_markup=kb)
    except Exception:
        pass
    if player:
        await ensure_user(player, game.get("player_username"))
        await award_loss(player)
    await cq.answer("Solution revealed. Round ended.", show_alert=False)


@app.on_message(filters.command("cancel"))
async def cmd_cancel(app: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /cancel <game_id>")

    gid = message.command[1]
    try:
        game_oid = ObjectId(gid)
    except Exception:
        return await message.reply_text("⚠️ Invalid game ID format.")

    game = await games_col.find_one({"_id": game_oid})
    if not game:
        return await message.reply_text("🚫 Game not found or already ended.")

    # Only player or admin can cancel
    player = game.get("player_id")
    allowed = False

    if message.from_user.id == player:
        allowed = True
    else:
        try:
            member = await app.get_chat_member(game["chat_id"], message.from_user.id)
            if member.status in ("administrator", "creator"):
                allowed = True
        except Exception:
            allowed = False

    if not allowed:
        return await message.reply_text("⚠️ Only the player or a group admin can cancel the game.")

    await games_col.update_one(
        {"_id": game_oid},
        {"$set": {"active": False, "last_update": datetime.utcnow()}}
    )

    try:
        await app.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["message_id"],
            text="❌ Game cancelled by user."
        )
    except Exception:
        pass

    await message.reply_text("✅ Game cancelled successfully.")

@app.on_callback_query(filters.regex(r"^cancel\|"))
async def cb_cancel(_, cq: CallbackQuery):
    data = cq.data
    try:
        _, gid = data.split("|",1)
        game_oid = ObjectId(gid)
    except:
        return await cq.answer("Invalid game id.", show_alert=True)

    game = await games_col.find_one({"_id": game_oid})
    if not game:
        return await cq.answer("Game not found.", show_alert=True)

    # Only player or admin can cancel
    player = game.get("player_id")
    allowed = False
    if cq.from_user.id == player:
        allowed = True
    else:
        try:
            member = await app.get_chat_member(game["chat_id"], cq.from_user.id)
            if member.status in ("administrator","creator"):
                allowed = True
        except Exception:
            allowed = False
    if not allowed:
        return await cq.answer("Only the player or group admin may cancel the game.", show_alert=True)

    await games_col.update_one({"_id": game_oid}, {"$set": {"active": False, "last_update": datetime.utcnow()}})
    try:
        await app.edit_message_text(game["chat_id"], game["message_id"], "❌ Game cancelled.")
    except:
        pass
    await cq.answer("Game cancelled.", show_alert=False)

# ---------- Stale game cleaner ----------

async def stale_cleaner_loop():
    LOG.info("Starting stale game cleaner (seconds=%s)", CLEANUP_SECONDS)
    while True:
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=CLEANUP_SECONDS)
            stale = await games_col.find({"active": True, "last_update": {"$lt": cutoff}}).to_list(length=200)
            for g in stale:
                try:
                    await games_col.update_one({"_id": g["_id"]}, {"$set": {"active": False}})
                    # try to mark message timed out
                    if g.get("message_id"):
                        try:
                            await app.edit_message_text(g["chat_id"], g["message_id"], "⏰ Game timed out due to inactivity.")
                        except Exception:
                            pass
                    # if a player was assigned, mark a loss
                    if g.get("player_id"):
                        await ensure_user(g["player_id"], g.get("player_username"))
                        await award_loss(g["player_id"])
                except Exception:
                    LOG.exception("Error cleaning game %s", g.get("_id"))
        except Exception:
            LOG.exception("Stale cleaner error")
        await asyncio.sleep(max(15, CLEANUP_SECONDS // 4))

# ---------- Startup / Shutdown ----------
"""
@app.on_start()
async def on_start():
    LOG.info("Mini Sudoku 5x5 bot starting...")
    try:
        await games_col.create_index("chat_id")
        await games_col.create_index("active")
        await users_col.create_index("user_id", unique=True)
    except Exception:
        pass
    # spawn cleaner
    asyncio.create_task(stale_cleaner_loop())
    LOG.info("Ready.")

@app.on_stop()
async def on_stop():
    LOG.info("Stopping bot...")

# ---------- Run ----------
if __name__ == "__main__":
    app.run()
"""
