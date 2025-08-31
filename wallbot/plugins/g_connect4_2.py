import random
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from wallbot import wbot as app



mongo = AsyncIOMotorClient(DB_URL)
db = mongo["connect42_db"]

# ─── GAME CONSTANTS ───────────────────────
ROWS, COLS = 6, 7
EMPTY, P1, P2 = "⚪", "🔴", "🟡"
GAME_TIMEOUT = 300  # auto-cleanup after 5 min inactivity

# ─── IN-MEMORY ACTIVE GAMES ───────────────
active_games = {}  # chat_id -> game state

# ─── DATABASE HELPERS ─────────────────────
async def update_stats(user_id, username, result):
    """Update player stats in MongoDB"""
    player = await db.players.find_one({"_id": user_id})
    if not player:
        player = {"_id": user_id, "username": username, "wins": 0, "losses": 0, "draws": 0, "rating": 1000}

    if result == "win":
        player["wins"] += 1
        player["rating"] += 15
    elif result == "loss":
        player["losses"] += 1
        player["rating"] -= 10
    elif result == "draw":
        player["draws"] += 1
        player["rating"] += 2

    await db.players.update_one({"_id": user_id}, {"$set": player}, upsert=True)


async def get_leaderboard():
    """Return top 10 players"""
    players = db.players.find().sort("rating", -1).limit(10)
    leaderboard = "🏆 **Leaderboard** 🏆\n\n"
    pos = 1
    async for p in players:
        leaderboard += f"{pos}. {p['username']} — {p['rating']} pts (W:{p['wins']} L:{p['losses']} D:{p['draws']})\n"
        pos += 1
    return leaderboard

# ─── GAME LOGIC ───────────────────────────
def new_board():
    return [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]

def render_board(board):
    return "\n".join("".join(row) for row in board)

def make_move(board, col, piece):
    for r in reversed(range(ROWS)):
        if board[r][col] == EMPTY:
            board[r][col] = piece
            return True
    return False

def check_winner(board, piece):
    # Horizontal
    for r in range(ROWS):
        for c in range(COLS - 3):
            if all(board[r][c + i] == piece for i in range(4)):
                return True
    # Vertical
    for c in range(COLS):
        for r in range(ROWS - 3):
            if all(board[r + i][c] == piece for i in range(4)):
                return True
    # Diagonal \
    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            if all(board[r + i][c + i] == piece for i in range(4)):
                return True
    # Diagonal /
    for r in range(3, ROWS):
        for c in range(COLS - 3):
            if all(board[r - i][c + i] == piece for i in range(4)):
                return True
    return False

def is_full(board):
    return all(board[0][c] != EMPTY for c in range(COLS))

# ─── BOT AI ───────────────────────────────
def bot_move(board, difficulty="easy"):
    """Bot AI: easy=random, medium=block-win, hard=win/block priority"""
    if difficulty == "easy":
        return random.choice([c for c in range(COLS) if board[0][c] == EMPTY])

    # Medium & Hard: prevent opponent win
    for c in range(COLS):
        temp = [row[:] for row in board]
        if make_move(temp, c, P1) and check_winner(temp, P1):
            return c

    if difficulty == "hard":
        # Try to win
        for c in range(COLS):
            temp = [row[:] for row in board]
            if make_move(temp, c, P2) and check_winner(temp, P2):
                return c

    # Otherwise random
    return random.choice([c for c in range(COLS) if board[0][c] == EMPTY])

# ─── AUTO CLEANUP ─────────────────────────
async def cleanup_games():
    while True:
        now = time.time()
        to_remove = []
        for chat_id, game in active_games.items():
            if now - game["last_move"] > GAME_TIMEOUT:
                to_remove.append(chat_id)
        for cid in to_remove:
            active_games.pop(cid, None)
        await asyncio.sleep(60)

