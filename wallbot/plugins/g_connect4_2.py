# connect4_ultimate.py
"""
Advanced Connect 4 Bot (Pyrogram + motor + MongoDB)
Features:
 - PvP (group/private) and PvE (vs bot) with Easy/Medium/Hard (minimax)
 - Spectator mode: /spectate <game_id>
 - Undo (one-step) and Replay of games
 - Tournament mode (create/join/start) in group chats
 - Custom emojis/themes for board rendering
 - Persistent games + players + tournaments in MongoDB
 - Auto-cleanup inactive games and error handling
"""

import asyncio
import uuid
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from config import DB_URL
from wallbot import wbot as app

# ------------------- CONFIG -------------------

DB_NAME = "connect4_ultimate"

# Game constants
ROWS, COLS = 6, 7
DEFAULT_THEME = {
    "empty": "⚪",
    "p1": "🔴",  # represents X
    "p2": "🟡"   # represents O / bot
}
GAME_TIMEOUT_MINUTES = 15   # inactivity -> auto-forfeit / cleanup
MINIMAX_DEPTH_MEDIUM = 3
MINIMAX_DEPTH_HARD = 5
# ----------------------------------------------

mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["games"]
players_col = db["players"]
tourn_col = db["tournaments"]
themes_col = db["themes"]

scheduler = AsyncIOScheduler(timezone="UTC")
scheduler.start()

# ----------------- UTILITIES ------------------
def new_board() -> List[List[str]]:
    return [[" " for _ in range(COLS)] for _ in range(ROWS)]

def board_to_text(board: List[List[str]], theme: dict) -> str:
    sym = { " ": theme["empty"], "X": theme["p1"], "O": theme["p2"] }
    lines = ["".join(sym[cell] for cell in row) for row in board]
    header = " ".join(str(i+1) for i in range(COLS))
    return f"Cols: {header}\n" + "\n".join(lines)

def possible_moves(board: List[List[str]]) -> List[int]:
    return [c for c in range(COLS) if board[0][c] == " "]

def drop_piece(board: List[List[str]], col: int, piece: str) -> bool:
    for r in range(ROWS-1, -1, -1):
        if board[r][col] == " ":
            board[r][col] = piece
            return True
    return False

def board_full(board: List[List[str]]) -> bool:
    return all(cell != " " for row in board for cell in row)

def check_winner(board: List[List[str]]) -> Optional[str]:
    # returns "X" or "O" or "DRAW" or None
    for r in range(ROWS):
        for c in range(COLS-3):
            if board[r][c] != " " and all(board[r][c+i] == board[r][c] for i in range(4)):
                return board[r][c]
    for c in range(COLS):
        for r in range(ROWS-3):
            if board[r][c] != " " and all(board[r+i][c] == board[r][c] for i in range(4)):
                return board[r][c]
    for r in range(ROWS-3):
        for c in range(COLS-3):
            if board[r][c] != " " and all(board[r+i][c+i] == board[r][c] for i in range(4)):
                return board[r][c]
    for r in range(3, ROWS):
        for c in range(COLS-3):
            if board[r][c] != " " and all(board[r-i][c+i] == board[r][c] for i in range(4)):
                return board[r][c]
    if board_full(board):
        return "DRAW"
    return None

def render_kb(gid: str, active: bool = True) -> InlineKeyboardMarkup:
    # top row: columns 1..7
    row = []
    for c in range(COLS):
        cb = f"move|{gid}|{c}" if active else f"noop|{gid}|{c}"
        row.append(InlineKeyboardButton(str(c+1), callback_data=cb))
    # controls
    ctrl = [
        InlineKeyboardButton("↺ Undo", callback_data=f"undo|{gid}"),
        InlineKeyboardButton("⟳ Replay", callback_data=f"replay|{gid}"),
        InlineKeyboardButton("🔁 Rematch", callback_data=f"rematch|{gid}")
    ]
    return InlineKeyboardMarkup([row, ctrl, [InlineKeyboardButton("👀 Spectate", callback_data=f"spectate|{gid}")]])

# ----------------- DB HELPERS -----------------
async def ensure_player(uid: int) -> Dict[str, Any]:
    p = await players_col.find_one({"_id": uid})
    if not p:
        p = {"_id": uid, "wins": 0, "losses": 0, "draws": 0, "elo": 1200, "games": 0}
        await players_col.insert_one(p)
    return p

