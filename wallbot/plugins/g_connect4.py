# connect4_advanced Made with Girk_Ai
import asyncio
import time
import uuid
import random
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message
)
from config import DB_URL
from wallbot import wbot as app
# ---------------- CONFIG ----------------



DB_NAME = "connect4_advanced"

# Game settings
ROWS, COLS = 6, 7
INACTIVITY_TIMEOUT_MINUTES = 10  # auto-forfeit after X minutes
ELO_K = 32  # Elo K-factor
# ----------------------------------------

# ---------- Setup ----------
mongo = AsyncIOMotorClient(DB_URL)
db = mongo[DB_NAME]
games_col = db["games"]
players_col = db["players"]

scheduler = AsyncIOScheduler(timezone="UTC")
scheduler.start()
# ---------------------------

# ---------- Utilities ----------
EMPTY = " "

def new_board() -> List[List[str]]:
    return [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]

def board_to_text(board: List[List[str]]) -> str:
    # top row first
    symbol = {EMPTY: "⚪", "X": "🔴", "O": "🟡"}
    lines = ["".join(symbol[cell] for cell in row) for row in board]
    # show column numbers on top
    header = " ".join(str(i+1) for i in range(COLS))
    return f"Cols: {header}\n" + "\n".join(lines)

def render_board_kb(gid: str, active: bool = True) -> InlineKeyboardMarkup:
    # If active: callbacks include gid and column. If not, use dummy callbacks to disable moves.
    buttons = []
    for c in range(COLS):
        cb = f"move|{gid}|{c}" if active else f"noop|{gid}|{c}"
        buttons.append(InlineKeyboardButton(str(c+1), callback_data=cb))
    # single row of columns
    return InlineKeyboardMarkup([buttons, [
        InlineKeyboardButton("🔁 Rematch", callback_data=f"rematch|{gid}"),
        InlineKeyboardButton("👀 Spectate", callback_data=f"spectate|{gid}")
    ]])

def current_timestamp() -> float:
    return time.time()

# Version of check_winner returning winning piece or None
def check_winner(board: List[List[str]]) -> Optional[str]:
    # horizontal
    for r in range(ROWS):
        for c in range(COLS-3):
            if board[r][c] != EMPTY and all(board[r][c+i] == board[r][c] for i in range(4)):
                return board[r][c]
    # vertical
    for c in range(COLS):
        for r in range(ROWS-3):
            if board[r][c] != EMPTY and all(board[r+i][c] == board[r][c] for i in range(4)):
                return board[r][c]
    # diagonal down-right
    for r in range(ROWS-3):
        for c in range(COLS-3):
            if board[r][c] != EMPTY and all(board[r+i][c+i] == board[r][c] for i in range(4)):
                return board[r][c]
    # diagonal up-right
    for r in range(3, ROWS):
        for c in range(COLS-3):
            if board[r][c] != EMPTY and all(board[r-i][c+i] == board[r][c] for i in range(4)):
                return board[r][c]
    # draw
    if all(cell != EMPTY for row in board for cell in row):
        return "DRAW"
    return None

def drop_piece(board: List[List[str]], col: int, piece: str) -> bool:
    for r in range(ROWS-1, -1, -1):
        if board[r][col] == EMPTY:
            board[r][col] = piece
            return True
    return False

# minimal heuristic for medium/hard
def score_window(window: List[str], piece: str) -> int:
    score = 0
    opp = "O" if piece == "X" else "X"
    if window.count(piece) == 4:
        score += 100
    elif window.count(piece) == 3 and window.count(EMPTY) == 1:
        score += 5
    elif window.count(piece) == 2 and window.count(EMPTY) == 2:
        score += 2
    if window.count(opp) == 3 and window.count(EMPTY) == 1:
        score -= 4
    return score

