"""
Connect 4 Advanced Bot (Pyrogram + motor + MongoDB)

Features:
- PvP (challenge + accept)
- PvE (bot) with difficulty easy/medium/hard (minimax)
- Inline board controls (1..7)
- Resign, Rematch, Undo (single), Replay
- Tournament: create / join / start / status
- Leaderboard in MongoDB (wins/losses/draws, elo)
- Auto-cleanup: forfeit inactive games, remove old finished games
- Message editing of board message where possible
"""

import asyncio
import random
import math
import uuid
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "connect4_bot_db"

# Game settings
ROWS, COLS = 6, 7
EMPTY = " "
P1_SYMBOL = "X"   # stored as X in DB
P2_SYMBOL = "O"
# Auto-forfeit if no move for this many seconds
INACTIVITY_TIMEOUT = 60 * 15   # 15 minutes
# Delete finished games older than N days
FINISHED_TTL_DAYS = 14

# Minimax depths
MINIMAX_DEPTH_MEDIUM = 3
MINIMAX_DEPTH_HARD = 5

# ----------------------------------------

mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["games"]
players_col = db["players"]
tourn_col = db["tournaments"]

scheduler = AsyncIOScheduler(timezone="UTC")
scheduler.start()

# ---------------- helpers ----------------
def new_board() -> List[List[str]]:
    return [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]

def board_to_text(board: List[List[str]]) -> str:
    # top row first
    em = {EMPTY: "⚪", P1_SYMBOL: "🔴", P2_SYMBOL: "🟡"}
    lines = ["".join(em[cell] for cell in row) for row in board]
    header = " ".join(str(i+1) for i in range(COLS))
    return f"Cols: {header}\n" + "\n".join(lines)

def possible_moves(board: List[List[str]]) -> List[int]:
    return [c for c in range(COLS) if board[0][c] == EMPTY]

def drop_piece(board: List[List[str]], col: int, piece: str) -> bool:
    for r in range(ROWS-1, -1, -1):
        if board[r][col] == EMPTY:
            board[r][col] = piece
            return True
    return False

def board_full(board: List[List[str]]) -> bool:
    return all(cell != EMPTY for row in board for cell in row)

def check_winner(board: List[List[str]]) -> Optional[str]:
    # return P1_SYMBOL or P2_SYMBOL or "DRAW" or None
    # horizontal
    for r in range(ROWS):
        for c in range(COLS-3):
            if board[r][c] != EMPTY and board[r][c] == board[r][c+1] == board[r][c+2] == board[r][c+3]:
                return board[r][c]
    # vertical
    for c in range(COLS):
        for r in range(ROWS-3):
            if board[r][c] != EMPTY and board[r][c] == board[r+1][c] == board[r+2][c] == board[r+3][c]:
                return board[r][c]
    # diagonal down-right
    for r in range(ROWS-3):
        for c in range(COLS-3):
            if board[r][c] != EMPTY and board[r][c] == board[r+1][c+1] == board[r+2][c+2] == board[r+3][c+3]:
                return board[r][c]
    # diagonal up-right
    for r in range(3, ROWS):
        for c in range(COLS-3):
            if board[r][c] != EMPTY and board[r][c] == board[r-1][c+1] == board[r-2][c+2] == board[r-3][c+3]:
                return board[r][c]
    if board_full(board):
        return "DRAW"
    return None

# ELO utility (simple)
def elo_expected(a: int, b: int) -> float:
    return 1.0 / (1.0 + 10 ** ((b - a) / 400.0))

def elo_update(a: int, b: int, score_a: float, k: int = 32) -> int:
    exp = elo_expected(a, b)
    return int(a + k * (score_a - exp))

async def ensure_player(uid: int):
    p = await players_col.find_one({"_id": uid})
    if not p:
        p = {"_id": uid, "wins": 0, "losses": 0, "draws": 0, "elo": 1200}
        await players_col.insert_one(p)
    return p

