import uuid
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    Message
)
from pymongo import MongoClient
from config import DB_URL
from wallbot import wbot as app

DB_NAME = "tictactoe"
# ------------------------


# MongoDB setup
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
games = db["games"]
players = db["players"]

# ---------- HELPERS ----------

def render_board(board, gid):
    keyboard = []
    for r in range(3):
        row = []
        for c in range(3):
            idx = r * 3 + c
            txt = board[idx] if board[idx] != " " else "▫️"
            row.append(InlineKeyboardButton(txt, callback_data=f"ttt_play|{gid}|{idx}"))
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("🏳️ Resign", callback_data=f"ttt_resign|{gid}"),
        InlineKeyboardButton("📊 Info", callback_data=f"ttt_info|{gid}")
    ])
    return InlineKeyboardMarkup(keyboard)

def check_winner(board):
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in wins:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    if all(s != " " for s in board):
        return "draw"
    return None

async def update_stats(winner_id=None, loser_id=None, draw=False):
    if draw:
        for uid in [winner_id, loser_id]:
            players.update_one({"_id": uid}, {"$inc": {"draws": 1}}, upsert=True)
    else:
        players.update_one({"_id": winner_id}, {"$inc": {"wins": 1}}, upsert=True)
        players.update_one({"_id": loser_id}, {"$inc": {"losses": 1}}, upsert=True)

# ---------- COMMANDS ----------

@app.on_message(filters.command("challenge"))
async def challengxoxe_cmd(_, message: Message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        return await message.reply_text("Usage:\n/challenge <@username|id>")
    try:
        target = await _.get_users(args[1].strip())
    except:
        return await message.reply_text("❌ Invalid user.")

    if target.id == message.from_user.id:
        return await message.reply_text("You cannot challenge yourself.")

    gid = str(uuid.uuid4())
    board = [" "] * 9
    games.insert_one({
        "_id": gid,
        "players": [message.from_user.id, target.id],
        "symbols": {str(message.from_user.id): "❌", str(target.id): "⭕"},
        "board": board,
        "turn": message.from_user.id,
        "status": "pending",
        "chat_id": message.chat.id,
        "created_at": datetime.utcnow()
    })

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"ttt_accept|{gid}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"ttt_decline|{gid}")]
    ])

    await message.reply_text(
        f"🎮 <b>TicTacToe Challenge</b>\n\n"
        f"{message.from_user.mention} challenged {target.mention}!",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex(r"^ttt_accept\|"))
async def accept_cb(_, query: CallbackQuery):
    gid = query.data.split("|")[1]
    game = games.find_one({"_id": gid})
    if not game: return await query.answer("Game not found.", show_alert=True)
    if query.from_user.id != game["players"][1]:
        return await query.answer("Only the challenged user can accept.", show_alert=True)

    board = game["board"]
    msg = await query.message.reply_text(
        f"🎮 TicTacToe Started!\n\n"
        f"❌ {(await _.get_users(game['players'][0])).mention} vs ⭕ {(await _.get_users(game['players'][1])).mention}\n\n"
        f"Turn: {(await _.get_users(game['turn'])).mention}",
        reply_markup=render_board(board, gid), parse_mode="html"
    )
    games.update_one({"_id": gid}, {"$set": {"status": "active", "msg_id": msg.id}})

@app.on_callback_query(filters.regex(r"^ttt_play\|"))
async def play_cb(_, query: CallbackQuery):
    _, gid, idx = query.data.split("|")
    idx = int(idx)
    game = games.find_one({"_id": gid})
    if not game: return await query.answer("Game not found.", show_alert=True)

    uid = query.from_user.id
    if uid != game["turn"]: return await query.answer("Not your turn!", show_alert=True)

    board = game["board"]
    if board[idx] != " ": return await query.answer("Cell already taken.", show_alert=True)

    sym = game["symbols"][str(uid)]
    board[idx] = sym

    result = check_winner(board)
    next_turn = game["players"][0] if uid == game["players"][1] else game["players"][1]

    if result == "draw":
        await query.message.edit_text(
            "🤝 Draw!\n\nFinal board:", reply_markup=render_board(board, gid))
        await update_stats(game["players"][0], game["players"][1], draw=True)
        games.delete_one({"_id": gid})
        return

    if result in ["❌", "⭕"]:
        winner = [pid for pid, s in game["symbols"].items() if s == result][0]
        loser = [pid for pid, s in game["symbols"].items() if s != result][0]
        await query.message.edit_text(
            f"🎉 Winner: {(await _.get_users(int(winner))).mention}\n\nFinal board:",
            reply_markup=render_board(board, gid), parse_mode="html")
        await update_stats(int(winner), int(loser))
        games.delete_one({"_id": gid})
        return

    # continue game
    games.update_one({"_id": gid}, {"$set": {"board": board, "turn": next_turn}})
    await query.message.edit_text(
        f"🎮 TicTacToe\n\nTurn: {(await _.get_users(next_turn)).mention}",
        reply_markup=render_board(board, gid), parse_mode="html"
    )
    await query.answer("Move registered.")

@app.on_callback_query(filters.regex(r"^ttt_resign\|"))
async def resign_cb(_, query: CallbackQuery):
    gid = query.data.split("|")[1]
    game = games.find_one({"_id": gid})
    if not game: return await query.answer("Game not found.", show_alert=True)
    uid = query.from_user.id
    if uid not in game["players"]: return await query.answer("Not your game.", show_alert=True)

    other = game["players"][0] if uid == game["players"][1] else game["players"][1]
    await query.message.edit_text(
        f"🏳️ {query.from_user.mention} resigned.\nWinner: {(await _.get_users(other)).mention}"
    )
    await update_stats(other, uid)
    games.delete_one({"_id": gid})

@app.on_message(filters.command("leaderboard"))
async def leaderboard_cmd(_, message: Message):
    top = players.find().sort("wins", -1).limit(10)
    text = "🏆 <b>Leaderboard</b>\n\n"
    rank = 1
    async def mention_user(uid):
        try: return (await _.get_users(uid)).mention
        except: return f"User({uid})"
    for p in top:
        name = await mention_user(p["_id"])
        text += f"{rank}. {name} — {p.get('wins',0)}W/{p.get('losses',0)}L/{p.get('draws',0)}D\n"
        rank += 1
    if rank == 1: text += "No players yet!"
    await message.reply_text(text, parse_mode="html")

