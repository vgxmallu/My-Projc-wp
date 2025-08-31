import asyncio
import random
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "gomoku_db"
# ----------------------------------------

# Init
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
users = db["users"]
games = db["games"]

WIN_COUNT = 5
CLEANUP_MINUTES = 30

# ----------------- HELPERS -----------------
def empty_board(size):
    return [["⬜" for _ in range(size)] for _ in range(size)]

def render_board(board):
    return "\n".join("".join(row) for row in board)

def check_winner(board, symbol, win_count=WIN_COUNT):
    size = len(board)
    for r in range(size):
        for c in range(size):
            if c + win_count <= size and all(board[r][c+i] == symbol for i in range(win_count)):
                return True
            if r + win_count <= size and all(board[r+i][c] == symbol for i in range(win_count)):
                return True
            if r + win_count <= size and c + win_count <= size and all(board[r+i][c+i] == symbol for i in range(win_count)):
                return True
            if r - win_count >= -1 and c + win_count <= size and all(board[r-i][c+i] == symbol for i in range(win_count)):
                return True
    return False

def make_buttons(game_id):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎮 Make Move", callback_data=f"move_{game_id}")],
            [InlineKeyboardButton("🛑 Resign", callback_data=f"resign_{game_id}")]
        ]
    )

def update_user(user_id, won=False, lost=False, draw=False):
    user = users.find_one({"user_id": user_id})
    if not user:
        user = {"user_id": user_id, "wins": 0, "losses": 0, "draws": 0, "games": 0}
    user["games"] += 1
    if won: user["wins"] += 1
    if lost: user["losses"] += 1
    if draw: user["draws"] += 1
    users.update_one({"user_id": user_id}, {"$set": user}, upsert=True)

# AI move (random for now)
def ai_move(board):
    empty = [(r, c) for r in range(len(board)) for c in range(len(board)) if board[r][c] == "⬜"]
    return random.choice(empty) if empty else None

# ----------------- COMMANDS -----------------
@app.on_message(filters.command("start"))
async def start_cmd(_, msg):
    await msg.reply(
        "🎮 Welcome to Gomoku Bot!\n\n"
        "Commands:\n"
        "/play <size> – Start a new PVP game (default 9)\n"
        "/play_ai <size> – Play vs Bot AI (default 9)\n"
        "/profile – Show your stats\n"
        "/leaderboard – Show global leaderboard"
    )

@app.on_message(filters.command("play"))
async def play_cmd(_, msg):
    args = msg.text.split()
    size = int(args[1]) if len(args) > 1 else 9
    if size < 5 or size > 15:
        return await msg.reply("❌ Board size must be between 5 and 15.")

    board = empty_board(size)
    game = {
        "game_id": msg.chat.id + msg.id,
        "board": board,
        "players": [msg.from_user.id],
        "turn": 0,
        "size": size,
        "created": datetime.utcnow(),
        "finished": False
    }
    games.insert_one(game)
    await msg.reply(
        f"🎮 Gomoku {size}x{size} started!\n{render_board(board)}\n\nWaiting for opponent...",
        reply_markup=make_buttons(game["game_id"])
    )

@app.on_message(filters.command("play_ai"))
async def play_ai_cmd(_, msg):
    args = msg.text.split()
    size = int(args[1]) if len(args) > 1 else 9
    if size < 5 or size > 15:
        return await msg.reply("❌ Board size must be between 5 and 15.")

    board = empty_board(size)
    game = {
        "game_id": msg.chat.id + msg.id,
        "board": board,
        "players": [msg.from_user.id, "AI"],
        "turn": 0,
        "size": size,
        "created": datetime.utcnow(),
        "finished": False
    }
    games.insert_one(game)
    await msg.reply(
        f"🤖 Gomoku {size}x{size} vs AI!\n{render_board(board)}\n\nYour turn (❌)",
        reply_markup=make_buttons(game["game_id"])
    )