async def update_player_on_finish(winner: Optional[int], loser: Optional[int], draw: bool=False):
    if draw:
        if winner is None and loser is None:
            return
        # in our canonical call when draw: pass both players as winner & loser?
        # here we expect winner==p1, loser==p2 but draw True indicates tie
        if winner is not None:
            await players_col.update_one({"_id": winner}, {"$inc": {"draws": 1}}, upsert=True)
        if loser is not None:
            await players_col.update_one({"_id": loser}, {"$inc": {"draws": 1}}, upsert=True)
        return
    # winner & loser are ints
    await ensure_player(winner)
    await ensure_player(loser)
    wdoc = await players_col.find_one({"_id": winner})
    ldoc = await players_col.find_one({"_id": loser})
    new_w = elo_update(wdoc.get("elo", 1200), ldoc.get("elo", 1200), 1.0)
    new_l = elo_update(ldoc.get("elo", 1200), wdoc.get("elo", 1200), 0.0)
    await players_col.update_one({"_id": winner}, {"$inc": {"wins":1}, "$set": {"elo": new_w}}, upsert=True)
    await players_col.update_one({"_id": loser}, {"$inc": {"losses":1}, "$set": {"elo": new_l}}, upsert=True)

# ---------------- Minimax AI ----------------
def score_window(window: List[str], piece: str) -> int:
    opp = P1_SYMBOL if piece == P2_SYMBOL else P2_SYMBOL
    score = 0
    if window.count(piece) == 4:
        score += 10000
    elif window.count(piece) == 3 and window.count(EMPTY) == 1:
        score += 50
    elif window.count(piece) == 2 and window.count(EMPTY) == 2:
        score += 10
    if window.count(opp) == 3 and window.count(EMPTY) == 1:
        score -= 80
    return score

def board_score(board: List[List[str]], piece: str) -> int:
    score = 0
    center_count = sum(1 for r in range(ROWS) if board[r][COLS//2] == piece)
    score += center_count * 3
    # horizontal
    for r in range(ROWS):
        row_array = board[r]
        for c in range(COLS-3):
            score += score_window(row_array[c:c+4], piece)
    # vertical
    for c in range(COLS):
        col_array = [board[r][c] for r in range(ROWS)]
        for r in range(ROWS-3):
            score += score_window(col_array[r:r+4], piece)
    # diag down-right
    for r in range(ROWS-3):
        for c in range(COLS-3):
            window = [board[r+i][c+i] for i in range(4)]
            score += score_window(window, piece)
    # diag up-right
    for r in range(3, ROWS):
        for c in range(COLS-3):
            window = [board[r-i][c+i] for i in range(4)]
            score += score_window(window, piece)
    return score

def minimax(board: List[List[str]], depth: int, alpha: int, beta: int, maximizing: bool, piece: str) -> Tuple[int, Optional[int]]:
    valid = possible_moves(board)
    is_terminal = check_winner(board)
    if depth == 0 or is_terminal is not None:
        if is_terminal == piece:
            return (1000000, None)
        elif is_terminal == (P1_SYMBOL if piece == P2_SYMBOL else P2_SYMBOL):
            return (-1000000, None)
        elif is_terminal == "DRAW":
            return (0, None)
        else:
            return (board_score(board, piece), None)
    if maximizing:
        value = -10**9
        best_col = random.choice(valid)
        for col in valid:
            bcopy = [r[:] for r in board]
            drop_piece(bcopy, col, piece)
            new_score, _ = minimax(bcopy, depth-1, alpha, beta, False, piece)
            if new_score > value:
                value, best_col = new_score, col
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value, best_col
    else:
        value = 10**9
        opp = P1_SYMBOL if piece == P2_SYMBOL else P2_SYMBOL
        best_col = random.choice(valid)
        for col in valid:
            bcopy = [r[:] for r in board]
            drop_piece(bcopy, col, opp)
            new_score, _ = minimax(bcopy, depth-1, alpha, beta, True, piece)
            if new_score < value:
                value, best_col = new_score, col
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value, best_col

def ai_choose(board: List[List[str]], level: str) -> int:
    moves = possible_moves(board)
    if not moves:
        return None
    if level == "easy":
        return random.choice(moves)
    if level == "medium":
        # immediate win/block or basic minimax depth 3
        for c in moves:
            bcopy = [r[:] for r in board]
            drop_piece(bcopy, c, P2_SYMBOL)
            if check_winner(bcopy) == P2_SYMBOL:
                return c
        for c in moves:
            bcopy = [r[:] for r in board]
            drop_piece(bcopy, c, P1_SYMBOL)
            if check_winner(bcopy) == P1_SYMBOL:
                return c
        _, col = minimax(board, MINIMAX_DEPTH_MEDIUM, -10**9, 10**9, True, P2_SYMBOL)
        return col if col is not None else random.choice(moves)
    # hard
    _, col = minimax(board, MINIMAX_DEPTH_HARD, -10**9, 10**9, True, P2_SYMBOL)
    return col if col is not None else random.choice(moves)

# ---------------- Inline keyboards ----------------
def board_kb(game_id: str, active: bool = True) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(str(i+1), callback_data=f"move|{game_id}|{i}") for i in range(COLS)]
    ctrl = [
        InlineKeyboardButton("🏳 Resign", callback_data=f"resign|{game_id}"),
        InlineKeyboardButton("🔁 Rematch", callback_data=f"rematch|{game_id}"),
        InlineKeyboardButton("↩ Undo", callback_data=f"undo|{game_id}")
    ]
    return InlineKeyboardMarkup([row, ctrl])

def spectator_kb(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("👀 Spectate", callback_data=f"spectate|{game_id}")]])