async def update_player_result(winner: Optional[int], loser: Optional[int], draw=False):
    if draw:
        if winner is None and loser is None:
            return
    if draw:
        # both players increment draws
        if winner is not None: await players_col.update_one({"_id": winner}, {"$inc": {"draws": 1, "games": 1}}, upsert=True)
        if loser  is not None: await players_col.update_one({"_id": loser}, {"$inc": {"draws": 1, "games": 1}}, upsert=True)
        return
    # winner & loser numeric
    await ensure_player(winner)
    await ensure_player(loser)
    # simple elo change
    w_doc = await players_col.find_one({"_id": winner})
    l_doc = await players_col.find_one({"_id": loser})
    # elo expected
    def exp(a,b): return 1/(1+10**((b-a)/400))
    k = 32
    e_w = exp(w_doc["elo"], l_doc["elo"])
    e_l = exp(l_doc["elo"], w_doc["elo"])
    new_w = int(w_doc["elo"] + k*(1 - e_w))
    new_l = int(l_doc["elo"] + k*(0 - e_l))
    await players_col.update_one({"_id": winner}, {"$inc": {"wins":1, "games":1}, "$set": {"elo": new_w}})
    await players_col.update_one({"_id": loser}, {"$inc": {"losses":1, "games":1}, "$set": {"elo": new_l}})

# themes table with a default
async def get_theme(chat_id: int) -> Dict[str,str]:
    t = await themes_col.find_one({"_id": chat_id})
    if not t:
        return DEFAULT_THEME
    return {"empty": t.get("empty", DEFAULT_THEME["empty"]), "p1": t.get("p1", DEFAULT_THEME["p1"]), "p2": t.get("p2", DEFAULT_THEME["p2"])}

async def set_theme(chat_id: int, empty: str, p1: str, p2: str):
    await themes_col.update_one({"_id": chat_id}, {"$set": {"empty": empty, "p1": p1, "p2": p2}}, upsert=True)

# ----------------- AI (Minimax) ----------------
# evaluation heuristics similar to earlier: centre preference + window scoring
def score_window(window: List[str], piece: str) -> int:
    score = 0
    opp = "O" if piece == "X" else "X"
    if window.count(piece) == 4:
        score += 1000
    elif window.count(piece) == 3 and window.count(" ") == 1:
        score += 50
    elif window.count(piece) == 2 and window.count(" ") == 2:
        score += 10
    if window.count(opp) == 3 and window.count(" ") == 1:
        score -= 80
    return score