def board_score(board: List[List[str]], piece: str) -> int:
    score = 0
    # center column preference
    center_array = [board[r][COLS//2] for r in range(ROWS)]
    score += center_array.count(piece) * 3
    # horizontal
    for r in range(ROWS):
        row_array = board[r]
        for c in range(COLS-3):
            window = row_array[c:c+4]
            score += score_window(window, piece)
    # vertical
    for c in range(COLS):
        col_array = [board[r][c] for r in range(ROWS)]
        for r in range(ROWS-3):
            window = col_array[r:r+4]
            score += score_window(window, piece)
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

def possible_moves(board: List[List[str]]) -> List[int]:
    return [c for c in range(COLS) if board[0][c] == EMPTY]

# Depth-limited minimax with alpha-beta for hard AI
def minimax(board: List[List[str]], depth: int, alpha: int, beta: int, maximizing: bool, piece: str) -> Tuple[int, Optional[int]]:
    valid_locations = possible_moves(board)
    is_terminal = check_winner(board) is not None
    if depth == 0 or is_terminal:
        if is_terminal:
            winner = check_winner(board)
            if winner == piece:
                return (10_000_000, None)
            elif winner == ("O" if piece == "X" else "X"):
                return (-10_000_000, None)
            else:
                return (0, None)
        else:
            return (board_score(board, piece), None)
    if maximizing:
        value = -10_000_000
        chosen_col = random.choice(valid_locations)
        for col in valid_locations:
            # copy board
            b_copy = [row[:] for row in board]
            drop_piece(b_copy, col, piece)
            new_score, _ = minimax(b_copy, depth-1, alpha, beta, False, piece)
            if new_score > value:
                value = new_score
                chosen_col = col
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value, chosen_col
    else:
        value = 10_000_000
        opp = "O" if piece == "X" else "X"
        chosen_col = random.choice(valid_locations)
        for col in valid_locations:
            b_copy = [row[:] for row in board]
            drop_piece(b_copy, col, opp)
            new_score, _ = minimax(b_copy, depth-1, alpha, beta, True, piece)
            if new_score < value:
                value = new_score
                chosen_col = col
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value, chosen_col

# ---------- Database helpers ----------
async def ensure_player(uid: int) -> Dict:
    p = await players_col.find_one({"_id": uid})
    if not p:
        p = {"_id": uid, "wins": 0, "losses": 0, "draws": 0, "elo": 1200}
        await players_col.insert_one(p)
    return p

def elo_expected(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def elo_update(rating_a: float, rating_b: float, score_a: float, k: int = ELO_K) -> float:
    exp = elo_expected(rating_a, rating_b)
    return rating_a + k * (score_a - exp)

# ---------- Auto-timeout job ----------
async def check_timeouts():
    cutoff = datetime.utcnow() - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)
    cursor = games_col.find({"status": "active", "last_move_at": {"$lte": cutoff.timestamp()}})
    async for g in cursor:
        # forfeit the player who was supposed to play (turn) and award the other
        try:
            gid = g["_id"]
            turn = g["turn"]
            players = g["players"]
            winner = players[0] if players[1] == turn else players[1]
            # update stats
            await ensure_player(winner)
            await ensure_player(turn)
            await players_col.update_one({"_id": winner}, {"$inc": {"wins": 1}})
            await players_col.update_one({"_id": turn}, {"$inc": {"losses": 1}})
            # update elo
            p_w = await players_col.find_one({"_id": winner})
            p_l = await players_col.find_one({"_id": turn})
            new_w = elo_update(p_w["elo"], p_l["elo"], 1.0)
            new_l = elo_update(p_l["elo"], p_w["elo"], 0.0)
            await players_col.update_one({"_id": winner}, {"$set": {"elo": int(new_w)}})
            await players_col.update_one({"_id": turn}, {"$set": {"elo": int(new_l)}})
            # mark game finished
            await games_col.update_one({"_id": gid}, {"$set": {"status": "finished", "winner": winner}})
        except Exception:
            continue

# schedule to run every minute
scheduler.add_job(lambda: asyncio.create_task(check_timeouts()), "interval", minutes=1)

# ---------- Commands ----------
@app.on_message(filters.command("c4sta") & filters.private)
async def cmd_c4start(client: Client, message: Message):
    await message.reply(
        "🎮 Connect 4 — Advanced Bot\n\n"
        "Commands:\n"
        "`/challenge` (reply to a user) — challenge in group or private\n"
        "`/pve easy|medium|hard` — play vs bot in private\n"
        "`/profile` — show your stats & ELO\n"
        "`/leaderboard` — top players by ELO\n"
        "`/spectate <game_id>` — view a game's board\n\n"
        "Gameplay: Use column buttons to drop your piece. Red (🔴) starts and is X; Yellow (🟡) is O."
    )

@app.on_message(filters.command("c4challenge") & (filters.group | filters.private))
async def cmd_c4challenge(_, message: Message):
    # must be a reply or provide username/id
    if not message.reply_to_message and len(message.command) < 2:
        return await message.reply("Reply to someone or use `/challenge @user`")
    try:
        if message.reply_to_message:
            opponent_user = message.reply_to_message.from_user
        else:
            opponent_user = await app.get_users(message.command[1])
    except Exception:
        return await message.reply("Couldn't find that user.")

    challenger = message.from_user
    if opponent_user.id == challenger.id:
        return await message.reply("You can't challenge yourself.")

    # create game id
    gid = str(uuid.uuid4())
    board = new_board()
    game_doc = {
        "_id": gid,
        "chat_id": message.chat.id,
        "players": [challenger.id, opponent_user.id],  # players[0] = X (starts)
        "board": board,
        "turn": challenger.id,  # start with challenger
        "status": "pending",
        "created_at": current_timestamp(),
        "last_move_at": current_timestamp(),
        "mode": "pvp",
        "winner": None,
        "log": []
    }
    await games_col.insert_one(game_doc)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"accept|{gid}|{opponent_user.id}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"decline|{gid}|{opponent_user.id}")]
    ])
    await message.reply(
        f"🎮 Challenge: {challenger.mention} ➜ {opponent_user.mention}\nGame ID: `{gid}`\n\n"
        f"{opponent_user.mention} — press Accept to start.",
        reply_markup=kb
    )