# --------------- Background cleanup ----------------
async def forfeit_inactive_games():
    cutoff = datetime.utcnow().timestamp() - INACTIVITY_TIMEOUT
    cursor = games_col.find({"status": "active", "last_move_at": {"$lt": cutoff}})
    async for g in cursor:
        # award win to opponent of current turn
        players = g["players"]
        turn = g["turn"]
        if len(players) >= 2:
            winner = players[0] if players[1] == turn else players[1]
            loser = turn
            try:
                await update_player_on_finish(winner, loser, draw=False)
            except Exception:
                pass
        await games_col.update_one({"_id": g["_id"]}, {"$set": {"status": "forfeited", "ended_at": datetime.utcnow().timestamp()}})
        # try to edit board message if exists
        try:
            if g.get("message_id"):
                text = f"⚠️ Game `{g['_id']}` forfeited due to inactivity.\nWinner: {winner}\n"
                await app.edit_message_text(g["chat_id"], g["message_id"], text)
        except Exception:
            pass

async def cleanup_old_finished():
    cutoff = datetime.utcnow() - timedelta(days=FINISHED_TTL_DAYS)
    res = await games_col.delete_many({"status": {"$in": ["finished","forfeited","cancelled"]}, "ended_at": {"$lt": cutoff.timestamp()}})
    # optional logging: print("deleted", res.deleted_count)

# schedule background jobs
scheduler.add_job(lambda: asyncio.create_task(forfeit_inactive_games()), "interval", minutes=5)
scheduler.add_job(lambda: asyncio.create_task(cleanup_old_finished()), "interval", hours=6)

# ---------------- Commands ----------------
@app.on_message(filters.command("art"))
async def cmd_sgitart(_, message: Message):
    await message.reply(
        "🎮 Connect 4 Advanced\n\n"
        "Commands:\n"
        "/challenge (reply) — challenge player\n"
        "/pve <easy|medium|hard> — play vs bot (private)\n"
        "/leaderboard — show top players\n"
        "/spectate <game_id> — watch a game\n"
        "/tourney create <name> | join <id> | start <id> | status <id>\n"
        "/profile — show your stats"
    )

@app.on_message(filters.command("c4profile"))
async def cmd_prcuofile(_, message: Message):
    uid = message.from_user.id
    p = await players_col.find_one({"_id": uid})
    if not p:
        return await message.reply("No stats yet. Play some games!")
    await message.reply_text(f"👤 {message.from_user.first_name}\nELO: {p.get('elo',1200)}\nW:{p.get('wins',0)} L:{p.get('losses',0)} D:{p.get('draws',0)}")