def board_score(board: List[List[str]], piece: str) -> int:
    score = 0
    center_array = [board[r][COLS//2] for r in range(ROWS)]
    score += center_array.count(piece) * 6
    # horizontal
    for r in range(ROWS):
        row = board[r]
        for c in range(COLS-3):
            score += score_window(row[c:c+4], piece)
    # vertical
    for c in range(COLS):
        col = [board[r][c] for r in range(ROWS)]
        for r in range(ROWS-3):
            score += score_window(col[r:r+4], piece)
    # diags
    for r in range(ROWS-3):
        for c in range(COLS-3):
            window = [board[r+i][c+i] for i in range(4)]
            score += score_window(window, piece)
    for r in range(3, ROWS):
        for c in range(COLS-3):
            window = [board[r-i][c+i] for i in range(4)]
            score += score_window(window, piece)
    return score

def minimax(board: List[List[str]], depth:int, alpha:int, beta:int, maximizing:bool, piece:str) -> Tuple[int, Optional[int]]:
    valid_cols = possible_moves(board)
    terminal = check_winner(board)
    if depth == 0 or terminal is not None:
        if terminal == piece:
            return (10**7, None)
        elif terminal == ("O" if piece == "X" else "X"):
            return (-10**7, None)
        elif terminal == "DRAW":
            return (0, None)
        else:
            return (board_score(board, piece), None)
    if maximizing:
        value = -10**9
        best_col = random.choice(valid_cols)
        for col in valid_cols:
            bcopy = [row[:] for row in board]
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
        opp = "O" if piece == "X" else "X"
        best_col = random.choice(valid_cols)
        for col in valid_cols:
            bcopy = [row[:] for row in board]
            drop_piece(bcopy, col, opp)
            new_score, _ = minimax(bcopy, depth-1, alpha, beta, True, piece)
            if new_score < value:
                value, best_col = new_score, col
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value, best_col

# entry AI mover
def ai_choose(board: List[List[str]], level:str) -> int:
    empty = possible_moves(board)
    if level == "easy":
        return random.choice(empty)
    if level == "medium":
        # try to win or block immediate, else one-step minimax small depth
        for c in empty:
            bcopy = [row[:] for row in board]
            drop_piece(bcopy, c, "O")
            if check_winner(bcopy) == "O":
                return c
        for c in empty:
            bcopy = [row[:] for row in board]
            drop_piece(bcopy, c, "X")
            if check_winner(bcopy) == "X":
                return c
        _, col = minimax(board, MINIMAX_DEPTH_MEDIUM, -10**9, 10**9, True, "O")
        return col if col is not None else random.choice(empty)
    # hard
    _, col = minimax(board, MINIMAX_DEPTH_HARD, -10**9, 10**9, True, "O")
    return col if col is not None else random.choice(empty)

# ----------------- GAME LIFECYCLE ----------------
# Games are stored in MongoDB with fields:
# _id, chat_id, players [p1,p2], board, turn (player id or 0 for bot), status, created_at, last_move_at, history(list), theme
# We'll also maintain a simple in-memory mapping of message_id -> game_id for in-chat message edits (best-effort)
msg_to_game: Dict[int, str] = {}   # message_id -> gid

# Auto cleanup scheduled job: close games inactive beyond timeout
async def cleanup_job():
    cutoff = datetime.utcnow() - timedelta(minutes=GAME_TIMEOUT_MINUTES)
    cursor = games_col.find({"status": "active", "last_move_at": {"$lt": cutoff.timestamp()}})
    async for g in cursor:
        gid = g["_id"]
        # award win to opponent of turn
        turn = g["turn"]
        players = g["players"]
        if len(players) >= 2:
            winner = players[0] if players[1] == turn else players[1]
            await update_player_result(winner, turn, draw=False)  # uses same function
        await games_col.update_one({"_id": gid}, {"$set": {"status": "forfeited", "ended_at": datetime.utcnow().timestamp()}})

scheduler.add_job(lambda: asyncio.create_task(cleanup_job()), "interval", minutes=2)

# ----------------- COMMANDS -----------------
@app.on_message(filters.command("start"))
async def cmd_start(_, message: Message):
    await message.reply(
        "🎮 Connect 4 Ultimate\nCommands:\n"
        "/challenge (reply to user) — challenge in chat\n"
        "/pve <easy|medium|hard> — play private vs bot\n        /spectate <game_id> — view a game's board\n"
        "/undo — undo last move (only allowed immediately by previous mover)\n"
        "/replay <game_id> — replay a finished game step-by-step\n"
        "/theme set <empty> <p1> <p2> — set emojis for this chat\n"
        "/tourney create <name> — create tournament (group)\n/tourney join <id> — join\n/tourney start <id> — start tournament\n"
        "/profile — show your stats\n/leaderboard — top players by ELO"
    )

# ----------------- PvP Challenge -----------------
@app.on_message(filters.command("c4challenge") & (filters.group | filters.private))
async def cmd_ccehallenge(_, message: Message):
    # must reply to a user or provide username
    if not message.reply_to_message and len(message.command) < 2:
        return await message.reply("Reply to someone or use `/challenge @username`")
    try:
        target = message.reply_to_message.from_user if message.reply_to_message else (await app.get_users(message.command[1]))
    except Exception:
        return await message.reply("Couldn't find that user.")
    if target.id == message.from_user.id:
        return await message.reply("You can't challenge yourself.")
    gid = str(uuid.uuid4())
    board = new_board()
    theme = await get_theme(message.chat.id)
    game_doc = {
        "_id": gid,
        "chat_id": message.chat.id,
        "players": [message.from_user.id, target.id],
        "board": board,
        "turn": message.from_user.id,
        "status": "pending",
        "created_at": datetime.utcnow().timestamp(),
        "last_move_at": datetime.utcnow().timestamp(),
        "history": [],  # list of moves: {by, col, piece, ts}
        "theme": theme,
        "message_id": None
    }
    await games_col.insert_one(game_doc)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"accept|{gid}|{target.id}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"decline|{gid}|{target.id}")
    ]])
    sent = await message.reply_text(
        f"🎮 Challenge created (ID `{gid}`)\n{message.from_user.mention} ➜ {target.mention}\n{target.mention}, press Accept to start.",
        reply_markup=kb
    )
    await games_col.update_one({"_id": gid}, {"$set": {"message_id": sent.message_id}})