@app.on_message(filters.command("goprofile"))
async def profilgge_cmd(_, msg):
    user = users.find_one({"user_id": msg.from_user.id})
    if not user:
        return await msg.reply("❌ No profile found. Play games first!")
    await msg.reply(
        f"📊 Profile of {msg.from_user.first_name}\n"
        f"🏆 Wins: {user['wins']}\n"
        f"💀 Losses: {user['losses']}\n"
        f"🤝 Draws: {user['draws']}\n"
        f"🎮 Games: {user['games']}"
    )

@app.on_message(filters.command("goleaderboard"))
async def gomleaderboard_cmd(_, msg):
    top = users.find().sort("wins", -1).limit(10)
    text = "🏆 Global Leaderboard:\n\n"
    for i, u in enumerate(top, 1):
        text += f"{i}. {u['user_id']} – {u['wins']} Wins\n"
    await msg.reply(text)

# ----------------- CALLBACKS -----------------
@app.on_callback_query(filters.regex("^move_"))
async def movge_cb(_, query: CallbackQuery):
    game_id = int(query.data.split("_")[1])
    game = games.find_one({"game_id": game_id})
    if not game or game["finished"]:
        return await query.answer("❌ Game not found/finished!", show_alert=True)

    user_id = query.from_user.id
    if user_id not in game["players"]:
        if len(game["players"]) < 2:
            game["players"].append(user_id)
            games.update_one({"game_id": game_id}, {"$set": {"players": game["players"]}})
        else:
            return await query.answer("Spectator mode: You can't move!", show_alert=True)

    turn = game["turn"] % 2
    if game["players"][turn] != user_id and game["players"][turn] != "AI":
        return await query.answer("⏳ Not your turn!", show_alert=True)

    board = game["board"]
    if game["players"][turn] == "AI":
        r, c = ai_move(board)
    else:
        r, c = ai_move(board)  # placeholder: choose random (replace with real move logic)
    symbol = "❌" if turn == 0 else "⭕"
    board[r][c] = symbol

    if check_winner(board, symbol):
        winner = "AI" if game["players"][turn] == "AI" else query.from_user.mention
        await query.message.edit(
            f"{render_board(board)}\n\n🏆 {winner} wins!",
            reply_markup=None
        )
        games.update_one({"game_id": game_id}, {"$set": {"finished": True}})
        if game["players"][turn] != "AI":
            update_user(game["players"][turn], won=True)
            if game["players"][1-turn] != "AI":
                update_user(game["players"][1-turn], lost=True)
        return

    game["turn"] += 1
    games.update_one({"game_id": game_id}, {"$set": {"board": board, "turn": game["turn"]}})
    await query.message.edit(
        f"{render_board(board)}\n\nTurn: {game['players'][game['turn']%2]}",
        reply_markup=make_buttons(game_id)
    )

@app.on_callback_query(filters.regex("^resign_"))
async def resiggn_cb(_, query: CallbackQuery):
    game_id = int(query.data.split("_")[1])
    game = games.find_one({"game_id": game_id})
    if not game or game["finished"]:
        return await query.answer("❌ Already finished!", show_alert=True)

    loser = query.from_user.id
    winner = game["players"][1] if game["players"][0] == loser else game["players"][0]
    await query.message.edit(
        f"{render_board(game['board'])}\n\n🏆 {winner} wins by resignation!",
        reply_markup=None
    )
    games.update_one({"game_id": game_id}, {"$set": {"finished": True}})
    if winner != "AI":
        update_user(winner, won=True)
    if loser != "AI":
        update_user(loser, lost=True)

# ----------------- AUTO CLEANUP -----------------
async def cleanup_games():
    while True:
        expire_time = datetime.utcnow() - timedelta(minutes=CLEANUP_MINUTES)
        games.delete_many({"finished": False, "created": {"$lt": expire_time}})
        await asyncio.sleep(300)