@app.on_message(filters.command("c4leaderboard"))
async def cmd_leajvderboard(_, message: Message):
    cursor = players_col.find().sort("elo", -1).limit(10)
    lines = ["🏆 Leaderboard (top 10 by ELO):"]
    async for p in cursor:
        try:
            u = await app.get_users(p["_id"])
            name = u.first_name
        except:
            name = f"User({p['_id']})"
        lines.append(f"{name} — ELO {p.get('elo',1200)} W:{p.get('wins',0)}")
    await message.reply("\n".join(lines))

# ---------------- PvP: challenge ----------------
@app.on_message(filters.command("c4tchallenge") & (filters.group | filters.private))
async def cmdyh_chagllenge(_, message: Message):
    # must reply or provide username
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        parts = message.text.split()
        if len(parts) < 2:
            return await message.reply("Reply to someone's message or: /challenge @username")
        try:
            target = await app.get_users(parts[1])
        except:
            return await message.reply("User not found.")
    if target.id == message.from_user.id:
        return await message.reply("You cannot challenge yourself.")

    gid = str(uuid.uuid4())
    board = new_board()
    game = {
        "_id": gid,
        "chat_id": message.chat.id,
        "players": [message.from_user.id, target.id],  # players[0] is X and starts
        "board": board,
        "turn": message.from_user.id,
        "status": "pending",
        "created_at": datetime.utcnow().timestamp(),
        "last_move_at": datetime.utcnow().timestamp(),
        "history": [],
        "message_id": None,
        "mode": "pvp"
    }
    await games_col.insert_one(game)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"accept|{gid}|{target.id}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"decline|{gid}|{target.id}")]
    ])
    sent = await message.reply_text(f"🎯 Challenge {message.from_user.mention} ➜ {target.mention}\nGame ID `{gid}`\n{target.mention}, accept?", reply_markup=kb)
    await games_col.update_one({"_id": gid}, {"$set": {"message_id": sent.message_id}})

@app.on_callback_query(filters.regex(r"^accept\|"))
async def cb_accept(_, query: CallbackQuery):
    _, gid, target_s = query.data.split("|")
    if query.from_user.id != int(target_s):
        return await query.answer("You are not the challenged user.", show_alert=True)
    g = await games_col.find_one({"_id": gid})
    if not g or g["status"] != "pending":
        return await query.answer("Game not found or already started.", show_alert=True)
    await ensure_player(g["players"][0]); await ensure_player(g["players"][1])
    await games_col.update_one({"_id": gid}, {"$set": {"status":"active", "last_move_at": datetime.utcnow().timestamp()}})
    text = f"🎮 Game `{gid}` started!\n\n{board_to_text(g['board'])}\nTurn: <a href='tg://user?id={g['turn']}'>player</a>"
    kb = board_kb(gid)
    try:
        if g.get("message_id"):
            await query.message.edit(text, reply_markup=kb)
        else:
            sent = await query.message.reply(text, reply_markup=kb)
            await games_col.update_one({"_id": gid}, {"$set": {"message_id": sent.message_id}})
    except:
        await query.message.reply(text, reply_markup=kb)
    await query.answer("Game started!")

@app.on_callback_query(filters.regex(r"^decline\|"))
async def cb_decline(_, query: CallbackQuery):
    _, gid, target_s = query.data.split("|")
    if query.from_user.id != int(target_s):
        return await query.answer("You are not the challenged user.", show_alert=True)
    await games_col.delete_one({"_id": gid})
    await query.message.edit("❌ Challenge declined.")
    await query.answer("Declined.")

# ---------------- PvE (private) ----------------
@app.on_message(filters.command("c4pve") & filters.private)
async def cmdce4_pve(_, message: Message):
    parts = message.text.split()
    level = "easy"
    if len(parts) >= 2:
        level = parts[1].lower()
        if level not in ("easy","medium","hard"):
            return await message.reply("Choose difficulty: easy / medium / hard")
    gid = str(uuid.uuid4())
    board = new_board()
    game = {
        "_id": gid,
        "chat_id": message.chat.id,
        "players": [message.from_user.id, 0],  # 0 denotes bot
        "board": board,
        "turn": message.from_user.id,
        "status": "active",
        "created_at": datetime.utcnow().timestamp(),
        "last_move_at": datetime.utcnow().timestamp(),
        "history": [],
        "message_id": None,
        "mode": "pve",
        "level": level
    }
    await games_col.insert_one(game)
    kb = board_kb(gid)
    sent = await message.reply(f"🤖 PvE ({level}) started. Game ID: `{gid}`\n\n{board_to_text(board)}", reply_markup=kb)
    await games_col.update_one({"_id": gid}, {"$set": {"message_id": sent.message_id}})
    # store message mapping optional
    # Bot moves handled after player moves (see move handler)