@app.on_callback_query(filters.regex(r"^accept\|"))
async def cb_accept(_, query: CallbackQuery):
    _, gid, expected_id = query.data.split("|")
    if query.from_user.id != int(expected_id):
        return await query.answer("Only the challenged user can accept.", show_alert=True)
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.", show_alert=True)
    if g["status"] != "pending":
        return await query.answer("Game already started or canceled.", show_alert=True)
    await ensure_player(g["players"][0]); await ensure_player(g["players"][1])
    await games_col.update_one({"_id": gid}, {"$set": {"status": "active", "last_move_at": datetime.utcnow().timestamp()}})
    theme = g.get("theme", DEFAULT_THEME)
    text = f"🎮 Game `{gid}` started!\n\n{board_to_text(g['board'], theme)}\n\nTurn: <a href='tg://user?id={g['turn']}'>player</a>"
    kb = render_kb(gid)
    # edit the original message if present else send new
    try:
        if g.get("message_id"):
            await query.message.edit(text, reply_markup=kb)
            msg_id = g["message_id"]
        else:
            m = await query.message.reply(text, reply_markup=kb)
            msg_id = m.message_id
        msg_to_game[msg_id] = gid
        await games_col.update_one({"_id": gid}, {"$set": {"message_id": msg_id}})
    except Exception:
        await query.message.reply(text, reply_markup=kb)
    await query.answer("Game started!")

@app.on_callback_query(filters.regex(r"^decline\|"))
async def cb_decline(_, query: CallbackQuery):
    _, gid, expected_id = query.data.split("|")
    if query.from_user.id != int(expected_id):
        return await query.answer("Only challenged user can decline.", show_alert=True)
    await games_col.delete_one({"_id": gid})
    await query.message.edit("❌ Challenge declined.")
    await query.answer("Declined.")