# ─── BOT COMMANDS ─────────────────────────
@app.on_message(filters.command("connect4"))
async def startc4(_, msg):
    text = "🎮 Welcome to **Connect 4 Bot**!\n\nChoose a mode to play:"
    buttons = [
        [InlineKeyboardButton("👥 PvP", callback_data="mode_pvp")],
        [InlineKeyboardButton("🤖 vs Bot (Easy)", callback_data="mode_bot_easy")],
        [InlineKeyboardButton("🤖 vs Bot (Medium)", callback_data="mode_bot_medium")],
        [InlineKeyboardButton("🤖 vs Bot (Hard)", callback_data="mode_bot_hard")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")]
    ]
    await msg.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^mode_"))
async def mode_select(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    if chat_id in active_games:
        return await query.answer("Game already running in this chat!", show_alert=True)

    mode = query.data.split("_")[1]
    difficulty = query.data.split("_")[2] if "bot" in query.data else None
    board = new_board()
    active_games[chat_id] = {
        "board": board,
        "turn": P1,
        "players": [query.from_user.id],
        "mode": mode,
        "difficulty": difficulty,
        "last_move": time.time()
    }

    if mode == "pvp":
        await query.message.edit("👥 PvP Mode started!\nWaiting for another player to join...\nSend /join", reply_markup=None)
    else:
        buttons = [[InlineKeyboardButton(str(i+1), callback_data=f"move_{i}")] for i in range(COLS)]
        await query.message.edit(f"🤖 Playing vs Bot ({difficulty.title()})\n\n{render_board(board)}\n\n🔴 Your turn!", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_message(filters.command("joinc4"))
async def joinc4(_, msg):
    chat_id = msg.chat.id
    if chat_id not in active_games:
        return await msg.reply("No game to join. Start one with /start")
    game = active_games[chat_id]
    if game["mode"] != "pvp":
        return await msg.reply("This is not a PvP game.")
    if len(game["players"]) == 2:
        return await msg.reply("Game already full!")

    game["players"].append(msg.from_user.id)
    game["last_move"] = time.time()
    buttons = [[InlineKeyboardButton(str(i+1), callback_data=f"move_{i}")] for i in range(COLS)]
    await msg.reply(f"Game started!\n\n{render_board(game['board'])}\n\n🔴 Player 1's turn", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^move_"))
async def handle_move(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    if chat_id not in active_games:
        return await query.answer("No active game!", show_alert=True)

    game = active_games[chat_id]
    col = int(query.data.split("_")[1])
    board = game["board"]
    turn = game["turn"]

    # Make move
    if not make_move(board, col, turn):
        return await query.answer("Column full!", show_alert=True)

    game["last_move"] = time.time()

    # Check winner/draw
    if check_winner(board, turn):
        winner = query.from_user
        await update_stats(winner.id, winner.first_name, "win")
        for pid in game["players"]:
            if pid != winner.id:
                await update_stats(pid, "", "loss")
        await query.message.edit(f"{render_board(board)}\n\n🎉 {winner.mention} wins!")
        active_games.pop(chat_id)
        return

    if is_full(board):
        for pid in game["players"]:
            await update_stats(pid, "", "draw")
        await query.message.edit(f"{render_board(board)}\n\n🤝 It's a draw!")
        active_games.pop(chat_id)
        return

    # Switch turn
    game["turn"] = P1 if turn == P2 else P2

    # Bot AI move
    if game["mode"] == "bot" and game["turn"] == P2:
        await asyncio.sleep(1)
        col = bot_move(board, game["difficulty"])
        make_move(board, col, P2)
        if check_winner(board, P2):
            await update_stats(query.from_user.id, query.from_user.first_name, "loss")
            await query.message.edit(f"{render_board(board)}\n\n🤖 Bot wins!")
            active_games.pop(chat_id)
            return
        game["turn"] = P1

    # Update board
    buttons = [[InlineKeyboardButton(str(i+1), callback_data=f"move_{i}")] for i in range(COLS)]
    await query.message.edit(f"{render_board(board)}\n\n{'🔴' if game['turn']==P1 else '🟡'} turn", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^leaderboard$"))
async def show_lb(_, query: CallbackQuery):
    lb = await get_leaderboard()
    await query.message.edit(lb)