# ---------------- Move handler ----------------
@app.on_callback_query(filters.regex(r"^move\|"))
async def cb_move(_, query: CallbackQuery):
    _, gid, col_s = query.data.split("|")
    col = int(col_s)
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.", show_alert=True)
    if g["status"] != "active":
        return await query.answer("Game not active.", show_alert=True)
    uid = query.from_user.id
    if uid != g["turn"]:
        return await query.answer("Not your turn!", show_alert=True)
    board = g["board"]
    # determine piece: players[0] -> X, players[1] -> O
    piece = P1_SYMBOL if uid == g["players"][0] else P2_SYMBOL
    if not drop_piece(board, col, piece):
        return await query.answer("Column is full!", show_alert=True)
    # record history
    g["history"].append({"by": uid, "col": col, "piece": piece, "ts": datetime.utcnow().timestamp()})
    g["board"] = board
    g["last_move_at"] = datetime.utcnow().timestamp()
    # check win/draw
    win = check_winner(board)
    if win == piece:
        # winner is uid
        opponent = g["players"][0] if uid == g["players"][1] else g["players"][1]
        # update players
        if opponent != 0:  # if opponent is human
            await update_player_on_finish(uid, opponent, draw=False)
        else:
            # vs bot: award win to player (no elo change for bot)
            await ensure_player(uid)
            await players_col.update_one({"_id": uid}, {"$inc": {"wins": 1}}, upsert=True)
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status": "finished", "winner": uid, "ended_at": datetime.utcnow().timestamp(), "last_move_at": g["last_move_at"], "history": g["history"]}})
        text = f"🏆 Game `{gid}` finished!\nWinner: <a href='tg://user?id={uid}'>player</a>\n\n{board_to_text(board)}"
        try:
            if g.get("message_id"):
                await app.edit_message_text(g["chat_id"], g["message_id"], text, reply_markup=board_kb(gid, active=False))
            else:
                await app.send_message(g["chat_id"], text)
        except:
            pass
        return await query.answer("You won!")
    if win == "DRAW":
        # draw
        p1, p2 = g["players"][0], g["players"][1]
        if p2 != 0:
            await update_player_on_finish(p1, p2, draw=True)
        else:
            # vs bot draw: increment draw for player only
            await players_col.update_one({"_id": p1}, {"$inc": {"draws": 1}}, upsert=True)
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status": "finished", "winner": None, "ended_at": datetime.utcnow().timestamp(), "last_move_at": g["last_move_at"], "history": g["history"]}})
        text = f"🤝 Game `{gid}` ended in a draw.\n\n{board_to_text(board)}"
        try:
            if g.get("message_id"):
                await app.edit_message_text(g["chat_id"], g["message_id"], text, reply_markup=board_kb(gid, active=False))
            else:
                await app.send_message(g["chat_id"], text)
        except:
            pass
        return await query.answer("Draw!")
    # switch turn
    next_turn = g["players"][1] if uid == g["players"][0] else g["players"][0]
    await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": next_turn, "last_move_at": g["last_move_at"], "history": g["history"]}})
    # update board message
    text = f"🎮 Game `{gid}`\n\n{board_to_text(board)}\nTurn: <a href='tg://user?id={next_turn}'>player</a>"
    try:
        if g.get("message_id"):
            await app.edit_message_text(g["chat_id"], g["message_id"], text, reply_markup=board_kb(gid))
        else:
            sent = await app.send_message(g["chat_id"], text, reply_markup=board_kb(gid))
            await games_col.update_one({"_id": gid}, {"$set": {"message_id": sent.message_id}})
    except:
        pass
    await query.answer("Move registered.")
    # if pve and it's bot's turn then schedule bot move
    g2 = await games_col.find_one({"_id": gid})
    if g2["mode"] == "pve" and g2["players"][1] == 0 and g2["turn"] == 0 and g2["status"] == "active":
        asyncio.create_task(bot_move_task(gid))