# ----------------- PvE (private) -----------------
@app.on_message(filters.command("c4pve") & filters.private)
async def cmd_pvc4e(_, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /pve easy|medium|hard")
    level = message.command[1].lower()
    if level not in ("easy","medium","hard"):
        return await message.reply("Choose easy/medium/hard")
    gid = str(uuid.uuid4())
    board = new_board()
    theme = await get_theme(message.chat.id)
    game_doc = {
        "_id": gid, "chat_id": message.chat.id, "players":[message.from_user.id, 0],
        "board": board, "turn": message.from_user.id, "status":"active",
        "created_at": datetime.utcnow().timestamp(), "last_move_at": datetime.utcnow().timestamp(),
        "history": [], "theme": theme, "pve_level": level, "message_id": None
    }
    await games_col.insert_one(game_doc)
    kb = render_kb(gid)
    sent = await message.reply(f"🤖 PvE `{level}` started. Game ID: `{gid}`\n{board_to_text(board, theme)}", reply_markup=kb)
    await games_col.update_one({"_id": gid}, {"$set": {"message_id": sent.message_id}})
    msg_to_game[sent.message_id] = gid

# ----------------- Move Handler -----------------
@app.on_callback_query(filters.regex(r"^move\|"))
async def cb_move(_, query: CallbackQuery):
    _, gid, col_s = query.data.split("|")
    col = int(col_s)
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.", show_alert=True)
    if g["status"] != "active":
        return await query.answer("Game is not active.", show_alert=True)
    user = query.from_user
    # turn validation
    if g["turn"] != user.id:
        return await query.answer("Not your turn!", show_alert=True)
    board = g["board"]
    if board[0][col] != " ":
        return await query.answer("Column is full!", show_alert=True)
    # place
    piece = "X" if user.id == g["players"][0] else "O"
    drop_piece(board, col, piece)
    g["history"].append({"by": user.id, "col": col, "piece": piece, "ts": datetime.utcnow().timestamp()})
    g["last_move_at"] = datetime.utcnow().timestamp()
    # winner check
    win = check_winner(board)
    theme = g.get("theme", DEFAULT_THEME)
    if win == "X" or win == "O":
        # map piece to player id
        winner_id = g["players"][0] if win == "X" else g["players"][1]
        loser_id = g["players"][1] if winner_id == g["players"][0] else g["players"][0]
        await update_player_result(winner_id, loser_id, draw=False)
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status":"finished", "winner": winner_id, "ended_at": datetime.utcnow().timestamp(), "history": g["history"]}})
        text = f"🏆 Game `{gid}` finished!\nWinner: <a href='tg://user?id={winner_id}'>player</a>\n\n{board_to_text(board, theme)}"
        try:
            if g.get("message_id"):
                await query.message.edit(text, reply_markup=render_kb(gid, active=False))
            else:
                await query.message.reply(text, reply_markup=render_kb(gid, active=False))
        except:
            pass
        return await query.answer("You won!")
    elif win == "DRAW":
        # draw
        await update_player_result(g["players"][0], g["players"][1], draw=True)
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status":"finished", "winner": None, "ended_at": datetime.utcnow().timestamp(), "history": g["history"]}})
        text = f"🤝 Game `{gid}` ended in a draw.\n\n{board_to_text(board, theme)}"
        try:
            if g.get("message_id"):
                await query.message.edit(text, reply_markup=render_kb(gid, active=False))
            else:
                await query.message.reply(text, reply_markup=render_kb(gid, active=False))
        except:
            pass
        return await query.answer("Draw!")
    # switch turn
    # for pve, bot is players[1]==0
    next_turn = g["players"][1] if user.id == g["players"][0] else g["players"][0]
    await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": next_turn, "last_move_at": g["last_move_at"], "history": g["history"]}})
    # edit board message
    text = f"🎮 Game `{gid}`\n\n{board_to_text(board, theme)}\n\nTurn: <a href='tg://user?id={next_turn}'>player</a>"
    try:
        if g.get("message_id"):
            await query.message.edit(text, reply_markup=render_kb(gid))
        else:
            await query.message.reply(text, reply_markup=render_kb(gid))
    except:
        pass
    await query.answer("Move played.")
    # If pve and it's bot's turn, schedule bot move
    g2 = await games_col.find_one({"_id": gid})
    if g2["players"][1] == 0 and g2["turn"] == 0 and g2["status"] == "active":
        asyncio.create_task(do_bot_move(gid))

# bot auto-move for pve
async def do_bot_move(gid: str):
    await asyncio.sleep(1.0 + random.random()*1.5)
    g = await games_col.find_one({"_id": gid})
    if not g or g["status"] != "active": return
    board = g["board"]
    level = g.get("pve_level", "easy")
    col = ai_choose(board, level)
    if col is None:
        return
    drop_piece(board, col, "O")
    g["history"].append({"by": 0, "col": col, "piece": "O", "ts": datetime.utcnow().timestamp()})
    g["last_move_at"] = datetime.utcnow().timestamp()
    # check
    win = check_winner(board)
    theme = g.get("theme", DEFAULT_THEME)
    if win == "O":
        # bot wins
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status":"finished", "winner": 0, "ended_at": datetime.utcnow().timestamp(), "history": g["history"]}})
        try:
            if g.get("message_id"):
                await app.edit_message_text(g["chat_id"], g["message_id"], f"🤖 Bot wins in game `{gid}`\n\n{board_to_text(board, theme)}", reply_markup=render_kb(gid, active=False))
            else:
                await app.send_message(g["chat_id"], f"🤖 Bot wins in game `{gid}`\n\n{board_to_text(board, theme)}")
        except:
            pass
        return
    elif win == "DRAW":
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "status":"finished", "winner": None, "ended_at": datetime.utcnow().timestamp(), "history": g["history"]}})
        try:
            if g.get("message_id"):
                await app.edit_message_text(g["chat_id"], g["message_id"], f"🤝 Draw vs Bot in `{gid}`\n\n{board_to_text(board, theme)}", reply_markup=render_kb(gid, active=False))
            else:
                await app.send_message(g["chat_id"], f"🤝 Draw vs Bot in `{gid}`\n\n{board_to_text(board, theme)}")
        except:
            pass
        return
    # else switch to human
    await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": g["players"][0], "last_move_at": g["last_move_at"], "history": g["history"]}})
    try:
        if g.get("message_id"):
            await app.edit_message_text(g["chat_id"], g["message_id"], f"🎮 Game `{gid}`\n\n{board_to_text(board, theme)}\n\nYour turn", reply_markup=render_kb(gid))
    except:
        pass