@app.on_message(filters.command("c4pve") & filters.private)
async def cmd_c4pve(_, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /pve easy|medium|hard")
    level = message.command[1].lower()
    if level not in ("easy", "medium", "hard"):
        return await message.reply("Choose: easy / medium / hard")

    uid = message.from_user.id
    gid = str(uuid.uuid4())
    board = new_board()
    mode = {"mode": "pve", "level": level}
    game_doc = {
        "_id": gid,
        "chat_id": message.chat.id,
        "players": [uid, 0],  # second player 0 denotes bot
        "board": board,
        "turn": uid,
        "status": "active",
        "created_at": current_timestamp(),
        "last_move_at": current_timestamp(),
        "mode": "pve",
        "level": level,
        "winner": None,
        "log": []
    }
    await games_col.insert_one(game_doc)
    await ensure_player(uid)

    await message.reply(
        f"🎮 PvE started ({level.title()})\nGame ID: `{gid}`\nYou are 🔴 (X).",
        reply_markup=render_board_kb(gid)
    )

@app.on_message(filters.command("c4profile"))
async def cmd_c4profile(_, message: Message):
    uid = message.from_user.id
    p = await ensure_player(uid)
    text = (
        f"👤 {message.from_user.mention}\n"
        f"ELO: {p['elo']}\n"
        f"Wins: {p['wins']} | Losses: {p['losses']} | Draws: {p['draws']}"
    )
    await message.reply(text)

@app.on_message(filters.command("c4leaderboard"))
async def cmd_c4leaderboard(_, message: Message):
    # global top by elo
    cursor = players_col.find().sort("elo", -1).limit(10)
    lines = ["🏆 Top Players (by ELO):"]
    async for p in cursor:
        try:
            user = await app.get_users(p["_id"])
            name = user.first_name
        except:
            name = f"User({p['_id']})"
        lines.append(f"{name} — ELO {p['elo']} (W:{p['wins']} L:{p['losses']})")
    if len(lines) == 1:
        lines.append("No players yet.")
    await message.reply("\n".join(lines))

@app.on_message(filters.command("spectate"))
async def cmd_spectate(_, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /spectate <game_id>")
    gid = message.command[1].strip()
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await message.reply("Game not found.")
    # render board but disabled
    text = board_to_text(g["board"])
    kb = render_board_kb(gid, active=False)
    await message.reply(f"👀 Spectating Game `{gid}`\n\n{text}", reply_markup=kb)

# ---------- Callback handlers ----------
@app.on_callback_query(filters.regex(r"^accept\|"))
async def cb_accept(_, query: CallbackQuery):
    _, gid, expected_uid = query.data.split("|")
    expected_uid = int(expected_uid)
    game = await games_col.find_one({"_id": gid})
    if not game:
        return await query.answer("Game not found.", show_alert=True)
    if query.from_user.id != expected_uid:
        return await query.answer("You are not the challenged user.", show_alert=True)
    if game["status"] != "pending":
        return await query.answer("Game already started or canceled.", show_alert=True)

    # activate
    await ensure_player(game["players"][0])
    await ensure_player(game["players"][1])
    await games_col.update_one({"_id": gid}, {"$set": {"status": "active", "last_move_at": current_timestamp()}})
    text = board_to_text(game["board"])
    kb = render_board_kb(gid)
    await query.message.edit(f"🎮 Game started! Game ID: `{gid}`\n\n{text}", reply_markup=kb)
    await query.answer("Game accepted!")

@app.on_callback_query(filters.regex(r"^decline\|"))
async def cb_decline(_, query: CallbackQuery):
    _, gid, expected_uid = query.data.split("|")
    expected_uid = int(expected_uid)
    game = await games_col.find_one({"_id": gid})
    if not game:
        return await query.answer("Game not found.")
    if query.from_user.id != expected_uid:
        return await query.answer("Only the challenged user can decline.", show_alert=True)
    await games_col.delete_one({"_id": gid})
    await query.message.edit("❌ Challenge declined.")
    await query.answer("Declined.")

@app.on_callback_query(filters.regex(r"^move\|"))
async def cb_move(_, query: CallbackQuery):
    # format: move|gid|col
    _, gid, col_s = query.data.split("|")
    col = int(col_s)
    game = await games_col.find_one({"_id": gid})
    if not game:
        return await query.answer("Game not found.", show_alert=True)
    if game["status"] != "active":
        return await query.answer("Game is not active.", show_alert=True)

    player_id = query.from_user.id
    # check it's this player's turn
    if player_id != game["turn"]:
        return await query.answer("Not your turn!", show_alert=True)

    # validate column
    if game["board"][0][col] != EMPTY:
        return await query.answer("Column full!", show_alert=True)

    # determine piece: players[0] is X (🔴), players[1] is O (🟡)
    piece = "X" if player_id == game["players"][0] else "O"
    # apply
    board = game["board"]
    success = drop_piece(board, col, piece)
    if not success:
        return await query.answer("Column full!", show_alert=True)

    # log
    game["log"].append({"time": current_timestamp(), "by": player_id, "action": "move", "col": col, "piece": piece})
    game["board"] = board
    game["last_move_at"] = current_timestamp()

    winner = check_winner(board)
    if winner == "DRAW" or winner == "DRAW\n":
        # draw
        await players_col.update_one({"_id": game["players"][0]}, {"$inc": {"draws": 1}}, upsert=True)
        await players_col.update_one({"_id": game["players"][1]}, {"$inc": {"draws": 1}}, upsert=True)
        await games_col.update_one({"_id": gid}, {"$set": {"status": "finished", "winner": None, "board": board}})
        text = board_to_text(board)
        await query.message.edit(f"🤝 Draw!\n\n{text}", reply_markup=render_board_kb(gid, active=False))
        return await query.answer("It's a draw!")

    if winner in ("X", "O"):
        # find winner id
        winner_id = game["players"][0] if winner == "X" else game["players"][1]
        loser_id = game["players"][1] if winner == "X" else game["players"][0]
        # update stats & elo
        await ensure_player(winner_id)
        await ensure_player(loser_id)
        await players_col.update_one({"_id": winner_id}, {"$inc": {"wins": 1}}, upsert=True)
        await players_col.update_one({"_id": loser_id}, {"$inc": {"losses": 1}}, upsert=True)
        # elo
        p_w = await players_col.find_one({"_id": winner_id})
        p_l = await players_col.find_one({"_id": loser_id})
        new_w = int(elo_update(p_w["elo"], p_l["elo"], 1.0))
        new_l = int(elo_update(p_l["elo"], p_w["elo"], 0.0))
        await players_col.update_one({"_id": winner_id}, {"$set": {"elo": new_w}})
        await players_col.update_one({"_id": loser_id}, {"$set": {"elo": new_l}})
        await games_col.update_one({"_id": gid}, {"$set": {"status": "finished", "winner": winner_id, "board": board}})
        text = board_to_text(board)
        kb = render_board_kb(gid, active=False)
        await query.message.edit(f"🏆 {await app.get_users(winner_id).then(lambda u: u.mention) if False else 'Winner!'}\n\n{text}", reply_markup=kb)
        # (we do not await mention in edit for performance; clients will show plain text)
        return await query.answer("You won!")

    # switch turn
    next_turn = game["players"][0] if game["turn"] == game["players"][1] else game["players"][1]
    await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": next_turn, "last_move_at": game["last_move_at"], "log": game["log"]}})
    text = board_to_text(board)
    kb = render_board_kb(gid)
    await query.message.edit(f"🎮 Game `{gid}`\nNext turn: <a href='tg://user?id={next_turn}'>Player</a>\n\n{text}", reply_markup=kb)
    await query.answer("Move registered.")

@app.on_callback_query(filters.regex(r"^noop\|"))
async def cb_noop(_, query: CallbackQuery):
    await query.answer("This is a spectator board. Use /spectate <game_id> to open.", show_alert=True)

@app.on_callback_query(filters.regex(r"^rematch\|"))
async def cb_rematch(_, query: CallbackQuery):
    _, gid = query.data.split("|")
    g = await games_col.find_one({"_id": gid})
    if not g:
        return await query.answer("Game not found.", show_alert=True)
    if g["status"] == "active":
        return await query.answer("Game still active.")
    # create a new game with same players and same chat
    new_gid = str(uuid.uuid4())
    board = new_board()
    new_game = {
        "_id": new_gid,
        "chat_id": g["chat_id"],
        "players": g["players"],
        "board": board,
        "turn": g["players"][0],
        "status": "active",
        "created_at": current_timestamp(),
        "last_move_at": current_timestamp(),
        "mode": g.get("mode", "pvp"),
        "winner": None,
        "log": []
    }
    await games_col.insert_one(new_game)
    kb = render_board_kb(new_gid)
    await query.message.reply(f"🔁 Rematch started! Game ID: `{new_gid}`", reply_markup=kb)
    await query.answer("Rematch started!")

# Bot PvE AI move handler: after player moves, if game is pve and still active, bot moves
# We implement a small loop check to let bot play automatically
async def try_bot_move(gid: str):
    g = await games_col.find_one({"_id": gid})
    if not g or g["status"] != "active" or g["mode"] != "pve":
        return
    # if it's bot's turn (players[1] == 0)
    if g["turn"] != 0:
        return
    board = g["board"]
    level = g.get("level", "easy")
    # pick move based on level
    if level == "easy":
        moves = possible_moves(board)
        col = random.choice(moves)
    elif level == "medium":
        # try to win or block or random
        moves = possible_moves(board)
        chosen = None
        # try win
        for c in moves:
            bc = [row[:] for row in board]
            drop_piece(bc, c, "O")
            if check_winner(bc) == "O":
                chosen = c; break
        if chosen is None:
            for c in moves:
                bc = [row[:] for row in board]
                drop_piece(bc, c, "X")
                if check_winner(bc) == "X":
                    chosen = c; break
        col = chosen if chosen is not None else random.choice(moves)
    else:  # hard
        _, col = minimax(board, depth=4, alpha=-10_000_000, beta=10_000_000, maximizing=True, piece="O")
        if col is None:
            col = random.choice(possible_moves(board))
    # apply move as bot
    drop_piece(board, col, "O")
    g["board"] = board
    g["log"].append({"time": current_timestamp(), "by": 0, "action": "move", "col": col, "piece": "O"})
    g["last_move_at"] = current_timestamp()
    # check result
    winner = check_winner(board)
    if winner == "O":
        # bot wins
        await games_col.update_one({"_id": gid}, {"$set": {"status": "finished", "winner": 0, "board": board}})
        # update stats for human: loss
        human = g["players"][0]
        await ensure_player(human)
        await players_col.update_one({"_id": human}, {"$inc": {"losses": 1}})
        # no elo change vs bot
        text = board_to_text(board)
        # find message to edit? we cannot directly know which message; we rely on chat message previously created referencing gid
        # For simplicity, post a new message in chat with final board
        try:
            await app.send_message(g["chat_id"], f"🤖 Bot wins!\nGame `{gid}`\n\n{text}")
        except:
            pass
        return
    elif winner == "DRAW":
        await games_col.update_one({"_id": gid}, {"$set": {"status": "finished", "winner": None, "board": board}})
        text = board_to_text(board)
        try:
            await app.send_message(g["chat_id"], f"🤝 Draw vs Bot!\nGame `{gid}`\n\n{text}")
        except:
            pass
        return
    else:
        # switch turn to human (players[0])
        await games_col.update_one({"_id": gid}, {"$set": {"board": board, "turn": g["players"][0], "last_move_at": g["last_move_at"], "log": g["log"]}})
        # update the last board message: best-effort, we don't track message_id to update to keep code simpler
        return

# Try to detect pve games after a move and schedule bot move
# After each move in cb_move we can call try_bot_move(gid) as a task

# ---------- Attach post-move hook in cb_move ----------
# To keep code simpler in this single-file, we'll call try_bot_move inline: modify cb_move earlier to call it.
# (We've already updated DB; now call try_bot_move)
# But we need to call it in cb_move; to avoid duplicating code here, we will schedule it now:
# NOTE: In cb_move after updating DB, call: asyncio.create_task(try_bot_move(gid))

# (We updated cb_move above to write DB; now append call:)
# We'll monkey-patch by redefining cb_move? Simpler: run a small wrapper to check recent pve active games and call bot moves periodically:
async def bot_loop_worker():
    while True:
        cursor = games_col.find({"mode": "pve", "status": "active"})
        async for g in cursor:
            # if it's bot's turn (turn == 0)
            if g["turn"] == 0:
                await try_bot_move(g["_id"])
        await asyncio.sleep(2)  # poll every 2 seconds

# start background task when bot starts
@app.on_message(filters.command("runchecker") & filters.private)
async def _runchecker(_, message: Message):
    # debug helper to start bot worker manually if needed
    asyncio.create_task(bot_loop_worker())
    await message.reply("Bot worker started (debug).")

# Start worker on startup
@app.on_message(filters.command("start_worker") & filters.private)
async def _starter(_, message: Message):
    asyncio.create_task(bot_loop_worker())
    await message.reply("Worker queued.")

# ---------- Startup / shutdown ----------
@app.on_message(filters.command("cstat") & filters.private)
async def cmd_stcatus(_, message: Message):
    count = await games_col.count_documents({})
    await message.reply(f"DB games: {count}")

# ---------- Run ----------