async def bot_move_task(gid: str):
    await asyncio.sleep(random.uniform(0.8, 1.8))
    g = await games_col.find_one({"_id": gid})
    if not g or g["status"] != "active": return
    board = g["board"]
    level = g.get("level","easy")
    col = ai_choose(board, level)
    if col is None:
        return
    drop_piece(board, col, P2_SYMBOL)
    g["history"].append({"by": 0, "col": col, "piece": P2_SYMBOL, "ts": datetime.utcnow().timestamp()})
    g["last_move_at"] = datetime.utcnow().timestamp()
    # check
    win = check_winner(board)
    if win == P2_SYMBOL:
        # bot wins
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status":"finished", "winner": 0, "ended_at": datetime.utcnow().timestamp(), "history": g["history"]}})
        try:
            if g.get("message_id"):
                await app.edit_message_text(g["chat_id"], g["message_id"], f"🤖 Bot wins in `{gid}`\n\n{board_to_text(board)}", reply_markup=board_kb(gid, active=False))
            else:
                await app.send_message(g["chat_id"], f"🤖 Bot wins in `{gid}`\n\n{board_to_text(board)}")
        except:
            pass
        return
    if win == "DRAW":
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status":"finished", "winner": None, "ended_at": datetime.utcnow().timestamp(), "history": g["history"]}})
        try:
            if g.get("message_id"):
                await app.edit_message_text(g["chat_id"], g["message_id"], f"🤝 Draw vs Bot in `{gid}`\n\n{board_to_text(board)}", reply_markup=board_kb(gid, active=False))
            else:
                await app.send_message(g["chat_id"], f"🤝 Draw vs Bot in `{gid}`\n\n{board_to_text(board)}")
        except:
            pass
        return
    # switch to player
    await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": g["players"][0], "last_move_at": g["last_move_at"], "history": g["history"]}})
    try:
        if g.get("message_id"):
            await app.edit_message_text(g["chat_id"], g["message_id"], f"🎮 Game `{gid}`\n\n{board_to_text(board)}\nYour turn", reply_markup=board_kb(gid))
    except:
        pass