# ----------------- Spectator -----------------
@app.on_message(filters.command("spectatec4"))
async def cmd_spec4ctate(_, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /spectate <game_id>")
    gid = message.command[1].strip()
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await message.reply("Game not found.")
    theme = g.get("theme", DEFAULT_THEME)
    text = f"👀 Spectating `{gid}`\nStatus: {g['status']}\n\n{board_to_text(g['board'], theme)}"
    kb = render_kb(gid, active=(g["status"]=="active"))
    await message.reply(text, reply_markup=kb)

# ----------------- Undo (one-step) -----------------
@app.on_callback_query(filters.regex(r"^undo\|"))
async def cb_undo(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g: return await query.answer("Game not found.")
    if g["status"] != "active":
        return await query.answer("Can only undo in active games.")
    # only the player who made the last move can request undo immediately
    if not g["history"]:
        return await query.answer("No moves to undo.")
    last = g["history"][-1]
    if query.from_user.id != last["by"]:
        return await query.answer("Only the player who made the last move can undo it.", show_alert=True)
    # pop last move and revert board
    g["history"].pop()
    # rebuild board from history
    board = new_board()
    for mv in g["history"]:
        drop_piece(board, mv["col"], mv["piece"])
    # revert turn to the player who made undone move
    prev_turn = last["by"]
    await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": prev_turn, "history": g["history"], "last_move_at": datetime.utcnow().timestamp()}})
    theme = g.get("theme", DEFAULT_THEME)
    text = f"↺ Undo performed by <a href='tg://user?id={prev_turn}'>player</a>\n\n{board_to_text(board, theme)}"
    try:
        if g.get("message_id"):
            await query.message.edit(text, reply_markup=render_kb(gid))
        else:
            await query.message.reply(text, reply_markup=render_kb(gid))
    except:
        pass
    await query.answer("Move undone.")

# ----------------- Replay -----------------
@app.on_callback_query(filters.regex(r"^replay\|"))
async def cb_replay(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.")
    history = g.get("history", [])
    theme = g.get("theme", DEFAULT_THEME)
    if not history:
        return await query.answer("No history.")
    # post the replay steps as separate messages (or one message with step buttons)
    # for brevity we'll do stepwise edited message with Next/Prev controls
    # We'll create a simple ephemeral message and run a small stepper
    msg = await query.message.reply_text("▶️ Starting replay...")
    idx = 0
    board = new_board()
    async def update_step(i):
        b = new_board()
        for mv in history[:i+1]:
            drop_piece(b, mv["col"], mv["piece"])
        await msg.edit(f"Replay `{gid}` — step {i+1}/{len(history)}\n\n{board_to_text(b, theme)}")
    await update_step(idx)
    # quick manual stepper: react to Next/Prev via inline buttons - we'll send buttons and handle interaction for 60s
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Prev", callback_data=f"rprev|{gid}|{msg.message_id}|{0}"), InlineKeyboardButton("Next ▶️", callback_data=f"rnext|{gid}|{msg.message_id}|{0}")],
    ])
    await msg.edit_reply_markup(kb)
    await query.answer("Replay started. Use buttons on the replay message.")

# handlers for replay next/prev (embed message_id for reference)
@app.on_callback_query(filters.regex(r"^rnext\|"))
async def cb_rnext(_, query: CallbackQuery):
    _, gid, mid_s, idx_s = query.data.split("|")
    mid = int(mid_s); idx = int(idx_s)
    m = query  # reuse query info
    # fetch message
    try:
        msg = await app.get_messages(query.message.chat.id, mid)
    except:
        return await query.answer("Replay expired.")
    g = await games_col.find_one({"_id": gid})
    if not g: return await query.answer("Game gone.")
    history = g.get("history", [])
    theme = g.get("theme", DEFAULT_THEME)
    idx = min(len(history)-1, idx+1)
    b = new_board()
    for mv in history[:idx+1]:
        drop_piece(b, mv["col"], mv["piece"])
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Prev", callback_data=f"rprev|{gid}|{mid}|{idx}"), InlineKeyboardButton("Next ▶️", callback_data=f"rnext|{gid}|{mid}|{idx}")]])
    await app.edit_message_text(query.message.chat.id, mid, f"Replay `{gid}` — step {idx+1}/{len(history)}\n\n{board_to_text(b, theme)}", reply_markup=kb)
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
    history = g.get("history", [])
    theme = g.get("theme", DEFAULT_THEME)
    idx = max(0, idx-1)
    b = new_board()
    for mv in history[:idx+1]:
        drop_piece(b, mv["col"], mv["piece"])
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Prev", callback_data=f"rprev|{gid}|{mid}|{idx}"), InlineKeyboardButton("Next ▶️", callback_data=f"rnext|{gid}|{mid}|{idx}")]])
    await app.edit_message_text(query.message.chat.id, mid, f"Replay `{gid}` — step {idx+1}/{len(history)}\n\n{board_to_text(b, theme)}", reply_markup=kb)
    await query.answer()

# ----------------- Rematch -----------------
@app.on_callback_query(filters.regex(r"^rematch\|"))
async def cb_rematch(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.")
    players = g["players"]
    new_gid = str(uuid.uuid4())
    board = new_board()
    newdoc = {
        "_id": new_gid, "chat_id": g["chat_id"], "players": players, "board": board,
        "turn": players[0], "status": "active", "created_at": datetime.utcnow().timestamp(),
        "last_move_at": datetime.utcnow().timestamp(), "history": [], "theme": g.get("theme", DEFAULT_THEME)
    }
    await games_col.insert_one(newdoc)
    kb = render_kb(new_gid)
    try:
        await app.send_message(g["chat_id"], f"🔁 Rematch started! Game `{new_gid}`", reply_markup=kb)
    except:
        pass
    await query.answer("Rematch created.")

# ----------------- Theme commands -----------------
@app.on_message(filters.command("c4theme") & (filters.group | filters.private))
async def cmdhd_theme(_, message: Message):
    # /theme ssset <empty> <p1> <p2>
    if len(message.command) >= 2 and message.command[1] == "set":
        if len(message.command) != 5:
            return await message.reply("Usage: /theme set <empty> <p1> <p2>  (each is a single emoji/string)")
        empty, p1, p2 = message.command[2], message.command[3], message.command[4]
        await set_theme(message.chat.id, empty, p1, p2)
        await message.reply(f"Theme set for this chat: {empty} {p1} {p2}")
    else:
        th = await get_theme(message.chat.id)
        await message.reply(f"Current theme for this chat: {th['empty']} {th['p1']} {th['p2']}\nSet with: /theme set <empty> <p1> <p2>")

# ----------------- Profile & Leaderboard -----------------
@app.on_message(filters.command("profile"))
async def cmd_profile(_, message: Message):
    uid = message.from_user.id
    p = await players_col.find_one({"_id": uid}) or {"wins":0,"losses":0,"draws":0,"elo":1200,"games":0}
    await message.reply(f"👤 {message.from_user.mention}\nELO: {p.get('elo',1200)}\nW:{p.get('wins',0)} L:{p.get('losses',0)} D:{p.get('draws',0)} Games:{p.get('games',0)}")

@app.on_message(filters.command("c4leaderboard2"))
async def cmd_c4rleaderboard(_, message: Message):
    cur = players_col.find().sort("elo",-1).limit(10)
    lines = ["🏆 Top Players by ELO:"]
    async for p in cur:
        try:
            u = await app.get_users(p["_id"])
            name = u.first_name
        except:
            name = f"User({p['_id']})"
        lines.append(f"{name} — ELO {p.get('elo',1200)} W:{p.get('wins',0)}")
    await message.reply("\n".join(lines))

# ----------------- Tournament System -----------------
# Simple bracketed tournament for groups: create -> join -> start -> bot pairs and posts matches
@app.on_message(filters.command("tourney"))
async def cmd_tourney(_, message: Message):
    # /tourney create <name>
    # /tourney join <id>
    # /tourney start <id>
    if len(message.command) < 2:
        return await message.reply("Usage: /tourney create <name> | join <id> | start <id> | status <id>")
    action = message.command[1]
    if action == "create":
        if len(message.command) < 3:
            return await message.reply("Usage: /tourney create <name>")
        name = " ".join(message.command[2:])
        tid = str(uuid.uuid4())[:8]
        doc = {"_id": tid, "name": name, "chat_id": message.chat.id, "owner": message.from_user.id, "players": [], "status":"open", "created_at": datetime.utcnow().timestamp(), "matches": []}
        await tourn_col.insert_one(doc)
        await message.reply(f"Tournament '{name}' created!\nID: {tid}\nPlayers join with: /tourney join {tid}")
    elif action == "join":
        if len(message.command) < 3:
            return await message.reply("Usage: /tourney join <id>")
        tid = message.command[2]
        t = await tourn_col.find_one({"_id": tid})
        if not t:
            return await message.reply("Tournament not found.")
        if t["status"] != "open":
            return await message.reply("Tournament not open for joining.")
        if message.from_user.id in t["players"]:
            return await message.reply("You already joined.")
        await tourn_col.update_one({"_id":tid}, {"$push": {"players": message.from_user.id}})
        await message.reply("You joined the tournament!")
    elif action == "start":
        if len(message.command) < 3:
            return await message.reply("Usage: /tourney start <id>")
        tid = message.command[2]
        t = await tourn_col.find_one({"_id": tid})
        if not t:
            return await message.reply("Tournament not found.")
        if message.from_user.id != t["owner"]:
            return await message.reply("Only the tournament owner can start.")
        players = t.get("players",[])
        if len(players) < 2:
            return await message.reply("Need at least 2 players.")
        # create random bracket pairing in rounds, best-effort single-elimination
        random.shuffle(players)
        matches = []
        while len(players) >= 2:
            a = players.pop(); b = players.pop()
            gid = str(uuid.uuid4())
            board = new_board()
            gdoc = {"_id": gid, "chat_id": t["chat_id"], "players":[a,b], "board": board, "turn": a, "status":"pending", "created_at": datetime.utcnow().timestamp(), "history": [], "theme": await get_theme(t["chat_id"])}
            await games_col.insert_one(gdoc)
            matches.append(gid)
            # notify group
            try:
                await app.send_message(t["chat_id"], f"Tournament match: <a href='tg://user?id={a}'>A</a> vs <a href='tg://user?id={b}'>B</a>\nGame ID: `{gid}`")
            except:
                pass
        await tourn_col.update_one({"_id": tid}, {"$set": {"status":"running", "matches": matches}})
        await message.reply(f"Tournament {t['name']} started with {len(matches)} matches. Matches posted in chat.")
    elif action == "status":
        if len(message.command) < 3:
            return await message.reply("Usage: /tourney status <id>")
        tid = message.command[2]
        t = await tourn_col.find_one({"_id": tid})
        if not t:
            return await message.reply("Not found.")
        await message.reply(f"Tournament {t['name']} status: {t['status']} Players: {len(t.get('players',[]))}")

# ----------------- ADMIN / CLEANUP -----------------
@app.on_message(filters.command("cleanup") & filters.user(123456789))  # replace id with admin
async def cmd_cleanup(_, message: Message):
    # remove old finished games older than X days (admin)
    cutoff_ts = (datetime.utcnow() - timedelta(days=7)).timestamp()
    res = await games_col.delete_many({"status": {"$in":["finished","forfeited","cancelled"]}, "ended_at": {"$lt": cutoff_ts}})
    await message.reply(f"Cleanup done. Removed {res.deleted_count} games.")

# ---------------- START BOT ----------------
async def startup_tasks():
    # spawn background worker that ensures pve games get bot moves if missed and other maintenance
    async def pve_worker():
        while True:
            cursor = games_col.find({"status":"active", "players.1":0})
            async for g in cursor:
                # if it's bot's turn (turn == 0), do a move
                if g["turn"] == 0:
                    await do_bot_move(g["_id"])
            await asyncio.sleep(2)
    asyncio.create_task(pve_worker())

@app.on_message(filters.command("run_worker") & filters.private)
async def cmd_runworker(_, message: Message):
    asyncio.create_task(startup_tasks())
    await message.reply("Background workers started.")
