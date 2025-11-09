import asyncio
import os
import random
import time
from typing import Dict

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URL
from main import wbot as app

# ===================== CONFIG ======================

DB_NAME = "number_rush"

# ===================================================


mongo_client = AsyncIOMotorClient(DB_URL)
db = mongo_client[DB_NAME]
players_col = db["players"]

# Store active games in memory {chat_id: {...}}
active_games: Dict[int, dict] = {}

# ===================== HELPERS =====================
async def ensure_player(user_id: int, username: str):
    """Ensure a player profile exists in MongoDB."""
    user = await players_col.find_one({"_id": user_id})
    if not user:
        await players_col.insert_one({
            "_id": user_id,
            "username": username,
            "score": 0,
            "games_played": 0,
            "wins": 0
        })

async def update_score(user_id: int, points: int, won: bool = False):
    """Update player's score and stats."""
    inc_data = {"score": points, "games_played": 1}
    if won:
        inc_data["wins"] = 1
    await players_col.update_one({"_id": user_id}, {"$inc": inc_data})

async def get_leaderboard(limit: int = 10):
    """Return top players sorted by score."""
    cursor = players_col.find().sort("score", -1).limit(limit)
    return await cursor.to_list(length=limit)

# ===================== GAME LOGIC =====================
@app.on_message(filters.command("nrsstart"))
async def start_chdommand(client: Client, message: Message):
    await ensure_player(message.from_user.id, message.from_user.username or "")
    await message.reply_text(
        "🎮 Welcome to Number Rush!\n\n"
        "Press the right number before time runs out!\n\n"
        "Commands:\n"
        "/play - Start a game\n"
        "/leaderboard - Show top players\n"
        "/profile - Show your stats"
    )

@app.on_message(filters.command("play_rush") & filters.group)
async def play_cdhommand(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in active_games:
        return await message.reply_text("⚠️ A game is already running in this chat!")

    correct_number = random.randint(1, 9)
    buttons = [[InlineKeyboardButton(str(i), callback_data=f"num_{i}")] for i in range(1, 10)]

    msg = await message.reply_text(
        f"⚡ Number Rush! Press the correct number before 5 seconds!",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    active_games[chat_id] = {
        "message_id": msg.id,
        "chat_id": chat_id,
        "correct": correct_number,
        "start_time": time.time(),
        "answered": False
    }

    await asyncio.sleep(5)

    # Time's up
    if chat_id in active_games and not active_games[chat_id]["answered"]:
        correct = active_games[chat_id]["correct"]
        await msg.edit_text(f"⏰ Time's up! The correct number was: {correct}")
        del active_games[chat_id]

@app.on_callback_query(filters.regex(r"num_\d"))
async def buttonh_handler(client: Client, cq: CallbackQuery):
    data = cq.data
    user = cq.from_user
    chat_id = cq.message.chat.id

    if chat_id not in active_games:
        return await cq.answer("No active game!", show_alert=True)

    game = active_games[chat_id]
    if cq.message.id != game["message_id"]:
        return await cq.answer("This game is no longer active!", show_alert=True)

    chosen = int(data.split("_")[1])
    correct = game["correct"]

    await ensure_player(user.id, user.username or "")

    if game["answered"]:
        return await cq.answer("Too late! Someone already answered!", show_alert=True)

    if chosen == correct:
        game["answered"] = True
        reaction_time = round(time.time() - game["start_time"], 2)
        points = max(1, 10 - int(reaction_time))  # Faster = more points

        await update_score(user.id, points, won=True)

        await cq.message.edit_text(
            f"✅ {user.mention} pressed {chosen} correctly in {reaction_time}s!\n"
            f"+{points} points earned 🎉"
        )
    else:
        await update_score(user.id, 0)
        await cq.answer("❌ Wrong number!", show_alert=True)

        # Wrong choice does not end game; still waiting for correct one

@app.on_message(filters.command("rushleaderboard"))
async def leaderboahsrd_command(client: Client, message: Message):
    top_players = await get_leaderboard()
    if not top_players:
        return await message.reply_text("No players yet.")

    text = "🏆 <b>Leaderboard</b> 🏆\n\n"
    for i, player in enumerate(top_players, start=1):
        uname = f"@{player['username']}" if player.get("username") else f"ID:{player['_id']}"
        text += f"{i}. {uname} - {player['score']} pts\n"

    await message.reply_text(text)

@app.on_message(filters.command("rushprofile"))
async def profile_crhsommand(client: Client, message: Message):
    user_id = message.from_user.id
    await ensure_player(user_id, message.from_user.username or "")

    profile = await players_col.find_one({"_id": user_id})
    text = (
        f"👤 <b>Profile</b>\n\n"
        f"User: {message.from_user.mention}\n"
        f"Score: {profile['score']}\n"
        f"Games Played: {profile['games_played']}\n"
        f"Wins: {profile['wins']}\n"
    )
    await message.reply_text(text)