# ---------------- resign / rematch / undo / replay ----------------
@app.on_callback_query(filters.regex(r"^resign\|"))
async def cb_resign(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.")
    uid = query.from_user.id
    if uid not in g["players"]:
        return await query.answer("You are not a player in this game.")
    opponent = g["players"][0] if uid == g["players"][1] else g["players"][1]
    # update stats
    if opponent != 0:
        await update_player_on_finish(opponent, uid, draw=False)
    else:
        await ensure_player(opponent)
    await games_col.update_one({"_id": gid}, {"$set": {"status":"finished", "winner": opponent, "ended_at": datetime.utcnow().timestamp()}})
    try:
        if g.get("message_id"):
            await app.edit_message_text(g["chat_id"], g["message_id"], f"🏳️ {query.from_user.mention} resigned.\nWinner: <a href='tg://user?id={opponent}'>player</a>")
    except:
        pass
    await query.answer("You resigned.")

@app.on_callback_query(filters.regex(r"^rematch\|"))
async def cb_rematch(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.")
    players = g["players"]
    # create new game doc
    new_gid = str(uuid.uuid4())
    doc = {
        "_id": new_gid,
        "chat_id": g["chat_id"],
        "players": players,
        "board": new_board(),
        "turn": players[0],
        "status": "active",
        "created_at": datetime.utcnow().timestamp(),
        "last_move_at": datetime.utcnow().timestamp(),
        "history": [],
        "message_id": None,
        "mode": g.get("mode", "pvp"),
        "level": g.get("level")
    }
    await games_col.insert_one(doc)
    kb = board_kb(new_gid)
    try:
        await app.send_message(g["chat_id"], f"🔁 Rematch started! Game `{new_gid}`", reply_markup=kb)
    except:
        pass
    await query.answer("Rematch created.")

@app.on_callback_query(filters.regex(r"^undo\|"))
async def cb_undo(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.")
    if not g["history"]:
        return await query.answer("No moves to undo.")
    last = g["history"][-1]
    # only the player who made the last move may undo
    if query.from_user.id != last["by"]:
        return await query.answer("Only the player who made the last move can undo.", show_alert=True)
    # pop and rebuild board
    g["history"].pop()
    board = new_board()
    for mv in g["history"]:
        drop_piece(board, mv["col"], mv["piece"])
    turn = last["by"]
    await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": turn, "history": g["history"], "last_move_at": datetime.utcnow().timestamp()}})
    try:
        if g.get("message_id"):
            await app.edit_message_text(g["chat_id"], g["message_id"], f"↩ Undo by <a href='tg://user?id={turn}'>player</a>\n\n{board_to_text(board)}", reply_markup=board_kb(gid))
    except:
        pass
    await query.answer("Move undone.")

@app.on_callback_query(filters.regex(r"^replay\|"))
async def cb_replay(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g or not g["history"]:
        return await query.answer("No history to replay.")
    history = g["history"]
    theme_board = g["board"]
    # We'll create ephemeral message and step through history with Next/Prev (simple approach)
    msg = await query.message.reply_text(f"▶️ Starting replay for `{gid}`")
    idx = 0
    board = new_board()
    async def show_step(i):
        b = new_board()
        for mv in history[:i+1]:
            drop_piece(b, mv["col"], mv["piece"])
        await msg.edit_text(f"Replay `{gid}` — step {i+1}/{len(history)}\n\n{board_to_text(b)}")
    await show_step(0)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Prev", callback_data=f"rprev|{gid}|{msg.message_id}|0"), InlineKeyboardButton("Next ▶", callback_data=f"rnext|{gid}|{msg.message_id}|0")]])
    await msg.edit_reply_markup(kb)
    await query.answer("Replay started. Use buttons on the replay message.")

@app.on_callback_query(filters.regex(r"^rnext\|"))
async def cb_rnext(_, query: CallbackQuery):
    _, gid, mid_s, idx_s = query.data.split("|")
    mid = int(mid_s); idx = int(idx_s)
    try:
        msg = await app.get_messages(query.message.chat.id, mid)
    except:
        return await query.answer("Replay expired.")
    g = await games_col.find_one({"_id": gid})
    if not g: return await query.answer("Game gone.")
    history = g["history"]
    idx = min(len(history)-1, idx+1)
    b = new_board()
    for mv in history[:idx+1]:
        drop_piece(b, mv["col"], mv["piece"])
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Prev", callback_data=f"rprev|{gid}|{mid}|{idx}"), InlineKeyboardButton("Next ▶", callback_data=f"rnext|{gid}|{mid}|{idx}")]])
    await app.edit_message_text(query.message.chat.id, mid, f"Replay `{gid}` — step {idx+1}/{len(history)}\n\n{board_to_text(b)}", reply_markup=kb)
    await query.answer()

@app.on_callback_query(filters.regex(r"^rprev\|"))
async def cb_rprev(_, query: CallbackQuery):
    _, gid, mid_s, idx_s = query.data.split("|")
    mid = int(mid_s); idx = int(idx_s)
    try:
        msg = await app.get_messages(query.message.chat.id, mid)
    except:
        return await query.answer("Replay expired.")
    g = await games_col.find_one({"_id": gid})
    if not g: return await query.answer("Game gone.")
    history = g["history"]
    idx = max(0, idx-1)
    b = new_board()
    for mv in history[:idx+1]:
        drop_piece(b, mv["col"], mv["piece"])
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Prev", callback_data=f"rprev|{gid}|{mid}|{idx}"), InlineKeyboardButton("Next ▶", callback_data=f"rnext|{gid}|{mid}|{idx}")]])
    await app.edit_message_text(query.message.chat.id, mid, f"Replay `{gid}` — step {idx+1}/{len(history)}\n\n{board_to_text(b)}", reply_markup=kb)
    await query.answer()

# ---------------- Tournament (simple single-elim) ----------------
@app.on_message(filters.command("tourney"))
async def cmd_tourney(_, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply("Usage: /tourney create <name> | join <id> | start <id> | status <id>")
    action = parts[1].lower()
    if action == "create":
        if len(parts) < 3:
            return await message.reply("Usage: /tourney create <name>")
        name = " ".join(parts[2:])
        tid = str(uuid.uuid4())[:8]
        doc = {"_id": tid, "name": name, "chat_id": message.chat.id, "owner": message.from_user.id, "players": [], "status": "open", "created_at": datetime.utcnow().timestamp(), "matches": []}
        await tourn_col.insert_one(doc)
        await message.reply(f"Tournament '{name}' created. ID: {tid}\nPlayers: /tourney join {tid}")
    elif action == "join":
        if len(parts) < 3:
            return await message.reply("Usage: /tourney join <id>")
        tid = parts[2]
        t = await tourn_col.find_one({"_id": tid})
        if not t:
            return await message.reply("Tournament not found.")
        if t["status"] != "open":
            return await message.reply("Tournament not open.")
        if message.from_user.id in t["players"]:
            return await message.reply("You already joined.")
        await tourn_col.update_one({"_id": tid}, {"$push": {"players": message.from_user.id}})
        await message.reply("You joined the tournament.")
    elif action == "start":
        if len(parts) < 3:
            return await message.reply("Usage: /tourney start <id>")
        tid = parts[2]
        t = await tourn_col.find_one({"_id": tid})
        if not t:
            return await message.reply("Not found.")
        if t["owner"] != message.from_user.id:
            return await message.reply("Only owner can start.")
        players = t.get("players", [])
        if len(players) < 2:
            return await message.reply("Not enough players.")
        random.shuffle(players)
        matches = []
        while len(players) >= 2:
            a = players.pop(); b = players.pop()
            gid = str(uuid.uuid4())
            doc = {"_id": gid, "chat_id": t["chat_id"], "players":[a,b], "board": new_board(), "turn": a, "status":"pending", "created_at": datetime.utcnow().timestamp(), "last_move_at": datetime.utcnow().timestamp(), "history": [], "message_id": None, "mode":"pvp", "tourney_id": tid}
            await games_col.insert_one(doc)
            matches.append(gid)
            # notify
            try:
                await app.send_message(t["chat_id"], f"Tournament match: <a href='tg://user?id={a}'>A</a> vs <a href='tg://user?id={b}'>B</a>\nGame ID `{gid}`")
            except:
                pass
        await tourn_col.update_one({"_id": tid}, {"$set": {"status":"running", "matches": matches}})
        await message.reply(f"Tournament started with {len(matches)} matches.")
    elif action == "status":
        if len(parts) < 3:
            return await message.reply("Usage: /tourney status <id>")
        tid = parts[2]
        t = await tourn_col.find_one({"_id": tid})
        if not t:
            return await message.reply("Not found.")
        await message.reply(f"Tourney '{t['name']}' status: {t['status']} Players: {len(t.get('players',[]))} Matches: {len(t.get('matches',[]))}")

# ---------------- Spectate ----------------
@app.on_message(filters.command("spectate"))
async def cmd_jspectate(_, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply("Usage: /spectate <game_id>")
    gid = parts[1].strip()
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await message.reply("Game not found.")
    await message.reply(f"👀 Spectating `{gid}`\nStatus: {g['status']}\n\n{board_to_text(g['board'])}", reply_markup=spectator_kb(gid))

# --------------- Start background worker ---------------
async def startup_worker():
    # ensure background cleanup tasks are scheduled (they already are via scheduler)
    # but we also run a light pve worker to ensure bot moves aren't missed
    async def pve_checker():
        while True:
            cursor = games_col.find({"mode":"pve","status":"active"})
            async for g in cursor:
                if g["players"][1] == 0 and g["turn"] == 0:
                    # bot's turn
                    asyncio.create_task(bot_move_task(g["_id"]))
            await asyncio.sleep(2)
    asyncio.create_task(pve_checker())

