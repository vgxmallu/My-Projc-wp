import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from datetime import datetime
from config import DB_URL
from wallbot import wbot as app


mongo = MongoClient(DB_URL)
db = mongo["game_2048"]
games_col = db["games"]
profiles_col = db["profiles"]

# --- Game helpers ---
def new_board():
    board = [[0]*4 for _ in range(4)]
    add_random(board)
    add_random(board)
    return board

def add_random(board):
    empty = [(i,j) for i in range(4) for j in range(4) if board[i][j]==0]
    if empty:
        i,j = random.choice(empty)
        board[i][j] = 2 if random.random()<0.9 else 4

def board_to_text(board):
    emojis = {0:"⬛", 2:"2️⃣",4:"4️⃣",8:"8️⃣",16:"1️⃣6️⃣",32:"3️⃣2️⃣",64:"6️⃣4️⃣",
              128:"1️⃣2️⃣8️⃣",256:"2️⃣5️⃣6️⃣",512:"5️⃣1️⃣2️⃣",1024:"1️⃣0️⃣2️⃣4️⃣",2048:"2️⃣0️⃣4️⃣8️⃣"}
    return "\n".join("".join(emojis.get(cell, str(cell)) for cell in row) for row in board)

def move_board(board, direction):
    def compress(row):
        new_row = [i for i in row if i!=0]
        for i in range(len(new_row)-1):
            if new_row[i]==new_row[i+1]:
                new_row[i]*=2
                new_row[i+1]=0
        return [i for i in new_row if i!=0]+[0]*(4-len(new_row))
    
    rotated = False
    if direction=="up":
        board = list(map(list, zip(*board)))
        rotated = True
    elif direction=="down":
        board = list(map(list, zip(*board[::-1])))
        rotated = True
    elif direction=="right":
        board = [row[::-1] for row in board]
    
    new_board = [compress(row) for row in board]
    
    if direction=="up" and rotated:
        new_board = list(map(list, zip(*new_board)))
    elif direction=="down" and rotated:
        new_board = list(map(list, zip(*new_board)))[::-1]
    elif direction=="right":
        new_board = [row[::-1] for row in new_board]
    
    if new_board!=board:
        add_random(new_board)
    
    return new_board

def check_game_over(board):
    for i in range(4):
        for j in range(4):
            if board[i][j]==0:
                return False
            if j<3 and board[i][j]==board[i][j+1]:
                return False
            if i<3 and board[i][j]==board[i+1][j]:
                return False
    return True

def update_profile(user_id, score):
    profiles_col.update_one({"user_id":user_id},{"$max":{"high_score":score}},upsert=True)

def leaderboard_text():
    top = profiles_col.find().sort("high_score",-1).limit(10)
    text = "🏆 **2048 Leaderboard** 🏆\n\n"
    for i,u in enumerate(top,1):
        text+=f"{i}. `{u['user_id']}` → {u.get('high_score',0)}\n"
    return text

# --- Commands ---
@app.on_message(filters.command("play2048"))
async def start_g2048ame(client, message):
    user_id = message.from_user.id
    board = new_board()
    games_col.update_one({"chat_id":message.chat.id,"user_id":user_id},{"$set":{"board":board,"score":0}},upsert=True)
    await message.reply(f"🎮 **2048 Game Started!**\nScore: 0\n\n{board_to_text(board)}",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⬆️",callback_data="move_up")],
                            [InlineKeyboardButton("⬅️",callback_data="move_left"),
                             InlineKeyboardButton("➡️",callback_data="move_right")],
                            [InlineKeyboardButton("⬇️",callback_data="move_down")]
                        ]))

@app.on_message(filters.command("2048_leaderboard"))
async def shojdw_leaderboard(client, message):
    await message.reply(leaderboard_text())

# --- Moves ---
@app.on_callback_query(filters.regex(r"move_(up|down|left|right)"))
async def handle_move(client, cq: CallbackQuery):
    user_id = cq.from_user.id
    move = cq.data.split("_")[1]
    game = games_col.find_one({"chat_id":cq.message.chat.id,"user_id":user_id})
    if not game:
        return await cq.answer("❌ No active game. Start with /play2048",show_alert=True)
    
    board = game["board"]
    new_board_state = move_board(board, move)
    
    if new_board_state==board:
        return await cq.answer("❌ Invalid move!",show_alert=True)
    
    score = sum(sum(row) for row in new_board_state)
    games_col.update_one({"chat_id":cq.message.chat.id,"user_id":user_id},{"$set":{"board":new_board_state,"score":score}})
    update_profile(user_id,score)
    
    if check_game_over(new_board_state):
        games_col.delete_one({"chat_id":cq.message.chat.id,"user_id":user_id})
        return await cq.message.edit(f"💀 **Game Over!**\nFinal Score: {score}\n\n{board_to_text(new_board_state)}")
    
    await cq.message.edit(f"🎮 **2048 Game**\nScore: {score}\n\n{board_to_text(new_board_state)}",
                          reply_markup=InlineKeyboardMarkup([
                              [InlineKeyboardButton("⬆️",callback_data="move_up")],
                              [InlineKeyboardButton("⬅️",callback_data="move_left"),
                               InlineKeyboardButton("➡️",callback_data="move_right")],
                              [InlineKeyboardButton("⬇️",callback_data="move_down")]
                          ]))
    await cq.answer()

