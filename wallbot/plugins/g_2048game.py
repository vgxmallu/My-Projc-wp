import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from datetime import datetime
from config import DB_URL
from wallbot import wbot as app
from pymongo.errors import PyMongoError

# --- Mongo ---
mongo = MongoClient(DB_URL)
db = mongo["game_2048"]
games_col = db["games"]
profiles_col = db["profiles"]

# --- Game helpers ---
def new_board():
    board = [[0] * 4 for _ in range(4)]
    add_random(board)
    add_random(board)
    return board

def add_random(board):
    # ensure board is valid 4x4
    if not board or len(board) != 4 or any(len(row) != 4 for row in board):
        board = [[0] * 4 for _ in range(4)]
    empty = [(i, j) for i in range(4) for j in range(4) if board[i][j] == 0]
    if empty:
        i, j = random.choice(empty)
        board[i][j] = 2 if random.random() < 0.9 else 4

def board_to_text(board):
    emojis = {
        0: "⬜", 2: "2️⃣", 4: "4️⃣", 8: "8️⃣", 16: "1️⃣6️⃣", 32: "3️⃣2️⃣", 64: "6️⃣4️⃣",
        128: "1️⃣2️⃣8️⃣", 256: "2️⃣5️⃣6️⃣", 512: "5️⃣1️⃣2️⃣", 1024: "1️⃣0️⃣2️⃣4️⃣", 2048: "2️⃣0️⃣4️⃣8️⃣"
    }
    return "\n".join("".join(emojis.get(cell, str(cell)) for cell in row) for row in board)

def move_board(board, direction):
    def compress(row):
        new_row = [i for i in row if i != 0]
        for i in range(len(new_row) - 1):
            if new_row[i] == new_row[i + 1]:
                new_row[i] *= 2
                new_row[i + 1] = 0
        return [i for i in new_row if i != 0] + [0] * (4 - len(new_row))

    original_board = [row[:] for row in board]

    if direction == "up":
        board = list(map(list, zip(*board)))
        board = [compress(row) for row in board]
        board = list(map(list, zip(*board)))
    elif direction == "down":
        board = list(map(list, zip(*board[::-1])))
        board = [compress(row) for row in board]
        board = list(map(list, zip(*board)))[::-1]
    elif direction == "left":
        board = [compress(row) for row in board]
    elif direction == "right":
        board = [compress(row[::-1])[::-1] for row in board]

    if board != original_board:
        add_random(board)

    return board

def check_game_over(board):
    for i in range(4):
        for j in range(4):
            if board[i][j] == 0:
                return False
            if j < 3 and board[i][j] == board[i][j + 1]:
                return False
            if i < 3 and board[i][j] == board[i + 1][j]:
                return False
    return True

def update_profile(user, score):
    profiles_col.update_one(
        {"user_id": user.id},
        {"$max": {"high_score": score},
         "$set": {"username": user.username, "first_name": user.first_name}},
        upsert=True
    )

def leaderboard_text():
    top = profiles_col.find().sort("high_score", -1).limit(10)
    text = "🏆 **2048 Leaderboard** 🏆\n\n"
    for i, u in enumerate(top, 1):
        name = u.get("username") or u.get("first_name") or str(u["user_id"])
        text += f"{i}. `{name}` → {u.get('high_score', 0)}\n"
    return text

# --- Commands ---
@app.on_message(filters.command("play2048"))
async def start_g2048ame(client, message):
    user = message.from_user
    board = new_board()
    games_col.update_one(
        {"chat_id": message.chat.id, "user_id": user.id},
        {"$set": {"board": board, "score": 0}},
        upsert=True
    )
    await message.reply(
        f"🎮 **2048 Game Started!**\nScore: 0\n\n{board_to_text(board)}",
        reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("⬆️", callback_data="mmove_up")
                ],[
                    InlineKeyboardButton("⬅️", callback_data="mmove_left"),
                    InlineKeyboardButton("➡️", callback_data="mmove_right")
                ],[
                    InlineKeyboardButton("⬇️", callback_data="mmove_down")
                ],[
                    InlineKeyboardButton("🔄 Restart", callback_data="restart_2048")
                ]]
            )
        )

@app.on_message(filters.command("2048_leaderboard"))
async def shojdw_leaderboard(client, message):
    await message.reply(leaderboard_text())

# --- Moves ---
@app.on_callback_query(filters.regex(r"mmove_(up|down|left|right)"))
async def handlen_move(client, cq: CallbackQuery):
    user = cq.from_user
    move = cq.data.split("_")[1]
    game = games_col.find_one({"chat_id": cq.message.chat.id, "user_id": user.id})
    if not game:
        return await cq.answer("❌ No active game. Start with /play2048", show_alert=True)

    board = game["board"]
    new_board_state = move_board(board, move)

    if new_board_state == board:
        return await cq.answer("❌ Invalid move!", show_alert=True)

    score = sum(sum(row) for row in new_board_state)
    games_col.update_one(
        {"chat_id": cq.message.chat.id, "user_id": user.id},
        {"$set": {"board": new_board_state, "score": score}}
    )
    update_profile(user, score)

    if check_game_over(new_board_state):
        games_col.delete_one({"chat_id": cq.message.chat.id, "user_id": user.id})
        try:
            await cq.message.edit(
                f"💀 **Game Over!**\nFinal Score: {score}\n\n{board_to_text(new_board_state)}"
            )
        except Exception:
            pass
        return await cq.answer("Game Over!", show_alert=True)

    try:
        await cq.message.edit(
            f"🎮 **2048 Game**\nScore: {score}\n\n{board_to_text(new_board_state)}",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("⬆️", callback_data="mmove_up")
                ],[
                    InlineKeyboardButton("⬅️", callback_data="mmove_left"),
                    InlineKeyboardButton("➡️", callback_data="mmove_right")
                ],[
                    InlineKeyboardButton("⬇️", callback_data="mmove_down")
                ],[
                    InlineKeyboardButton("🔄 Restart", callback_data="restart_2048")
                ]]
            )
        )
    except Exception:
        pass

    await cq.answer()

# --- Restart ---
@app.on_callback_query(filters.regex(r"restart_2048"))
async def rehstart_game(client, cq: CallbackQuery):
    user = cq.from_user
    board = new_board()
    games_col.update_one(
        {"chat_id": cq.message.chat.id, "user_id": user.id},
        {"$set": {"board": board, "score": 0}},
        upsert=True
    )
    try:
        await cq.message.edit(
            f"🎮 **2048 Game Restarted!**\nScore: 0\n\n{board_to_text(board)}",
            reply_markup=game_keyboard()
        )
    except Exception:
        pass
    await cq.answer("Game restarted!")
